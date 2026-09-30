"""
Load-chain refresh orchestrator — the single scheduled entry point that replaces
four independently-run manual modules (#296).

Sweeps every Hevy-keyed user and, per user, runs the load chain IN ORDER:

    1. hevy_workouts.sync_workouts                        Hevy API -> hevy_workouts   (async, soft-fail)
    2. polar_ingest.sync_user (run_cascade=False)         Polar v4 -> aerobic_sessions (soft-fail)
    3. load_events.compute_all_users                     resistance events   tier0-v2
    4. load_events_metabolic.compute_all_users_metabolic metabolic events    metab-v1
    5. load_metrics.compute_all_users (tier0-v2)         mechanical / neuromuscular metrics
    6. load_metrics.compute_all_users (metab-v1)         metabolic metrics

Version labels above track the module constants — steps 5/6 pass
`load_events.FORMULA_VERSION` / `load_events_metabolic.FORMULA_VERSION_METABOLIC` rather than
literals, so a formula bump (e.g. tier0-v1 → tier0-v2, P3) propagates without editing here.

Per-user isolation mirrors `scripts/garmin_sync.py`: one user's failure is caught,
recorded, and skipped -- it never aborts the sweep. Steps 3-6 depend on their
predecessor, so once a COMPUTE step fails the rest of that user's chain is marked skipped.
An aggregate summary (users attempted / succeeded / failed + per-user, per-step
outcomes) is printed and returned.

Ingest steps soft-fail, compute steps hard-fail (Brief A C.1). Steps 1-2 pull from third-party APIs
(Hevy, Polar): an outage there must not stall load compute, because the compute steps still have
everything already stored to roll. A soft step's failure is recorded in its own entry
(`{"error": "<Type>: <msg>"}`), printed, and the chain carries on -- it never marks the user failed
and never skips a later step. A compute step (3-6) reads and writes our own tables; its failure is
ours, so it fails the user and skips what depends on it. `SOFT_STEPS` is the one place that
membership lives.

Aerobic ingest (Q154): step 2 pulls new Polar sessions (summary upsert + v4 zone
enrichment) through the same core the manual Sync route uses, over the chain's `days`
window, with the cascade OFF — step 4 and step 6 recompute metabolic load from what it
stored, so nothing is computed twice. A user with no Polar connection records
`{"skipped": "no_polar"}`; any other ingest failure (token refresh, v4 API) records
`{"error": "<Type>: <msg>"}` (soft-fail, above), so a Polar outage cannot stall resistance
load, and step 4 still rolls the aerobic sessions already stored. Hevy ingest (step 1)
soft-fails the same way: a Hevy outage leaves `hevy_workouts` as last synced and the compute
steps run over it.

Idempotent: steps 1-2 upsert (Polar dedups by `source_session_id`; enrichment targets
zoneless rows only); steps 3-4 delete-then-insert their `(user, formula_version)`
`load_events` rows; steps 5-6 delete-then-insert their `(user, formula_version,
metrics_version)` `load_metrics` rows. A second run does not duplicate.

Async shape: step 1 is `async`; steps 2-6 are sync. The Hevy ingest is driven with
`asyncio.run` per user (the proven `hevy_workouts.__main__` pattern), so each user's
event loop is created and torn down in isolation.

Triggers (#297, supersedes #296's dedicated Railway cron service): the per-user
`POST /load/refresh` route (`routers/load.py`) on Training-page open, and the in-process
nightly all-users sweep at 02:00 Brisbane (`load_sweep.py`, wired in `main.lifespan`). Both
reuse `refresh_load` UNCHANGED. Load buckets on the AEST calendar day, so the nightly sweep
runs after the AEST day boundary. This `__main__` entry point remains for manual runs:

    /opt/venv/bin/python -m scripts.refresh_load                    # all keyed users
    /opt/venv/bin/python -m scripts.refresh_load --user 4          # one user only
    /opt/venv/bin/python -m scripts.refresh_load --days 30         # Hevy + Polar window
    /opt/venv/bin/python -m scripts.refresh_load --as-of 2026-09-13
"""
import argparse
import asyncio
import sys
from datetime import date
from typing import Any, Callable

import hevy_workouts
import load_events
import load_events_metabolic
import load_metrics
import polar_ingest
from database import SessionLocal
from hevy_templates import users_with_hevy_key


def _per_user(result: dict[str, Any], uid: int) -> dict[str, Any]:
    """Unwrap a compute module's `{"users": .., "per_user": {uid: {...}}}` envelope to
    this user's inner outcome dict. Falls back to the whole envelope (e.g. Hevy's
    `{"users": 0, "detail": "user N has no Hevy key"}` shape) when the user is absent."""
    per_user = result.get("per_user")
    if isinstance(per_user, dict) and uid in per_user:
        return per_user[uid]
    return result


# INGEST steps: their failure is recorded but never fails the user or skips later steps (Brief A C.1 —
# ingest steps soft-fail, compute steps hard-fail). Every other step is a compute step.
SOFT_STEPS = frozenset({"hevy_sync", "polar_sync"})


def _polar_sync(db, uid: int, days: int) -> dict[str, Any]:
    """The chain's aerobic ingest: `polar_ingest.sync_user` with the cascade off (the
    chain's own metabolic steps recompute). Soft-fail by construction -- it never raises:
    no Polar connection -> `{"skipped": "no_polar"}`; any other failure -> the chain's
    `{"error": "<Type>: <msg>"}` shape, with the session rolled back so a half-written
    ingest cannot leak into the later steps' transactions."""
    try:
        return polar_ingest.sync_user(db, uid, days=days, run_cascade=False)
    except polar_ingest.NotConnected:
        return {"skipped": "no_polar"}
    except Exception as exc:  # noqa: BLE001 -- soft-fail: a Polar failure never stops the chain
        db.rollback()
        return {"error": f"{type(exc).__name__}: {exc}"}


def run_user_chain(
    db,
    uid: int,
    *,
    days: int,
    as_of: date | None,
) -> dict[str, Any]:
    """Run the full ordered load chain for one user. Returns a per-user outcome
    `{"status": "succeeded"|"failed", "steps": {step_key: outcome_or_error}}`.

    Steps are recorded as they complete. On the first COMPUTE step that raises, that step's
    entry becomes `{"error": "<Type>: <msg>"}`, every later step is marked `"skipped"`,
    and `status` is `"failed"` -- the exception does NOT propagate, so the sweep goes on.
    A SOFT_STEPS member (an ingest step: `hevy_sync`, `polar_sync`) that raises has the same
    `{"error": ...}` entry, but the session is rolled back, `status` is untouched, and every
    later step still runs -- an ingest outage never blocks load compute.
    """
    # (key, callable) in strict chain order. Each callable returns this user's outcome.
    steps: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("hevy_sync", lambda: _per_user(
            asyncio.run(hevy_workouts.sync_workouts(db, only_user_id=uid, days=days)), uid)),
        ("polar_sync", lambda: _polar_sync(db, uid, days)),
        ("load_events_tier0", lambda: _per_user(
            load_events.compute_all_users(db, only_user_id=uid), uid)),
        ("load_events_metabolic", lambda: _per_user(
            load_events_metabolic.compute_all_users_metabolic(db, only_user_id=uid), uid)),
        ("load_metrics_tier0", lambda: _per_user(
            load_metrics.compute_all_users(
                db, only_user_id=uid,
                formula_version=load_events.FORMULA_VERSION, as_of=as_of), uid)),
        ("load_metrics_metab", lambda: _per_user(
            load_metrics.compute_all_users(
                db, only_user_id=uid,
                formula_version=load_events_metabolic.FORMULA_VERSION_METABOLIC, as_of=as_of), uid)),
    ]

    outcome: dict[str, Any] = {"status": "succeeded", "steps": {}}
    failed_at: int | None = None
    for i, (key, fn) in enumerate(steps):
        if failed_at is not None:
            outcome["steps"][key] = "skipped"
            continue
        try:
            outcome["steps"][key] = fn()
        except Exception as exc:  # noqa: BLE001 -- one user's failure never aborts the sweep
            outcome["steps"][key] = {"error": f"{type(exc).__name__}: {exc}"}
            if key in SOFT_STEPS:
                # Ingest step: roll back a half-written ingest so it cannot leak into the compute
                # steps' transactions, record the error, carry on.
                db.rollback()
                continue
            outcome["status"] = "failed"
            failed_at = i
    return outcome


def refresh_load(
    db,
    *,
    only_user_id: int | None = None,
    days: int = hevy_workouts.DEFAULT_BACKFILL_DAYS,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Sweep Hevy-keyed users (or one, when `only_user_id` is set) through the load
    chain and return the aggregate summary. Never raises for a single user's failure."""
    if only_user_id is not None:
        user_ids = [only_user_id]
    else:
        user_ids = [uid for uid, _key in users_with_hevy_key(db)]

    summary: dict[str, Any] = {
        "users_attempted": len(user_ids),
        "users_succeeded": 0,
        "users_failed": 0,
        "days": days,
        "as_of": as_of.isoformat() if as_of else "today(AEST)",
        "per_user": {},
    }

    print(f"refresh_load: {len(user_ids)} Hevy-keyed user(s) in scope; "
          f"days={days}, as_of={summary['as_of']}")

    for uid in user_ids:
        outcome = run_user_chain(db, uid, days=days, as_of=as_of)
        summary["per_user"][uid] = outcome
        if outcome["status"] == "succeeded":
            summary["users_succeeded"] += 1
        else:
            summary["users_failed"] += 1

        steps = outcome["steps"]
        ps = steps.get("polar_sync")
        ev = steps.get("load_events_tier0")
        mev = steps.get("load_events_metabolic")
        m0 = steps.get("load_metrics_tier0")
        mm = steps.get("load_metrics_metab")

        def _n(d: Any, key: str) -> Any:
            return d.get(key) if isinstance(d, dict) else "-"

        def _polar(d: Any) -> Any:
            if isinstance(d, dict) and "error" in d:
                return f"error({d['error']})"
            if isinstance(d, dict) and "skipped" in d:
                return d["skipped"]
            return _n(d, "synced")

        # A soft-failed ingest step is not a chain failure, but it must not be silent: name it.
        soft_errors = [f"{k}: {v['error']}" for k in sorted(SOFT_STEPS)
                       if isinstance(v := steps.get(k), dict) and "error" in v]

        if outcome["status"] == "succeeded":
            print(f"  user {uid}: OK  "
                  f"polar_synced={_polar(ps)} "
                  f"tier0_events={_n(ev, 'events_written')} "
                  f"metab_events={_n(mev, 'events_written')} "
                  f"tier0_metrics={_n(m0, 'rows_written')} "
                  f"metab_metrics={_n(mm, 'rows_written')}")
            for err in soft_errors:
                print(f"    soft-fail (chain continued) -- {err}", file=sys.stderr)
        else:
            failed_key = next((k for k, v in steps.items()
                               if k not in SOFT_STEPS and isinstance(v, dict) and "error" in v), "?")
            err = steps[failed_key]["error"] if failed_key in steps else "?"
            print(f"  user {uid}: FAILED at {failed_key} -- {err}", file=sys.stderr)

    print(f"refresh_load done: {summary['users_succeeded']} succeeded, "
          f"{summary['users_failed']} failed, of {summary['users_attempted']} attempted")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the full load chain (Hevy + Polar ingest -> load_events -> load_metrics) "
                    "for all Hevy-keyed users. Nightly Railway cron entry point (#296).")
    parser.add_argument("--user", type=int, default=None,
                        help="only this user id (default: all Hevy-keyed users)")
    parser.add_argument("--days", type=int, default=hevy_workouts.DEFAULT_BACKFILL_DAYS,
                        help="Hevy + Polar ingest window in days "
                             f"(default {hevy_workouts.DEFAULT_BACKFILL_DAYS})")
    parser.add_argument("--as-of", dest="as_of", default=None,
                        help="ISO date the metrics rollup is computed as-of "
                             "(default: today, AEST)")
    args = parser.parse_args()

    as_of = date.fromisoformat(args.as_of) if args.as_of else None

    db = SessionLocal()
    try:
        summary = refresh_load(db, only_user_id=args.user, days=args.days, as_of=as_of)
    finally:
        db.close()

    print(summary)
    return 1 if summary["users_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
