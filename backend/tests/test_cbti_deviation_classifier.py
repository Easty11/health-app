"""#436 deviation classifier — REAL NIGHTS, by explicit operator request (2026-10-21).

The older engine tests (test_cbti_engine.py) say "no real rows (both repos are public)" and stay
synthetic. These do not: the operator asked for the rulings to be pinned on the nights that
motivated them. The fixtures are diary clocks and scored TST/SE only (no notes, no HRV, no
prose), the same figures DECISIONS_LOG #436 already quotes.

Prescription in force for every night here: lights-out 21:48, wake anchor 05:45, window 477
(rx 19 and rx 20). The 2026-10-09 row is a FROZEN copy of the values it held before the
operator corrected it (12-hour clock-entry error, corrected to 21:45 / 22:05 on 2026-10-21);
the tests never read the live row.
"""
from datetime import date, timedelta

import pytest

import cbti.engine as engine
from cbti.engine import (
    ADHERENCE_TOL_MIN,
    LATE_RISE_TOL_MIN,
    LEGACY_RULESET_VERSION,
    MAX_PLAUSIBLE_TIB_MIN,
    MAX_PLAUSIBLE_TST_MIN,
    RULESET_VERSION,
    Night,
    NightVerdict,
    _ledger_status_reason,
    classify_night,
    evaluate_cycle,
)
from cbti.replay import LedgerRx, replay

RX = "21:48"
ANCHOR = "05:45"
WINDOW = 477


def real(day, tst, se, lo, oob, fw, *, naps=0, alcohol=None, month=10):
    return Night(date=date(2026, month, day), tst_min=tst, se_pct=se, lights_out=lo,
                 out_of_bed=oob, final_wake=fw, naps_min=naps, alcohol_units=alcohol)


# the cycle the operator left to lapse (2026-10-15..18) and the night before it
N1014 = real(14, 255, 91.1, "21:40", "02:20", "02:10")                      # 02:10 wake
N1015 = real(15, 396, 84.26, "21:40", "05:30", "05:16")                     # -8
N1016 = real(16, 331, 90.68, "22:30", "04:35", "04:31")                     # +42
N1017 = real(17, 350, 92.11, "23:25", "05:45", "05:45", naps=20)            # +97, 20 min nap (under the floor)
N1018 = real(18, 491, 84.8, "21:41", "07:20", "06:29", alcohol=2)           # lights-out -7, out of bed +95
# the stored 2026-10-09 row as it was before correction: lights_out 10:05, TST 1083
N1009_ERR = real(9, 1083, 92.96, "10:05", "05:30", "04:30")
# the same night as corrected on the operator's ruling (21:45 / 22:05; TST 363, SE 81.57)
N1009_FIXED = real(9, 363, 81.57, "22:05", "05:30", "04:30")


def clean(day, *, tst=360, se=90.0, lo=RX, oob=ANCHOR, month=10):    # TST 360 fits every TIB used below
    return Night(date=date(2026, month, day), tst_min=tst, se_pct=se, lights_out=lo,
                 out_of_bed=oob, final_wake=oob, naps_min=0, alcohol_units=0)


def cls(n):
    return classify_night(n, RX, ANCHOR)


# ── the cycle that was left to lapse ──────────────────────────────────────────

def test_cycle_1015_to_1018_is_an_adherence_hold():
    d = evaluate_cycle([N1015, N1016, N1017, N1018], WINDOW, RX, ANCHOR)
    assert d.decision == "hold" and d.reason.startswith("adherence")
    assert d.sufficient is True                       # a decision on the merits, acceptable
    assert d.window_minutes == WINDOW
    assert d.excluded_nights == {"2026-10-16": "deviation", "2026-10-17": "deviation",
                                 "2026-10-18": "deviation"}
    assert d.basis_nights_n == 1                      # only 10-15 stays
    assert d.basis_tst_min is None and d.basis_se_pct is None   # < MIN_VALID_NIGHTS valid: no basis


def test_each_deviation_names_what_it_missed():
    v16, v17, v18 = cls(N1016), cls(N1017), cls(N1018)
    assert (v16.reason, v16.adherence_delta_min) == ("deviation", 42)
    assert (v17.reason, v17.adherence_delta_min) == ("deviation", 97)
    # 10-18: lights-out was on time (-7); the miss is the rise, 07:20 against 05:45
    assert v18.reason == "deviation" and v18.adherence_delta_min == -7 and v18.rise_delta_min == 95
    assert "+97 min" in v17.deviation_detail and "+95 min" in v18.deviation_detail


def test_the_ledger_row_for_1017_is_a_deviation_not_training():
    d = evaluate_cycle([N1015, N1016, N1017, N1018], WINDOW, RX, ANCHOR)
    row = {r["date"]: r for r in d.basis_ledger}["2026-10-17"]
    assert row["status"] == "excluded" and row["reason"] == "deviation"
    assert "23:25" in row["evidence"] and "+97" in row["evidence"]


def test_a_20_minute_nap_does_not_decide_the_night():
    """The nap rule is unchanged (#219): 20 min is under the floor, so 10-17 is excluded for the
    miss, not for the nap."""
    assert cls(N1017).reason == "deviation"
    assert classify_night(real(17, 350, 92.11, RX, ANCHOR, ANCHOR, naps=20), RX, ANCHOR).valid


# ── an early wake is the measured outcome ─────────────────────────────────────

def test_1014_with_a_0210_wake_stays_in_the_basis():
    v = cls(N1014)
    assert v.valid and v.reason is None and v.adherent is True
    d = evaluate_cycle([N1014, clean(15), clean(16), clean(17)], WINDOW, RX, ANCHOR)
    row = {r["date"]: r for r in d.basis_ledger}["2026-10-14"]
    assert row["status"] == "included" and d.basis_nights_n == 4


@pytest.mark.parametrize("oob", ["04:00", "02:20", "05:15"])
def test_an_early_out_of_bed_is_never_a_deviation(oob):
    assert cls(clean(1, tst=240, oob=oob)).valid


# ── the plausibility guard ────────────────────────────────────────────────────

def test_the_stored_1009_row_is_incomplete():
    v = cls(N1009_ERR)
    assert v.valid is False and v.reason == "incomplete"


def test_an_implausible_night_is_not_a_deviation_and_does_not_count_toward_the_gate():
    """10-09 would read as -703 min against the prescription. As `incomplete` it is bad data,
    not a miss: with one real deviation beside it the cycle is NOT an adherence hold."""
    d = evaluate_cycle([N1009_ERR, clean(10), clean(11), real(12, 331, 90.68, "22:30", "04:35", "04:31")],
                       WINDOW, RX, ANCHOR)
    assert not d.reason.startswith("adherence")
    assert d.excluded_nights["2026-10-09"] == "incomplete"
    assert d.excluded_nights["2026-10-12"] == "deviation"
    assert d.reason.startswith("insufficient_nights")      # 2 valid of 4, 1 deviation


def test_the_corrected_1009_row_is_a_valid_adherent_night():
    v = cls(N1009_FIXED)
    assert v.valid and v.adherent is True and v.adherence_delta_min == 17


def test_the_tst_ceiling_is_a_boundary_not_a_range():
    assert MAX_PLAUSIBLE_TST_MIN == 720
    # no wake anchor passed, so the long TIB is not also read as a late rise; TIB 720 is the cap
    assert classify_night(clean(1, tst=720, oob="09:48"), RX).valid is True            # TIB 720, TST 720
    assert classify_night(clean(1, tst=721, oob="09:48"), RX).reason == "incomplete"   # one over the TST ceiling


def test_a_tst_above_its_own_time_in_bed_is_incomplete():
    n = clean(1, tst=400, lo="23:00", oob="05:00")                              # TIB 360
    assert cls(n).reason == "incomplete"


# ── two-sided lights-out, one-sided rise ──────────────────────────────────────

def test_an_early_lights_out_of_minus_40_is_a_deviation():
    v = cls(clean(1, lo="21:08"))                                              # 21:48 - 40
    assert v.reason == "deviation" and v.adherence_delta_min == -40 and v.adherent is False


@pytest.mark.parametrize("lo, deviates", [("21:18", False), ("21:17", True),     # -30 / -31
                                          ("22:18", False), ("22:19", True)])     # +30 / +31
def test_lights_out_tolerance_is_30_minutes_either_side(lo, deviates):
    assert ADHERENCE_TOL_MIN == 30
    assert (cls(clean(1, lo=lo)).reason == "deviation") is deviates


@pytest.mark.parametrize("oob, deviates", [("06:15", False), ("06:16", True)])    # +30 / +31
def test_a_late_rise_is_a_deviation_only_past_30_minutes(oob, deviates):
    assert LATE_RISE_TOL_MIN == 30
    v = cls(clean(1, oob=oob))
    assert (v.reason == "deviation") is deviates
    if deviates:
        assert v.rise_delta_min == 31 and v.adherence_delta_min == 0


# ── gate order ────────────────────────────────────────────────────────────────

def test_two_deviations_beside_two_clean_nights_is_an_adherence_hold_not_an_insufficiency():
    nights = [clean(1), clean(2), clean(3, lo="23:30"), clean(4, lo="23:30")]
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert d.reason.startswith("adherence") and d.sufficient is True
    assert d.basis_nights_n == 2 and d.basis_tst_min is None


def test_one_deviation_leaves_sufficiency_to_decide():
    nights = [clean(1), clean(2), clean(3), clean(4, lo="23:30")]
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert not d.reason.startswith("adherence") and not d.reason.startswith("insufficient")
    assert d.basis_nights_n == 3 and d.excluded_nights == {"2026-10-04": "deviation"}


def test_an_adherence_hold_records_a_basis_only_with_enough_valid_nights(monkeypatch):
    nights = [clean(1, tst=400), clean(2, tst=420), clean(3, lo="23:30"), clean(4, lo="23:30")]
    assert evaluate_cycle(nights, WINDOW, RX, ANCHOR).basis_tst_min is None     # 2 valid < 3
    monkeypatch.setattr(engine, "MIN_VALID_NIGHTS", 2)
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert d.reason.startswith("adherence") and d.basis_tst_min == 410          # 2 valid >= 2


def test_an_adherence_hold_with_no_basis_adds_nothing_to_the_plateau_history():
    """replay() appends a cycle's basis to prior_basis_tst only when it has one."""
    d0 = date(2026, 10, 1)
    nights = [clean(d, tst=430, month=10) for d in range(1, 5)]                    # cycle 1: clean
    nights += [clean(5, lo="23:30"), clean(6, lo="23:30"), clean(7), clean(8)]     # cycle 2: adherence hold
    rxs = [LedgerRx(d0, None, RX, ANCHOR, WINDOW, "adopt")]
    series = replay(nights, rxs, date(2026, 10, 8))
    assert series[0]["tst"] == 430
    assert series[1]["decision"] == "hold" and series[1]["reason"].startswith("adherence")
    assert series[1]["tst"] is None and series[1]["ruleset_version"] == RULESET_VERSION


def test_the_cut_is_the_evaluation_not_the_night_date():
    """#436, ruled 2026-10-21: every cycle of the LIVE prescription is adjudicated under the new
    rules for ALL of its nights, whatever their dates. The nights here are dated 2026-08, long
    before any 'ruleset date', and a miss still leaves the basis."""
    nights = [clean(d, tst=360, month=8) for d in (1, 2)] + [clean(3, lo="23:30", month=8), clean(4, lo="23:30", month=8)]
    live = [LedgerRx(date(2026, 8, 1), None, RX, ANCHOR, WINDOW, "adopt")]       # effective_to None = live
    s = replay(nights, live, date(2026, 8, 4))[0]
    assert s["reason"].startswith("adherence") and s["excluded"] == {"2026-08-03": "deviation", "2026-08-04": "deviation"}
    assert s["ruleset_version"] == RULESET_VERSION and s["n"] == 2


def test_a_superseded_prescriptions_cycles_keep_the_legacy_gate_so_history_is_not_rewritten():
    """The same four nights under a prescription that has been SUPERSEDED (effective_to set) are
    history. The replay re-walks them only to rebuild the plateau history, under the legacy gate:
    the two late nights stay VALID nights whose miss is counted after sufficiency, the basis is
    recorded, and the cycle is stamped with the legacy ruleset."""
    nights = [clean(d, tst=430, month=8) for d in (1, 2)] + [clean(3, lo="23:30", month=8), clean(4, lo="23:30", month=8)]
    past = LedgerRx(date(2026, 8, 1), date(2026, 8, 4), RX, ANCHOR, WINDOW, "adopt")
    live = LedgerRx(date(2026, 8, 5), None, RX, ANCHOR, WINDOW, "adopt")
    s = replay(nights, [past, live], date(2026, 8, 4))[0]
    assert s["reason"].startswith("adherence") and "valid nights outside" in s["reason"]    # the legacy wording
    assert s["n"] == 4 and s["excluded"] == {} and s["tst"] is not None
    assert s["ruleset_version"] == LEGACY_RULESET_VERSION


# ── inverted and wrapped clocks (ruled 2026-10-21) ────────────────────────────

@pytest.mark.parametrize("lo, oob", [
    ("22:05", "21:00"),      # out of bed an hour BEFORE lights-out: the wrap reads it as 22 h 55 min
    ("01:10", "00:30"),      # the same inversion across the midnight line (23 h 20 min)
    ("05:30", "22:05"),      # a morning and an evening swapped (16 h 35 min)
    ("10:05", "05:30"),      # the stored 2026-10-09 clocks (19 h 25 min)
    ("22:00", "22:00"),      # equal clocks: TIB 0, never a positive span
])
def test_an_inverted_or_degenerate_clock_pair_is_incomplete_never_a_positive_span(lo, oob):
    n = Night(date=date(2026, 10, 22), tst_min=400, se_pct=80.0, lights_out=lo, out_of_bed=oob,
              final_wake=oob, naps_min=0, alcohol_units=0)
    for v in (classify_night(n, RX, ANCHOR), classify_night(n, RX)):
        assert v.valid is False and v.reason == "incomplete"


def test_an_inverted_pair_is_not_a_deviation_and_does_not_count_toward_the_gate():
    bad = Night(date=date(2026, 10, 1), tst_min=400, se_pct=80.0, lights_out="22:05", out_of_bed="21:00",
                final_wake="21:00", naps_min=0, alcohol_units=0)
    d = evaluate_cycle([bad, clean(2), clean(3), real(4, 331, 90.68, "22:30", "04:35", "04:31")], WINDOW, RX, ANCHOR)
    assert d.excluded_nights["2026-10-01"] == "incomplete" and not d.reason.startswith("adherence")


def test_a_real_midnight_crossing_is_not_an_inversion():
    assert MAX_PLAUSIBLE_TIB_MIN == 720
    assert cls(clean(1, oob="05:30")).valid                                           # 7 h 42 min, crosses midnight
    assert classify_night(clean(1, tst=300, lo="23:50", oob="06:10"), "23:50").valid  # a post-midnight-ish pair
    long_ok = Night(date=date(2026, 10, 1), tst_min=400, se_pct=80.0, lights_out="21:48", out_of_bed="09:48",
                    final_wake="09:48", naps_min=0, alcohol_units=0)                  # TIB exactly 720
    assert classify_night(long_ok, RX).valid
    too_long = Night(date=date(2026, 10, 1), tst_min=400, se_pct=80.0, lights_out="21:48", out_of_bed="09:49",
                     final_wake="09:49", naps_min=0, alcohol_units=0)                 # TIB 721
    assert classify_night(too_long, RX).reason == "incomplete"


# ── training is not read, the legacy reason still reads ───────────────────────

def test_training_constrained_stays_in_the_enum_as_legacy_but_is_never_emitted():
    v = NightVerdict(N1017, False, "training_constrained")
    assert _ledger_status_reason(v) == ("excluded", "training_constrained")
    emitted = {cls(n).reason for n in (N1014, N1015, N1016, N1017, N1018, N1009_ERR, N1009_FIXED)}
    assert "training_constrained" not in emitted


def test_the_ruleset_version_moved_and_the_replay_no_longer_reads_sessions():
    import cbti.replay as replay_mod
    assert RULESET_VERSION == "cbti-se-band/2026-10-25.1"
    assert not hasattr(replay_mod, "_TRAINING_SQL")
    assert not hasattr(Night(date=date(2026, 10, 1)), "training_end")
