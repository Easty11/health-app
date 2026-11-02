"""`POST /integrations/garmin/refresh` — the on-read wake-day capture trigger (#299, widened).

The route is a thin wrapper over `wake_day_capture.run` (whose gates, request budget and slot states are proven
in `test_wake_day_capture.py`, against the real client at the transport layer). Proven here, calling the route
function directly with `current_user=`/`db=` (the `test_load_refresh_endpoint` pattern):

  * the route passes the right TRIGGER: no force -> the surface named by `via` (default `recovery`),
    `force=true` -> `refresh`;
  * GRACEFUL DEGRADE — any failure returns a last-good, skipped-shaped payload and NEVER raises: the endpoint
    can never error the card;
  * the sweep's window still ends on the AEST wake-day, never the UTC date.

The route is `def` (not `async`): the Garmin client is blocking network I/O, run in FastAPI's threadpool.
"""
from datetime import datetime, timedelta, timezone

import pytest

import models
import wake_day_capture
from routers import garmin as garmin_router
from routers.garmin import refresh_garmin_hrv


def _user(db, uid):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()
    return db.get(models.User, uid)


def _garmin_key(db, uid, key="garmin-token"):
    from encryption import encrypt
    db.add(models.UserIntegration(
        user_id=uid, provider="garmin", api_key_encrypted=encrypt(key)))
    db.commit()


def _spy_run(monkeypatch, *, raises=None):
    """Replace the capture so the trigger the route chose is observable without a Garmin call."""
    calls: list[dict] = []

    def _run(db, user_id, *, trigger, force=False, **_kw):
        calls.append({"user_id": user_id, "trigger": trigger, "force": force})
        if raises is not None:
            raise raises
        return {"wake_day": "2026-11-02", "outcome": "complete", "via": trigger, "requests": {}, "status": {}}

    monkeypatch.setattr(wake_day_capture, "run", _run)
    return calls


def test_an_unforced_open_defaults_to_the_recovery_trigger(db_session, monkeypatch):
    caller = _user(db_session, 1)
    calls = _spy_run(monkeypatch)
    out = refresh_garmin_hrv(force=False, via=None, current_user=caller, db=db_session)
    assert calls == [{"user_id": 1, "trigger": "recovery", "force": False}]
    assert "skipped" not in out and out["outcome"] == "complete"


def test_the_checkin_names_itself_so_the_landing_path_is_reported(db_session, monkeypatch):
    caller = _user(db_session, 1)
    calls = _spy_run(monkeypatch)
    refresh_garmin_hrv(force=False, via="checkin", current_user=caller, db=db_session)
    assert calls[0]["trigger"] == "checkin"


def test_an_unknown_via_is_treated_as_recovery_not_trusted(db_session, monkeypatch):
    caller = _user(db_session, 1)
    calls = _spy_run(monkeypatch)
    refresh_garmin_hrv(force=False, via="backstop", current_user=caller, db=db_session)
    assert calls[0]["trigger"] == "recovery"          # the backstop is the scheduler's alone


def test_force_is_the_refresh_trigger_whatever_via_says(db_session, monkeypatch):
    caller = _user(db_session, 1)
    calls = _spy_run(monkeypatch)
    refresh_garmin_hrv(force=True, via="checkin", current_user=caller, db=db_session)
    assert calls == [{"user_id": 1, "trigger": "refresh", "force": True}]


def test_any_failure_returns_last_good_never_raises(db_session, monkeypatch):
    caller = _user(db_session, 1)
    _garmin_key(db_session, 1)
    db_session.add(models.HrvReading(user_id=1, source="garmin", captured_at=datetime(2026, 9, 14).date(),
                                     rmssd_ms=78.0, created_at=datetime.now(timezone.utc) - timedelta(hours=1)))
    db_session.commit()
    _spy_run(monkeypatch, raises=RuntimeError("garmin API 503"))

    out = refresh_garmin_hrv(force=True, via=None, current_user=caller, db=db_session)   # must NOT raise

    assert out["skipped"] is True and out["reason"] == "error"
    assert out["last_ingested_at"] is not None                       # last-good preserved


def test_a_user_with_no_key_gets_a_skipped_shaped_payload_with_status(db_session):
    caller = _user(db_session, 1)
    out = refresh_garmin_hrv(force=False, via=None, current_user=caller, db=db_session)
    assert out["skipped"] is True and out["reason"] == "no_personal_key"
    assert out["status"]["connected"] is False


def test_the_wake_day_route_reads_the_status(db_session):
    from routers.garmin import wake_day_status
    caller = _user(db_session, 1)
    assert wake_day_status(current_user=caller, db=db_session)["connected"] is False


# ── WINDOW DATE (#327 follow-up): the sweep's pull ends on the AEST wake-day, never the UTC date ──

class _FrozenClock(datetime):
    """07:00 AEST on 2026-09-25 == 21:00 UTC on 2026-09-24 — the morning window where the UTC
    date is still yesterday."""
    _NOW = datetime(2026, 9, 24, 21, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls._NOW.astimezone(tz) if tz is not None else cls._NOW.replace(tzinfo=None)


def test_sweep_window_ends_on_aest_wake_day(db_session, monkeypatch):
    from datetime import date
    from scripts import garmin_sync

    monkeypatch.setattr(garmin_router, "datetime", _FrozenClock)
    seen = []
    monkeypatch.setattr(garmin_sync, "sync_hrv_for_user",
                        lambda db, uid, s, e: seen.append(e) or {"days_with_data": 0,
                                                                  "readings_upserted": 0,
                                                                  "samples_upserted": 0})
    _user(db_session, 1)
    _garmin_key(db_session, 1)

    garmin_sync.sweep_garmin_hrv(db_session)

    assert seen == [date(2026, 9, 25)]
