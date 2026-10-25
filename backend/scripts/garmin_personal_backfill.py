"""One-shot Garmin Personal API backfill for one user (S3). DRY RUN BY DEFAULT.

    /opt/venv/bin/python -m scripts.garmin_personal_backfill --user-id 1                   # dry run
    /opt/venv/bin/python -m scripts.garmin_personal_backfill --user-id 1 --confirm         # writes
    /opt/venv/bin/python -m scripts.garmin_personal_backfill --user-id 1 --remap --from 2026-09-01 --to 2026-10-25 --confirm

Walks NEWEST -> OLDEST from `--newest` (default the Brisbane wake-day) and stops after `--stop-after-empty`
consecutive days on which EVERY wellness endpoint returned nothing (default 30): the personal API has no
observed lookback cap, so "the earliest date Garmin returns" is where the data stops, not a fixed floor.
HRV is walked on the same days. Requests are paced by the client (2 s apart on the real host: a burst got 429, 12 requests 2 s apart all 200). Idempotent (raw landing keys on
the payload hash; the mappers upsert), so an interrupted run is resumed by running it again.

A dry run fetches and counts but writes no data (no raw payload, no table row; only the cached bearer token may be refreshed). `--remap` re-runs
the mappers over what is already LANDED for the window, with no network: the recovery after a mapper fix.
Activities are out of scope (HC and hevy_mirror are unchanged), as is FIT download.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta
from typing import Any, Callable

import garmin_personal_lanes as gpl
import garmin_raw
import garmin_wellness
from connectors import garmin_personal as gp
from connectors.garmin import normalize_hrv_day
from database import SessionLocal
from routers.garmin import _upsert_hrv_day, garmin_wake_day


def _day_has_data(client: gp.PersonalClient, ref: str) -> dict[str, Any]:
    """Fetch every endpoint for one day; `{endpoint: payload}` for those with data (HRV included)."""
    got: dict[str, Any] = {}
    hrv = client.hrv_day(ref)
    if not garmin_wellness._is_empty(hrv):
        got["hrv"] = hrv
    for ep in garmin_wellness.DAY_ENDPOINTS:
        payload = garmin_wellness._FETCH[ep](client, ref)
        if not garmin_wellness._is_empty(payload):
            got[ep] = payload
    return got


def backfill(db, user_id: int, client: gp.PersonalClient, *, newest: date, stop_after_empty: int, confirm: bool,
             pause: float = 0.0, floor: date = date(2020, 1, 1),
             sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    out = {"days_walked": 0, "days_with_data": 0, "oldest_with_data": None, "newest_with_data": None,
           "stopped": "floor", "payloads_landed": 0, "hrv_nights": 0, "mapped": garmin_wellness._new_counts()}
    empty_streak = 0
    d = newest
    while d >= floor:
        ref = d.isoformat()
        got = _day_has_data(client, ref)
        out["days_walked"] += 1
        if not got:
            empty_streak += 1
            if empty_streak >= stop_after_empty:
                out["stopped"] = f"empty_streak_{stop_after_empty}"
                break
        else:
            empty_streak = 0
            out["days_with_data"] += 1
            out["oldest_with_data"] = ref
            out["newest_with_data"] = out["newest_with_data"] or ref
            if confirm:
                for ep, payload in got.items():
                    landed = garmin_raw.land(db, user_id, ep, ref, payload)
                    out["payloads_landed"] += int(landed.inserted)
                    if ep == "hrv":
                        night = normalize_hrv_day(landed.payload, ref)
                        if night is not None:
                            _upsert_hrv_day(db, user_id, "garmin", night, transport="personal_api", keep_existing=True)
                            out["hrv_nights"] += 1
                    else:
                        garmin_wellness.apply_payload(db, user_id, ep, ref, landed.payload, landed.sha256, out["mapped"])
                db.commit()
        d -= timedelta(days=1)
        sleep(pause)
    if confirm:
        zones = client.hr_zones()
        if not garmin_wellness._is_empty(zones):
            landed = garmin_raw.land(db, user_id, garmin_wellness.EP_HR_ZONES, "current", zones)
            garmin_wellness.apply_payload(db, user_id, garmin_wellness.EP_HR_ZONES, "current", landed.payload,
                                          landed.sha256, out["mapped"])
            db.commit()
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Garmin Personal API backfill (dry run unless --confirm).")
    p.add_argument("--user-id", type=int, required=True)
    p.add_argument("--confirm", action="store_true", help="write (default is a dry run)")
    p.add_argument("--newest", help="first (newest) day to walk, YYYY-MM-DD; default the Brisbane wake-day")
    p.add_argument("--stop-after-empty", type=int, default=30)
    p.add_argument("--pause", type=float, default=0.0, help="extra seconds between days (the client already paces requests)")
    p.add_argument("--remap", action="store_true", help="re-run mappers over landed payloads; no network")
    p.add_argument("--from", dest="from_", help="--remap window start")
    p.add_argument("--to", help="--remap window end")
    args = p.parse_args(argv)

    db = SessionLocal()
    try:
        if args.remap:
            if not (args.from_ and args.to):
                print("--remap needs --from and --to", file=sys.stderr)
                return 2
            if not args.confirm:
                print("remap is a write: add --confirm", file=sys.stderr)
                return 2
            counts = garmin_wellness.remap_user(db, args.user_id, start=date.fromisoformat(args.from_),
                                                end=date.fromisoformat(args.to))
            print(f"remapped: {counts}")
            return 0
        newest = date.fromisoformat(args.newest) if args.newest else garmin_wake_day()
        try:
            with gpl.personal_client(db, args.user_id) as client:
                if client is None:
                    print(f"user {args.user_id} has no garmin_personal key", file=sys.stderr)
                    return 1
                result = backfill(db, args.user_id, client, newest=newest,
                                  stop_after_empty=args.stop_after_empty, confirm=args.confirm, pause=args.pause)
        except gp.PersonalApiError as exc:
            db.rollback()
            print(f"STOPPED: {type(exc).__name__}: {exc} (re-run to resume)", file=sys.stderr)
            return 1
        print(("WROTE" if args.confirm else "DRY RUN (nothing written)") + f": {result}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
