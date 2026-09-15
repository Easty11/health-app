"""Nightly in-process all-users load sweep (`load_sweep.py`, #297).

Proves the Step-2 gates:

  * NEXT-FIRE — 02:00 Australia/Brisbane resolves to the correct UTC instant, including across
    the local/UTC day boundary, and is always strictly in the future.
  * STARTUP RUN-IF-STALE — `all_users_stale` is True when a keyed user is stale or never computed,
    False when everyone is fresh (and False with no keyed users).
  * OFF-THE-LOOP — the sweep runs via `asyncio.to_thread`, so the orchestrator's `asyncio.run`
    (which raises inside a running loop) does not collide.
  * CANCELLATION — `sweep_loop` runs the startup sweep once, then cancels cleanly on shutdown.
  * SEEDED SWEEP — a real in-memory sweep returns and reports the aggregate summary.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytz

import hevy_workouts
import load_sweep
import models
from load_metrics import METRICS_VERSION

_BRISBANE = pytz.timezone("Australia/Brisbane")
UTC = timezone.utc


# ── seeding ───────────────────────────────────────────────────────────────────────

def _user(db, uid):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


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


def _metric(db, *, user_id, computed_at):
    db.add(models.LoadMetric(
        user_id=user_id, day=computed_at.date(), load_window="mechanical",
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


# ── NEXT-FIRE ─────────────────────────────────────────────────────────────────────

def test_next_fire_is_0200_brisbane_before_local_0200():
    # 2026-09-15T10:00Z == 20:00 Brisbane; next 02:00 Brisbane is the following morning =
    # 2026-09-15T16:00Z (a DIFFERENT UTC calendar day from the 02:00 local target).
    now = datetime(2026, 9, 15, 10, 0, tzinfo=UTC)
    fire = load_sweep.next_sweep_fire_utc(now)
    assert fire == datetime(2026, 9, 15, 16, 0, tzinfo=UTC)
    local = fire.astimezone(_BRISBANE)
    assert (local.hour, local.minute) == (2, 0)
    assert local.date() == datetime(2026, 9, 16).date()  # crossed the local day boundary


def test_next_fire_after_local_0200_is_next_day():
    # 2026-09-15T17:00Z == 2026-09-16T03:00 Brisbane (past 02:00) -> fire the day after.
    now = datetime(2026, 9, 15, 17, 0, tzinfo=UTC)
    fire = load_sweep.next_sweep_fire_utc(now)
    assert fire == datetime(2026, 9, 16, 16, 0, tzinfo=UTC)
    assert fire.astimezone(_BRISBANE).date() == datetime(2026, 9, 17).date()


def test_next_fire_at_exact_boundary_is_strictly_future():
    now = datetime(2026, 9, 15, 16, 0, tzinfo=UTC)  # exactly 02:00 Brisbane on the 16th
    fire = load_sweep.next_sweep_fire_utc(now)
    assert fire > now
    assert fire == datetime(2026, 9, 16, 16, 0, tzinfo=UTC)


# ── STARTUP RUN-IF-STALE ──────────────────────────────────────────────────────────

def test_all_users_stale_true_when_a_user_is_old(db_session):
    _user(db_session, 1)
    _hevy_key(db_session, 1)
    _metric(db_session, user_id=1, computed_at=datetime.now(UTC) - timedelta(hours=48))
    assert load_sweep.all_users_stale(db_session) is True


def test_all_users_stale_true_when_a_keyed_user_never_computed(db_session):
    _user(db_session, 1)
    _hevy_key(db_session, 1)  # keyed, but no load_metrics row at all
    assert load_sweep.all_users_stale(db_session) is True


def test_all_users_stale_false_when_all_fresh(db_session):
    _user(db_session, 1)
    _hevy_key(db_session, 1)
    _metric(db_session, user_id=1, computed_at=datetime.now(UTC) - timedelta(hours=1))
    assert load_sweep.all_users_stale(db_session) is False


def test_all_users_stale_false_with_no_keyed_users(db_session):
    _user(db_session, 1)  # no Hevy key -> not in scope -> nothing to sweep
    assert load_sweep.all_users_stale(db_session) is False


# ── OFF-THE-LOOP (the asyncio.run constraint) ─────────────────────────────────────

def test_asyncio_run_collides_on_loop_but_not_off_thread():
    """The exact reason the sweep is threaded: `asyncio.run` raises inside a running loop, and
    `asyncio.to_thread` is what makes it legal."""
    async def _noop():
        return "ok"

    def _calls_asyncio_run():          # emulates run_user_chain's asyncio.run(sync_workouts(...))
        return asyncio.run(_noop())

    async def _on_loop():
        coro = _noop()
        with pytest.raises(RuntimeError):
            asyncio.run(coro)          # direct on the running loop -> RuntimeError
        coro.close()                   # the leaked coroutine was never awaited; close it cleanly
        return await asyncio.to_thread(_calls_asyncio_run)  # off the loop -> fine

    assert asyncio.run(_on_loop()) == "ok"


def test_sweep_runs_off_thread_from_a_running_loop(db_session, monkeypatch):
    """`_sweep` (which internally drives `asyncio.run`) succeeds when reached via `to_thread`
    from inside a running loop — the prod path."""
    async def _fake_hevy():
        return {"ok": True}

    def _fake_refresh(db, *, only_user_id=None, days=None):
        asyncio.run(_fake_hevy())  # the collision-prone call, now legal in the worker thread
        return {"users_attempted": 1, "users_succeeded": 1, "users_failed": 0, "days": days}

    monkeypatch.setattr(load_sweep, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(load_sweep, "refresh_load", _fake_refresh)

    async def _drive():
        return await asyncio.to_thread(load_sweep._sweep)

    summary = asyncio.run(_drive())
    assert summary["users_succeeded"] == 1


# ── CANCELLATION ──────────────────────────────────────────────────────────────────

def test_sweep_loop_runs_startup_then_cancels_clean(monkeypatch):
    ran = {"count": 0}
    monkeypatch.setattr(load_sweep, "_startup_is_stale", lambda: True)
    monkeypatch.setattr(load_sweep, "_sweep",
                        lambda: (ran.__setitem__("count", ran["count"] + 1),
                                 {"users_attempted": 0})[1])
    # Push the first scheduled fire far out so the loop parks in asyncio.sleep after the
    # startup run, giving the test a stable point to cancel at.
    monkeypatch.setattr(load_sweep, "next_sweep_fire_utc",
                        lambda now: now + timedelta(days=3650))

    async def _run():
        task = asyncio.create_task(load_sweep.sweep_loop())
        # The startup sweep runs via asyncio.to_thread, so give the executor real time (not just
        # loop yields) to complete before the loop parks in its far-future sleep.
        for _ in range(100):
            await asyncio.sleep(0.01)
            if ran["count"] >= 1:
                break
        assert ran["count"] == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()

    asyncio.run(_run())


def test_sweep_loop_skips_startup_when_fresh(monkeypatch):
    ran = {"count": 0}
    monkeypatch.setattr(load_sweep, "_startup_is_stale", lambda: False)
    monkeypatch.setattr(load_sweep, "_sweep",
                        lambda: (ran.__setitem__("count", ran["count"] + 1), {})[1])
    monkeypatch.setattr(load_sweep, "next_sweep_fire_utc",
                        lambda now: now + timedelta(days=3650))

    async def _run():
        task = asyncio.create_task(load_sweep.sweep_loop())
        # Give the (threaded) startup freshness check real time to run and decide to skip.
        for _ in range(20):
            await asyncio.sleep(0.01)
        assert ran["count"] == 0  # fresh -> no startup sweep
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())


# ── SEEDED SWEEP (report the summary) ─────────────────────────────────────────────

def test_seeded_in_memory_sweep_reports_summary(db_session, monkeypatch, capsys):
    _user(db_session, 1)
    _hevy_key(db_session, 1)
    _resistance_workout(db_session, "w1", 1)
    _mock_hevy_noop(monkeypatch)
    monkeypatch.setattr(load_sweep, "SessionLocal", lambda: db_session)

    # _sweep() is sync and here runs in the test's own (loopless) thread, so the orchestrator's
    # asyncio.run works directly — same code path to_thread runs in prod.
    summary = load_sweep._sweep()

    assert summary["users_attempted"] == 1
    assert summary["users_succeeded"] == 1
    assert summary["users_failed"] == 0
    assert summary["per_user"][1]["status"] == "succeeded"
    assert db_session.query(models.LoadMetric).filter_by(user_id=1).count() > 0

    print("SWEEP SUMMARY:", load_sweep._summary_brief(summary))
