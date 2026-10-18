"""Garmin overnight SpO2 backfill: walk back as far as the sleep endpoint returns SpO2 (Q150).

    /opt/venv/bin/python -m scripts.garmin_spo2_backfill --user-id 1 --dry-run
    /opt/venv/bin/python -m scripts.garmin_spo2_backfill --user-id 1

Run in the prod container from /app (`railway ssh --service health-app-backend`), after the migration has
applied. Starting at the newest wake-date and going backward one night at a time, it asks the sleep
endpoint for each night and stores what carries SpO2, through exactly the writer the nightly sweep uses
(`garmin_spo2.store_night`). It stops when `--stop-after-empty` nights IN A ROW carry no SpO2 (the point
where the watch's Pulse Ox sleep tracking begins, or where the endpoint stops returning history), when
`--max-days` nights have been tried, or at the first failure. It then REPORTS how far back the data went:
the earliest and latest night with SpO2, how many nights and epochs, and why it stopped. That report is
the answer to "how far does the endpoint return history".

Safe to run and re-run:
  * IDEMPOTENT. A night already stored with an identical payload is left untouched (no write); a night
    whose payload differs is replaced; a night with no SpO2 changes nothing.
  * NO REFRESH. Like `garmin_selfeval_probe` it reads through the no-refresh client: a token that needs a
    refresh stops the run (exit 2) before anything is sent. Open the app's Garmin card (it refreshes AND
    saves), then re-run.
  * `--dry-run` fetches and reports but writes nothing to the database.
  * READ-ONLY toward Garmin (GET only), throttled (`--pause` seconds between nights, default 1.0), and the
    token, the display name, the Garmin profile id and the device id are never printed. Output is ASCII.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from typing import Any, Callable

import garmin_spo2
import models
from database import SessionLocal
from encryption import decrypt
from routers.garmin import garmin_wake_day
from scripts.garmin_identity import RefreshWouldBeNeeded

DEFAULT_MAX_DAYS = 1100          # about three years
DEFAULT_STOP_AFTER_EMPTY = 21    # consecutive nights with no SpO2 before the walk concludes it has run out
DEFAULT_PAUSE_S = 1.0


def backfill(db, user_id: int, source, *, newest: date, max_days: int = DEFAULT_MAX_DAYS,
             stop_after_empty: int = DEFAULT_STOP_AFTER_EMPTY, pause: float = DEFAULT_PAUSE_S,
             dry_run: bool = False, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Walk back from `newest`; return the report. `stopped` is one of 'empty_streak', 'max_days',
    'needs_refresh', or 'error:<ExceptionClass>'."""
    rep: dict[str, Any] = {"nights_tried": 0, "nights_with_spo2": 0, "nights_inserted": 0, "nights_replaced": 0,
                           "nights_unchanged": 0, "epochs": 0, "gaps": 0, "earliest": None, "latest": None,
                           "stopped": "max_days"}
    empty_run = 0
    path = None
    try:
        path = garmin_spo2.display_name_path(source)
        d = newest
        for i in range(max_days):
            if i:
                sleep(pause)
            night = garmin_spo2.fetch_night(source, path, d)
            rep["nights_tried"] += 1
            if night is None:
                empty_run += 1
                if empty_run >= stop_after_empty:
                    rep["stopped"] = "empty_streak"
                    break
            else:
                empty_run = 0
                rep["nights_with_spo2"] += 1
                rep["epochs"] += night["reading_count"]
                rep["gaps"] += night["gap_count"]
                rep["earliest"] = d if rep["earliest"] is None or d < rep["earliest"] else rep["earliest"]
                rep["latest"] = d if rep["latest"] is None or d > rep["latest"] else rep["latest"]
                if not dry_run:
                    rep[f"nights_{garmin_spo2.store_night(db, user_id, night)}"] += 1
            d -= timedelta(days=1)
    except RefreshWouldBeNeeded:
        db.rollback()
        rep["stopped"] = "needs_refresh"
    except Exception as exc:  # noqa: BLE001 -- the error CLASS is the whole report
        db.rollback()
        rep["stopped"] = f"error:{type(exc).__name__}"
    return rep


def format_report(rep: dict[str, Any], *, user_id: int, newest: date, dry_run: bool) -> str:
    lines = [f"Garmin overnight SpO2 backfill, user {user_id}, walking back from {newest.isoformat()}"
             + ("  [DRY RUN: nothing written]" if dry_run else ""),
             f"  nights tried: {rep['nights_tried']}   with SpO2: {rep['nights_with_spo2']}   "
             f"epochs: {rep['epochs']}   gaps: {rep['gaps']}"]
    if rep["earliest"] is not None:
        span = (rep["latest"] - rep["earliest"]).days + 1
        lines.append(f"  history with SpO2: {rep['earliest'].isoformat()} -> {rep['latest'].isoformat()} "
                     f"({span} calendar days, {rep['nights_with_spo2']} nights with data)")
    else:
        lines.append("  history with SpO2: none found")
    if not dry_run:
        lines.append(f"  stored: inserted {rep['nights_inserted']}, replaced {rep['nights_replaced']}, "
                     f"unchanged {rep['nights_unchanged']}")
    lines.append(f"  stopped: {rep['stopped']}")
    if rep["stopped"] == "needs_refresh":
        lines.append("  The token needs a refresh and a fetch would refresh it. Nothing further was sent. Open the "
                     "app's Garmin card (it refreshes AND saves), then re-run; the walk resumes safely.")
    elif rep["stopped"] == "max_days":
        lines.append("  The cap was reached while data was still being returned: re-run with a larger --max-days "
                     "to go further back.")
    return "\n".join(lines)


def main(argv: list[str] | None = None, *, factory=None, sleep: Callable[[float], None] = time.sleep) -> int:
    p = argparse.ArgumentParser(description="Backfill Garmin overnight SpO2 as far as the endpoint returns it.")
    p.add_argument("--user-id", type=int, required=True)
    p.add_argument("--newest", help="newest wake-date to try (YYYY-MM-DD); default: today's Brisbane wake-day")
    p.add_argument("--max-days", type=int, default=DEFAULT_MAX_DAYS)
    p.add_argument("--stop-after-empty", type=int, default=DEFAULT_STOP_AFTER_EMPTY)
    p.add_argument("--pause", type=float, default=DEFAULT_PAUSE_S)
    p.add_argument("--dry-run", action="store_true", help="fetch and report; write nothing")
    args = p.parse_args(argv)
    if args.max_days < 1 or args.stop_after_empty < 1 or args.pause < 0:
        p.error("--max-days and --stop-after-empty must be >= 1 and --pause >= 0")
    try:
        newest = date.fromisoformat(args.newest) if args.newest else garmin_wake_day()
    except ValueError:
        p.error("--newest must be YYYY-MM-DD")

    db = SessionLocal()
    try:
        row = db.query(models.UserIntegration).filter_by(user_id=args.user_id, provider="garmin").first()
        if row is None:
            print(f"user {args.user_id} has no Garmin connection; nothing fetched.")
            return 1
        try:
            source = (factory or garmin_spo2.ProbeSource)(decrypt(row.api_key_encrypted))
        except Exception as exc:  # noqa: BLE001 -- class only
            print(f"could not build the Garmin client: {type(exc).__name__}")
            return 1
        rep = backfill(db, args.user_id, source, newest=newest, max_days=args.max_days,
                       stop_after_empty=args.stop_after_empty, pause=args.pause, dry_run=args.dry_run, sleep=sleep)
    finally:
        db.close()
    print(format_report(rep, user_id=args.user_id, newest=newest, dry_run=args.dry_run)
          .encode("ascii", "backslashreplace").decode("ascii"))
    if rep["stopped"] == "needs_refresh":
        return 2
    return 1 if rep["stopped"].startswith("error:") else 0


if __name__ == "__main__":
    sys.exit(main())
