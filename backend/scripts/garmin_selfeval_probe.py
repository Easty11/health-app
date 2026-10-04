"""Does Garmin Connect send a self-evaluation (perceived effort / feel) on an activity? -- a READ-ONLY probe.

    /opt/venv/bin/python -m scripts.garmin_selfeval_probe --user-id 1
    /opt/venv/bin/python -m scripts.garmin_selfeval_probe --user-id 1 --limit 20 --activity-id 123456789

Built for Q209 (per-session sRPE capture at session save). `garminconnect` 0.3.11 has no named
self-evaluation field, but it returns Garmin's JSON unmodelled (`get_activity` and `get_activities`
are raw dicts; the typed `Activity` model allows extra keys), so a field Garmin sends is not
dropped. Whether Garmin SENDS one, under what key and on what scale is unverified; this prints it.

Two GET requests, nothing else:
  1. the recent-activity list (`/activitylist-service/activities/search/activities`, `--limit` items);
  2. ONE activity's detail record (`/activity-service/activity/{id}`; `--activity-id`, else the
     most recent listed activity).
Every key anywhere in those payloads whose NAME matches `rpe|feel|eval` (case-insensitive) is
printed as `path = value`. Nothing else from a payload is printed: no other key and no other
value, only an activity id, its local start DATE and its type key, so a hit can be identified.

Read-only, and enforced rather than promised, on the same seam as `scripts/garmin_identity.py`
(#361): the source subclasses its `LibrarySource`, so
  * the Garmin token is NEVER refreshed (`_refresh_session` is replaced on the instance with one
    that raises; both refresh paths route through it). An expiring token is reported as needing
    a refresh with the workaround, and exits 2: open the app's Garmin card (it refreshes AND saves),
    then re-run;
  * no database write (one SELECT, rolled back on close); the token is decrypted in memory and
    never printed; no Hevy call;
  * a failed fetch prints the error CLASS only; output is pure ASCII (FEEDBACK section 30).

READ A NEGATIVE NARROWLY (FEEDBACK section 17). "No matching key" means none in THESE payloads. An
activity the operator never rated may simply omit the key, so a negative from unrated activities
proves nothing about rated ones. Rate one activity in Garmin Connect first, then re-run with its
`--activity-id`: the hit on a known rating is the positive control, and gives the scale by
comparing the printed value with what was entered.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from sqlalchemy import text

from scripts.garmin_identity import LibrarySource, RefreshWouldBeNeeded

# The two library endpoints this reads, pinned to 0.3.11's own attributes by a value-guard test.
ACTIVITY_LIST_PATH = "/activitylist-service/activities/search/activities"
ACTIVITY_PATH = "/activity-service/activity"

KEY_PATTERN = re.compile(r"rpe|feel|eval", re.IGNORECASE)
MAX_LIMIT = 50
_VALUE_CHARS = 120


class ProbeSource(LibrarySource):
    """`LibrarySource` (no-refresh client) plus a generic GET, with the same token-unchanged check."""

    def get(self, path: str, params: dict[str, str] | None = None) -> Any:
        data = self._client.connectapi(path, params=params) if params else self._client.connectapi(path)
        if (self._client.di_token, self._client.di_refresh_token) != self._before:
            raise RuntimeError("token changed in memory during a probe fetch")
        return data


def scan(obj: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Every (path, value) whose key name matches `KEY_PATTERN`, anywhere in a JSON structure.

    A matching key is reported with its whole value and NOT descended into, so a container such as
    `selfEvaluation: {...}` is one hit. Lists are indexed (`splits[2].x`)."""
    hits: list[tuple[str, Any]] = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if KEY_PATTERN.search(str(key)):
                hits.append((path, val))
            else:
                hits.extend(scan(val, path))
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            hits.extend(scan(val, f"{prefix}[{i}]"))
    return hits


def _ascii(s: str) -> str:
    return s.encode("ascii", "backslashreplace").decode("ascii")


def render_value(val: Any) -> str:
    s = json.dumps(val, default=str, ensure_ascii=True)
    return s if len(s) <= _VALUE_CHARS else s[:_VALUE_CHARS] + "...(truncated)"


def _ident(item: Any) -> dict[str, str]:
    """An activity's id, local start DATE (not time) and type key: enough to find it, no more."""
    if not isinstance(item, dict):
        return {"id": "?", "date": "?", "type": "?"}
    atype = item.get("activityType")
    return {
        "id": str(item.get("activityId", "?")),
        "date": str(item.get("startTimeLocal") or "?")[:10],
        "type": str((atype or {}).get("typeKey", "?")) if isinstance(atype, dict) else "?",
    }


def probe(source: ProbeSource, *, limit: int, activity_id: str | None) -> dict[str, Any]:
    """Two GETs: the recent-activity list, then one activity's detail record."""
    listed = source.get(ACTIVITY_LIST_PATH, {"start": "0", "limit": str(limit)})
    items = listed if isinstance(listed, list) else []
    rows = [{**_ident(it), "hits": scan(it)} for it in items]
    target = activity_id or (rows[0]["id"] if rows and rows[0]["id"] != "?" else None)
    detail = None
    if target is not None:
        raw = source.get(f"{ACTIVITY_PATH}/{target}")
        meta = next((r for r in rows if r["id"] == target), None)
        detail = {
            "id": target,
            "date": meta["date"] if meta else "?",
            "type": meta["type"] if meta else "?",
            "hits": scan(raw),
        }
    return {"listed": rows, "detail": detail}


def format_report(result: dict[str, Any], target: str) -> str:
    out: list[str] = [f"Target database: {target}", ""]
    rows = result["listed"]
    out.append(f"Activity list: {len(rows)} activities.")
    for r in rows:
        out.append(f"  activity {r['id']}  {r['date']}  {r['type']}: "
                   + (f"{len(r['hits'])} matching key(s)" if r["hits"] else "no matching key"))
        for path, val in r["hits"]:
            out.append(f"      {path} = {render_value(val)}")
    out.append("")
    d = result["detail"]
    if d is None:
        out.append("Activity detail: not fetched (the list was empty and no --activity-id was given).")
    else:
        out.append(f"Activity detail: activity {d['id']}  {d['date']}  {d['type']}: "
                   + (f"{len(d['hits'])} matching key(s)" if d["hits"] else "no matching key"))
        for path, val in d["hits"]:
            out.append(f"      {path} = {render_value(val)}")
    anywhere = any(r["hits"] for r in rows) or bool(d and d["hits"])
    out.append("")
    if not anywhere:
        out.append("NEGATIVE, narrowly: no key matching rpe|feel|eval in these payloads. An activity with no"
                   " rating entered may omit the key, so this does not show the field is absent for a rated"
                   " one. Rate one activity in Garmin Connect, then re-run with its --activity-id.")
    out.append("READ-ONLY: nothing was written, no token was refreshed, no Hevy call was made;"
               " two GET requests (the activity list, one activity detail).")
    return "\n".join(out)


def fetch_blob(conn, user_id: int) -> str | None:
    """The user's stored Garmin token blob, decrypted in memory (never printed). One SELECT."""
    from encryption import decrypt

    row = conn.execute(
        text("SELECT api_key_encrypted FROM user_integrations WHERE user_id = :u AND provider = 'garmin'"),
        {"u": user_id},
    ).first()
    return None if row is None else decrypt(row[0])


def main(argv: list[str] | None = None, *, factory=ProbeSource) -> int:
    p = argparse.ArgumentParser(description="Read-only probe for Garmin activity self-evaluation fields.")
    p.add_argument("--user-id", type=int, required=True)
    p.add_argument("--limit", type=int, default=10, help=f"activities to list (1-{MAX_LIMIT}; default 10)")
    p.add_argument("--activity-id", default=None, help="fetch this activity's detail instead of the most recent")
    args = p.parse_args(argv)
    if not 1 <= args.limit <= MAX_LIMIT:
        p.error(f"--limit must be 1-{MAX_LIMIT}")
    if args.activity_id is not None and not re.fullmatch(r"\d{1,20}", args.activity_id):
        p.error("--activity-id must be digits only")

    import database

    engine = database.engine
    with engine.connect() as conn:  # SELECT only; rolls back on close
        blob = fetch_blob(conn, args.user_id)
    url = engine.url
    target = (f"sqlite file={url.database}" if engine.dialect.name == "sqlite"
              else f"{engine.dialect.name} host={url.host} port={url.port} db={url.database}")
    if blob is None:
        print(f"Target database: {target}\n\nuser {args.user_id} has no Garmin connection; nothing was fetched.")
        return 1
    try:
        result = probe(factory(blob), limit=args.limit, activity_id=args.activity_id)
    except RefreshWouldBeNeeded:
        print("Garmin token needs a refresh, and a fetch would refresh it (and may rotate the stored token)."
              " Nothing was sent. Open the app's Garmin card (it refreshes and saves), then re-run.")
        return 2
    except Exception as exc:  # noqa: BLE001 -- the error CLASS is the whole report
        print(f"Garmin fetch failed: {type(exc).__name__}")
        return 1
    print(_ascii(format_report(result, target)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
