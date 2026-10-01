"""Load-chain refresh orchestrator (`scripts/refresh_load.py`, #296).

Proves the four things the brief's Step-1 gate asks for, on the FK-enforced SQLite
substrate (conftest `db_session`):

  * ORDER — the seven steps run per user in the fixed chain order (Hevy ingest ->
    Polar ingest -> HC zone fill -> load_events tier0 -> load_events_metabolic -> load_metrics tier0-v2 ->
    load_metrics metab-v1);
  * NON-ZERO — a Hevy-keyed user with a resistance workout gets non-zero resistance
    events and non-zero mechanical/NM metrics (real compute for steps 2-5; only the
    external Hevy API of step 1 is mocked, since the workout rows are already seeded);
  * IDEMPOTENT — a second sweep duplicates nothing (delete-then-insert / upsert), and
    the per-user counts are identical;
  * ISOLATION — one user's failure is caught, recorded against the failing step with the
    rest of that user's chain skipped, and never aborts the sweep (mirrors
    `scripts/garmin_sync.py`);
  * POLAR SOFT-FAIL (Q154) — the `polar_sync` step never fails the user or skips a later
    step: a Polar error is recorded in its entry, a user with no Polar connection records
    `{"skipped": "no_polar"}`, and it runs with the chain's `days` and the cascade off.
  * HEVY SOFT-FAIL (Brief A C.1) — ingest steps soft-fail, compute steps hard-fail: a
    `hevy_sync` exception is recorded in its entry, rolls the session back, and neither fails
    the user nor skips a later step; a compute step's failure still fails the user.
"""
from datetime import date, datetime, timezone

import pytest

import hevy_templates
import hevy_workouts
import load_events
import models
import polar_ingest
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

def test_chain_runs_seven_steps_in_order(db_session, monkeypatch):
    _user(db_session, 1)
    _hevy_key(db_session, 1)

    calls: list[str] = []

    async def _sync(db, *, only_user_id=None, days=None):
        calls.append("hevy_sync")
        return {"users": 1, "per_user": {only_user_id: {"workouts_upserted": 0}}}

    def _polar(db, user_id, *, days, run_cascade=True):
        calls.append(f"polar_sync:days={days}:cascade={run_cascade}")
        return {"synced": 0, "enriched": 0, "available": 0}

    def _hc_zones(db, user_id):
        calls.append("hc_zone_enrich")
        return {"rows": 0, "zoned": 0}

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
    monkeypatch.setattr(polar_ingest, "sync_user", _polar)
    monkeypatch.setattr(refresh_load.hc_zone_enrich, "enrich_user", _hc_zones)
    monkeypatch.setattr(load_events, "compute_all_users", _events)
    monkeypatch.setattr(refresh_load.load_events_metabolic, "compute_all_users_metabolic", _metab)
    monkeypatch.setattr(refresh_load.load_metrics, "compute_all_users", _metrics)

    summary = refresh_load.refresh_load(db_session, as_of=AS_OF)

    # Steps 5/6 pass the module version constants (P3: tier0-v2 for strength, metab-v1
    # unchanged) rather than literals — reference the constants so this can't drift on a bump.
    # polar_sync sits after hevy_sync and BEFORE load_events_metabolic (which rolls what it
    # stored), with the chain's `days` (default window here) and the cascade OFF.
    assert calls == [
        "hevy_sync",
        f"polar_sync:days={hevy_workouts.DEFAULT_BACKFILL_DAYS}:cascade=False",
        "hc_zone_enrich",           # after polar_sync, BEFORE the metabolic transform reads the rows
        "load_events_tier0",
        "load_events_metabolic",
        f"load_metrics:{load_events.FORMULA_VERSION}",
        f"load_metrics:{refresh_load.load_events_metabolic.FORMULA_VERSION_METABOLIC}",
    ]
    assert list(summary["per_user"][1]["steps"]) == [
        "hevy_sync", "polar_sync", "hc_zone_enrich", "load_events_tier0", "load_events_metabolic",
        "load_metrics_tier0", "load_metrics_metab",
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


# ── POLAR SOFT-FAIL (Q154) ──────────────────────────────────────────────────────

def test_no_polar_user_records_skipped_marker(db_session, monkeypatch):
    """Real core, no `UserIntegration(provider="polar")` row → NotConnected → marker."""
    _user(db_session, 1)
    _hevy_key(db_session, 1)
    _mock_hevy_noop(monkeypatch)

    summary = refresh_load.refresh_load(db_session, as_of=AS_OF)

    u1 = summary["per_user"][1]
    assert u1["status"] == "succeeded"
    assert u1["steps"]["polar_sync"] == {"skipped": "no_polar"}


def test_polar_failure_is_soft_and_later_steps_run(db_session, monkeypatch, capsys):
    _user(db_session, 1)
    _hevy_key(db_session, 1)
    _resistance_workout(db_session, "w1", 1)
    _mock_hevy_noop(monkeypatch)

    rolled_back: list[bool] = []
    real_rollback = db_session.rollback

    def _spy_rollback():
        rolled_back.append(True)
        real_rollback()

    monkeypatch.setattr(db_session, "rollback", _spy_rollback)

    def _polar_down(db, user_id, *, days, run_cascade=True):
        raise polar_ingest.PolarApiError("Polar v4 API error: 503 upstream")

    monkeypatch.setattr(polar_ingest, "sync_user", _polar_down)

    summary = refresh_load.refresh_load(db_session, as_of=AS_OF)

    u1 = summary["per_user"][1]
    assert u1["status"] == "succeeded"                 # never marks the chain failed
    assert summary["users_succeeded"] == 1 and summary["users_failed"] == 0
    assert u1["steps"]["polar_sync"] == {"error": "PolarApiError: Polar v4 API error: 503 upstream"}
    assert rolled_back == [True]                       # half-written ingest never leaks on
    # every later step RAN (real compute), none skipped
    for key in ("load_events_tier0", "load_events_metabolic", "load_metrics_tier0", "load_metrics_metab"):
        assert isinstance(u1["steps"][key], dict) and "error" not in u1["steps"][key], key
    assert u1["steps"]["load_events_tier0"]["events_written"] > 0
    # the per-user line surfaces the Polar error without reading as a chain failure
    out = capsys.readouterr().out
    assert "user 1: OK" in out and "polar_synced=error(PolarApiError" in out


def test_unexpected_polar_exception_is_also_soft(db_session, monkeypatch):
    """Soft-fail covers ANY core exception, not only the declared PolarIngestError family."""
    _user(db_session, 1)
    _hevy_key(db_session, 1)
    _mock_hevy_noop(monkeypatch)

    def _polar_bug(db, user_id, *, days, run_cascade=True):
        raise KeyError("access_token")

    monkeypatch.setattr(polar_ingest, "sync_user", _polar_bug)

    u1 = refresh_load.refresh_load(db_session, as_of=AS_OF)["per_user"][1]
    assert u1["status"] == "succeeded"
    assert u1["steps"]["polar_sync"] == {"error": "KeyError: 'access_token'"}


def test_later_hard_failure_is_attributed_to_its_step_not_polar(db_session, monkeypatch, capsys):
    """With a soft Polar error AND a later hard failure, the FAILED line names the hard step."""
    _user(db_session, 1)
    _hevy_key(db_session, 1)
    _mock_hevy_noop(monkeypatch)

    def _polar_down(db, user_id, *, days, run_cascade=True):
        raise polar_ingest.TokenRefreshFailed("Polar token refresh failed: 400")

    def _events_boom(db, *, only_user_id=None):
        raise RuntimeError("tier0 boom")

    monkeypatch.setattr(polar_ingest, "sync_user", _polar_down)
    monkeypatch.setattr(load_events, "compute_all_users", _events_boom)

    u1 = refresh_load.refresh_load(db_session, as_of=AS_OF)["per_user"][1]
    assert u1["status"] == "failed"
    assert "error" in u1["steps"]["polar_sync"]
    assert u1["steps"]["load_events_metabolic"] == "skipped"
    assert "FAILED at load_events_tier0 -- RuntimeError: tier0 boom" in capsys.readouterr().err


def test_hevy_failure_no_longer_skips_polar(db_session, monkeypatch):
    """Supersedes `test_hevy_hard_failure_skips_polar_like_every_later_step` (Brief A C.1): while
    `hevy_sync` hard-failed, a Hevy outage skipped the Polar pull too — two independent ingests coupled
    for no reason. Ingest steps soft-fail now, so the Polar step still runs and the chain succeeds."""
    _user(db_session, 1)
    _hevy_key(db_session, 1)

    async def _hevy_boom(db, *, only_user_id=None, days=None):
        raise RuntimeError("hevy down")

    polar_calls: list[int] = []

    def _polar(db, uid, *, days, run_cascade=True):
        polar_calls.append(uid)
        return {"synced": 0, "enriched": 0, "available": 0}

    monkeypatch.setattr(hevy_workouts, "sync_workouts", _hevy_boom)
    monkeypatch.setattr(polar_ingest, "sync_user", _polar)

    u1 = refresh_load.refresh_load(db_session, as_of=AS_OF)["per_user"][1]
    assert u1["status"] == "succeeded"
    assert u1["steps"]["polar_sync"] == {"synced": 0, "enriched": 0, "available": 0}
    assert polar_calls == [1]


def test_polar_sync_uses_the_chain_days(db_session, monkeypatch):
    _user(db_session, 1)
    _mock_hevy_noop(monkeypatch)
    seen: list[tuple[int, bool]] = []

    def _polar(db, user_id, *, days, run_cascade=True):
        seen.append((days, run_cascade))
        return {"synced": 0, "enriched": 0, "available": 0}

    monkeypatch.setattr(polar_ingest, "sync_user", _polar)
    refresh_load.refresh_load(db_session, only_user_id=1, days=30, as_of=AS_OF)
    assert seen == [(30, False)]


# ── HEVY SOFT-FAIL (Brief A C.1) — ingest steps soft-fail, compute steps hard-fail ──

def test_hevy_failure_is_soft_and_later_steps_run(db_session, monkeypatch, capsys):
    _user(db_session, 1)
    _hevy_key(db_session, 1)
    _resistance_workout(db_session, "w1", 1)   # already stored: the compute steps still have this to roll

    async def _hevy_down(db, *, only_user_id=None, days=None):
        raise RuntimeError("Hevy API: 503 upstream")

    monkeypatch.setattr(hevy_workouts, "sync_workouts", _hevy_down)

    rolled_back: list[bool] = []
    real_rollback = db_session.rollback

    def _spy_rollback():
        rolled_back.append(True)
        real_rollback()

    monkeypatch.setattr(db_session, "rollback", _spy_rollback)

    summary = refresh_load.refresh_load(db_session, as_of=AS_OF)

    u1 = summary["per_user"][1]
    assert u1["status"] == "succeeded"                       # never marks the chain failed
    assert summary["users_succeeded"] == 1 and summary["users_failed"] == 0
    assert u1["steps"]["hevy_sync"] == {"error": "RuntimeError: Hevy API: 503 upstream"}   # recorded
    assert rolled_back == [True]                             # a half-written ingest never leaks on
    # every later step RAN (polar_sync included — no Polar connection here), none skipped
    assert u1["steps"]["polar_sync"] == {"skipped": "no_polar"}
    for key in ("load_events_tier0", "load_events_metabolic", "load_metrics_tier0", "load_metrics_metab"):
        assert isinstance(u1["steps"][key], dict) and "error" not in u1["steps"][key], key
    assert u1["steps"]["load_events_tier0"]["events_written"] > 0   # computed over what was already stored
    # not silent: the soft failure is named on stderr, the user line still reads as a completed chain
    cap = capsys.readouterr()
    assert "user 1: OK" in cap.out
    assert "soft-fail (chain continued) -- hevy_sync: RuntimeError: Hevy API: 503 upstream" in cap.err


def test_both_ingest_steps_failing_still_runs_the_compute_steps(db_session, monkeypatch):
    _user(db_session, 1)
    _hevy_key(db_session, 1)
    _resistance_workout(db_session, "w1", 1)

    async def _hevy_down(db, *, only_user_id=None, days=None):
        raise RuntimeError("hevy down")

    def _polar_down(db, user_id, *, days, run_cascade=True):
        raise polar_ingest.PolarApiError("polar down")

    monkeypatch.setattr(hevy_workouts, "sync_workouts", _hevy_down)
    monkeypatch.setattr(polar_ingest, "sync_user", _polar_down)

    u1 = refresh_load.refresh_load(db_session, as_of=AS_OF)["per_user"][1]
    assert u1["status"] == "succeeded"
    assert "error" in u1["steps"]["hevy_sync"] and "error" in u1["steps"]["polar_sync"]
    assert u1["steps"]["load_metrics_metab"] != "skipped"


def test_a_compute_step_failure_still_fails_the_user_after_a_soft_ingest_failure(db_session, monkeypatch):
    """The other half of the principle: soft applies to INGEST only. A compute step's own failure is
    ours, so it fails the user and skips what depends on it — with or without an ingest outage."""
    _user(db_session, 1)
    _hevy_key(db_session, 1)

    async def _hevy_down(db, *, only_user_id=None, days=None):
        raise RuntimeError("hevy down")

    def _metab_fail(db, *, only_user_id=None):
        raise RuntimeError("metabolic compute broke")

    monkeypatch.setattr(hevy_workouts, "sync_workouts", _hevy_down)
    monkeypatch.setattr(refresh_load.load_events_metabolic, "compute_all_users_metabolic", _metab_fail)

    u1 = refresh_load.refresh_load(db_session, as_of=AS_OF)["per_user"][1]
    assert u1["status"] == "failed"
    assert "error" in u1["steps"]["hevy_sync"]                      # the soft one is still recorded
    assert "metabolic compute broke" in u1["steps"]["load_events_metabolic"]["error"]
    assert u1["steps"]["load_metrics_tier0"] == "skipped" and u1["steps"]["load_metrics_metab"] == "skipped"


def test_soft_steps_are_exactly_the_ingest_and_fill_steps():
    """Ingest = the two steps that pull from a third-party API; the HC zone fill joins them (Q159
    stage 2): a failure leaves rows in the stage-1 state, so it can only withhold information.
    Everything after them computes."""
    assert refresh_load.SOFT_STEPS == frozenset({"hevy_sync", "polar_sync", "hc_zone_enrich"})


def test_hc_zone_enrich_failure_is_soft_and_later_steps_still_run(db_session, monkeypatch, capsys):
    """A raising fill is recorded, the session rolled back, the user stays `succeeded`, and the
    four compute steps still run for real over what is stored. Mutation: re-raising from
    `_hc_zone_enrich` (or dropping it from SOFT_STEPS) fails this."""
    _user(db_session, 1)
    _hevy_key(db_session, 1)
    _resistance_workout(db_session, "w1", 1)
    _mock_hevy_noop(monkeypatch)
    monkeypatch.setattr(polar_ingest, "sync_user",
                        lambda db, uid, *, days, run_cascade=True: {"synced": 0})

    def _boom(db, uid):
        raise RuntimeError("zone fill broke")
    monkeypatch.setattr(refresh_load.hc_zone_enrich, "enrich_user", _boom)
    rollbacks: list[int] = []
    real_rollback = db_session.rollback
    monkeypatch.setattr(db_session, "rollback", lambda: (rollbacks.append(1), real_rollback())[1])

    u1 = refresh_load.refresh_load(db_session, as_of=AS_OF)["per_user"][1]
    assert u1["status"] == "succeeded"
    assert u1["steps"]["hc_zone_enrich"] == {"error": "RuntimeError: zone fill broke"}
    assert rollbacks, "a failed fill must roll the session back"
    assert u1["steps"]["load_events_tier0"]["events_written"] > 0       # compute ran for real
    assert "hc_zone_enrich: RuntimeError: zone fill broke" in capsys.readouterr().err


def test_hc_zone_enrich_report_line_names_reasons_and_over_ceiling(db_session, monkeypatch, capsys):
    """The chain's per-user line surfaces the closed-set reason counts and the over-ceiling count."""
    _user(db_session, 1)
    _hevy_key(db_session, 1)
    _mock_hevy_noop(monkeypatch)
    monkeypatch.setattr(polar_ingest, "sync_user",
                        lambda db, uid, *, days, run_cascade=True: {"synced": 0})
    monkeypatch.setattr(refresh_load.hc_zone_enrich, "enrich_user", lambda db, uid: {
        "rows": 16, "zoned": 8, "over_ceiling": 1,
        "reasons": {"sparse": 3, "no_same_writer_hr": 2, "no_hrmax": 3, "none": 8}})
    refresh_load.refresh_load(db_session, as_of=AS_OF)
    out = capsys.readouterr().out
    assert "hc_zoned=8/16 (sparse=3 no_same_writer_hr=2 no_hrmax=3 over_ceiling=1)" in out
