"""Pure HR zoning (`hr_zones`, Q159 stage 2, G1).

No DB: samples in, zone seconds out. Each discriminator below is mutation-checked (see the
DECISIONS entry's How-you-know): a flipped boundary operator, a dropped gap cap, a coverage
comparison moved, a float boundary, a first-sample credit, a hr_avg simple-mean, a plausibility
bound removed, or `no_hrmax` demoted below the sample checks each fails a named test here.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

import hr_zones
from hr_zones import (BAND_PCT, MAX_SAMPLE_GAP_S, MIN_ZONE_COVERAGE, PLAUSIBLE_BPM, REASONS,
                      band_for, hrmax_in_force, zone_session)

T0 = datetime(2026, 9, 28, 5, 0, 0, tzinfo=timezone.utc)


def _stop(minutes=10):
    return T0 + timedelta(minutes=minutes)


def _every(step_s, bpms, start=T0):
    """Samples `step_s` apart starting at `start`, one per bpm."""
    return [(start + timedelta(seconds=step_s * i), b) for i, b in enumerate(bpms)]


# ---- constants are the rulings (value guard) ---------------------------------------

def test_constants_are_the_ruled_values():
    assert BAND_PCT == (50, 60, 70, 80, 90)
    assert MAX_SAMPLE_GAP_S == 60
    assert MIN_ZONE_COVERAGE == 0.6
    assert PLAUSIBLE_BPM == (30, 240)
    assert REASONS == ("sparse", "no_same_writer_hr", "no_hrmax", "none")


# ---- bucketing at each boundary ------------------------------------------------------

@pytest.mark.parametrize("hrmax", [100, 173, 185, 197])
def test_every_band_edge_is_lower_inclusive(hrmax):
    """For each edge: the smallest integer bpm at/above it is in the band, one below is the band
    beneath. Integer arithmetic — no float edge can put a boundary bpm in the wrong band."""
    for band, pct in enumerate(BAND_PCT, start=1):
        edge = -(-pct * hrmax // 100)               # ceil(pct% of hrmax)
        assert band_for(edge, hrmax) == band, (hrmax, pct, edge)
        assert band_for(edge - 1, hrmax) == band - 1, (hrmax, pct, edge - 1)


def test_below_band_one_is_zero_and_z5_is_open_topped():
    assert band_for(40, 100) == 0
    assert band_for(49, 100) == 0 and band_for(50, 100) == 1
    assert band_for(100, 100) == 5 and band_for(250, 100) == 5          # above HRmax -> z5


def test_edges_that_float_arithmetic_gets_wrong_are_exact():
    """0.07 * 100 = 7.000000000000001 in floats; the percent compare is integer. HRmax values chosen
    so pct*hrmax/100 is an exact integer at every band: the boundary bpm must land IN the band."""
    for hrmax in (50, 100, 150, 200):
        for band, pct in enumerate(BAND_PCT, start=1):
            assert band_for(pct * hrmax // 100, hrmax) == band


def test_zone_seconds_land_in_the_right_bands():
    # hrmax 100, one sample per 10 s, each credited 10 s (last credited to stop).
    bpms = [49, 50, 59, 60, 70, 80, 89, 90, 100, 130]
    res = zone_session(_every(10, bpms), T0, T0 + timedelta(seconds=100), 100)
    assert res.reason == "none"
    # below(49)=10s uncredited-to-band; z1: 50,59 ; z2: 60 ; z3: 70 ; z4: 80,89 ; z5: 90,100,130
    assert res.zones == (20, 10, 10, 20, 30)
    assert res.coverage == pytest.approx(1.0)


# ---- gap cap: unobserved time is never credited --------------------------------------

def test_gap_cap_drops_the_excess_not_credits_it():
    # Two samples 120 s apart in a 240 s session: each credited 60, the other 120 s DROPPED.
    res = zone_session([(T0, 120), (T0 + timedelta(seconds=120), 120)], T0, T0 + timedelta(seconds=240),
                       170, min_coverage=0.0)
    assert res.credited_s == 120.0
    assert res.coverage == pytest.approx(0.5)


def test_a_gap_exactly_at_the_cap_is_fully_credited_and_one_over_is_capped():
    at = zone_session([(T0, 150)], T0, T0 + timedelta(seconds=60), 173)
    assert at.credited_s == 60.0
    over = zone_session([(T0, 150)], T0, T0 + timedelta(seconds=61), 173, min_coverage=0.0)
    assert over.credited_s == 60.0                                   # 61 s available, 60 credited


def test_passive_two_minute_sampling_stays_sparse_by_construction():
    """The Garmin Pilates shape (rows 69/85/92): a sample every 120 s across the session credits
    half of it — under the 0.6 floor, so the row is withheld, not interpolated."""
    samples = _every(120, [95] * 30)
    res = zone_session(samples, T0, T0 + timedelta(seconds=3600), 173)
    assert res.reason == "sparse" and res.zones is None
    assert 0.45 < res.coverage < 0.55


# ---- coverage threshold, both sides ---------------------------------------------------

def test_coverage_exactly_at_threshold_zones_and_just_under_is_sparse():
    # 100 s session; samples credited 60 s total -> 0.6 exactly (zones), 59 s -> 0.59 (sparse).
    at = zone_session([(T0, 150)], T0, T0 + timedelta(seconds=100), 173)         # 60 s credited
    assert at.coverage == pytest.approx(0.6) and at.reason == "none"
    under = zone_session([(T0 + timedelta(seconds=41), 150)], T0, T0 + timedelta(seconds=100), 173)
    assert under.coverage == pytest.approx(0.59) and under.reason == "sparse"
    assert under.zones is None and under.hr_avg is None and under.hr_max is None


# ---- lead-in uncredited, last sample credited to stop ---------------------------------

def test_lead_in_is_uncredited_and_the_last_sample_is_credited_to_stop():
    # Lead-in: first sample 30 s in, session 100 s: credited = 70 (30 s lead-in lost).
    res = zone_session(_every(10, [150] * 7, start=T0 + timedelta(seconds=30)), T0,
                       T0 + timedelta(seconds=100), 173)
    assert res.credited_s == 70.0
    assert res.coverage == pytest.approx(0.7)
    # last sample at +90 s, stop at +100: its 10 s run to stop IS credited (counted in the 70).


# ---- hr_avg / hr_max -------------------------------------------------------------------

def test_hr_avg_is_time_weighted_not_a_simple_mean():
    # 100 bpm for 10 s then 200 bpm for 50 s (last credited to stop, capped at 60): weighted
    # (100*10 + 200*50)/60 = 183.3 -> 183; the simple mean would be 150.
    res = zone_session([(T0, 100), (T0 + timedelta(seconds=10), 200)], T0,
                       T0 + timedelta(seconds=60), 220)
    assert res.hr_avg == 183
    assert res.hr_max == 200


def test_hr_max_is_the_max_raw_sample_in_the_window_only():
    inside = _every(10, [120, 190, 130, 125, 120, 118])
    outside = [(T0 - timedelta(seconds=5), 239), (T0 + timedelta(seconds=61), 238)]
    res = zone_session(inside + outside, T0, T0 + timedelta(seconds=60), 200)
    assert res.hr_max == 190


# ---- plausibility at zone time ----------------------------------------------------------

def test_plausibility_bounds_are_inclusive_and_drops_are_counted():
    samples = _every(10, [29, 30, 120, 240, 241, 125, 120, 118])
    res = zone_session(samples, T0, T0 + timedelta(seconds=80), 200)
    assert res.dropped_implausible == 2                    # 29 and 241
    assert res.n_samples == 6
    assert res.hr_max == 240                               # 240 is kept; 241 never counts


def test_an_implausible_max_cannot_become_hr_max_or_a_ceiling_flag():
    res = zone_session(_every(10, [120, 255, 125, 130, 120, 118]), T0, T0 + timedelta(seconds=60), 173)
    assert res.hr_max == 130 and res.over_ceiling is False and res.dropped_implausible == 1


def test_only_implausible_samples_leaves_no_usable_hr():
    res = zone_session(_every(10, [5, 250, 0]), T0, T0 + timedelta(seconds=30), 173)
    assert res.reason == "no_same_writer_hr" and res.dropped_implausible == 3


# ---- reasons: the closed set --------------------------------------------------------------

def test_no_samples_is_no_same_writer_hr():
    res = zone_session([], T0, _stop(), 173)
    assert res.reason == "no_same_writer_hr" and res.zones is None and res.coverage is None


def test_no_hrmax_wins_even_when_there_are_no_samples():
    """User-level precondition first: the count of rows it blocks is complete (G3 surfaces it)."""
    assert zone_session([], T0, _stop(), None).reason == "no_hrmax"
    res = zone_session(_every(10, [150] * 6), T0, T0 + timedelta(seconds=60), None)
    assert res.reason == "no_hrmax" and res.zones is None and res.hr_avg is None


def test_every_outcome_is_in_the_closed_set():
    outs = [zone_session([], T0, _stop(), 173), zone_session([], T0, _stop(), None),
            zone_session([(T0, 150)], T0, _stop(), 173),
            zone_session(_every(10, [150] * 6), T0, T0 + timedelta(seconds=60), 173)]
    assert {o.reason for o in outs} == set(REASONS)


# ---- sub-band time is covered time (call 1) -------------------------------------------------

def test_a_session_wholly_below_band_one_is_covered_and_writes_zeros():
    res = zone_session(_every(10, [70] * 6), T0, T0 + timedelta(seconds=60), 173)   # 70 < 86.5
    assert res.reason == "none"
    assert res.zones == (0, 0, 0, 0, 0)                    # "measured, none" — not NULL
    assert res.hr_avg == 70 and res.hr_max == 70
    assert res.coverage == pytest.approx(1.0)


# ---- over-ceiling: flagged, never auto-raised -------------------------------------------------

def test_over_ceiling_is_flagged_credited_to_z5_and_changes_nothing_else():
    res = zone_session(_every(10, [150, 175, 180, 150, 150, 150]), T0, T0 + timedelta(seconds=60), 173)
    assert res.over_ceiling is True
    assert res.hr_max == 180
    assert res.zones[4] >= 20                              # the 175 and 180 samples credit z5
    ok = zone_session(_every(10, [150, 173, 150, 150, 150, 150]), T0, T0 + timedelta(seconds=60), 173)
    assert ok.over_ceiling is False                        # equal to HRmax is not over


# ---- HRmax effective-date selection --------------------------------------------------------------

def test_hrmax_in_force_picks_the_greatest_effective_from_not_after_the_day():
    entries = [(date(2026, 9, 28), 180), (date(2026, 6, 1), 173)]          # unordered on purpose
    assert hrmax_in_force(entries, date(2026, 5, 31)) is None              # before any value
    assert hrmax_in_force(entries, date(2026, 6, 1)) == 173                # effective day inclusive
    assert hrmax_in_force(entries, date(2026, 9, 27)) == 173
    assert hrmax_in_force(entries, date(2026, 9, 28)) == 180
    assert hrmax_in_force(entries, date(2027, 1, 1)) == 180
    assert hrmax_in_force([], date(2026, 9, 28)) is None


def test_the_same_samples_zone_differently_under_a_different_hrmax():
    samples = _every(10, [140] * 6)
    low = zone_session(samples, T0, T0 + timedelta(seconds=60), 173)       # 140/173 = 80.9% -> z4
    high = zone_session(samples, T0, T0 + timedelta(seconds=60), 190)      # 140/190 = 73.7% -> z3
    assert low.zones == (0, 0, 0, 60, 0) and high.zones == (0, 0, 60, 0, 0)


# ---- misc -------------------------------------------------------------------------------------------

def test_a_session_without_positive_duration_is_refused_not_classified():
    with pytest.raises(ValueError):
        zone_session([(T0, 150)], T0, T0, 173)


def test_unsorted_samples_are_handled():
    fwd = _every(10, [120, 130, 140, 150, 160, 170])
    assert zone_session(list(reversed(fwd)), T0, T0 + timedelta(seconds=60), 173) == \
        zone_session(fwd, T0, T0 + timedelta(seconds=60), 173)


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
