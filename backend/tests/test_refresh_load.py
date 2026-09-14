"""Load-chain refresh orchestrator (`scripts/refresh_load.py`, #296).

Proves the four things the brief's Step-1 gate asks for, on the FK-enforced SQLite
substrate (conftest `db_session`):

  * ORDER — the five steps run per user in the fixed chain order (Hevy ingest ->
    load_events tier0 -> load_events_metabolic -> load_metrics tier0-v1 ->
    load_metrics metab-v1);
  * NON-ZERO — a Hevy-keyed user with a resistance workout gets non-zero resistance
    events and non-zero mechanical/NM metrics (real compute for steps 2-5; only the
    external Hevy API of step 1 is mocked, since the workout rows are already seeded);
  * IDEMPOTENT — a second sweep duplicates nothing (delete-then-insert / upsert), and
    the per-user counts are identical;
  * ISOLATION — one user's failure is caught, recorded against the failing step with the
    rest of that user's chain skipped, and never aborts the sweep (mirrors
    `scripts/garmin_sync.py`).
"""
from datetime import date, datetime, timezone

import pytest

import hevy_templates
import hevy_workouts
import load_events
import models
from scripts import refresh_load

AS_OF = date(2026, 9, 14)


# ── seeding ─────────────────────────────────────────────────────────────────────

def _user(db, uid):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


def _hevy_key(db, uid, key="test-key"):
    """Real UserIntegration so `users_with_hevy_key` (the sweep set) finds the user."""
    from encryption import encrypt
    db.add(models.UserIntegration(
        user_id=uid, provider="hevy", api_key_encrypted=encrypt(key)))
    db.commit()


def _resistance_workout(db, hevy_id, uid, start_iso="2026-06-01T10:00:00Z"):
    dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    db.add(models.HevyWorkout(
        hevy_id=hevy_id, user_id=uid, start_time=dt, title="W",
        raw={"id": hevy_id, "exercises": [
            {"exercise_template_id": "BENCH",
             "sets": [{"type": "normal", "weight_kg": 100.0, "reps": 5, "rpe": 8.0}]}]},
    ))
    db.commit()


def _mock_hevy_noop(monkeypatch):
    """Step 1 hits the Hevy API; the workout rows are already seeded, so stub it to a
    no-op that returns the module's real envelope shape."""
    async def _fake_sync(db, *, only_user_id=None, days=hevy_workouts.DEFAULT_BACKFILL_DAYS):
        return {"users": 1, "per_user": {only_user_id: {"workouts_upserted": 0, "note": "mocked"}}}
    monkeypatch.setattr(hevy_workouts, "sync_workouts", _fake_sync)


# ── ORDER ───────────────────────────────────────────────────────────────────────

def test_chain_runs_five_steps_in_order(db_session, monkeypatch):
    _user(db_session, 1)
    _hevy_key(db_session, 1)

    calls: list[str] = []

    async def _sync(db, *, only_user_id=None, days=None):
        calls.append("hevy_sync")
        return {"users": 1, "per_user": {only_user_id: {"workouts_upserted": 0}}}

    def _events(db, *, only_user_id=None):
        calls.append("load_events_tier0")
        return {"users": 1, "per_user": {only_user_id: {"events_written": 2}}}

    def _metab(db, *, only_user_id=None):
        calls.append("load_events_metabolic")
        return {"users": 1, "per_user": {only_user_id: {"events_written": 0}}}

    def _metrics(db, *, only_user_id=None, formula_version="tier0-v1", as_of=None):
        calls.append(f"load_metrics:{formula_version}")
        return {"users": 1, "per_user": {only_user_id: {"rows_written": 3, "formula_version": formula_version}}}

    monkeypatch.setattr(hevy_workouts, "sync_workouts", _sync)
    monkeypatch.setattr(load_events, "compute_all_users", _events)
    monkeypatch.setattr(refresh_load.load_events_metabolic, "compute_all_users_metabolic", _metab)
    monkeypatch.setattr(refresh_load.load_metrics, "compute_all_users", _metrics)

    refresh_load.refresh_load(db_session, as_of=AS_OF)

    assert calls == [
        "hevy_sync",
        "load_events_tier0",
        "load_events_metabolic",
        "load_metrics:tier0-v1",
        "load_metrics:metab-v1",
    ]


# ── NON-ZERO + IDEMPOTENT (real compute, steps 2-5) ─────────────────────────────

def test_full_chain_non_zero_and_idempotent(db_session, monkeypatch):
    _user(db_session, 1)
    _hevy_key(db_session, 1)
    _resistance_workout(db_session, "w1", 1)
    _mock_hevy_noop(monkeypatch)

    first = refresh_load.refresh_load(db_session, as_of=AS_OF)

    # aggregate summary shape
    assert first["users_attempted"] == 1
    assert first["users_succeeded"] == 1
    assert first["users_failed"] == 0
    assert first["as_of"] == "2026-09-14"

    steps = first["per_user"][1]["steps"]
    assert first["per_user"][1]["status"] == "succeeded"
    # non-zero resistance events + mechanical/NM metrics for a user with a resistance workout
    assert steps["load_events_tier0"]["events_written"] > 0
    assert steps["load_metrics_tier0"]["rows_written"] > 0
    # metabolic rolls existing aerobic_sessions (none seeded) -> 0, not a failure
    assert steps["load_events_metabolic"]["events_written"] == 0

    events_after_1 = db_session.query(models.LoadEvent).count()
    metrics_after_1 = db_session.query(models.LoadMetric).count()
    assert events_after_1 > 0 and metrics_after_1 > 0

    # second sweep — idempotent: identical row counts and identical per-user counts
    second = refresh_load.refresh_load(db_session, as_of=AS_OF)
    assert db_session.query(models.LoadEvent).count() == events_after_1
    assert db_session.query(models.LoadMetric).count() == metrics_after_1
    assert (second["per_user"][1]["steps"]["load_events_tier0"]["events_written"]
            == steps["load_events_tier0"]["events_written"])
    assert (second["per_user"][1]["steps"]["load_metrics_tier0"]["rows_written"]
            == steps["load_metrics_tier0"]["rows_written"])


# ── ISOLATION ───────────────────────────────────────────────────────────────────

def test_one_user_failure_never_aborts_the_sweep(db_session, monkeypatch):
    _user(db_session, 1)
    _hevy_key(db_session, 1)
    _user(db_session, 2)
    _hevy_key(db_session, 2)
    _mock_hevy_noop(monkeypatch)

    real_events = load_events.compute_all_users

    def _events_fail_uid2(db, *, only_user_id=None):
        if only_user_id == 2:
            raise RuntimeError("boom for user 2")
        return real_events(db, only_user_id=only_user_id)

    monkeypatch.setattr(load_events, "compute_all_users", _events_fail_uid2)

    summary = refresh_load.refresh_load(db_session, as_of=AS_OF)

    # sweep completed across BOTH users despite user 2 blowing up
    assert summary["users_attempted"] == 2
    assert summary["users_succeeded"] == 1
    assert summary["users_failed"] == 1
    assert set(summary["per_user"]) == {1, 2}

    u2 = summary["per_user"][2]
    assert u2["status"] == "failed"
    assert "error" in u2["steps"]["load_events_tier0"]
    assert "RuntimeError" in u2["steps"]["load_events_tier0"]["error"]
    # downstream steps for the failed user are skipped, not run
    assert u2["steps"]["load_events_metabolic"] == "skipped"
    assert u2["steps"]["load_metrics_tier0"] == "skipped"
    assert u2["steps"]["load_metrics_metab"] == "skipped"

    assert summary["per_user"][1]["status"] == "succeeded"


def test_only_user_scopes_to_one(db_session, monkeypatch):
    """`only_user_id` bypasses the Hevy-key sweep and runs exactly that user."""
    _user(db_session, 7)
    _resistance_workout(db_session, "w7", 7)
    _mock_hevy_noop(monkeypatch)

    summary = refresh_load.refresh_load(db_session, only_user_id=7, as_of=AS_OF)
    assert summary["users_attempted"] == 1
    assert list(summary["per_user"]) == [7]
    assert summary["per_user"][7]["status"] == "succeeded"
