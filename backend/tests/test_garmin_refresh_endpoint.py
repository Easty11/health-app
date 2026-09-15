"""`POST /integrations/garmin/refresh` — on-read Garmin HRV freshness trigger (#299, resolves Q155).

Proves the Step-1 gates on the FK-enforced SQLite substrate (conftest `db_session`), calling the
route function directly with `current_user=`/`db=` (the `test_load_refresh_endpoint` pattern —
auth and query wiring are FastAPI's, not the logic under test):

  * GATE PICKER — stale ingest runs; fresh-within-30-min skips; `force=true` runs regardless;
    a never-ingested (NULL marker) user runs.
  * GRACEFUL DEGRADE — a dead token (`GarminReconnectError`) and any other sync failure return a
    last-good, skipped-shaped payload and NEVER raise: the endpoint can never error the card.

The route is `def` (not `async`): the Garmin client is blocking network I/O, run in FastAPI's
threadpool; these direct calls run in the test's own thread, same as prod.
"""
from datetime import datetime, timedelta, timezone

import pytest

import models
from connectors.garmin import GarminReconnectError
from routers import garmin as garmin_router
from routers.garmin import RECOVERY_REFRESH_STALE_AFTER, refresh_garmin_hrv


# ── seeding ───────────────────────────────────────────────────────────────────────

def _user(db, uid):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()
    return db.get(models.User, uid)


def _garmin_key(db, uid, key="garmin-token"):
    from encryption import encrypt
    db.add(models.UserIntegration(
        user_id=uid, provider="garmin", api_key_encrypted=encrypt(key)))
    db.commit()


def _garmin_reading(db, uid, *, created_at, night="2026-09-14"):
    """A Garmin HRV row whose `created_at` is the freshness marker the gate reads. `night`
    (captured_at) is immaterial to the gate — recency is measured on ingest time, not the night."""
    from datetime import date
    db.add(models.HrvReading(
        user_id=uid, source="garmin", captured_at=date.fromisoformat(night),
        rmssd_ms=78.0, created_at=created_at))
    db.commit()


def _spy_sync(monkeypatch, *, raises=None):
    """Replace the per-user sync core so the gate decision is observable without a Garmin call.
    Returns the calls list; `raises` makes it raise that exception instead of succeeding."""
    calls: list[dict] = []

    def _sentinel(db, user_id, start, end):
        calls.append({"user_id": user_id, "start": start, "end": end})
        if raises is not None:
            raise raises
        return {"from": start.isoformat(), "to": end.isoformat(),
                "days_with_data": 1, "readings_upserted": 1, "samples_upserted": 10}

    monkeypatch.setattr(garmin_router, "sync_hrv_for_user", _sentinel)
    return calls


# ── GATE PICKER ───────────────────────────────────────────────────────────────────

def test_never_ingested_user_runs(db_session, monkeypatch):
    caller = _user(db_session, 1)
    _garmin_key(db_session, 1)
    assert garmin_router._latest_garmin_ingest_at(db_session, 1) is None  # NULL marker precondition
    calls = _spy_sync(monkeypatch)

    out = refresh_garmin_hrv(force=False, current_user=caller, db=db_session)

    assert "skipped" not in out
    assert out["readings_upserted"] == 1
    assert len(calls) == 1


def test_fresh_within_window_skips(db_session, monkeypatch):
    caller = _user(db_session, 1)
    _garmin_key(db_session, 1)
    _garmin_reading(db_session, 1, created_at=datetime.now(timezone.utc) - timedelta(minutes=5))
    calls = _spy_sync(monkeypatch)

    out = refresh_garmin_hrv(force=False, current_user=caller, db=db_session)

    assert out["skipped"] is True
    assert out["reason"] == "fresh"
    assert "last_ingested_at" in out
    assert calls == []  # the sync core was never invoked


def test_stale_beyond_window_runs(db_session, monkeypatch):
    caller = _user(db_session, 1)
    _garmin_key(db_session, 1)
    stale = datetime.now(timezone.utc) - (RECOVERY_REFRESH_STALE_AFTER + timedelta(minutes=5))
    _garmin_reading(db_session, 1, created_at=stale)
    calls = _spy_sync(monkeypatch)

    out = refresh_garmin_hrv(force=False, current_user=caller, db=db_session)

    assert "skipped" not in out
    assert out["readings_upserted"] == 1
    assert len(calls) == 1


def test_force_bypasses_the_gate_when_fresh(db_session, monkeypatch):
    caller = _user(db_session, 1)
    _garmin_key(db_session, 1)
    _garmin_reading(db_session, 1, created_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    calls = _spy_sync(monkeypatch)

    out = refresh_garmin_hrv(force=True, current_user=caller, db=db_session)

    assert "skipped" not in out  # ran despite being fresh
    assert len(calls) == 1


def test_naive_created_at_is_read_as_utc(db_session):
    """SQLite round-trips TIMESTAMPTZ as naive; the marker must be made UTC-aware, not crash on a
    naive/aware subtraction."""
    _user(db_session, 1)
    _garmin_key(db_session, 1)
    _garmin_reading(db_session, 1, created_at=datetime.utcnow())  # naive, ~now
    latest = garmin_router._latest_garmin_ingest_at(db_session, 1)
    assert latest is not None and latest.tzinfo is not None


# ── GRACEFUL DEGRADE (never errors the card) ─────────────────────────────────────

def test_dead_token_returns_last_good_never_raises(db_session, monkeypatch):
    caller = _user(db_session, 1)
    _garmin_key(db_session, 1)
    stale = datetime.now(timezone.utc) - (RECOVERY_REFRESH_STALE_AFTER + timedelta(minutes=5))
    _garmin_reading(db_session, 1, created_at=stale)
    _spy_sync(monkeypatch, raises=GarminReconnectError("token expired"))

    out = refresh_garmin_hrv(force=False, current_user=caller, db=db_session)  # must NOT raise

    assert out["skipped"] is True
    assert out["reason"] == "reconnect_required"
    assert out["last_ingested_at"] == stale.isoformat()  # last-good preserved


def test_generic_sync_failure_returns_last_good_never_raises(db_session, monkeypatch):
    caller = _user(db_session, 1)
    _garmin_key(db_session, 1)
    _spy_sync(monkeypatch, raises=RuntimeError("garmin API 503"))

    out = refresh_garmin_hrv(force=True, current_user=caller, db=db_session)  # must NOT raise

    assert out["skipped"] is True
    assert out["reason"] == "error"
    assert out["last_ingested_at"] is None  # never ingested -> null marker, still no raise
