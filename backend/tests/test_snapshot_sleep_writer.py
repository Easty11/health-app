"""Readiness snapshot sleep: ONE writer per night by fixed priority, named on every value,
never blended; and "HRV data continuity" counts every source that feeds HRV.

Operator ruling 2026-10-09: Garmin (com.garmin.android.apps.connectmobile) > Samsung Health
relay (com.sec.android.app.shealth) > Samsung scraper (samsung_hrv_readings). Synthetic nights
only — the values below are invented, not anyone's data.

The snapshot tool body is exercised end to end against the in-memory SQLite `db_session`
(same wiring as test_typed_entries_render): `SessionLocal` is pointed at it and the raw-SQL
helper for the non-sleep sections is stubbed, so only the code under test reads real rows.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import mcp_server
import models
from reads import snapshot_reads as sr

GARMIN = "com.garmin.android.apps.connectmobile"
SHEALTH = "com.sec.android.app.shealth"
TODAY = date(2026, 10, 9)


@pytest.fixture
def user(db_session, monkeypatch):
    u = models.User(email="snap@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: u.id)
    monkeypatch.setattr(mcp_server, "_db_rows", lambda sql, params: [])
    monkeypatch.setattr(mcp_server, "_aest_wake_day", lambda *a, **k: TODAY)
    return u


def _hc(db, u, night, *, duration=377, deep=55, rem=90, light=232):
    db.add(models.HealthConnectSync(
        user_id=u.id, date=night, sleep_duration_minutes=duration,
        deep_sleep_minutes=deep, rem_sleep_minutes=rem, light_sleep_minutes=light, sleep_score=6))


def _writer(db, u, night, pkg):
    """A sleep record by `pkg`, started the evening before the wake-date (the join window)."""
    db.add(models.HealthConnectRecordSource(
        user_id=u.id, record_type="sleep", source_package=pkg,
        record_start=f"{(night - timedelta(days=1)).isoformat()}T22:{10 + len(pkg) % 40}:00+10:00"))


def _scraper(db, u, night, **kw):
    base = dict(user_id=u.id, captured_at=night, context="passive_overnight", hrv_ms=70.0,
                total_sleep_time_minutes=399, deep_minutes=60, rem_minutes=95, light_minutes=240,
                sleep_efficiency_pct=94, respiratory_rate=13.3, sleep_hr_bpm=49, spo2_average_pct=94.0)
    base.update(kw)
    db.add(models.SamsungHRVReading(**base))


def _garmin_hrv(db, u, night, ms=60.0):
    db.add(models.HrvReading(user_id=u.id, captured_at=night, source="garmin", rmssd_ms=ms))


def _snapshot() -> str:
    return mcp_server.get_readiness_snapshot()


# ── the writer is named on the value ─────────────────────────────────────────────────

def test_garmin_night_is_labelled_garmin_and_beats_a_stale_scraper_night(db_session, user):
    _scraper(db_session, user, date(2026, 9, 14))            # frozen scraper
    _hc(db_session, user, TODAY)
    _writer(db_session, user, TODAY, GARMIN)
    db_session.commit()

    out = _snapshot()
    assert "Sleep 6 h 17 m · Garmin (night of 2026-10-09)" in out
    assert "Deep: 55 min  REM: 90 min · Garmin" in out
    # Nothing from the stale scraper night leaks in under the Garmin header.
    assert "Sleep efficiency" not in out and "SpO2" not in out and "2026-09-14" not in out


def test_samsung_health_relay_night_is_named_samsung_health_not_the_scraper(db_session, user):
    _hc(db_session, user, TODAY)
    _writer(db_session, user, TODAY, SHEALTH)
    db_session.commit()
    assert "· Samsung Health (night of 2026-10-09)" in _snapshot()


def test_scraper_night_is_named_samsung_scraper_and_keeps_its_own_vitals(db_session, user):
    _scraper(db_session, user, TODAY)
    db_session.commit()
    out = _snapshot()
    assert "Sleep 6 h 39 m · Samsung scraper (night of 2026-10-09)" in out
    assert "Sleep efficiency: 94% · Samsung scraper" in out


def test_same_night_tie_goes_to_health_connect_over_the_scraper(db_session, user):
    _scraper(db_session, user, TODAY)
    _hc(db_session, user, TODAY)
    _writer(db_session, user, TODAY, GARMIN)
    db_session.commit()
    out = _snapshot()
    assert "Sleep 6 h 17 m · Garmin" in out and "Samsung scraper" not in out


# ── never blended ────────────────────────────────────────────────────────────────────

def test_a_two_writer_night_withholds_stages_and_names_both_writers(db_session, user):
    _hc(db_session, user, TODAY)
    _writer(db_session, user, TODAY, GARMIN)
    _writer(db_session, user, TODAY, SHEALTH)
    db_session.commit()

    out = _snapshot()
    assert "Health Connect (multiple)" in out
    assert "Sleep stages: withheld — the night spans Garmin + Samsung Health" in out
    assert "Deep:" not in out and "REM:" not in out        # no mixed split under one name


def test_unknown_identity_night_is_generic_health_connect_not_a_guessed_brand(db_session, user):
    _hc(db_session, user, TODAY)
    _writer(db_session, user, TODAY, "unknown")
    db_session.commit()
    assert "· Health Connect (night of 2026-10-09)" in _snapshot()


def test_no_sleep_anywhere_says_so_instead_of_inventing_a_night(db_session, user):
    db_session.commit()
    assert "Latest biometrics: no sleep or HRV data found." in _snapshot()


def test_the_shared_read_returns_writers_and_blended_for_the_card_too(db_session, user):
    _hc(db_session, user, TODAY)
    _writer(db_session, user, TODAY, GARMIN)
    db_session.commit()
    night = sr.latest_sleep_night(db_session, user.id)
    assert (night["source"], night["writers"], night["blended"]) == ("garmin", ["Garmin"], False)


@pytest.mark.parametrize("minutes,text", [(377, "6 h 17 m"), (360, "6 h 00 m"), (45, "45 m"), (480.4, "8 h 00 m")])
def test_duration_reads_in_hours_and_minutes(minutes, text):
    assert sr.format_duration(minutes) == text


# ── HRV continuity counts the source that feeds HRV ──────────────────────────────────

def test_continuity_counts_garmin_nights_not_just_the_scraper(db_session, user):
    for back in (0, 1, 2, 4, 5):                              # 5 Garmin nights of the last 7
        _garmin_hrv(db_session, user, TODAY - timedelta(days=back))
    db_session.commit()
    c = sr.hrv_continuity(db_session, user.id, TODAY)
    assert (c["nights"], c["by_source"]) == (5, {"garmin": 5})
    assert "HRV data continuity: 5/7 nights in the last week (garmin 5)" in _snapshot()


def test_continuity_counts_a_night_two_sources_measured_once(db_session, user):
    _garmin_hrv(db_session, user, TODAY)
    _scraper(db_session, user, TODAY)
    _scraper(db_session, user, TODAY - timedelta(days=1))
    db_session.commit()
    c = sr.hrv_continuity(db_session, user.id, TODAY)
    assert c["nights"] == 2 and c["by_source"] == {"garmin": 1, "samsung": 2}


def test_continuity_window_is_seven_wake_days_inclusive(db_session, user):
    _garmin_hrv(db_session, user, TODAY - timedelta(days=6))   # in
    _garmin_hrv(db_session, user, TODAY - timedelta(days=7))   # out
    db_session.commit()
    assert sr.hrv_continuity(db_session, user.id, TODAY)["nights"] == 1


# ── the freshness block rides the snapshot ───────────────────────────────────────────

def test_snapshot_carries_the_freshness_block(db_session, user):
    from datetime import datetime, timezone
    db_session.add(models.HealthConnectSyncEvent(
        user_id=user.id, synced_at=datetime.now(timezone.utc) - timedelta(hours=14)))
    db_session.commit()
    out = _snapshot()
    assert "Data freshness:" in out
    assert "Health Connect last delivery: 14 h ago — AMBER, older than 13 h" in out
