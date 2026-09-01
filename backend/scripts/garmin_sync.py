"""
Garmin HRV sync runner — for `railway run` / external cron (there is no in-process
scheduler; the trigger is a deployment decision, not baked in).

Sweeps every user with a stored Garmin token and pulls their HRV for a date window,
upserting into hrv_readings + hrv_samples via the shared core (routers.garmin.
sync_hrv_for_user). One user's dead token (GarminReconnectError) is reported and
skipped — it never aborts the sweep.

    /opt/venv/bin/python -m scripts.garmin_sync                 # last 7 nights, all users
    /opt/venv/bin/python -m scripts.garmin_sync --days 30
    /opt/venv/bin/python -m scripts.garmin_sync --from 2026-08-01 --to 2026-08-31
    /opt/venv/bin/python -m scripts.garmin_sync --user-id 4     # one user only
"""
import argparse
import sys
from datetime import date, datetime, timedelta, timezone

from connectors.garmin import GarminReconnectError
from database import SessionLocal
import models
from routers.garmin import sync_hrv_for_user


def _resolve_window(args) -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    end = date.fromisoformat(args.to) if args.to else today
    if args.from_:
        start = date.fromisoformat(args.from_)
    else:
        start = end - timedelta(days=args.days)
    return start, end


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull Garmin HRV into hrv_readings/hrv_samples.")
    parser.add_argument("--days", type=int, default=7, help="Window length ending today (default 7).")
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
        q = db.query(models.UserIntegration).filter_by(provider="garmin")
        if args.user_id is not None:
            q = q.filter_by(user_id=args.user_id)
        user_ids = [row.user_id for row in q.all()]

        if not user_ids:
            print("No Garmin-connected users in scope.")
            return 0

        print(f"Syncing Garmin HRV for {len(user_ids)} user(s), {start}..{end}")
        failures = 0
        for uid in user_ids:
            try:
                result = sync_hrv_for_user(db, uid, start, end)
                print(f"  user {uid}: {result['readings_upserted']} readings, "
                      f"{result['samples_upserted']} samples "
                      f"({result['days_with_data']} days with data)")
            except GarminReconnectError as exc:
                failures += 1
                print(f"  user {uid}: RECONNECT NEEDED — {exc}", file=sys.stderr)
            except Exception as exc:  # noqa: BLE001 — one user's failure never aborts the sweep
                failures += 1
                print(f"  user {uid}: FAILED — {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1 if failures else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
