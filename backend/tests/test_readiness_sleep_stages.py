"""Daily readiness sleep-stage rendering (HRV & Sleep Data Integrity, Task 4).

Deep-sleep minutes are excluded as a standalone daily readiness term — the
Samsung Ring deep/light boundary is a two-class confusion, so only their robust
SUM (Deep+Light) is fed to the coaching model. REM, awake, efficiency, TST,
SpO2 are retained. Deep alone stays a long-run trend (get_recovery_metrics),
never a daily term.
"""
from datetime import date, datetime

from context_builder import _section_samsung_hrv, _section_health_connect

_NOW = datetime(2026, 6, 28, 8, 0, 0)


def test_samsung_section_reports_combined_deep_light_not_standalone_deep():
    readings = [{
        "captured_at": _NOW.date(),
        "hrv_ms": 57.0,
        "deep_minutes": 16,
        "light_minutes": 200,
        "rem_minutes": 91,
        "awake_minutes": 30,
    }]
    out = _section_samsung_hrv(readings, _NOW, None)
    assert "Deep+Light 216m" in out
    assert "Deep 16m" not in out       # standalone deep dropped as a daily term
    assert "Light 200m" not in out     # standalone light dropped
    assert "REM 91m" in out            # REM retained
    assert "Awake 30m" in out          # awake retained


def test_health_connect_section_reports_combined_deep_light():
    records = [{
        "date": _NOW.date(),
        "sleep_duration_minutes": 420,
        "deep_sleep_minutes": 16,
        "light_sleep_minutes": 200,
        "rem_sleep_minutes": 91,
    }]
    out = _section_health_connect(records, _NOW)
    assert "Deep+Light: 3h 36m" in out   # 16 + 200 = 216m = 3h 36m
    assert "REM: 1h 31m" in out          # 91m REM retained, matches Samsung app
    assert ", Light:" not in out         # no standalone light term (was ", Light: ...")
    assert "Deep: " not in out           # no standalone deep term (combined is "Deep+Light:")
