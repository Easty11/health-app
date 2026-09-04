"""Q130 HRV consumption — source-agnostic `/recovery/summary` `hrv` block + Samsung
unification into `hrv_readings` (dual-write helper + held backfill migration SQL).

No network. The DB path runs against the in-memory SQLite `db_session` fixture; the
`/summary` path uses a TestClient with `get_db`/`get_current_user` overridden (the
`test_garmin_hrv` pattern). The Samsung dual-write is tested through the importable
`_mirror_passive_overnight_hrv` helper rather than the `/samsung-hrv/sync` endpoint,
whose Postgres `on_conflict_do_update` does not run on SQLite.

Note on the same-date collapse: the SamsungHRVReading model still declares the stale
2-column `uq_samsung_hrv_user_date`, so the create_all'd test DB cannot hold two contexts
on one (user, date). The backfill's collapse-to-passive_overnight is therefore a prod-only
property (live constraint is `uq_samsung_hrv_user_date_context`, per migration
e1f2a3b4c5d6); here we prove context exclusion across distinct dates plus insert-only /
idempotency, which is what the SQL guard controls.
"""
from __future__ import annotations

import importlib.util
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

import models
from auth import get_current_user
from database import get_db
from routers import recovery
from routers.samsung_hrv import HRVReadingIn, _mirror_passive_overnight_hrv


# ── import the exact backfill SQL the migration runs ──────────────────────────────
_MIG = (
    Path(__file__).resolve().parent.parent
    / "migrations" / "versions"
    / "c1d2e3f4a5b6_backfill_samsung_hrv_into_hrv_readings.py"
)
_spec = importlib.util.spec_from_file_location("backfill_mig", _MIG)
_backfill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_backfill)
BACKFILL_SQL = _backfill.BACKFILL_SQL


def _user(db, uid=4):
    u = models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(recovery.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


# ── Stage A: scraper dual-write helper ────────────────────────────────────────────

def test_mirror_writes_passive_overnight_into_hrv_readings(db_session):
    user = _user(db_session)
    _mirror_passive_overnight_hrv(
        db_session, user.id,
        HRVReadingIn(captured_at=date(2026, 6, 1), hrv_ms=48.0, context="passive_overnight"),
    )
    db_session.commit()

    row = db_session.query(models.HrvReading).filter_by(user_id=user.id).one()
    assert (row.source, row.captured_at, row.rmssd_ms) == ("samsung", date(2026, 6, 1), 48.0)
    assert row.status is None and row.baseline_low is None and row.baseline_high is None
    assert row.weekly_avg is None
    assert db_session.query(models.HrvSample).count() == 0   # Samsung is nightly-only


def test_mirror_skips_session_and_calibration_and_null(db_session):
    user = _user(db_session)
    for ctx in ("session", "calibration"):
        _mirror_passive_overnight_hrv(
            db_session, user.id,
            HRVReadingIn(captured_at=date(2026, 6, 2), hrv_ms=50.0, context=ctx),
        )
    # passive_overnight but hrv_ms nulled out of range by the pydantic guard → skipped
    _mirror_passive_overnight_hrv(
        db_session, user.id,
        HRVReadingIn(captured_at=date(2026, 6, 3), hrv_ms=9999.0, context="passive_overnight"),
    )
    db_session.commit()
    assert db_session.query(models.HrvReading).count() == 0


def test_mirror_rescrape_updates_without_duplicating(db_session):
    user = _user(db_session)
    _mirror_passive_overnight_hrv(
        db_session, user.id,
        HRVReadingIn(captured_at=date(2026, 6, 4), hrv_ms=50.0, context="passive_overnight"),
    )
    db_session.commit()
    _mirror_passive_overnight_hrv(
        db_session, user.id,
        HRVReadingIn(captured_at=date(2026, 6, 4), hrv_ms=55.0, context="passive_overnight"),
    )
    db_session.commit()

    rows = db_session.query(models.HrvReading).filter_by(user_id=user.id).all()
    assert len(rows) == 1 and rows[0].rmssd_ms == 55.0


# ── Stage A: held backfill migration SQL ──────────────────────────────────────────

def _seed_samsung(db, uid, cdate, hrv_ms, context="passive_overnight"):
    db.add(models.SamsungHRVReading(
        user_id=uid, captured_at=cdate, hrv_ms=hrv_ms, context=context))


def test_backfill_sql_inserts_only_passive_overnight_with_hrv(db_session):
    user = _user(db_session)
    _seed_samsung(db_session, user.id, date(2026, 5, 1), 40.0, "passive_overnight")   # → insert
    _seed_samsung(db_session, user.id, date(2026, 5, 2), 41.0, "session")             # excluded
    _seed_samsung(db_session, user.id, date(2026, 5, 3), 42.0, "calibration")         # excluded
    _seed_samsung(db_session, user.id, date(2026, 5, 4), None, "passive_overnight")   # null → excluded
    db_session.commit()

    db_session.execute(text(BACKFILL_SQL))
    db_session.commit()

    rows = db_session.query(models.HrvReading).filter_by(user_id=user.id).all()
    assert {(r.captured_at, r.source, r.rmssd_ms) for r in rows} == {
        (date(2026, 5, 1), "samsung", 40.0),
    }
    assert all(r.status is None and r.baseline_low is None for r in rows)


def test_backfill_sql_is_insert_only_and_idempotent(db_session):
    user = _user(db_session)
    # A night already present (e.g. dual-written or a Garmin night): must be untouched.
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=date(2026, 5, 1), source="samsung", rmssd_ms=99.0))
    _seed_samsung(db_session, user.id, date(2026, 5, 1), 40.0, "passive_overnight")   # NOT EXISTS → skip
    _seed_samsung(db_session, user.id, date(2026, 5, 5), 44.0, "passive_overnight")   # absent → insert
    db_session.commit()

    db_session.execute(text(BACKFILL_SQL))
    db_session.commit()

    # Pre-existing row untouched (not overwritten to 40.0), new night inserted.
    kept = db_session.query(models.HrvReading).filter_by(
        user_id=user.id, captured_at=date(2026, 5, 1), source="samsung").one()
    assert kept.rmssd_ms == 99.0
    assert db_session.query(models.HrvReading).filter_by(
        user_id=user.id, captured_at=date(2026, 5, 5)).one().rmssd_ms == 44.0

    before = db_session.query(models.HrvReading).count()
    db_session.execute(text(BACKFILL_SQL))   # second run
    db_session.commit()
    assert db_session.query(models.HrvReading).count() == before   # idempotent — inserts 0


# ── Stage B: source-agnostic /summary hrv block ───────────────────────────────────

def test_summary_hrv_block_populated_for_garmin_only_user(db_session):
    user = _user(db_session)
    cdate = date.today() - timedelta(days=1)
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=cdate, source="garmin",
        rmssd_ms=42.0, status="BALANCED", baseline_low=38.0, baseline_high=58.0))
    db_session.commit()

    body = _client(db_session, user).get("/recovery/summary").json()
    hrv = body["hrv"]
    assert hrv["latest"]["source"] == "garmin"
    assert hrv["latest"]["rmssd_ms"] == 42.0
    assert hrv["latest"]["status"] == "BALANCED"
    assert hrv["latest"]["baseline_low"] == 38.0 and hrv["latest"]["baseline_high"] == 58.0
    assert hrv["trend"] == [{"date": cdate.isoformat(), "rmssd": 42.0}]
    assert hrv["baseline_mean"] == 42.0 and hrv["baseline_n"] == 1
    # A Garmin-only user has no Samsung rows — the device block stays empty, not errored.
    assert body["samsung"]["today"] is None and body["samsung"]["baseline_n"] == 0


def test_summary_hrv_block_populated_for_samsung_user(db_session):
    user = _user(db_session)
    cdate = date.today() - timedelta(days=1)
    # Unified row (as the backfill/dual-write would write it).
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=cdate, source="samsung", rmssd_ms=50.0))
    # The device row still exists (sleep lives there) — samsung block reads it.
    db_session.add(models.SamsungHRVReading(
        user_id=user.id, captured_at=cdate, hrv_ms=50.0, context="passive_overnight"))
    db_session.commit()

    body = _client(db_session, user).get("/recovery/summary").json()
    assert body["hrv"]["latest"]["source"] == "samsung"
    assert body["hrv"]["latest"]["rmssd_ms"] == 50.0
    assert body["hrv"]["baseline_mean"] == 50.0
    # samsung block still populated independently from the device table.
    assert body["samsung"]["today"]["hrv_ms"] == 50.0


def test_summary_both_source_night_shows_canonical_source(db_session):
    user = _user(db_session)
    cdate = date.today() - timedelta(days=1)
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=cdate, source="samsung", rmssd_ms=50.0))
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=cdate, source="garmin", rmssd_ms=42.0,
        status="BALANCED"))
    db_session.commit()

    hrv = _client(db_session, user).get("/recovery/summary").json()["hrv"]
    # Garmin outranks Samsung → canonical; exactly one trend entry for the contested night.
    assert hrv["latest"]["source"] == "garmin" and hrv["latest"]["rmssd_ms"] == 42.0
    assert hrv["trend"] == [{"date": cdate.isoformat(), "rmssd": 42.0}]
    assert hrv["baseline_n"] == 1


def test_summary_device_blocks_byte_identical_to_pre_change_snapshot(db_session):
    """Adding `hrv` must not disturb the `samsung`/`health_connect` keys."""
    user = _user(db_session)
    cdate = date.today() - timedelta(days=1)
    db_session.add(models.SamsungHRVReading(
        user_id=user.id, captured_at=cdate, hrv_ms=50.0, sleep_hr_bpm=54,
        context="passive_overnight"))
    db_session.add(models.HealthConnectSync(
        user_id=user.id, date=cdate, steps=8000, resting_heart_rate=52,
        synced_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)))
    # A hrv_readings row too, to prove the hrv block is built without touching the others.
    db_session.add(models.HrvReading(
        user_id=user.id, captured_at=cdate, source="garmin", rmssd_ms=42.0))
    db_session.commit()

    body = _client(db_session, user).get("/recovery/summary").json()

    # samsung block — exactly the pre-change shape/values.
    assert body["samsung"] == {
        "today": {
            "captured_at": cdate.isoformat(),
            "hrv_ms": 50.0,
            "sleep_hr_bpm": 54,
            "respiratory_rate": None,
            "spo2_average_pct": None,
            "sleep_efficiency_pct": None,
            "sleep_duration_minutes": None,
            "deep_minutes": None,
            "rem_minutes": None,
            "light_minutes": None,
            "awake_minutes": None,
            "bedtime": None,
            "wake_time": None,
        },
        "trend": [{"date": cdate.isoformat(), "rmssd": 50.0}],
        "baseline_mean": 50.0,
        "baseline_sd": None,
        "baseline_n": 1,
    }
    # health_connect block — unchanged.
    assert body["health_connect"] == {
        # SQLite does not preserve tz on the DateTime(timezone=True) round-trip, so the
        # isoformat is naive here; on Postgres it carries +00:00. Substrate detail — the
        # point of this test is that adding `hrv` leaves this block untouched.
        "last_synced": "2026-06-01T10:00:00",
        "date": cdate.isoformat(),
        "steps": 8000,
        "resting_heart_rate": 52,
        "hrv_rmssd": None,
        "sleep_duration_minutes": None,
        "sleep_score": None,
        "total_days_synced": 1,
    }
    assert body["has_data"] is True
