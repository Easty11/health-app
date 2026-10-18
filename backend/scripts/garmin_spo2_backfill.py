"""Garmin overnight SpO2 backfill: walk back through the sleep endpoint, gently (Q150).

    /opt/venv/bin/python -m scripts.garmin_spo2_backfill --user-id 1 --dry-run
    /opt/venv/bin/python -m scripts.garmin_spo2_backfill --user-id 1

Run in the prod container from /app (`railway ssh --service health-app-backend`), after the migration has
applied. Starting at the newest wake-date and going backward one night at a time, it asks the sleep
endpoint for each night and stores what carries SpO2, through exactly the writer the nightly sweep uses
(`garmin_spo2.store_night`). It then REPORTS the earliest and latest night with SpO2 it found, the LAST DATE
IT REACHED, and why it stopped.

WHY IT STOPS, and what each stop does and does not mean:
  * `stopped at empty streak`: `--stop-after-empty` nights IN A ROW carried no SpO2. This is NOT evidence that
    the history ends there. A stretch with Pulse Ox switched off looks identical to the edge of the history,
    so the report says so and prints the `--newest` to resume from. Nothing is concluded about what lies beyond.
  * `ABORTED`: Garmin answered HTTP 429, HTTP 403, or a page that was not JSON (a Cloudflare challenge). The run
    stops at once, retries nothing, and prints the last date it reached. Wait hours, not minutes, then resume.
  * the `--max-days` cap (default 1,100 nights), the first other error, or a stale token (exit 2).

Safe to run and re-run:
  * IDEMPOTENT. A night already stored with an identical payload is left untouched (no write); a night
    whose payload differs is replaced; a night with no SpO2 changes nothing.
  * NO REFRESH. Like `garmin_selfeval_probe` it reads through the no-refresh client: a token that needs a
    refresh stops the run (exit 2) before anything is sent. Open the app's Garmin card (it refreshes AND
    saves), then re-run.
  * `--dry-run` fetches and reports but writes nothing to the database.
  * GENTLE. At least 3 seconds between nights (the default, and a floor the command line enforces), GET only,
    and no retry of any kind. The token, the display name, the Garmin profile id and the device id are never
    printed. Output is ASCII.

Exit codes: 0 finished (any stop that is not a failure), 1 error or no Garmin connection, 2 the token needs a
refresh, 3 aborted on a 429 / 403 / challenge.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, timedelta
from typing import Any, Callable

from garminconnect import GarminConnectTooManyRequestsError

import garmin_spo2
import models
from database import SessionLocal
from encryption import decrypt
from routers.garmin import garmin_wake_day
from scripts.garmin_identity import RefreshWouldBeNeeded

DEFAULT_MAX_DAYS = 1100          # about three years
DEFAULT_STOP_AFTER_EMPTY = 21    # consecutive nights with no SpO2 before the walk stops (NOT "history ends")
MIN_PAUSE_S = 3.0                # the floor the command line enforces between nights
DEFAULT_PAUSE_S = 3.0

# On the data path `garminconnect` 0.3.11 raises a plain GarminConnectConnectionError("API Error <status> ...") for
# every status >= 400 except 404, so the status is read out of the message. A challenge page arrives as a 403 or as a
# 200 whose body is not JSON (the library's `.json()` then raises a JSONDecodeError). A bare ValueError is NOT
# treated as a block: the library also raises one for an invalid path or date, which is a bug here, not a challenge.
_STATUS_RE = re.compile(r"\bAPI Error (429|403)\b")
_STATUS_WORDS = {"429": "HTTP 429 (rate limited)", "403": "HTTP 403 (forbidden, possibly a Cloudflare challenge)"}


def classify_block(exc: BaseException) -> str | None:
    """A short description when `exc` is Garmin pushing back (429, 403, or a non-JSON page), else None."""
    if isinstance(exc, GarminConnectTooManyRequestsError):
        return _STATUS_WORDS["429"]
    m = _STATUS_RE.search(str(exc))
    if m:
        return _STATUS_WORDS[m.group(1)]
    if isinstance(exc, json.JSONDecodeError) or type(exc).__name__ == "JSONDecodeError":
        return "a response that was not JSON (possibly a Cloudflare challenge page)"
    return None


def backfill(db, user_id: int, source, *, newest: date, max_days: int = DEFAULT_MAX_DAYS,
             stop_after_empty: int = DEFAULT_STOP_AFTER_EMPTY, pause: float = DEFAULT_PAUSE_S,
             dry_run: bool = False, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Walk back from `newest`; return the report.

    `stopped` is one of 'empty_streak', 'max_days', 'needs_refresh', 'blocked' (a 429 / 403 / challenge, with the
    description in `block`) or 'error:<ExceptionClass>'. `last_date_reached` is the OLDEST night whose fetch
    completed (data or none); `failed_on` is the night being fetched when a failure stopped the walk. No failure is
    retried."""
    rep: dict[str, Any] = {"nights_tried": 0, "nights_with_spo2": 0, "nights_inserted": 0, "nights_replaced": 0,
                           "nights_unchanged": 0, "epochs": 0, "gaps": 0, "earliest": None, "latest": None,
                           "last_date_reached": None, "failed_on": None, "block": None, "empty_run": 0,
                           "stopped": "max_days"}
    empty_run = 0
    d = newest
    try:
        path = garmin_spo2.display_name_path(source)
        for i in range(max_days):
            if i:
                sleep(pause)
            night = garmin_spo2.fetch_night(source, path, d)
            rep["nights_tried"] += 1
            rep["last_date_reached"] = d
            if night is None:
                empty_run += 1
                rep["empty_run"] = empty_run
                if empty_run >= stop_after_empty:
                    rep["stopped"] = "empty_streak"
                    break
            else:
                empty_run = 0
                rep["empty_run"] = 0
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
    except Exception as exc:  # noqa: BLE001 -- the class (or the block description) is the whole report
        db.rollback()
        rep["failed_on"] = d
        block = classify_block(exc)
        if block is not None:
            rep["stopped"], rep["block"] = "blocked", block
        else:
            rep["stopped"] = f"error:{type(exc).__name__}"
    return rep


def format_report(rep: dict[str, Any], *, user_id: int, newest: date, dry_run: bool) -> str:
    lines = [f"Garmin overnight SpO2 backfill, user {user_id}, walking back from {newest.isoformat()}"
             + ("  [DRY RUN: nothing written]" if dry_run else ""),
             f"  nights tried: {rep['nights_tried']}   with SpO2: {rep['nights_with_spo2']}   "
             f"epochs: {rep['epochs']}   gaps: {rep['gaps']}"]
    if rep["earliest"] is not None:
        span = (rep["latest"] - rep["earliest"]).days + 1
        lines.append(f"  nights with SpO2 found: {rep['earliest'].isoformat()} -> {rep['latest'].isoformat()} "
                     f"({span} calendar days, {rep['nights_with_spo2']} nights with data)")
    else:
        lines.append("  nights with SpO2 found: none")
    if not dry_run:
        lines.append(f"  stored: inserted {rep['nights_inserted']}, replaced {rep['nights_replaced']}, "
                     f"unchanged {rep['nights_unchanged']}")
    reached = rep["last_date_reached"]
    lines.append(f"  last date reached: {reached.isoformat() if reached else 'none (nothing was fetched)'}")

    stopped = rep["stopped"]
    if stopped == "empty_streak":
        resume = (reached - timedelta(days=1)).isoformat()
        lines.append(f"  stopped at empty streak: {rep['empty_run']} nights in a row carried no SpO2.")
        lines.append("  This is NOT evidence that the history ends here: a stretch with Pulse Ox switched off looks the "
                     "same. Nothing is concluded about what lies further back.")
        lines.append(f"  To look further, run again with --newest {resume} (and a larger --stop-after-empty if the "
                     "gap may be longer).")
    elif stopped == "blocked":
        resume = rep["failed_on"].isoformat()
        lines.append(f"  ABORTED: Garmin answered {rep['block']} while fetching the night of {resume}.")
        lines.append("  Nothing was retried and the run stopped at once. Wait hours, not minutes, before trying "
                     f"again, then resume with --newest {resume}.")
    elif stopped == "needs_refresh":
        lines.append("  stopped: the token needs a refresh and a fetch would refresh it. Nothing further was sent. "
                     "Open the app's Garmin card (it refreshes AND saves), then re-run; the walk resumes safely.")
    elif stopped == "max_days":
        resume = ((reached or newest) - timedelta(days=1)).isoformat()
        lines.append("  stopped at the --max-days cap. Data may continue further back: re-run with --newest "
                     f"{resume} to go on.")
    else:  # error:<Class>
        lines.append(f"  stopped on an error ({stopped.split(':', 1)[1]}) while fetching the night of "
                     f"{rep['failed_on'].isoformat()}; nothing was retried.")
    return "\n".join(lines)


def main(argv: list[str] | None = None, *, factory=None, sleep: Callable[[float], None] = time.sleep) -> int:
    p = argparse.ArgumentParser(description="Backfill Garmin overnight SpO2 through the sleep endpoint, gently.")
    p.add_argument("--user-id", type=int, required=True)
    p.add_argument("--newest", help="newest wake-date to try (YYYY-MM-DD); default: today's Brisbane wake-day")
    p.add_argument("--max-days", type=int, default=DEFAULT_MAX_DAYS)
    p.add_argument("--stop-after-empty", type=int, default=DEFAULT_STOP_AFTER_EMPTY)
    p.add_argument("--pause", type=float, default=DEFAULT_PAUSE_S,
                   help=f"seconds between nights (minimum {MIN_PAUSE_S:g}, default {DEFAULT_PAUSE_S:g})")
    p.add_argument("--dry-run", action="store_true", help="fetch and report; write nothing")
    args = p.parse_args(argv)
    if args.max_days < 1 or args.stop_after_empty < 1:
        p.error("--max-days and --stop-after-empty must be >= 1")
    if args.pause < MIN_PAUSE_S:
        p.error(f"--pause must be at least {MIN_PAUSE_S:g} seconds (it is a politeness floor, not a tuning knob)")
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
    if rep["stopped"] == "blocked":
        return 3
    if rep["stopped"] == "needs_refresh":
        return 2
    return 1 if rep["stopped"].startswith("error:") else 0


if __name__ == "__main__":
    sys.exit(main())
