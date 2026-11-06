"""Does the Garmin Personal API serve recovery time? A READ-ONLY probe of two daily endpoints.

    /opt/venv/bin/python -m scripts.garmin_readiness_probe --user-id 1
    /opt/venv/bin/python -m scripts.garmin_readiness_probe --user-id 1 --date 2026-11-06

Recovery hours are not on the activity record: the 6 Nov 2026 key read of every stored `summaryDTO` (74
keys) has none, only `recoveryHeartRate` (a heart rate). In Garmin Connect they come from the watch's
training readiness / training status. This asks the Personal API host for the two endpoints the
`garminconnect` 0.3.11 library uses for those (`get_training_readiness`, `get_training_status`), for one
date (default today, UTC):

  1. `/metrics-service/metrics/trainingreadiness/{date}`
  2. `/metrics-service/metrics/trainingstatus/aggregated/{date}`

For each it prints the payload's shape and KEY NAMES (a list: its length and the first item's keys), and
every key whose name matches `recovery` (case-insensitive) as `path = value`, which is the question. No other
value is printed. A 404 says the host does not serve that endpoint (or has nothing for the date); any other
failure prints its error class only.

Read-only and guarded as the activity backfill is (`GuardedSource`): two GETs through the lane's own
`PersonalClient`; it refuses to start when the cached bearer token would need an exchange (exit 2, naming
where the app refreshes and saves it), and stops if the token changes during a fetch. No database write.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from typing import Any

import garmin_personal_lanes as gpl
from connectors import garmin_personal as gp
from scripts.garmin_activity_backfill import GuardedSource, RefreshWouldBeNeeded
from scripts.garmin_selfeval_probe import REFRESH_HINT

READINESS_PATH = "/metrics-service/metrics/trainingreadiness/{date}"
STATUS_PATH = "/metrics-service/metrics/trainingstatus/aggregated/{date}"
RECOVERY_KEY = re.compile(r"recovery", re.IGNORECASE)
_VALUE_CHARS = 120


def recovery_hits(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Every (path, value) whose key matches `recovery`, at any depth; a matching key is not descended into."""
    hits: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            if RECOVERY_KEY.search(str(k)):
                hits.append((path, v))
            else:
                hits.extend(recovery_hits(v, path))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(recovery_hits(v, f"{prefix}[{i}]"))
    return hits


def _shape(payload: Any) -> str:
    if isinstance(payload, list):
        first = payload[0] if payload else None
        keys = sorted(first) if isinstance(first, dict) else []
        return f"list of {len(payload)}; first item keys ({len(keys)}): {', '.join(keys) or '(none)'}"
    if isinstance(payload, dict):
        keys = sorted(payload)
        return f"object; keys ({len(keys)}): {', '.join(keys) or '(none)'}"
    return "empty body" if payload is None else type(payload).__name__


def _value(v: Any) -> str:
    s = json.dumps(v, default=str, ensure_ascii=True)
    return s if len(s) <= _VALUE_CHARS else s[:_VALUE_CHARS] + "...(truncated)"


def probe(source: Any, day: date) -> list[str]:
    lines = []
    for name, template in (("training readiness", READINESS_PATH), ("training status", STATUS_PATH)):
        path = template.format(date=day.isoformat())
        try:
            payload = source.get(path)
        except gp.PersonalNotFound:
            lines.append(f"{name} ({path}): 404 (not served, or nothing for {day})")
            continue
        except gp.PersonalApiError as exc:
            lines.append(f"{name} ({path}): fetch failed: {type(exc).__name__}")
            continue
        lines.append(f"{name} ({path}): {_shape(payload)}")
        hits = recovery_hits(payload)
        lines.extend(f"    {p} = {_value(v)}" for p, v in hits)
        if not hits:
            lines.append("    no key matching 'recovery'")
    return lines


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Read-only probe: does the Personal API serve recovery time?")
    p.add_argument("--user-id", type=int, required=True)
    p.add_argument("--date", default=None, help="YYYY-MM-DD (default today, UTC)")
    args = p.parse_args(argv)
    day = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    from database import SessionLocal

    db = SessionLocal()
    try:
        with gpl.personal_client(db, args.user_id) as client:
            if client is None:
                print(f"user {args.user_id} has no garmin_personal key; nothing was fetched.")
                return 1
            try:
                lines = probe(GuardedSource(client), day)
            except RefreshWouldBeNeeded:
                print("Garmin token needs a refresh, and a fetch would refresh it. Nothing was sent. " + REFRESH_HINT)
                return 2
    finally:
        db.rollback()
        db.close()
    print("\n".join(lines))
    print("READ-ONLY: two GET requests at most, nothing written, no token exchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
