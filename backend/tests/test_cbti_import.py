"""Pure-logic tests for the CBT-I block importer — SYNTHETIC data only.

The real workbook holds personal data and both repos are public, so no real
rows appear here (brief Gate 4). These lock in the two things that bit during
the import: the conditional midnight wrap in TIB (an after-midnight bedtime
made an unconditional +24h wrap under-read SE by 0.445), and that the SE
comparator actually detects an injected mismatch.
"""
import datetime as dt

from import_cbti_block import _tib, _parse_alcohol, reconcile, reconcile_with_control


def test_tib_normal_evening_bedtime_wraps_past_midnight():
    # lights out 21:45 (1305), out of bed 05:15 (315) next morning -> 450 min
    assert _tib(1305, 315) == 450


def test_tib_after_midnight_bedtime_does_not_wrap():
    # lights out 00:05 (5), out of bed 08:45 (525) same day -> 520 min, NOT 1960
    assert _tib(5, 525) == 520


def test_tib_none_when_component_missing():
    assert _tib(None, 300) is None and _tib(300, None) is None


def test_parse_alcohol_variants():
    assert _parse_alcohol("No") == 0        # explicit none
    assert _parse_alcohol("") is None       # not recorded
    assert _parse_alcohol(None) is None
    assert _parse_alcohol(3) == 3
    assert _parse_alcohol("14") == 14


def _night(date, tst, ref_se):
    """Synthetic night: recomputed SE forced equal to ref unless overridden."""
    return {"date": date, "recomp_se": ref_se, "_ref_se": ref_se, "diary_tst_min": tst}


def test_reconcile_passes_when_matched():
    ns = [_night(dt.date(2026, 1, i + 1), 400, 0.9) for i in range(5)]
    assert reconcile(ns) == []


def test_reconcile_flags_a_divergent_night():
    ns = [_night(dt.date(2026, 1, i + 1), 400, 0.9) for i in range(5)]
    ns[2]["recomp_se"] = 0.80   # 0.10 off -> beyond 0.001
    mm = reconcile(ns)
    assert len(mm) == 1 and mm[0][0] == dt.date(2026, 1, 3)


def test_negative_control_localizes_injected_mismatch():
    ns = [_night(dt.date(2026, 1, i + 1), 400, 0.9) for i in range(7)]
    rc = reconcile_with_control(ns)
    assert rc["real"] == []
    assert rc["control_ok"] is True
    assert len(rc["control_flagged"]) == 1
