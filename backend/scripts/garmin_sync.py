"""
Garmin HRV sync runner — the batch sweep over Garmin-connected users, reused by two callers:

  * `scripts/garmin_sync.py` CLI (this file's `main`) — `railway run` / ops one-shots.
  * The in-process nightly sweep (`load_sweep._sweep`, #299) — garmin_sync as the second job
    on #297's 02:00 Brisbane rail, beside the load chain.

`sweep_garmin_hrv` is the reusable core: it sweeps every user with a stored Garmin token (or one
named user), pulls their HRV for a date window, and upserts into hrv_readings + hrv_samples via
the shared per-user core (`routers.garmin.sync_hrv_for_user`). PER-USER ISOLATION: one user's dead
token (GarminReconnectError) or any other failure is caught, rolled back, logged and skipped — it
never aborts the batch. Idempotent: the upsert keys on (user, night, source).

    /opt/venv/bin/python -m scripts.garmin_sync                 # last 7 nights, all users
    /opt/venv/bin/python -m scripts.garmin_sync --days 30
    /opt/venv/bin/python -m scripts.garmin_sync --from 2026-08-01 --to 2026-08-31
    /opt/venv/bin/python -m scripts.garmin_sync --user-id 4     # one user only
"""
import argparse
import logging
import sys
from datetime import date, timedelta
from typing import Any

from connectors.garmin import GarminReconnectError
from database import SessionLocal
import models
from routers.garmin import garmin_wake_day, sync_hrv_for_user

logger = logging.getLogger(__name__)

# Default window when no explicit range is given — a week of nights. Enough to cover the prior
# night plus a short self-heal tail (bounded upstream by the ~7-day get_hrv_range ceiling).
_DEFAULT_SWEEP_DAYS = 7


def sweep_garmin_hrv(
    db,
    *,
    only_user_id: int | None = None,
    days: int = _DEFAULT_SWEEP_DAYS,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    """Pull + upsert Garmin HRV for every connected user (or just `only_user_id`) over the
    window, isolating per-user failures. Returns an aggregate summary (mirrors `refresh_load`).

    Not a route and not CLI-shaped, so it is callable from the nightly sweep. `db` is caller-owned
    (the CLI opens its own; the sweep passes its `SessionLocal()`); a per-user failure rolls the
    session back so the next user starts clean."""
    today = garmin_wake_day()   # AEST wake-day, not UTC (#327 follow-up)
    end = end or today
    start = start or (end - timedelta(days=days))

    q = db.query(models.UserIntegration).filter_by(provider="garmin")
    if only_user_id is not None:
        q = q.filter_by(user_id=only_user_id)
    user_ids = [row.user_id for row in q.all()]

    per_user: dict[int, dict] = {}
    succeeded = failed = 0
    for uid in user_ids:
        try:
            result = sync_hrv_for_user(db, uid, start, end)
            succeeded += 1
            per_user[uid] = {"status": "succeeded", **result}
            logger.info(
                "garmin sweep: user %s OK — %s readings, %s samples (%s days with data)",
                uid, result["readings_upserted"], result["samples_upserted"],
                result["days_with_data"],
            )
        except GarminReconnectError as exc:
            failed += 1
            per_user[uid] = {"status": "reconnect_required", "error": str(exc)}
            logger.warning("garmin sweep: user %s reconnect needed — %s", uid, exc)
            db.rollback()
        except Exception as exc:  # noqa: BLE001 — one user's failure never aborts the sweep
            failed += 1
            per_user[uid] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
            logger.exception("garmin sweep: user %s failed", uid)
            db.rollback()

    return {
        "users_attempted": len(user_ids),
        "users_succeeded": succeeded,
        "users_failed": failed,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "per_user": per_user,
    }


def _resolve_window(args) -> tuple[date, date]:
    today = garmin_wake_day()   # AEST wake-day, not UTC (#327 follow-up)
    end = date.fromisoformat(args.to) if args.to else today
    if args.from_:
        start = date.fromisoformat(args.from_)
    else:
        start = end - timedelta(days=args.days)
    return start, end


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull Garmin HRV into hrv_readings/hrv_samples.")
    parser.add_argument("--days", type=int, default=_DEFAULT_SWEEP_DAYS,
                        help=f"Window length ending today (default {_DEFAULT_SWEEP_DAYS}).")
    parser.add_argument("--from", dest="from_", help="Window start (YYYY-MM-DD); overrides --days.")
    parser.add_argument("--to", help="Window end (YYYY-MM-DD); default today.")
    parser.add_argument("--user-id", type=int, help="Sync only this user (default: all connected).")
    args = parser.parse_args()

    start, end = _resolve_window(args)
    if start > end:
        print("--from must not be after --to", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        summary = sweep_garmin_hrv(db, only_user_id=args.user_id, start=start, end=end)
        if summary["users_attempted"] == 0:
            print("No Garmin-connected users in scope.")
            return 0

        print(f"Syncing Garmin HRV for {summary['users_attempted']} user(s), {start}..{end}")
        for uid, detail in summary["per_user"].items():
            if detail["status"] == "succeeded":
                print(f"  user {uid}: {detail['readings_upserted']} readings, "
                      f"{detail['samples_upserted']} samples "
                      f"({detail['days_with_data']} days with data)")
            else:
                print(f"  user {uid}: {detail['status'].upper()} — {detail.get('error', '')}",
                      file=sys.stderr)
        return 1 if summary["users_failed"] else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
