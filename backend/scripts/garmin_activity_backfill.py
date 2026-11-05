"""Garmin activity metrics + activity HR stream backfill for one user. DRY RUN BY DEFAULT.

    /opt/venv/bin/python -m scripts.garmin_activity_backfill --user-id 1                  # dry run
    /opt/venv/bin/python -m scripts.garmin_activity_backfill --user-id 1 --limit 5        # a quick dry run
    /opt/venv/bin/python -m scripts.garmin_activity_backfill --user-id 1 --confirm        # writes

Operator-run, in `railway ssh --service health-app-backend`, from `/app`. Walks the Personal API activity
list from `--since` (default 2026-03-01), oldest first, 50 a page, and per activity makes at most two GETs
through the same `PersonalClient` the nightly lane uses (paced 2 s apart on the real host):

  1. the activity DETAIL -> its `summaryDTO` -> `garmin_activity_metrics` (`upsert_metrics`), skipped when
     the activity already has a metrics row;
  2. the DETAILS stream -> `directHeartRate` by `directTimestamp` -> `hr_samples` as `garmin` /
     `activity_details` (ruling R2; `capture_stream`), skipped when the stream was already captured.

Idempotent: a re-run skips what is captured and the sample write is insert-or-ignore, so an interrupted run
is resumed by running it again. A dry run makes the same GETs and writes NOTHING (no row, no sample, no
token). Prints COUNTS only, never a payload value; the thinning report (`thinned`, the median effective
interval in seconds) is how the details endpoint's resolution is recorded.

TOKEN GUARD (the probe's, on the Personal API's own token). This script never exchanges the key outside the
existing path: when the cached bearer token would need an exchange it STOPS before any request (exit 2) and
says where the app refreshes and saves it; and if the token changes in memory during the walk (a 401 forced a
re-exchange), it stops at once. The client is the lane's own (`garmin_personal_lanes.personal_client`), which
writes any token it holds back encrypted on exit.
"""
from __future__ import annotations

import argparse
import statistics
import sys
from datetime import date, datetime, timezone
from typing import Any, Optional

import garmin_activity_metrics as gam
import garmin_personal_lanes as gpl
import models
from connectors import garmin_personal as gp
from scripts.garmin_selfeval_probe import REFRESH_HINT

DEFAULT_SINCE = date(2026, 3, 1)
PAGE = 50
MAX_PAGES = 200


class RefreshWouldBeNeeded(Exception):
    """The cached bearer token would be re-exchanged by the next request."""


class GuardedSource:
    """`get(path, params)` over the lane's client, refusing to start on a token that needs an exchange and
    stopping if the token changes during a fetch (the probe's token-unchanged check)."""

    def __init__(self, client: gp.PersonalClient):
        if not client.token_usable():
            raise RefreshWouldBeNeeded()
        self._client = client
        self._before = client.token_state()[0]

    def get(self, path: str, params: Optional[dict[str, str]] = None) -> Any:
        data = self._client.get(path, params)
        if self._client.token_state()[0] != self._before:
            raise RuntimeError("token changed in memory during a backfill fetch")
        return data


def _new_counts() -> dict[str, Any]:
    return {"activities_listed": 0, "already_captured": 0, "details_fetched": 0, "metrics_found": 0,
            "metrics_written": 0, "detail_shape_errors": 0, "streams_fetched": 0, "streams_with_hr": 0,
            "samples_found": 0, "samples_written": 0, "null_bpm": 0, "thinned": 0, "param_fallback": 0,
            "median_interval_s": None, "stopped": "end_of_list"}


def _list_items(listed: Any) -> list[tuple[int, Optional[datetime], Optional[float]]]:
    out = []
    for it in listed if isinstance(listed, list) else []:
        if not isinstance(it, dict):
            continue
        aid = it.get("activityId")
        if isinstance(aid, bool) or not isinstance(aid, int):
            continue
        dur = it.get("duration")
        out.append((aid, gam._parse_gmt(it.get("startTimeGMT")),
                    float(dur) if isinstance(dur, (int, float)) and not isinstance(dur, bool) else None))
    return out


def backfill(db, user_id: int, source: Any, *, since: date, confirm: bool, limit: Optional[int] = None,
             now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    out = _new_counts()
    intervals: list[float] = []
    seen: set[int] = set()
    have = {r.garmin_activity_id: r for r in
            db.query(models.GarminActivityMetric).filter_by(user_id=user_id).all()}
    done = False
    for page in range(MAX_PAGES):
        listed = source.get(gp.ACTIVITY_LIST_PATH, {"startDate": since.isoformat(), "start": str(page * PAGE),
                                                    "limit": str(PAGE), "sortOrder": "asc"})
        items = _list_items(listed)
        fresh = [i for i in items if i[0] not in seen]
        if not fresh:
            break
        for aid, start, dur in fresh:
            seen.add(aid)
            if limit is not None and out["activities_listed"] >= limit:
                out["stopped"] = f"limit_{limit}"
                done = True
                break
            out["activities_listed"] += 1
            row = have.get(aid)
            if row is not None and row.hr_stream_fetched_at is not None:
                out["already_captured"] += 1
                continue
            if row is None:
                detail = source.get(f"{gp.ACTIVITY_PATH}/{aid}")
                out["details_fetched"] += 1
                if gam.parse_metrics(detail.get("summaryDTO") if isinstance(detail, dict) else None,
                                     start=start, duration_s=dur) is None:
                    out["detail_shape_errors"] += 1          # no summaryDTO object: nothing to place a stream on
                    continue
                out["metrics_found"] += 1
                if confirm:
                    gam.upsert_metrics(db, user_id, aid, detail, now=now, start=start, duration_s=dur)
                    db.flush()
                    row = db.query(models.GarminActivityMetric).filter_by(
                        user_id=user_id, garmin_activity_id=aid).first()
                    out["metrics_written"] += 1
            if confirm:
                res = gam.capture_stream(db, user_id, source, row, now=now)
                db.commit()
                found, written, thinned, fallback, interval, has_hr = (
                    res["found"], res["stored"], res["thinned"], res["param_fallback"], res["interval_s"], res["has_hr"])
                nulls = None
            else:
                parsed, fallback = gam.read_stream(source, aid)
                found, written, thinned, interval, has_hr = (
                    len(parsed.samples), 0, parsed.thinned, parsed.interval_s, parsed.has_hr)
                nulls = parsed.null_bpm
            out["streams_fetched"] += 1
            out["streams_with_hr"] += int(found > 0)
            out["samples_found"] += found
            out["samples_written"] += written
            out["null_bpm"] += nulls or 0
            out["thinned"] += int(thinned)
            out["param_fallback"] += int(fallback)
            if interval is not None:
                intervals.append(interval)
        if done or len(items) < PAGE:
            break
    else:
        out["stopped"] = f"max_pages_{MAX_PAGES}"
    out["median_interval_s"] = statistics.median(intervals) if intervals else None
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Garmin activity metrics + HR stream backfill (dry run unless --confirm).")
    p.add_argument("--user-id", type=int, required=True)
    p.add_argument("--since", default=DEFAULT_SINCE.isoformat(), help="first activity date, YYYY-MM-DD")
    p.add_argument("--limit", type=int, default=None, help="stop after this many listed activities")
    p.add_argument("--confirm", action="store_true", help="write (default is a dry run)")
    args = p.parse_args(argv)
    since = date.fromisoformat(args.since)

    from database import SessionLocal

    db = SessionLocal()
    try:
        try:
            with gpl.personal_client(db, args.user_id) as client:
                if client is None:
                    print(f"user {args.user_id} has no garmin_personal key; nothing was fetched.", file=sys.stderr)
                    return 1
                result = backfill(db, args.user_id, GuardedSource(client), since=since, confirm=args.confirm,
                                  limit=args.limit)
        except RefreshWouldBeNeeded:
            db.rollback()
            print("Garmin token needs a refresh, and a fetch would refresh it. Nothing was sent. " + REFRESH_HINT)
            return 2
        except Exception as exc:  # noqa: BLE001 -- the error CLASS is the whole report
            db.rollback()
            print(f"STOPPED: {type(exc).__name__} (re-run to resume; what was written stays)", file=sys.stderr)
            return 1
        print(("WROTE" if args.confirm else "DRY RUN (nothing written)") + f": {result}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
