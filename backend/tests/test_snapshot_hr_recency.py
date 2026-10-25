"""Context-bundle PR2: the readiness snapshot's heart-rate figures are recency-gated, and the recovery
reader surfaces the sleep nadir whatever the HRV branch.

The 7 Oct failure: a heart-rate number from an old night sat under "Resting HR" beside today's
biometrics and was read as current. Since Q243 the snapshot's "Resting HR" is the daily resting rate and
"Sleep HR" the ring's average (two figures, two lines), but neither carried an age of its own. Both are now
withheld with the reason once their night is more than 48 hours old; the sleep line, which names its night,
is untouched.

The snapshot tool body runs end to end on the in-memory SQLite `db_session` (the wiring of
test_snapshot_sleep_writer). Synthetic values only.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import mcp_server
import models
from reads import snapshot_reads as sr
from reads.recovery_night import recovery_text

TODAY = date(2026, 10, 26)
GARMIN = "com.garmin.android.apps.connectmobile"


@pytest.fixture
def user(db_session, monkeypatch):
    u = models.User(email="hr-recency@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: u.id)
    monkeypatch.setattr(mcp_server, "_db_rows", lambda sql, params: [])
    monkeypatch.setattr(mcp_server, "_aest_wake_day", lambda *a, **k: TODAY)
    return u


def _night(db, u, night, *, sleep_hr=49, resting=52):
    """A scraper night (carries the ring's sleep HR) plus the daily resting rate for the same day."""
    db.add(models.SamsungHRVReading(
        user_id=u.id, captured_at=night, context="passive_overnight", hrv_ms=70.0,
        total_sleep_time_minutes=399, deep_minutes=60, rem_minutes=95, light_minutes=240,
        sleep_hr_bpm=sleep_hr))
    if resting is not None:
        db.add(models.DailyPhysiology(user_id=u.id, date=night, source="garmin", transport="personal_api",
                                      resting_hr_bpm=resting))
    db.commit()


# ── the gate ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("age_days, gated", [(0, False), (1, False), (2, False), (3, True), (10, True)])
def test_hr_figures_are_withheld_past_48_hours_by_wake_day_age(db_session, user, age_days, gated):
    _night(db_session, user, TODAY - timedelta(days=age_days))
    out = mcp_server.get_readiness_snapshot()
    if gated:
        assert "Resting HR: — (withheld" in out and "Sleep HR: — (withheld" in out
        assert "Resting HR: 52" not in out and "Sleep HR: 49" not in out
    else:
        assert "Resting HR: 52 bpm" in out and "Sleep HR: 49 bpm" in out
        assert "withheld — the last reading" not in out


def test_a_gated_figure_prints_its_night_its_age_and_the_threshold(db_session, user):
    _night(db_session, user, date(2026, 10, 21))
    out = mcp_server.get_readiness_snapshot()
    assert ("  Resting HR: — (withheld — the last reading is from the night of 2026-10-21, "
            "5 days before 2026-10-26, over 48 h old)") in out


def test_the_gate_withholds_only_the_hr_lines_the_sleep_line_still_names_its_night(db_session, user):
    _night(db_session, user, date(2026, 10, 21))
    out = mcp_server.get_readiness_snapshot()
    assert "Sleep 6 h 39 m" in out and "(night of 2026-10-21)" in out


def test_a_missing_daily_rate_keeps_its_own_wording_when_the_night_is_old(db_session, user):
    _night(db_session, user, date(2026, 10, 21), resting=None)
    out = mcp_server.get_readiness_snapshot()
    assert "Resting HR: — (no daily resting rate)" in out
    assert "Sleep HR: — (withheld" in out


def test_without_a_today_the_formatter_does_not_gate():
    sleep = {"night": "2026-01-01", "writers": ["Samsung scraper"], "source_label": "Samsung", "blended": False,
             "duration_min": 400, "deep_min": 60, "rem_min": 90, "awake_min": None, "efficiency_pct": None,
             "spo2_pct": None, "resp_rate": None, "sleep_hr_bpm": 49, "resting_hr_bpm": 52,
             "field_sources": {}, "withheld": []}
    lines = sr.sleep_snapshot_lines(sleep)
    assert "  Resting HR: 52 bpm · Samsung scraper" in lines
    assert any(l.startswith("  Sleep HR: 49 bpm") for l in lines)
    assert sr.hr_figures_stale("2026-01-01", None) is None
    assert sr.hr_figures_stale("not-a-date", TODAY) is None


# ── get_recovery_metrics: the nadir does not depend on the HRV branch ────────

def _hc_row(db, u, day, **kw):
    db.add(models.HealthConnectSync(user_id=u.id, date=day, **kw))
    db.commit()


def test_the_sleep_nadir_prints_on_a_night_with_no_hrv_and_on_a_night_with_one(db_session, user):
    no_hrv, with_hrv = TODAY - timedelta(days=1), TODAY - timedelta(days=2)
    _hc_row(db_session, user, no_hrv, hr_nadir_bpm=48.2, hr_nadir_source_package=GARMIN)
    _hc_row(db_session, user, with_hrv, hr_nadir_bpm=51.0, hr_nadir_source_package=GARMIN)
    db_session.add(models.HrvReading(user_id=user.id, captured_at=with_hrv, source="garmin", rmssd_ms=64.0))
    db_session.commit()
    text = recovery_text(db_session, user.id, TODAY - timedelta(days=7), 7)
    line_no_hrv = next(l for l in text.splitlines() if l.startswith(no_hrv.isoformat()))
    line_hrv = next(l for l in text.splitlines() if l.startswith(with_hrv.isoformat()))
    assert "HRV=—" in line_no_hrv and "Sleep-nadir HR=48 bpm [garmin/HC]" in line_no_hrv
    assert "HRV=64 ms" in line_hrv and "Sleep-nadir HR=51 bpm [garmin/HC]" in line_hrv
