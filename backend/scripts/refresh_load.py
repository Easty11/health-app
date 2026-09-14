"""
Load-chain refresh orchestrator — the single scheduled entry point that replaces
four independently-run manual modules (#296).

Sweeps every Hevy-keyed user and, per user, runs the load chain IN ORDER:

    1. hevy_workouts.sync_workouts                        Hevy API -> hevy_workouts   (async)
    2. load_events.compute_all_users                     resistance events   tier0-v1
    3. load_events_metabolic.compute_all_users_metabolic metabolic events    metab-v1
    4. load_metrics.compute_all_users (tier0-v1)         mechanical / neuromuscular metrics
    5. load_metrics.compute_all_users (metab-v1)         metabolic metrics

Per-user isolation mirrors `scripts/garmin_sync.py`: one user's failure is caught,
recorded, and skipped -- it never aborts the sweep. Steps 2-5 depend on their
predecessor, so once a step fails the rest of that user's chain is marked skipped.
An aggregate summary (users attempted / succeeded / failed + per-user, per-step
outcomes) is printed and returned.

Idempotent: step 1 upserts; steps 2-3 delete-then-insert their `(user, formula_version)`
`load_events` rows; steps 4-5 delete-then-insert their `(user, formula_version,
metrics_version)` `load_metrics` rows. A second run does not duplicate.

Async shape: step 1 is `async`; steps 2-5 are sync. The Hevy ingest is driven with
`asyncio.run` per user (the proven `hevy_workouts.__main__` pattern), so each user's
event loop is created and torn down in isolation.

Aerobic scope (v1): step 3 ROLLS whatever is already in `aerobic_sessions`; this
orchestrator does NOT ingest aerobic data. The only automated aerobic ingest
(`routers/polar.py::sync_polar_sessions`) is request-coupled to `current_user` + its
OAuth client and is out of scope to refactor here. The aerobic-ingest-automation gap
is tracked in OPEN_QUESTIONS Q154.

Trigger: a nightly Railway cron (~02:00 AEST) runs `python -m scripts.refresh_load`
(all users). Load buckets on the AEST calendar day, so the sweep runs after the AEST
day boundary. See DECISIONS_LOG #296.

    /opt/venv/bin/python -m scripts.refresh_load                    # all keyed users
    /opt/venv/bin/python -m scripts.refresh_load --user 4          # one user only
    /opt/venv/bin/python -m scripts.refresh_load --days 30         # Hevy backfill window
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


def run_user_chain(
    db,
    uid: int,
    *,
    days: int,
    as_of: date | None,
) -> dict[str, Any]:
    """Run the full ordered load chain for one user. Returns a per-user outcome
    `{"status": "succeeded"|"failed", "steps": {step_key: outcome_or_error}}`.

    Steps are recorded as they complete. On the first step that raises, that step's
    entry becomes `{"error": "<Type>: <msg>"}`, every later step is marked `"skipped"`,
    and `status` is `"failed"` -- the exception does NOT propagate, so the sweep goes on.
    """
    # (key, callable) in strict chain order. Each callable returns this user's outcome.
    steps: list[tuple[str, Callable[[], dict[str, Any]]]] = [
        ("hevy_sync", lambda: _per_user(
            asyncio.run(hevy_workouts.sync_workouts(db, only_user_id=uid, days=days)), uid)),
        ("load_events_tier0", lambda: _per_user(
            load_events.compute_all_users(db, only_user_id=uid), uid)),
        ("load_events_metabolic", lambda: _per_user(
            load_events_metabolic.compute_all_users_metabolic(db, only_user_id=uid), uid)),
        ("load_metrics_tier0", lambda: _per_user(
            load_metrics.compute_all_users(
                db, only_user_id=uid, formula_version="tier0-v1", as_of=as_of), uid)),
        ("load_metrics_metab", lambda: _per_user(
            load_metrics.compute_all_users(
                db, only_user_id=uid, formula_version="metab-v1", as_of=as_of), uid)),
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
            outcome["status"] = "failed"
            outcome["steps"][key] = {"error": f"{type(exc).__name__}: {exc}"}
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
        ev = steps.get("load_events_tier0")
        mev = steps.get("load_events_metabolic")
        m0 = steps.get("load_metrics_tier0")
        mm = steps.get("load_metrics_metab")

        def _n(d: Any, key: str) -> Any:
            return d.get(key) if isinstance(d, dict) else "-"

        if outcome["status"] == "succeeded":
            print(f"  user {uid}: OK  "
                  f"tier0_events={_n(ev, 'events_written')} "
                  f"metab_events={_n(mev, 'events_written')} "
                  f"tier0_metrics={_n(m0, 'rows_written')} "
                  f"metab_metrics={_n(mm, 'rows_written')}")
        else:
            failed_key = next((k for k, v in steps.items()
                               if isinstance(v, dict) and "error" in v), "?")
            err = steps[failed_key]["error"] if failed_key in steps else "?"
            print(f"  user {uid}: FAILED at {failed_key} -- {err}", file=sys.stderr)

    print(f"refresh_load done: {summary['users_succeeded']} succeeded, "
          f"{summary['users_failed']} failed, of {summary['users_attempted']} attempted")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the full load chain (Hevy ingest -> load_events -> load_metrics) "
                    "for all Hevy-keyed users. Nightly Railway cron entry point (#296).")
    parser.add_argument("--user", type=int, default=None,
                        help="only this user id (default: all Hevy-keyed users)")
    parser.add_argument("--days", type=int, default=hevy_workouts.DEFAULT_BACKFILL_DAYS,
                        help="Hevy backfill window in days "
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
