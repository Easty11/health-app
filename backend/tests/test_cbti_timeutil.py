"""cbti.timeutil — the extracted midnight-wrap primitives.

The wrap is the defect the phase-1 Gate-4 reconciliation caught: an
unconditional +24h under-read an after-midnight night by 0.445 SE. These tests
pin the conditional form and prove the phase-2 extraction moved nothing — the
nine windows observed in the imported block are asserted against the extracted
`window_minutes`, which replaced a local version that wrapped unconditionally.
"""
import pytest

from cbti.timeutil import (
    clock_to_minutes,
    minutes_to_clock,
    minutes_between,
    tib_minutes,
    window_minutes,
    clock_delta_minutes,
)


# ── clock parsing ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("s,m", [("22:36", 1356), ("00:00", 0), ("05:00", 300),
                                 ("23:59", 1439), ("00:05", 5)])
def test_clock_to_minutes(s, m):
    assert clock_to_minutes(s) == m


@pytest.mark.parametrize("bad", [None, "", "  ", "nonsense", "25:00", "12:99", "1234", "12"])
def test_clock_to_minutes_rejects_bad_input_without_raising(bad):
    assert clock_to_minutes(bad) is None


def test_minutes_to_clock_roundtrips():
    for m in (0, 5, 300, 1356, 1439):
        assert clock_to_minutes(minutes_to_clock(m)) == m


# ── the conditional wrap ───────────────────────────────────────────────────────

def test_evening_bedtime_wraps():
    # 21:45 -> 05:15 next morning
    assert minutes_between(clock_to_minutes("21:45"), clock_to_minutes("05:15")) == 450


def test_after_midnight_bedtime_does_not_wrap():
    # 00:05 -> 08:45 the SAME day. Unconditional +24h would give 1960.
    assert minutes_between(clock_to_minutes("00:05"), clock_to_minutes("08:45")) == 520


def test_equal_times_are_zero_not_a_full_day():
    assert minutes_between(600, 600) == 0


def test_none_propagates():
    assert minutes_between(None, 300) is None
    assert minutes_between(300, None) is None
    assert tib_minutes(None, None) is None


def test_tib_is_the_se_denominator():
    # the 2026-03-21 night that exposed the phase-1 defect: TST 315 / TIB 520 = 0.6058
    tib = tib_minutes(clock_to_minutes("00:05"), clock_to_minutes("08:45"))
    assert tib == 520
    assert round(315 / tib, 4) == 0.6058


# ── behaviour preservation: the nine observed prescription windows ─────────────

OBSERVED = [
    ("22:36", 384), ("22:35", 385), ("22:16", 404), ("22:30", 390),
    ("21:55", 425), ("22:15", 405), ("22:00", 420), ("21:45", 435),
    ("21:22", 458),
]


@pytest.mark.parametrize("lights_out,expected", OBSERVED)
def test_window_minutes_matches_the_imported_block(lights_out, expected):
    """Every prescription in the completed block, against its constant 05:00
    anchor. These are the values phase 1 computed with an unconditional wrap;
    the extracted conditional version must reproduce them exactly."""
    assert window_minutes(lights_out, "05:00") == expected


def test_window_minutes_refuses_to_inflate_a_post_midnight_prescription():
    # the case the unconditional version got wrong; no observed prescription hits
    # it yet, which is precisely why it needs a test rather than a comment
    assert window_minutes("00:30", "05:00") == 270


# ── signed clock delta (adherence + prefill gate) ─────────────────────────────

def test_clock_delta_is_shortest_path_across_midnight():
    assert clock_delta_minutes("23:50", "00:10") == 20
    assert clock_delta_minutes("00:10", "23:50") == -20


def test_clock_delta_signs():
    assert clock_delta_minutes("22:00", "22:25") == 25     # later than prescribed
    assert clock_delta_minutes("22:00", "21:35") == -25    # earlier than prescribed


def test_clock_delta_none_propagates():
    assert clock_delta_minutes(None, "05:00") is None
    assert clock_delta_minutes("05:00", "bogus") is None
