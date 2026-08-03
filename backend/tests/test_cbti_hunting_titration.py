"""The hunting-search retune: 4-night cadence, no auto-close, centre-as-estimate.

The existing engine/replay suites were retuned to the new constants in place — they
already pinned those behaviours and would have gone quietly wrong, not red, if left
hardcoded to 7. This file covers what is genuinely NEW:

  * the cadence cascade is an invariant, not a coincidence (MIN_VALID < CYCLE_NIGHTS);
  * the engine never emits `close` again, while `close` stays a legal ledger value;
  * the sleep-need estimate is the CENTRE of the dither, not the current window;
  * a starved cycle says WHAT starved it, which at 4/3 is one nap night from happening.

SYNTHETIC data only; no real rows (both repos are public).
"""
from datetime import date

import pytest

from cbti.engine import (
    ADHERENCE_FAIL_N,
    CENTRE_CYCLES,
    CYCLE_NIGHTS,
    MAX_MOVE_MIN,
    MIN_VALID_NIGHTS,
    Decision,
    Night,
    centre_estimate,
    evaluate_cycle,
)

RX = "22:30"
ANCHOR = "05:00"
WINDOW = 390


def night(day, *, tst=420, se=90.0, lights_out=RX, naps=0, alcohol=0):
    return Night(date=date(2026, 6, day), tst_min=tst, se_pct=se, lights_out=lights_out,
                 final_wake="05:00", naps_min=naps, alcohol_units=alcohol)


def cycle(**kw):
    return [night(d, **kw) for d in range(1, CYCLE_NIGHTS + 1)]


# ── the cadence cascade ──────────────────────────────────────────────────────

def test_sufficiency_threshold_fits_inside_the_cycle():
    """The cascade that makes the cadence change safe. A threshold at or above the
    cycle length makes GATE 1 unsatisfiable — every cycle HOLDs forever and it reads as
    "titration stalled", not as a bad constant. Asserted at import too; asserted here so
    the reason is written down next to the test that would otherwise mysteriously fail.
    """
    assert MIN_VALID_NIGHTS < CYCLE_NIGHTS


def test_a_full_clean_cycle_actually_produces_a_decision():
    """Non-vacuity for the above: at 4/3 a whole clean cycle must clear sufficiency."""
    d = evaluate_cycle(cycle(), WINDOW, RX, ANCHOR)
    assert "insufficient" not in d.reason
    assert d.basis_nights_n == CYCLE_NIGHTS


def test_adherence_threshold_still_fits_the_cycle():
    assert ADHERENCE_FAIL_N <= CYCLE_NIGHTS


# ── no auto-close ────────────────────────────────────────────────────────────

def test_a_plateau_converges_and_holds_it_never_closes():
    d = evaluate_cycle(cycle(tst=445, se=92.0), 475, RX, ANCHOR,
                       prior_basis_tst=[440, 442])
    assert d.decision == "hold"
    assert d.converged is True
    assert d.window_minutes == 475           # the window stops moving...
    assert "block stays open" in d.reason    # ...and the block does not end


def test_close_remains_a_legal_ledger_value_even_though_the_engine_stops_emitting_it():
    """Block 1 was imported carrying `decision='close'` and the ledger is append-only, so
    retiring the value from the vocabulary would invalidate history. The engine simply
    never produces it now — those are different claims and only the second one changed.
    """
    assert "close" in Decision.__args__


@pytest.mark.parametrize("prior", [None, [], [440], [440, 442], [300, 305]])
def test_no_input_shape_makes_the_engine_emit_close(prior):
    for tst, se in ((445, 92.0), (445, 80.0), (300, 95.0), (500, 86.0)):
        d = evaluate_cycle(cycle(tst=tst, se=se), 475, RX, ANCHOR, prior_basis_tst=prior)
        assert d.decision != "close"


# ── centre-as-estimate ───────────────────────────────────────────────────────

def test_centre_is_the_mean_of_the_recent_window_series():
    """Worked example. A window dithering by +/-15 around 420 reports 420, not whichever
    end of the swing the latest cycle happens to sit on."""
    windows = [405, 420, 435, 420]
    assert centre_estimate(windows) == 420.0
    # the estimate does not lurch when the next probe swings high
    assert centre_estimate(windows + [435]) == pytest.approx(427.5)


def test_centre_averages_only_the_last_n_cycles():
    """Early history must age out, or a genuine drift in sleep need can never move the
    estimate."""
    old_low = [300] * 10
    recent_high = [450] * CENTRE_CYCLES
    assert centre_estimate(old_low + recent_high) == 450.0


def test_centre_uses_what_exists_when_there_are_fewer_than_n_cycles():
    assert centre_estimate([420, 430]) == 425.0
    assert centre_estimate([420]) == 420.0


def test_centre_is_none_when_there_is_nothing_to_average():
    assert centre_estimate([]) is None
    assert centre_estimate([None, None]) is None


def test_centre_is_distinct_from_the_current_window():
    """The whole point: the probe and the estimate are different numbers. A symmetric
    dither reports its centre even though no single cycle ever sat there."""
    windows = [420 - MAX_MOVE_MIN, 420 + MAX_MOVE_MIN,
               420 - MAX_MOVE_MIN, 420 + MAX_MOVE_MIN]
    assert centre_estimate(windows) == 420.0
    assert windows[-1] != centre_estimate(windows)


# ── nap over-exclusion is named, not silent (Q45 interaction) ────────────────

def test_two_nap_nights_starve_a_four_night_cycle_and_the_reason_says_so():
    """At 4/3 the margin is a single night, so two nap-flagged nights stall titration
    outright. Q45 excludes ANY nap night (the instrument does not say which day a nap
    belongs to), so a frequent napper can stall repeatedly — the HOLD must name the
    cause or the stall is undiagnosable from the surface.
    """
    nights = cycle()
    for n in nights[:2]:
        n.naps_min = 30
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)

    assert d.decision == "hold"
    assert "insufficient_nights" in d.reason
    assert "nap x2" in d.reason                       # the tally, not just a count
    assert f"2 excluded" in d.reason
    # and the per-night detail is still on the record, not only summarised
    assert sorted(d.excluded_nights.values()) == ["nap", "nap"]


def test_the_starvation_reason_distinguishes_mixed_causes():
    nights = cycle()
    nights[0].naps_min = 30
    nights[1].alcohol_units = 3
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert "insufficient_nights" in d.reason
    assert "alcohol x1" in d.reason and "nap x1" in d.reason


def test_one_nap_night_still_leaves_a_decidable_cycle():
    """Non-vacuity for the guard: one exclusion is survivable at 4/3, so the guard is
    reporting a real edge rather than firing on everything."""
    nights = cycle()
    nights[0].naps_min = 30
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert "insufficient" not in d.reason
    assert d.basis_nights_n == CYCLE_NIGHTS - 1


def test_the_guard_does_not_change_the_nap_predicate():
    """Surfacing only — Q45 stays open and exclude-all stands. A nap night is still
    excluded outright, at any duration."""
    from cbti.engine import NAP_EXCLUDE_MIN, classify_night
    assert NAP_EXCLUDE_MIN == 0
    assert classify_night(night(1, naps=1), RX).reason == "nap"
