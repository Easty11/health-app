"""Freshness read model: per (stream, writer) staleness and the per-pipe last delivery.

Synthetic data only. `now` is injected, so nothing here depends on the wall clock. The synthetic
dataset has three writers: one STALE (a writer that stopped delivering), one FRESH, and one SPARSE
(irregular by nature, information only, never an alarm).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from reads import freshness_reads as fr
from routers import freshness as freshness_router

GARMIN = "com.garmin.android.apps.connectmobile"
SHEALTH = "com.sec.android.app.shealth"
NOW = datetime(2026, 10, 9, 23, 0, tzinfo=timezone.utc)      # 10 Oct 09:00 AEST


@pytest.fixture
def user(db_session):
    u = models.User(email="fresh@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    return u


def _record(db, u, rtype, pkg, when: datetime | str):
    text = when if isinstance(when, str) else when.isoformat()
    db.add(models.HealthConnectRecordSource(
        user_id=u.id, record_type=rtype, source_package=pkg, record_start=text))


def _daily(db, u, rtype, pkg, last_days_ago: int, n: int = 20):
    """`n` consecutive daily records ending `last_days_ago` days before NOW."""
    for i in range(n):
        _record(db, u, rtype, pkg, NOW - timedelta(days=last_days_ago + i, hours=11))


def _event(db, u, hours_ago: float):
    db.add(models.HealthConnectSyncEvent(user_id=u.id, synced_at=NOW - timedelta(hours=hours_ago)))


def _by(f, stream, writer):
    return next(s for s in f["streams"] if s["stream"] == stream and s["writer"] == writer)


# ── the synthetic dataset: one stale, one fresh, one sparse ──────────────────────────

def _dataset(db, u):
    _daily(db, u, "sleep", GARMIN, last_days_ago=0)           # fresh: a night every day to today
    _daily(db, u, "sleep", SHEALTH, last_days_ago=11)         # stale: daily until 11 days ago
    for days_ago in (3, 9, 16, 23):                           # sparse: a workout every few days
        _record(db, u, "exercise", GARMIN, NOW - timedelta(days=days_ago))
    db.commit()


def test_one_stale_one_fresh_one_sparse(db_session, user):
    _dataset(db_session, user)
    f = fr.freshness(db_session, user.id, now=NOW)

    fresh = _by(f, "sleep", "Garmin")
    assert fresh["status"] == "fresh" and fresh["usual_gap_days"] == 1.0 and fresh["age_hours"] < 24

    stale = _by(f, "sleep", "Samsung Health")
    assert stale["status"] == "stale" and stale["usual_gap_days"] == 1.0
    assert 11 * 24 - 24 < stale["age_hours"] < 11 * 24 + 24

    sparse = _by(f, "exercise", "Garmin")
    assert sparse["status"] == "info"                         # reported, never an alarm
    assert sparse["age_hours"] > 2 * 24


def test_a_sparse_stream_is_never_stale_however_old(db_session, user):
    for days_ago in (50, 55, 60, 65):
        _record(db_session, user, "exercise", GARMIN, NOW - timedelta(days=days_ago))
    _record(db_session, user, "exercise", GARMIN, NOW - timedelta(days=45))
    db_session.commit()
    s = _by(fr.freshness(db_session, user.id, now=NOW), "exercise", "Garmin")
    assert s["status"] == "info"
    assert "exercise · Garmin" not in "\n".join(l for l in fr.freshness_snapshot_lines(
        fr.freshness(db_session, user.id, now=NOW)) if "STALE" in l)


def test_stale_threshold_is_three_times_the_usual_gap(db_session, user):
    # A writer that delivers every 2 days has a 2-day gap: stale only after 6 days.
    for i in range(10):
        _record(db_session, user, "hrv", GARMIN, NOW - timedelta(days=5 + 2 * i))
    db_session.commit()
    assert _by(fr.freshness(db_session, user.id, now=NOW), "hrv", "Garmin")["status"] == "fresh"
    assert fr.freshness(db_session, user.id, now=NOW)["streams"][0]["usual_gap_days"] == 2.0
    later = NOW + timedelta(days=2)                           # newest is now 7 days old (> 6)
    assert _by(fr.freshness(db_session, user.id, now=later), "hrv", "Garmin")["status"] == "stale"


def test_too_little_history_is_not_a_stale_alarm(db_session, user):
    for i in range(3):                                        # 3 record-days < MIN_RECORD_DAYS
        _record(db_session, user, "sleep", GARMIN, NOW - timedelta(days=20 + i))
    db_session.commit()
    s = _by(fr.freshness(db_session, user.id, now=NOW), "sleep", "Garmin")
    assert s["status"] == "insufficient_history" and s["usual_gap_days"] is None


def test_a_dense_stream_is_judged_at_day_grain_not_per_record(db_session, user):
    # Heart-rate-like: a record every few minutes today. Its newest record is 5 h old, which
    # would be "stale" against a minutes-long median gap. At day grain it is fresh.
    for day in range(10):
        for minute in range(0, 60, 5):
            _record(db_session, user, "heart_rate", GARMIN,
                    NOW - timedelta(days=day, hours=5) - timedelta(minutes=minute))
    db_session.commit()
    s = _by(fr.freshness(db_session, user.id, now=NOW), "heart_rate", "Garmin")
    assert s["status"] == "fresh" and s["usual_gap_days"] == 1.0


def test_date_only_record_covers_its_whole_day(db_session, user):
    # Steps are keyed by date. Today's steps must not read as 23 h old late in the day.
    for i in range(10):
        _record(db_session, user, "steps", GARMIN, (date(2026, 10, 10) - timedelta(days=i)).isoformat())
    db_session.commit()
    s = _by(fr.freshness(db_session, user.id, now=NOW), "steps", "Garmin")
    assert s["age_hours"] == 0.0 and s["status"] == "fresh"


def test_unparseable_record_times_are_skipped_not_fatal(db_session, user):
    _record(db_session, user, "sleep", GARMIN, "not a timestamp")
    _daily(db_session, user, "sleep", GARMIN, last_days_ago=0, n=6)
    db_session.commit()
    assert _by(fr.freshness(db_session, user.id, now=NOW), "sleep", "Garmin")["status"] == "fresh"


def test_a_long_retired_writer_is_not_listed(db_session, user):
    _daily(db_session, user, "sleep", "com.withings.wiscale2", last_days_ago=90, n=6)
    db_session.commit()
    assert fr.freshness(db_session, user.id, now=NOW)["streams"] == []


def test_samsung_scraper_silence_is_visible(db_session, user):
    for i in range(10):
        db_session.add(models.SamsungHRVReading(
            user_id=user.id, captured_at=date(2026, 9, 14) - timedelta(days=i),
            context="passive_overnight", hrv_ms=70.0))
    db_session.commit()
    s = _by(fr.freshness(db_session, user.id, now=NOW), "sleep+hrv", "Samsung scraper")
    assert s["status"] == "stale"


# ── pipes: the last delivery of each route ───────────────────────────────────────────

def test_hc_delivery_older_than_13h_is_amber(db_session, user):
    _event(db_session, user, 14)
    _event(db_session, user, 40)
    db_session.commit()
    f = fr.freshness(db_session, user.id, now=NOW)
    hc = f["pipes"]["health_connect"]
    assert hc["status"] == "amber" and hc["age_hours"] == 14.0
    assert f["load_inputs_stale"] is True and f["load_stale_pipes"] == ["health_connect"]


def test_hc_delivery_within_13h_is_fresh(db_session, user):
    _event(db_session, user, 12.9)
    db_session.commit()
    f = fr.freshness(db_session, user.id, now=NOW)
    assert f["pipes"]["health_connect"]["status"] == "fresh" and f["load_inputs_stale"] is False


def test_the_newest_event_decides_not_the_first(db_session, user):
    _event(db_session, user, 50)
    _event(db_session, user, 2)
    db_session.commit()
    assert fr.freshness(db_session, user.id, now=NOW)["pipes"]["health_connect"]["age_hours"] == 2.0


def test_no_deliveries_is_never_not_amber(db_session, user):
    f = fr.freshness(db_session, user.id, now=NOW)
    assert f["pipes"]["health_connect"]["status"] == "never"
    assert f["load_inputs_stale"] is False and f["data_as_of"] is None


def test_polar_is_information_only_however_old(db_session, user):
    db_session.add(models.AerobicSession(
        user_id=user.id, source="polar_v4", source_session_id="p1",
        session_date=date(2026, 9, 1), start_time=NOW - timedelta(days=38)))
    db_session.commit()
    f = fr.freshness(db_session, user.id, now=NOW)
    assert f["pipes"]["polar"]["status"] == "info" and f["pipes"]["polar"]["age_hours"] == 38 * 24.0
    assert f["load_inputs_stale"] is False


def test_data_as_of_is_the_last_hc_delivery_not_the_newest_arrival(db_session, user):
    """Ruling 2026-10-10: Polar fresh + HC 14 h old -> "as of" shows the HC age and the card is
    amber. A max() across pipes would let a fresh Polar session mask a stale HC (the 9 Oct failure)."""
    _event(db_session, user, 14)
    db_session.add(models.AerobicSession(
        user_id=user.id, source="polar_v4", source_session_id="p2",
        session_date=date(2026, 10, 9), start_time=NOW - timedelta(hours=1)))
    db_session.commit()
    f = fr.freshness(db_session, user.id, now=NOW)
    assert f["pipes"]["polar"]["age_hours"] == 1.0                      # Polar is fresh ...
    assert f["data_as_of"]["age_hours"] == 14.0                         # ... and does not move "as of"
    assert f["data_as_of"]["newest_at"] == f["pipes"]["health_connect"]["newest_at"]
    assert f["load_inputs_stale"] is True and f["load_stale_pipes"] == ["health_connect"]


def test_data_as_of_and_the_amber_gate_share_one_clock(db_session, user):
    for hours in (2, 12.9, 13.1, 30):
        db_session.query(models.HealthConnectSyncEvent).delete()
        _event(db_session, user, hours)
        db_session.commit()
        f = fr.freshness(db_session, user.id, now=NOW)
        assert f["data_as_of"]["age_hours"] == f["pipes"]["health_connect"]["age_hours"]
        assert f["load_inputs_stale"] is (hours > 13)


def test_old_polar_does_not_make_a_fresh_hc_amber(db_session, user):
    """The other direction: Polar is training-only and legitimately sparse, so a long-quiet Polar
    never drives amber and never moves "as of"."""
    _event(db_session, user, 3)
    db_session.add(models.AerobicSession(
        user_id=user.id, source="polar_v4", source_session_id="p3",
        session_date=date(2026, 9, 1), start_time=NOW - timedelta(days=38)))
    db_session.commit()
    f = fr.freshness(db_session, user.id, now=NOW)
    assert f["data_as_of"]["age_hours"] == 3.0 and f["load_inputs_stale"] is False


def test_polar_only_delivery_leaves_data_as_of_empty(db_session, user):
    """No Health Connect delivery at all: nothing to anchor "as of" on, even with a Polar session."""
    db_session.add(models.AerobicSession(
        user_id=user.id, source="polar_v4", source_session_id="p4",
        session_date=date(2026, 10, 9), start_time=NOW - timedelta(hours=1)))
    db_session.commit()
    assert fr.freshness(db_session, user.id, now=NOW)["data_as_of"] is None


def test_garmin_hrv_pipe_reads_its_newest_night(db_session, user):
    for i in range(8):
        db_session.add(models.HrvReading(user_id=user.id, captured_at=date(2026, 10, 10) - timedelta(days=i),
                                         source="garmin", rmssd_ms=60.0))
    db_session.commit()
    p = fr.freshness(db_session, user.id, now=NOW)["pipes"]["garmin_hrv"]
    assert p["status"] == "fresh" and p["age_hours"] == 0.0


# ── the snapshot block and the endpoint ──────────────────────────────────────────────

def test_snapshot_lines_name_the_stale_stream_and_the_amber_pipe(db_session, user, monkeypatch):
    monkeypatch.setattr(fr, "RETIRED_WRITERS", frozenset())      # Samsung Health sleep is retired in prod (#478)
    _dataset(db_session, user)
    _event(db_session, user, 14)
    db_session.commit()
    text = "\n".join(fr.freshness_snapshot_lines(fr.freshness(db_session, user.id, now=NOW)))
    assert "Health Connect last delivery: 14 h ago — AMBER, older than 13 h" in text
    assert "STALE sleep · Samsung Health" in text
    assert "Irregular streams, information only: exercise · Garmin" in text
    assert "STALE sleep · Garmin" not in text


def test_ago_wording():
    assert fr._ago(None) == "never" and fr._ago(0.5) == "30 min ago"
    assert fr._ago(14) == "14 h ago" and fr._ago(72) == "3 d ago"


def test_endpoint_returns_the_read_model(db_session, user):
    _event(db_session, user, 14)
    db_session.commit()
    app = FastAPI()
    app.include_router(freshness_router.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: user
    body = TestClient(app).get("/freshness").json()
    assert set(body) >= {"streams", "pipes", "data_as_of", "load_inputs_stale", "load_stale_pipes"}
    assert body["pipes"]["health_connect"]["status"] in ("fresh", "amber")


def test_a_writer_dead_for_weeks_reads_stale_not_no_history(db_session, user):
    """Regression: the usual gap is taken from the 28 days ending at the writer's OWN last record.
    Anchored at now, a writer silent for 40 days had no record-days left in the window and read
    'insufficient_history' instead of stale — the dead-scraper case this signal exists to catch."""
    _daily(db_session, user, "sleep", SHEALTH, last_days_ago=40, n=12)
    db_session.commit()
    s = _by(fr.freshness(db_session, user.id, now=NOW), "sleep", "Samsung Health")
    assert s["status"] == "stale" and s["record_days_28d"] >= fr.MIN_RECORD_DAYS


# ── retired writers (S4, #478) ───────────────────────────────────────────────────────

def _lines(db, u):
    return fr.freshness_snapshot_lines(fr.freshness(db, u.id, now=NOW))


def test_the_retired_set_is_exactly_the_four_the_operator_ruled():
    assert fr.RETIRED_WRITERS == {("heart_rate", "Samsung Health"), ("sleep", "Samsung Health"),
                                  ("sleep+hrv", "Samsung scraper"), ("steps", "unknown writer")}


def test_a_retired_writer_drops_out_of_stale_and_rides_one_information_line(db_session, user):
    _daily(db_session, user, "heart_rate", SHEALTH, last_days_ago=48)
    _daily(db_session, user, "sleep", SHEALTH, last_days_ago=32)
    _daily(db_session, user, "steps", "unknown", last_days_ago=40)
    db_session.commit()

    f = fr.freshness(db_session, user.id, now=NOW)
    text = "\n".join(fr.freshness_snapshot_lines(f))

    assert "STALE" not in text
    assert text.count("Retired writers, information only:") == 1
    for frag in ("heart_rate · Samsung Health 48 d ago", "sleep · Samsung Health 32 d ago",
                 "steps · unknown writer 40 d ago"):
        assert frag in text
    # the read model still carries the truth: stale, flagged retired
    s = _by(f, "heart_rate", "Samsung Health")
    assert s["status"] == "stale" and s["retired"] is True and s["returned"] is False


def test_the_flag_is_keyed_on_stream_and_writer_so_live_samsung_steps_stay_tracked(db_session, user):
    _daily(db_session, user, "steps", SHEALTH, last_days_ago=12)          # Samsung Health steps gone quiet
    _daily(db_session, user, "heart_rate", "com.withings.wiscale2", last_days_ago=12)
    db_session.commit()

    text = "\n".join(_lines(db_session, user))

    assert "STALE steps · Samsung Health" in text                          # not retired: still an alarm
    assert "STALE heart_rate · Withings" in text or "STALE heart_rate · com.withings.wiscale2" in text


def test_a_retired_writer_that_writes_again_is_shown_not_hidden(db_session, user):
    _daily(db_session, user, "sleep", SHEALTH, last_days_ago=1)           # back, yesterday
    db_session.commit()

    f = fr.freshness(db_session, user.id, now=NOW)
    text = "\n".join(fr.freshness_snapshot_lines(f))

    assert _by(f, "sleep", "Samsung Health")["returned"] is True
    assert "RETURNED retired writer sleep · Samsung Health: wrote" in text
    assert "Retired writers, information only" not in text                 # it is not silent any more
    assert "STALE sleep · Samsung Health" not in text


def test_no_retired_writers_means_no_retired_line(db_session, user):
    _daily(db_session, user, "sleep", GARMIN, last_days_ago=0)
    db_session.commit()
    assert "Retired writers" not in "\n".join(_lines(db_session, user))


# ── Garmin lanes and key expiry in the block (S4) ────────────────────────────────────

def _garmin_user(db, u, *, expires_in=355, di=False):
    from encryption import encrypt
    db.add(models.UserIntegration(user_id=u.id, provider="garmin_personal", api_key_encrypted=encrypt("k"),
                                  key_expires_on=date(2026, 10, 10) + timedelta(days=expires_in)))   # Brisbane today, not the UTC date
    if di:
        db.add(models.UserIntegration(user_id=u.id, provider="garmin", api_key_encrypted=encrypt("d")))
    db.commit()


def test_healthy_garmin_lanes_and_the_key_expiry_are_always_in_the_block(db_session, user):
    import garmin_raw
    _garmin_user(db_session, user, di=True)
    db_session.add(models.Spo2Night(user_id=user.id, captured_at=date(2026, 10, 10), source="garmin", reading_count=1,
                                    gap_count=0))                      # a captured epoch night: no DI alert
    db_session.commit()
    for lane in ("personal_hrv", "personal_wellness", "personal_selfeval", "di_spo2"):
        garmin_raw.record_lane(db_session, user.id, lane, garmin_raw.OK, now=NOW - timedelta(hours=3))
    garmin_raw.record_lane(db_session, user.id, garmin_raw.LANE_WAKE_DAY, garmin_raw.OK,
                           "2026-10-10 complete via=checkin", now=NOW - timedelta(hours=1))

    lines = _lines(db_session, user)
    text = "\n".join(lines)

    assert ("  Garmin lanes: HRV ok 3 h ago · sleep/HR/SpO2 ok 3 h ago · self-eval ok 3 h ago · "
            "wake-day fetch 2026-10-10 complete via=checkin · epoch SpO2 (DI) ok 3 h ago") in lines
    assert "  Garmin Personal API key: expires in 355 days (2027-09-30)" in lines
    assert "GARMIN" not in text.replace("Garmin lanes", "").replace("Garmin Personal", "")  # no alert when healthy


def test_a_failed_lane_is_named_with_its_last_good_age_and_the_key_alert_still_prints(db_session, user):
    import garmin_raw
    _garmin_user(db_session, user, expires_in=20)
    garmin_raw.record_lane(db_session, user.id, "personal_wellness", garmin_raw.OK, now=NOW - timedelta(hours=30))
    garmin_raw.record_lane(db_session, user.id, "personal_wellness", garmin_raw.ERROR, "x", now=NOW - timedelta(hours=1))

    text = "\n".join(_lines(db_session, user))

    assert "sleep/HR/SpO2 FAILED (error), last ok 30 h ago" in text
    assert "Garmin Personal API key: expires in 20 days (2026-10-30)" in text
    assert "GARMIN AMBER: Garmin Personal API key expires in 20 days" in text


def test_a_user_with_no_garmin_gets_no_lane_lines(db_session, user):
    text = "\n".join(_lines(db_session, user))
    assert "Garmin lanes" not in text and "Garmin Personal API key" not in text


def test_the_hrv_line_names_the_night_not_a_fetch_age(db_session, user):
    db_session.add(models.HrvReading(user_id=user.id, source="garmin", captured_at=date(2026, 10, 10), rmssd_ms=60.0))
    db_session.commit()
    lines = _lines(db_session, user)
    assert "  Garmin HRV newest night: 2026-10-10" in lines
