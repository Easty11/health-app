"""`POST /load/refresh` — on-demand per-user load refresh (#297).

Proves the Step-1 gates on the FK-enforced SQLite substrate (conftest `db_session`), calling the
route function directly with `current_user=`/`db=` (the `test_series_load` pattern — auth and
query wiring are FastAPI's, not the logic under test):

  * SYNC-ROUTE REUSE + SCOPING — a real run drives the full #296 chain for the CALLER ONLY: the
    caller gets non-zero metrics, a second seeded user is never touched.
  * NULL computed_at (a never-computed user) — runs.
  * GATE — a call inside the 15-min window returns `skipped`; a call outside it runs; `force=true`
    runs regardless.

The route is `def` (not `async`), so FastAPI runs it in the threadpool where the orchestrator's
`asyncio.run` is legal; these direct calls run in the test's own (loopless) thread, same as prod.
"""
from datetime import datetime, timedelta, timezone

import pytest

import hevy_workouts
import models
from load_metrics import METRICS_VERSION
from routers import load as load_router
from routers.load import LOAD_REFRESH_STALE_AFTER, refresh_current_user_load


# ── seeding (mirrors test_refresh_load) ──────────────────────────────────────────

def _user(db, uid):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()
    return db.get(models.User, uid)


def _hevy_key(db, uid, key="test-key"):
    from encryption import encrypt
    db.add(models.UserIntegration(
        user_id=uid, provider="hevy", api_key_encrypted=encrypt(key)))
    db.commit()


def _resistance_workout(db, hevy_id, uid, start_iso="2026-09-13T10:00:00Z"):
    dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    db.add(models.HevyWorkout(
        hevy_id=hevy_id, user_id=uid, start_time=dt, title="W",
        raw={"id": hevy_id, "exercises": [
            {"exercise_template_id": "BENCH",
             "sets": [{"type": "normal", "weight_kg": 100.0, "reps": 5, "rpe": 8.0}]}]},
    ))
    db.commit()


def _metric(db, *, user_id, computed_at, day=None, window="mechanical"):
    """A single load_metrics row with an explicit computed_at — the freshness marker the gate
    reads. Field values are immaterial to the gate."""
    day = day or datetime.now(timezone.utc).date()
    db.add(models.LoadMetric(
        user_id=user_id, day=day, load_window=window,
        daily_load=1.0, fitness=1.0, fatigue=1.0, form=0.0,
        acute_load=1.0, chronic_load=1.0, load_ratio=1.0,
        unit="kg_reps", maturity="ok",
        formula_version="tier0-v1", metrics_version=METRICS_VERSION,
        computed_at=computed_at,
    ))
    db.commit()


def _mock_hevy_noop(monkeypatch):
    async def _fake_sync(db, *, only_user_id=None, days=hevy_workouts.DEFAULT_BACKFILL_DAYS):
        return {"users": 1, "per_user": {only_user_id: {"workouts_upserted": 0, "note": "mocked"}}}
    monkeypatch.setattr(hevy_workouts, "sync_workouts", _fake_sync)


# ── SYNC-ROUTE REUSE + SCOPING (gate a) ──────────────────────────────────────────

def test_real_run_drives_full_chain_for_caller_only(db_session, monkeypatch):
    caller = _user(db_session, 1)
    _hevy_key(db_session, 1)
    _resistance_workout(db_session, "w1", 1)
    # a second keyed user with their own workout — must be left untouched
    _user(db_session, 2)
    _hevy_key(db_session, 2)
    _resistance_workout(db_session, "w2", 2)
    _mock_hevy_noop(monkeypatch)

    summary = refresh_current_user_load(force=False, current_user=caller, db=db_session)

    # returned the orchestrator summary (a real run), scoped to the one caller
    assert summary["users_attempted"] == 1
    assert summary["users_succeeded"] == 1
    assert list(summary["per_user"]) == [1]

    # caller got metrics; the other user was never touched
    assert db_session.query(models.LoadMetric).filter_by(user_id=1).count() > 0
    assert db_session.query(models.LoadMetric).filter_by(user_id=2).count() == 0


# ── NULL computed_at → runs (gate c) ──────────────────────────────────────────────

def test_never_computed_user_runs(db_session, monkeypatch):
    caller = _user(db_session, 1)
    _hevy_key(db_session, 1)
    _resistance_workout(db_session, "w1", 1)
    _mock_hevy_noop(monkeypatch)

    assert load_router._latest_computed_at(db_session, 1) is None  # precondition: NULL marker

    summary = refresh_current_user_load(force=False, current_user=caller, db=db_session)
    assert "skipped" not in summary
    assert summary["users_attempted"] == 1
    assert db_session.query(models.LoadMetric).filter_by(user_id=1).count() > 0


# ── GATE: fresh skips, stale runs, force overrides (gate b) ───────────────────────

def _spy_run(monkeypatch):
    """Replace the orchestrator with a sentinel so the gate decision is observable without
    running the real chain. Returns the calls list."""
    calls: list[dict] = []

    def _sentinel(db, *, only_user_id=None, days=None):
        calls.append({"only_user_id": only_user_id, "days": days})
        return {"ran": True, "users_attempted": 1}

    monkeypatch.setattr(load_router, "run_refresh_load", _sentinel)
    return calls


def test_fresh_within_window_skips(db_session, monkeypatch):
    caller = _user(db_session, 1)
    _metric(db_session, user_id=1, computed_at=datetime.now(timezone.utc) - timedelta(minutes=5))
    calls = _spy_run(monkeypatch)

    out = refresh_current_user_load(force=False, current_user=caller, db=db_session)

    assert out["skipped"] is True
    assert out["reason"] == "fresh"
    assert "last_computed_at" in out
    assert calls == []  # orchestrator never invoked


def test_stale_beyond_window_runs(db_session, monkeypatch):
    caller = _user(db_session, 1)
    stale = datetime.now(timezone.utc) - (LOAD_REFRESH_STALE_AFTER + timedelta(minutes=5))
    _metric(db_session, user_id=1, computed_at=stale)
    calls = _spy_run(monkeypatch)

    out = refresh_current_user_load(force=False, current_user=caller, db=db_session)

    assert out.get("ran") is True
    assert calls == [{"only_user_id": 1, "days": load_router.ON_DEMAND_BACKFILL_DAYS}]


def test_force_bypasses_the_gate_when_fresh(db_session, monkeypatch):
    caller = _user(db_session, 1)
    _metric(db_session, user_id=1, computed_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    calls = _spy_run(monkeypatch)

    out = refresh_current_user_load(force=True, current_user=caller, db=db_session)

    assert out.get("ran") is True  # ran despite being fresh
    assert calls == [{"only_user_id": 1, "days": load_router.ON_DEMAND_BACKFILL_DAYS}]


def test_naive_computed_at_is_read_as_utc(db_session):
    """SQLite round-trips TIMESTAMPTZ as naive; the gate must treat it as UTC, not crash on a
    naive/aware subtraction."""
    _user(db_session, 1)
    _metric(db_session, user_id=1, computed_at=datetime.utcnow())  # naive, ~now
    latest = load_router._latest_computed_at(db_session, 1)
    assert latest is not None and latest.tzinfo is not None
