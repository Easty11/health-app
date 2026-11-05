"""Pure HR zoning (`hr_zones`, Q159 stage 2, G1; per-class model, design 0010).

No DB: samples in, zone seconds out. Each discriminator below is mutation-checked (see the
DECISIONS entries' How-you-know): a flipped boundary operator, a dropped gap cap, a coverage
comparison moved, a float boundary, a first-sample credit, a hr_avg simple-mean, a plausibility
bound removed, or `no_anchor` demoted below the sample checks each fails a named test here.

The interval / coverage / plausibility mechanics are pinned under an HRR spec with RHR 0, which
reduces Karvonen to the retired %HRmax arithmetic exactly (reserve = HRmax), so those tests keep
their original numbers; the band tables of both bases get their own edge tests with real anchors.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

import hr_zones
from hr_zones import (ANCHORS_NEEDED, BASES, BASIS_HRR, BASIS_LTHR, HRR_BAND_PCT, LTHR_BAND_PCT,
                      MAX_SAMPLE_GAP_S, MIN_ZONE_COVERAGE, PLAUSIBLE_BPM, REASONS, HrmaxEntry, ZoneSpec,
                      anchor_in_force, band_for, hrmax_in_force, resolve_zone_spec, zone_session, zone_spec)

T0 = datetime(2026, 9, 28, 5, 0, 0, tzinfo=timezone.utc)


def S(hrmax):
    """An HRR spec with RHR 0: edges = ceil(pct × HRmax / 100), the retired %HRmax arithmetic."""
    return zone_spec(BASIS_HRR, hrmax=hrmax, rhr=0)


def _stop(minutes=10):
    return T0 + timedelta(minutes=minutes)


def _every(step_s, bpms, start=T0):
    """Samples `step_s` apart starting at `start`, one per bpm."""
    return [(start + timedelta(seconds=step_s * i), b) for i, b in enumerate(bpms)]


# ---- constants are the rulings (value guard) ---------------------------------------

def test_constants_are_the_ruled_values():
    assert LTHR_BAND_PCT == (0, 81, 90, 94, 100)
    assert HRR_BAND_PCT == (50, 60, 70, 80, 90)
    assert BASES == ("lthr", "hrr")
    assert ANCHORS_NEEDED == {"lthr": ("lthr",), "hrr": ("hrmax", "rhr")}
    assert MAX_SAMPLE_GAP_S == 60
    assert MIN_ZONE_COVERAGE == 0.6
    assert PLAUSIBLE_BPM == (30, 240)
    assert REASONS == ("sparse", "no_same_writer_hr", "no_anchor", "none")


# ---- the band tables, in bpm, on the brief's anchors (design 0010 §3) --------------------

def test_the_briefs_anchors_give_the_briefs_bands():
    """LTHR 158 (Friel) and RHR 51 / HRmax 179 (Karvonen): z2 is 128-142 and 128-140 bpm; the retired
    %HRmax model put z2 at 107-124 (recovery intensity) — the defect the model replaces."""
    lthr = zone_spec(BASIS_LTHR, lthr=158, hrmax=179)
    assert lthr.edges_bpm == (0, 128, 143, 149, 158)         # 81%=127.98→128, 90%=142.2→143, 94%=148.52→149
    hrr = zone_spec(BASIS_HRR, hrmax=179, rhr=51)             # reserve 128
    assert hrr.edges_bpm == (115, 128, 141, 154, 167)        # 51 + ceil(64 | 76.8 | 89.6 | 102.4 | 115.2)
    assert band_for(134, lthr) == 2 and band_for(134, hrr) == 2
    assert band_for(124, S(179)) == 2 and band_for(124, hrr) == 1   # the old model's z2 is the new z1
    assert lthr.hrmax == 179 and hrr.hrmax == 179
    assert lthr.anchors == {"lthr": 158} and hrr.anchors == {"hrmax": 179, "rhr": 51}
    assert lthr.pct == LTHR_BAND_PCT and hrr.pct == HRR_BAND_PCT


@pytest.mark.parametrize("lthr", [100, 150, 158, 171])
def test_every_lthr_edge_is_lower_inclusive_and_z1_has_no_floor(lthr):
    spec = zone_spec(BASIS_LTHR, lthr=lthr)
    for band, pct in enumerate(LTHR_BAND_PCT[1:], start=2):
        edge = -(-pct * lthr // 100)
        assert spec.edges_bpm[band - 1] == edge
        assert band_for(edge, spec) == band and band_for(edge - 1, spec) == band - 1, (lthr, pct)
    assert band_for(30, spec) == 1 and band_for(1, spec) == 1          # no floor: everything below 81% is z1
    assert band_for(lthr, spec) == 5 and band_for(250, spec) == 5       # 100% and above: z5, open-topped


@pytest.mark.parametrize("hrmax,rhr", [(100, 0), (173, 53), (179, 51), (197, 40)])
def test_every_hrr_edge_is_lower_inclusive_and_below_fifty_percent_is_uncredited(hrmax, rhr):
    spec = zone_spec(BASIS_HRR, hrmax=hrmax, rhr=rhr)
    reserve = hrmax - rhr
    for band, pct in enumerate(HRR_BAND_PCT, start=1):
        edge = rhr + -(-pct * reserve // 100)
        assert spec.edges_bpm[band - 1] == edge
        assert band_for(edge, spec) == band and band_for(edge - 1, spec) == band - 1, (hrmax, rhr, pct)
    assert band_for(rhr, spec) == 0 and band_for(spec.edges_bpm[0] - 1, spec) == 0
    assert band_for(hrmax, spec) == 5 and band_for(250, spec) == 5


def test_a_spec_needs_its_anchors_and_a_reserve():
    with pytest.raises(ValueError, match="LTHR"):
        zone_spec(BASIS_LTHR)
    with pytest.raises(ValueError, match="HRmax and RHR"):
        zone_spec(BASIS_HRR, hrmax=179)
    with pytest.raises(ValueError, match="reserve"):
        zone_spec(BASIS_HRR, hrmax=179, rhr=179)
    with pytest.raises(ValueError, match="unknown"):
        zone_spec("hrmax", hrmax=179)


def test_the_legacy_integer_form_of_band_for_is_the_old_percent_of_hrmax():
    """Kept for the operator projection script only; it equals the RHR-0 spec at every edge."""
    for hrmax in (100, 173, 185):
        for bpm in range(40, 200):
            assert band_for(bpm, hrmax) == band_for(bpm, S(hrmax))


# ---- the resolver: basis + anchors in force on a day --------------------------------------

D0, D1 = date(2026, 3, 1), date(2026, 9, 1)


def test_resolve_zone_spec_needs_the_anchors_its_basis_needs_and_no_others():
    hr = [HrmaxEntry(D0, 179, id=1)]
    lt = [HrmaxEntry(D0, 158, id=1)]
    rh = [HrmaxEntry(D0, 51, id=1)]
    assert resolve_zone_spec(BASIS_LTHR, D1, lthr_entries=lt).edges_bpm == (0, 128, 143, 149, 158)
    assert resolve_zone_spec(BASIS_LTHR, D1, lthr_entries=lt).hrmax is None        # the ceiling is optional there
    assert resolve_zone_spec(BASIS_LTHR, D1, lthr_entries=lt, hrmax_entries=hr).hrmax == 179
    assert resolve_zone_spec(BASIS_LTHR, D1, hrmax_entries=hr, rhr_entries=rh) is None   # LTHR missing
    assert resolve_zone_spec(BASIS_HRR, D1, hrmax_entries=hr, rhr_entries=rh).edges_bpm == (115, 128, 141, 154, 167)
    assert resolve_zone_spec(BASIS_HRR, D1, hrmax_entries=hr, lthr_entries=lt) is None  # RHR missing
    assert resolve_zone_spec(BASIS_HRR, D1, rhr_entries=rh, lthr_entries=lt) is None    # HRmax missing
    assert resolve_zone_spec(BASIS_HRR, date(2026, 2, 1), hrmax_entries=hr, rhr_entries=rh) is None  # before any value
    assert resolve_zone_spec(BASIS_HRR, D1, hrmax_entries=hr, rhr_entries=[HrmaxEntry(D0, 200, id=1)]) is None  # incoherent


def test_the_resolver_applies_dated_and_restated_anchors_per_kind():
    """RHR restated at the seed date (51 → 48) reflows the whole span; LTHR changed by a dated row (158 → 165
    from 1 Sep) applies forward only; HRmax untouched."""
    hr = [HrmaxEntry(D0, 179, id=1)]
    rh = [HrmaxEntry(D0, 51, id=1), HrmaxEntry(D0, 48, id=2, restates=1)]
    lt = [HrmaxEntry(D0, 158, id=1), HrmaxEntry(D1, 165, id=2)]
    may, sep = date(2026, 5, 15), date(2026, 9, 2)
    assert resolve_zone_spec(BASIS_HRR, may, hrmax_entries=hr, rhr_entries=rh).anchors == {"hrmax": 179, "rhr": 48}
    assert resolve_zone_spec(BASIS_HRR, sep, hrmax_entries=hr, rhr_entries=rh).anchors == {"hrmax": 179, "rhr": 48}
    assert resolve_zone_spec(BASIS_LTHR, may, lthr_entries=lt).anchors == {"lthr": 158}
    assert resolve_zone_spec(BASIS_LTHR, sep, lthr_entries=lt).anchors == {"lthr": 165}


def test_anchor_in_force_is_the_hrmax_resolver():
    assert anchor_in_force is hrmax_in_force


# ---- bucketing at each boundary (RHR 0 = the retired arithmetic) ------------------------

def test_below_band_one_is_zero_and_z5_is_open_topped():
    assert band_for(40, S(100)) == 0
    assert band_for(49, S(100)) == 0 and band_for(50, S(100)) == 1
    assert band_for(100, S(100)) == 5 and band_for(250, S(100)) == 5          # above HRmax -> z5


def test_edges_that_float_arithmetic_gets_wrong_are_exact():
    """0.07 * 100 = 7.000000000000001 in floats; the edges are integer. HRmax values chosen
    so pct*hrmax/100 is an exact integer at every band: the boundary bpm must land IN the band."""
    for hrmax in (50, 100, 150, 200):
        for band, pct in enumerate(HRR_BAND_PCT, start=1):
            assert band_for(pct * hrmax // 100, S(hrmax)) == band


def test_zone_seconds_land_in_the_right_bands():
    # hrmax 100, one sample per 10 s, each credited 10 s (last credited to stop).
    bpms = [49, 50, 59, 60, 70, 80, 89, 90, 100, 130]
    res = zone_session(_every(10, bpms), T0, T0 + timedelta(seconds=100), S(100))
    assert res.reason == "none"
    # below(49)=10s uncredited-to-band; z1: 50,59 ; z2: 60 ; z3: 70 ; z4: 80,89 ; z5: 90,100,130
    assert res.zones == (20, 10, 10, 20, 30)
    assert res.coverage == pytest.approx(1.0)


def test_zone_seconds_under_the_lthr_basis_have_no_sub_band_time():
    spec = zone_spec(BASIS_LTHR, lthr=100, hrmax=120)
    res = zone_session(_every(10, [40, 80, 81, 89, 90, 93, 94, 99, 100, 130]), T0, T0 + timedelta(seconds=100), spec)
    assert res.zones == (20, 20, 20, 20, 20) and res.over_ceiling is True     # 130 > 120


# ---- gap cap: unobserved time is never credited --------------------------------------

def test_gap_cap_drops_the_excess_not_credits_it():
    # Two samples 120 s apart in a 240 s session: each credited 60, the other 120 s DROPPED.
    res = zone_session([(T0, 120), (T0 + timedelta(seconds=120), 120)], T0, T0 + timedelta(seconds=240),
                       S(170), min_coverage=0.0)
    assert res.credited_s == 120.0
    assert res.coverage == pytest.approx(0.5)


def test_a_gap_exactly_at_the_cap_is_fully_credited_and_one_over_is_capped():
    at = zone_session([(T0, 150)], T0, T0 + timedelta(seconds=60), S(173))
    assert at.credited_s == 60.0
    over = zone_session([(T0, 150)], T0, T0 + timedelta(seconds=61), S(173), min_coverage=0.0)
    assert over.credited_s == 60.0                                   # 61 s available, 60 credited


def test_passive_two_minute_sampling_stays_sparse_by_construction():
    """The Garmin Pilates shape (rows 69/85/92): a sample every 120 s across the session credits
    half of it — under the 0.6 floor, so the row is withheld, not interpolated."""
    samples = _every(120, [95] * 30)
    res = zone_session(samples, T0, T0 + timedelta(seconds=3600), S(173))
    assert res.reason == "sparse" and res.zones is None
    assert 0.45 < res.coverage < 0.55


# ---- coverage threshold, both sides ---------------------------------------------------

def test_coverage_exactly_at_threshold_zones_and_just_under_is_sparse():
    # 100 s session; samples credited 60 s total -> 0.6 exactly (zones), 59 s -> 0.59 (sparse).
    at = zone_session([(T0, 150)], T0, T0 + timedelta(seconds=100), S(173))         # 60 s credited
    assert at.coverage == pytest.approx(0.6) and at.reason == "none"
    under = zone_session([(T0 + timedelta(seconds=41), 150)], T0, T0 + timedelta(seconds=100), S(173))
    assert under.coverage == pytest.approx(0.59) and under.reason == "sparse"
    assert under.zones is None and under.hr_avg is None and under.hr_max is None


# ---- lead-in uncredited, last sample credited to stop ---------------------------------

def test_lead_in_is_uncredited_and_the_last_sample_is_credited_to_stop():
    # Lead-in: first sample 30 s in, session 100 s: credited = 70 (30 s lead-in lost).
    res = zone_session(_every(10, [150] * 7, start=T0 + timedelta(seconds=30)), T0,
                       T0 + timedelta(seconds=100), S(173))
    assert res.credited_s == 70.0
    assert res.coverage == pytest.approx(0.7)
    # last sample at +90 s, stop at +100: its 10 s run to stop IS credited (counted in the 70).


# ---- hr_avg / hr_max -------------------------------------------------------------------

def test_hr_avg_is_time_weighted_not_a_simple_mean():
    # 100 bpm for 10 s then 200 bpm for 50 s (last credited to stop, capped at 60): weighted
    # (100*10 + 200*50)/60 = 183.3 -> 183; the simple mean would be 150.
    res = zone_session([(T0, 100), (T0 + timedelta(seconds=10), 200)], T0,
                       T0 + timedelta(seconds=60), S(220))
    assert res.hr_avg == 183
    assert res.hr_max == 200


def test_hr_max_is_the_max_raw_sample_in_the_window_only():
    inside = _every(10, [120, 190, 130, 125, 120, 118])
    outside = [(T0 - timedelta(seconds=5), 239), (T0 + timedelta(seconds=61), 238)]
    res = zone_session(inside + outside, T0, T0 + timedelta(seconds=60), S(200))
    assert res.hr_max == 190


# ---- plausibility at zone time ----------------------------------------------------------

def test_plausibility_bounds_are_inclusive_and_drops_are_counted():
    samples = _every(10, [29, 30, 120, 240, 241, 125, 120, 118])
    res = zone_session(samples, T0, T0 + timedelta(seconds=80), S(200))
    assert res.dropped_implausible == 2                    # 29 and 241
    assert res.n_samples == 6
    assert res.hr_max == 240                               # 240 is kept; 241 never counts


def test_an_implausible_max_cannot_become_hr_max_or_a_ceiling_flag():
    res = zone_session(_every(10, [120, 255, 125, 130, 120, 118]), T0, T0 + timedelta(seconds=60), S(173))
    assert res.hr_max == 130 and res.over_ceiling is False and res.dropped_implausible == 1


def test_only_implausible_samples_leaves_no_usable_hr():
    res = zone_session(_every(10, [5, 250, 0]), T0, T0 + timedelta(seconds=30), S(173))
    assert res.reason == "no_same_writer_hr" and res.dropped_implausible == 3


# ---- reasons: the closed set --------------------------------------------------------------

def test_no_samples_is_no_same_writer_hr():
    res = zone_session([], T0, _stop(), S(173))
    assert res.reason == "no_same_writer_hr" and res.zones is None and res.coverage is None


def test_no_anchor_wins_even_when_there_are_no_samples():
    """User-level precondition first: the count of rows it blocks is complete (G3 surfaces it)."""
    assert zone_session([], T0, _stop(), None).reason == "no_anchor"
    res = zone_session(_every(10, [150] * 6), T0, T0 + timedelta(seconds=60), None)
    assert res.reason == "no_anchor" and res.zones is None and res.hr_avg is None


def test_every_outcome_is_in_the_closed_set():
    outs = [zone_session([], T0, _stop(), S(173)), zone_session([], T0, _stop(), None),
            zone_session([(T0, 150)], T0, _stop(), S(173)),
            zone_session(_every(10, [150] * 6), T0, T0 + timedelta(seconds=60), S(173))]
    assert {o.reason for o in outs} == set(REASONS)


# ---- sub-band time is covered time (call 1) -------------------------------------------------

def test_a_session_wholly_below_band_one_is_covered_and_writes_zeros():
    res = zone_session(_every(10, [70] * 6), T0, T0 + timedelta(seconds=60), S(173))   # 70 < 86.5
    assert res.reason == "none"
    assert res.zones == (0, 0, 0, 0, 0)                    # "measured, none" — not NULL
    assert res.hr_avg == 70 and res.hr_max == 70
    assert res.coverage == pytest.approx(1.0)


# ---- over-ceiling: flagged, never auto-raised -------------------------------------------------

def test_over_ceiling_is_flagged_credited_to_z5_and_changes_nothing_else():
    res = zone_session(_every(10, [150, 175, 180, 150, 150, 150]), T0, T0 + timedelta(seconds=60), S(173))
    assert res.over_ceiling is True
    assert res.hr_max == 180
    assert res.zones[4] >= 20                              # the 175 and 180 samples credit z5
    ok = zone_session(_every(10, [150, 173, 150, 150, 150, 150]), T0, T0 + timedelta(seconds=60), S(173))
    assert ok.over_ceiling is False                        # equal to HRmax is not over


def test_the_ceiling_is_hrmax_under_the_lthr_basis_too_and_absent_without_one():
    with_ceiling = zone_spec(BASIS_LTHR, lthr=158, hrmax=173)
    without = zone_spec(BASIS_LTHR, lthr=158)
    samples = _every(10, [150, 175, 180, 150, 150, 150])
    assert zone_session(samples, T0, T0 + timedelta(seconds=60), with_ceiling).over_ceiling is True
    assert zone_session(samples, T0, T0 + timedelta(seconds=60), without).over_ceiling is False


# ---- effective-date selection --------------------------------------------------------------

def test_hrmax_in_force_picks_the_greatest_effective_from_not_after_the_day():
    entries = [(date(2026, 9, 28), 180), (date(2026, 6, 1), 173)]          # unordered on purpose
    assert hrmax_in_force(entries, date(2026, 5, 31)) is None              # before any value
    assert hrmax_in_force(entries, date(2026, 6, 1)) == 173                # effective day inclusive
    assert hrmax_in_force(entries, date(2026, 9, 27)) == 173
    assert hrmax_in_force(entries, date(2026, 9, 28)) == 180
    assert hrmax_in_force(entries, date(2027, 1, 1)) == 180
    assert hrmax_in_force([], date(2026, 9, 28)) is None


# ---- restatement versus dated change (#383) -------------------------------------------------------------
# A restatement stands in for the entry it restates over that entry's whole span, even on the same
# date; a dated change applies forward only. The rank is explicit (ids), never input order.

def _seed_and_restatement():
    return [HrmaxEntry(D0, 173, id=1), HrmaxEntry(D0, 175, id=2, restates=1)]


@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
def test_a_restatement_wins_on_the_date_it_shares_whatever_the_input_order(order):
    """The old resolver kept the FIRST of two same-date entries (strict `>`): [173, 177] gave 173 and
    the reverse gave 177. Now the restatement outranks what it restates in both orders."""
    base = _seed_and_restatement()
    entries = [base[i] for i in order]
    assert hrmax_in_force(entries, D0) == 175                  # on the shared date itself
    assert hrmax_in_force(entries, date(2026, 6, 1)) == 175    # and across the whole span
    assert hrmax_in_force(entries, date(2026, 2, 28)) is None  # a restatement reaches no earlier than its date


def test_a_restatement_reflows_history_a_dated_change_does_not():
    """Same new value, two kinds. Restated (retroactive): every day from the seed reads 175, so no step
    in the series. Dated (forward only): days before the date keep 173 and the step is real."""
    restated = _seed_and_restatement()
    dated = [HrmaxEntry(D0, 173, id=1), HrmaxEntry(D1, 175, id=2)]
    days = [date(2026, 3, 1), date(2026, 5, 15), date(2026, 8, 31), date(2026, 9, 1), date(2026, 12, 1)]
    assert [hrmax_in_force(restated, d) for d in days] == [175, 175, 175, 175, 175]
    assert [hrmax_in_force(dated, d) for d in days] == [173, 173, 173, 175, 175]


def test_a_dated_change_after_a_restatement_still_applies_forward_only():
    """Restate the seed (173 -> 175), then a later genuine change (178 from 1 Sep): the restated value
    holds up to 31 Aug, the dated change from 1 Sep. Restating the seed does not touch the later date."""
    entries = _seed_and_restatement() + [HrmaxEntry(D1, 178, id=3)]
    assert hrmax_in_force(entries, date(2026, 8, 31)) == 175
    assert hrmax_in_force(entries, D1) == 178
    assert hrmax_in_force(list(reversed(entries)), D1) == 178


@pytest.mark.parametrize("order", [(0, 1, 2), (2, 1, 0), (1, 2, 0), (1, 0, 2)])
def test_chained_restatements_resolve_to_the_latest(order):
    """173 restated to 175, then 175 restated to 177: only the end of the chain is live, in any order."""
    chain = [HrmaxEntry(D0, 173, id=1), HrmaxEntry(D0, 175, id=2, restates=1),
             HrmaxEntry(D0, 177, id=3, restates=2)]
    entries = [chain[i] for i in order]
    assert hrmax_in_force(entries, D0) == 177
    assert hrmax_in_force(entries, date(2026, 10, 5)) == 177


def test_restating_an_old_row_leaves_a_later_row_in_force():
    """Restate the seed AFTER a later dated change exists: the later row still wins from its date."""
    entries = [HrmaxEntry(D0, 173, id=1), HrmaxEntry(D1, 180, id=2), HrmaxEntry(D0, 175, id=3, restates=1)]
    assert hrmax_in_force(entries, date(2026, 8, 31)) == 175
    assert hrmax_in_force(entries, D1) == 180


def test_plain_pairs_still_work_and_mix_with_entries():
    assert hrmax_in_force([(D1, 180), (D0, 173)], date(2026, 9, 2)) == 180
    assert hrmax_in_force([HrmaxEntry(D0, 175, id=2, restates=1), HrmaxEntry(D0, 173, id=1), (D1, 180)],
                          date(2026, 6, 1)) == 175


def test_two_unranked_entries_on_one_date_are_refused_not_resolved_by_input_order():
    """Neither restates the other: the resolver will not guess (the old behaviour silently kept the
    first, which is how a same-date `--hrmax` projection used to be ignored)."""
    with pytest.raises(ValueError, match="ambiguous"):
        hrmax_in_force([(D0, 173), (D0, 177)], D0)
    with pytest.raises(ValueError, match="ambiguous"):
        hrmax_in_force([HrmaxEntry(D0, 173, id=1), HrmaxEntry(D0, 177, id=2)], D0)
    # ambiguity on a date that is not the winning date is not this day's problem
    assert hrmax_in_force([(D0, 173), (D0, 177), (D1, 180)], D1) == 180


def test_an_incoherent_restatement_is_refused():
    with pytest.raises(ValueError, match="not among the entries"):
        hrmax_in_force([HrmaxEntry(D0, 175, id=2, restates=99)], D0)
    with pytest.raises(ValueError, match="shares its target's date"):
        hrmax_in_force([HrmaxEntry(D0, 173, id=1), HrmaxEntry(D1, 175, id=2, restates=1)], D1)


def test_the_same_samples_zone_differently_under_a_different_anchor():
    samples = _every(10, [140] * 6)
    low = zone_session(samples, T0, T0 + timedelta(seconds=60), S(173))       # 140/173 = 80.9% -> z4
    high = zone_session(samples, T0, T0 + timedelta(seconds=60), S(190))      # 140/190 = 73.7% -> z3
    assert low.zones == (0, 0, 0, 60, 0) and high.zones == (0, 0, 60, 0, 0)
    lthr = zone_session(samples, T0, T0 + timedelta(seconds=60), zone_spec(BASIS_LTHR, lthr=158))   # 88.6% -> z2
    hrr = zone_session(samples, T0, T0 + timedelta(seconds=60), zone_spec(BASIS_HRR, hrmax=179, rhr=51))  # 69.5% -> z2
    assert lthr.zones == (0, 60, 0, 0, 0) and hrr.zones == (0, 60, 0, 0, 0)


# ---- misc -------------------------------------------------------------------------------------------

def test_a_session_without_positive_duration_is_refused_not_classified():
    with pytest.raises(ValueError):
        zone_session([(T0, 150)], T0, T0, S(173))


def test_unsorted_samples_are_handled():
    fwd = _every(10, [120, 130, 140, 150, 160, 170])
    assert zone_session(list(reversed(fwd)), T0, T0 + timedelta(seconds=60), S(173)) == \
        zone_session(fwd, T0, T0 + timedelta(seconds=60), S(173))


def test_a_zone_spec_is_frozen():
    spec = S(173)
    assert isinstance(spec, ZoneSpec)
    with pytest.raises(Exception):
        spec.basis = "lthr"


def test_the_module_imports_nothing_from_the_app():
    """Pure: no DB, no models, no source knowledge — only stdlib imports."""
    import ast
    tree = ast.parse(open(hr_zones.__file__, encoding="utf-8").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__", "dataclasses", "datetime", "typing"}, imported
