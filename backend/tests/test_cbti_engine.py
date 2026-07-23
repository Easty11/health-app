"""CBT-I titration engine — SYNTHETIC data only.

Real data cannot reach the adherence gate: Samsung `bedtime` begins 2026-06-08
and the imported block closed 2026-05-11, so every replayed night falls back to
the diary source and no night has an independent bedtime to disagree with. The
gate is therefore exercised here or nowhere — which is the whole reason these
tests are synthetic rather than fixtures cut from the block.

No real rows appear (both repos are public).
"""
from datetime import date, datetime, timedelta

import pytest

from cbti.engine import (
    ADHERENCE_TOL_MIN,
    BUFFER_MIN,
    FLOOR_MIN,
    MAX_MOVE_MIN,
    MIN_VALID_NIGHTS,
    Night,
    classify_night,
    evaluate_cycle,
)

RX = "22:30"          # prescribed lights-out
ANCHOR = "05:00"
WINDOW = 390          # 22:30 -> 05:00


def night(day: int, *, tst=420, se=90.0, lights_out=RX, wake="05:00",
          naps=0, alcohol=0, samsung=None, training_end=None, travel=False) -> Night:
    return Night(
        date=date(2026, 6, day), tst_min=tst, se_pct=se, lights_out=lights_out,
        final_wake=wake, naps_min=naps, alcohol_units=alcohol,
        samsung_bedtime=samsung, training_end=training_end, travel_or_match=travel,
    )


def week(**kw) -> list[Night]:
    return [night(d, **kw) for d in range(1, 8)]


# ── exclusions ────────────────────────────────────────────────────────────────

def test_alcohol_recorded_nonzero_is_excluded():
    v = classify_night(night(1, alcohol=2), RX)
    assert not v.valid and v.reason == "alcohol"


def test_alcohol_unknown_is_distinguishable_from_recorded_zero():
    """SUPERSEDED BEHAVIOUR: unknown was briefly EXCLUDED alongside recorded
    drinks. That starved the observed block (29 of 53 nights removed, 8 straight
    HOLDs) and was refuted by the adjacency test — see the alcohol-predicate
    block below. Unknown is now admitted; what survives is that the two states
    remain distinguishable, which is what the flag is for."""
    unknown = classify_night(night(1, alcohol=None), RX)
    zero = classify_night(night(1, alcohol=0), RX)
    assert unknown.valid and zero.valid
    assert unknown.alcohol_unknown is True and zero.alcohol_unknown is False


def test_any_nap_excludes_the_night_per_Q45():
    """Q45: the instrument does not say which day a nap belongs to, so nap nights
    are excluded rather than attributed. Not a >20min threshold — any nap."""
    assert not classify_night(night(1, naps=15), RX).valid
    assert classify_night(night(1, naps=15), RX).reason == "nap"
    assert not classify_night(night(1, naps=120), RX).valid
    assert classify_night(night(1, naps=0), RX).valid


def test_travel_or_match_excluded():
    assert classify_night(night(1, travel=True), RX).reason == "travel_or_match"


def test_training_night_excluded_only_when_session_end_pushes_past_prescription():
    """Session end + 90 min is a physical floor, not a compliance failure."""
    late = classify_night(night(1, training_end=datetime(2026, 6, 1, 21, 30)), RX)
    assert not late.valid and late.reason == "training_constrained"   # 21:30+90 = 23:00 > 22:30
    early = classify_night(night(1, training_end=datetime(2026, 6, 1, 19, 0)), RX)
    assert early.valid                                               # 19:00+90 = 20:30 <= 22:30


def test_incomplete_night_excluded():
    assert classify_night(night(1, tst=None), RX).reason == "incomplete"


# ── gate 1: sufficiency, and it short-circuits ────────────────────────────────

def test_insufficient_valid_nights_holds():
    nights = week()
    for n in nights[:3]:
        n.alcohol_units = 2                      # 3 excluded -> 4 valid
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert d.decision == "hold"
    assert "insufficient_nights" in d.reason
    assert d.window_minutes == WINDOW            # window untouched on a hold
    assert d.basis_nights_n == 4


def test_sufficiency_failure_short_circuits_before_adherence():
    """A HOLD names the FIRST failing gate, not the last one checked. Here both
    gates would fail; the reason must be sufficiency."""
    nights = week(samsung="01:00")               # wildly non-adherent
    for n in nights[:3]:
        n.alcohol_units = 2                      # RECORDED drinks -> excluded
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert d.decision == "hold" and "insufficient_nights" in d.reason
    assert "adherence" not in d.reason


# ── gate 2: adherence — unreachable from real data, so tested only here ───────

def test_adherence_failure_holds_and_reports_source_composition():
    nights = week(samsung="23:45")               # +75 min, all 7 outside tolerance
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert d.decision == "hold" and d.reason.startswith("adherence")
    assert d.basis_n_samsung == 7 and d.basis_n_diary == 0
    assert d.window_minutes == WINDOW


def test_adherence_passes_at_the_tolerance_boundary():
    nights = week(samsung="23:00")               # exactly +30
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert d.decision != "hold" or "adherence" not in d.reason


def test_two_failures_is_below_the_threshold_three_is_not():
    ok = week()
    for n in ok[:2]:
        n.samsung_bedtime = "23:45"
    for n in ok[2:]:
        n.samsung_bedtime = RX
    assert "adherence" not in evaluate_cycle(ok, WINDOW, RX, ANCHOR).reason

    bad = week()
    for n in bad[:3]:
        n.samsung_bedtime = "23:45"
    for n in bad[3:]:
        n.samsung_bedtime = RX
    assert evaluate_cycle(bad, WINDOW, RX, ANCHOR).reason.startswith("adherence")


def test_adherence_falls_back_to_diary_and_labels_it():
    """No Samsung row -> diary lights_out, counted as n_diary. This is the regime
    the entire replay runs in."""
    d = evaluate_cycle(week(samsung=None), WINDOW, RX, ANCHOR)
    assert d.basis_n_samsung == 0 and d.basis_n_diary == 7


def test_samsung_is_preferred_over_diary_when_both_present():
    v = classify_night(night(1, lights_out="22:30", samsung="23:40"), RX)
    assert v.adherence_source == "samsung"
    assert v.adherent is False           # +70 by the device, adherent by the diary


def test_adherence_delta_uses_shortest_path_across_midnight():
    v = classify_night(night(1, samsung="00:10"), "23:50")
    assert v.adherence_delta_min == 20 and v.adherent is True


# ── titration ─────────────────────────────────────────────────────────────────

def test_window_is_mean_tst_plus_buffer():
    # start close enough that the per-cycle cap does not bind, so this test
    # measures the buffer rule rather than the cap
    d = evaluate_cycle(week(tst=400), 405, RX, ANCHOR)
    assert d.window_minutes == 400 + BUFFER_MIN      # 430
    assert d.decision == "extend"
    assert d.move_capped is False


def test_window_never_goes_below_the_five_hour_floor():
    d = evaluate_cycle(week(tst=180), 320, RX, ANCHOR)
    assert d.window_minutes >= FLOOR_MIN


def test_move_is_capped_and_the_cap_is_reported():
    d = evaluate_cycle(week(tst=500), 300, RX, ANCHOR)   # wants +230
    assert d.window_minutes == 300 + MAX_MOVE_MIN
    assert d.move_capped is True


def test_new_lights_out_is_derived_from_the_anchor_not_the_old_prescription():
    d = evaluate_cycle(week(tst=390), 390, RX, ANCHOR)
    assert d.window_minutes == 420                      # 390 TST + 30 buffer = 7h00
    assert d.prescribed_lights_out == "22:00"           # 05:00 minus 7h00


def test_compress_when_tst_falls():
    d = evaluate_cycle(week(tst=330), 420, RX, ANCHOR)
    assert d.decision == "compress" and d.window_minutes < 420


# ── exit condition — TST plateau, NOT SE stall (#107) ────────────────────────

def test_plateau_with_se_at_floor_closes_the_block():
    d = evaluate_cycle(week(tst=445, se=92.0), 475, RX, ANCHOR,
                       prior_basis_tst=[440, 442])
    assert d.decision == "close" and "tst_plateau" in d.reason


def test_plateau_below_the_se_floor_does_NOT_close():
    """SE is a floor. A plateau reached at poor efficiency is not an exit."""
    d = evaluate_cycle(week(tst=445, se=80.0), 475, RX, ANCHOR,
                       prior_basis_tst=[440, 442])
    assert d.decision != "close"


def test_high_se_alone_does_not_close_the_block():
    """The #107 counterexample: an SE-maximising rule would exit here. TST is
    still climbing, so this engine must not."""
    d = evaluate_cycle(week(tst=445, se=97.0), 420, RX, ANCHOR,
                       prior_basis_tst=[380, 410])
    assert d.decision != "close"


def test_a_single_prior_cycle_is_not_a_plateau():
    d = evaluate_cycle(week(tst=445, se=92.0), 475, RX, ANCHOR, prior_basis_tst=[443])
    assert d.decision != "close"


# ── diagnostics are computed and never gate ──────────────────────────────────

def test_regularity_is_reported_but_does_not_gate(monkeypatch):
    """#114: lights-out SD is instrumented, not a HOLD condition. Wildly irregular
    bedtimes inside tolerance must still titrate."""
    nights = week()
    for i, n in enumerate(nights):
        n.lights_out = ["22:10", "22:50", "22:20", "22:45", "22:15", "22:55", "22:30"][i]
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert d.lights_out_sd_min is not None and d.lights_out_sd_min > 0
    assert d.decision != "hold" or "regularity" not in d.reason


def test_ema_is_counted_and_never_compresses():
    """#108: early wakes are instrumented; they must not drive compression."""
    nights = week(tst=430, wake="04:30")
    d = evaluate_cycle(nights, 400, RX, ANCHOR)
    assert d.ema_count == 7
    assert d.decision == "extend"      # TST says extend; EMA does not veto it


# ── excluded nights are recorded, not dropped ────────────────────────────────

def test_excluded_nights_are_reason_tagged():
    nights = week()
    nights[0].alcohol_units = 3
    nights[1].naps_min = 30
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert d.excluded_nights[nights[0].date.isoformat()] == "alcohol"
    assert d.excluded_nights[nights[1].date.isoformat()] == "nap"
    assert d.basis_nights_n == 5


def test_composition_never_exceeds_basis_count():
    d = evaluate_cycle(week(), WINDOW, RX, ANCHOR)
    assert d.basis_n_samsung + d.basis_n_diary <= d.basis_nights_n


# ── alcohol predicate: admit unknown, flag it ────────────────────────────────
# Refuted on the observed block: excluding unknowns removed 29 of 53 nights and
# starved sufficiency to 8 straight HOLDs. Zero of 19 blanks sat adjacent to a
# drink night (~3.7 expected under random placement, p=0.0033), which refutes
# "blank means drank and did not log" — the only hypothesis exclusion guarded.

def test_unknown_alcohol_is_ADMITTED_and_flagged():
    v = classify_night(night(1, alcohol=None), RX)
    assert v.valid is True
    assert v.alcohol_unknown is True


def test_recorded_zero_is_admitted_and_NOT_flagged():
    v = classify_night(night(1, alcohol=0), RX)
    assert v.valid is True and v.alcohol_unknown is False


def test_recorded_nonzero_is_still_excluded():
    """Still excluded — but as a NON-ADHERENCE proxy, not as suppressed sleep.
    Drink nights carry the block's HIGHEST TST (430 vs 370 for recorded-zero),
    i.e. more time in bed, so the original 'alcohol suppresses TST' rationale is
    refuted by the data it described."""
    v = classify_night(night(1, alcohol=2), RX)
    assert not v.valid and v.reason == "alcohol"


def test_alcohol_unknown_count_reaches_the_basis():
    nights = week()
    for n in nights[:3]:
        n.alcohol_units = None
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert d.basis_nights_n == 7                  # all admitted
    assert d.basis_n_alcohol_unknown == 3         # three assumed clean, not verified


def test_unknown_alcohol_no_longer_starves_sufficiency():
    """The regression this predicate change exists to prevent."""
    d = evaluate_cycle(week(alcohol=None), WINDOW, RX, ANCHOR)
    assert "insufficient_nights" not in d.reason
    assert d.basis_n_alcohol_unknown == 7


# ── EXIT CONDITION — untouched by the observed block, synthetic-only ─────────
# The replay never plateaued, so this rule and PLATEAU_TOL_MIN have no empirical
# support whatsoever. These are the only coverage they have.

def test_plateau_within_tolerance_and_SE_at_floor_closes():
    d = evaluate_cycle(week(tst=445, se=88.0), 475, RX, ANCHOR,
                       prior_basis_tst=[440, 444])          # deltas +4, +1
    assert d.decision == "close" and "tst_plateau" in d.reason


def test_plateau_JUST_outside_tolerance_does_not_close():
    """One delta at 11 min against PLATEAU_TOL_MIN=10 — still climbing."""
    d = evaluate_cycle(week(tst=455, se=88.0), 475, RX, ANCHOR,
                       prior_basis_tst=[440, 444])          # deltas +4, +11
    assert d.decision != "close"


def test_plateau_at_the_tolerance_boundary_closes():
    d = evaluate_cycle(week(tst=454, se=88.0), 475, RX, ANCHOR,
                       prior_basis_tst=[440, 444])          # delta exactly +10
    assert d.decision == "close"


def test_plateau_with_SE_BELOW_floor_does_not_close():
    """SE is a floor, not a target. A plateau at poor efficiency is not an exit —
    it is a window that is too wide."""
    d = evaluate_cycle(week(tst=445, se=84.9), 475, RX, ANCHOR,
                       prior_basis_tst=[440, 444])
    assert d.decision != "close"


def test_plateau_with_SE_exactly_at_floor_closes():
    d = evaluate_cycle(week(tst=445, se=85.0), 475, RX, ANCHOR,
                       prior_basis_tst=[440, 444])
    assert d.decision == "close"


def test_falling_tst_is_not_a_plateau():
    d = evaluate_cycle(week(tst=400, se=95.0), 475, RX, ANCHOR,
                       prior_basis_tst=[440, 444])
    assert d.decision != "close"


def test_close_is_reachable_only_after_two_prior_cycles():
    for prior in ([], [444]):
        d = evaluate_cycle(week(tst=445, se=90.0), 475, RX, ANCHOR, prior_basis_tst=prior)
        assert d.decision != "close"
