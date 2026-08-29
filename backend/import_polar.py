"""
Polar Flow ZIP-export ingest into aerobic_sessions.

The parsing / sport-name mapping / dedup core lives in `import_flow_export`, a
per-user callable shared by the in-app upload endpoint (`routers/polar.py`) and by
this CLI. The CLI is retained for ops / backfill runs; `--email` resolution is
CLI-only (the endpoint keys on the authenticated user, never an email parameter).

Usage (from backend/, venv activated):
    python import_polar.py --zip /path/to/polar-user-data-export.zip --email user@example.com
    python import_polar.py --zip ... --email ... --dry-run
"""
import argparse
import io
import json
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, BinaryIO, Union

from sqlalchemy.orm import Session

from database import SessionLocal
from models import AerobicSession, User

# A ZIP source the shared core accepts: raw bytes, a filesystem path, or a
# file-like object — anything `zipfile.ZipFile` opens, plus bytes (wrapped here).
ZipSource = Union[bytes, bytearray, str, BinaryIO]

# Polar sport ID → human name. IDs not listed here will have sport_name=None.
SPORT_NAMES: dict[str, str] = {
    "1": "Running",
    "2": "Cycling",
    "3": "Cross-country skiing",
    "4": "Walking",
    "5": "Hiking",
    "7": "Swimming",
    "8": "Rowing",
    "11": "Skiing",
    "15": "Aerobics",
    "17": "Strength training",
    "18": "Road cycling",
    "20": "Other outdoor",
    "22": "Swimming",
    "28": "Rowing",
    "36": "Yoga",
    "43": "Indoor cycling",
    "55": "Fitness",
    "63": "Functional training",
    "83": "Core",
    "117": "Crossfit",
}


def _parse_session(data: dict) -> dict | None:
    """Return a dict of AerobicSession field values, or None if unparseable."""
    tz_offset = data.get("timezoneOffsetMinutes", 0)
    tz = timezone(timedelta(minutes=int(tz_offset)))

    def parse_dt(s: str | None) -> datetime | None:
        if not s:
            return None
        dt = datetime.fromisoformat(s)
        return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt

    start_time = parse_dt(data.get("startTime"))
    if not start_time:
        return None

    # Load — top-level trainingLoadReport is most reliable
    load = data.get("trainingLoadReport") or {}
    cardio_load = load.get("cardioLoad")  # absent means not calculated
    muscle_load = load.get("muscleLoad")
    if muscle_load == -1.0:  # Polar sentinel for "not available"
        muscle_load = None

    # Recovery
    rec_ms = data.get("recoveryTimeMillis")
    recovery_hours = int(rec_ms) / 3_600_000 if rec_ms else None

    # Duration
    dur_ms = data.get("durationMillis")
    duration_minutes = dur_ms / 60_000 if dur_ms else None

    # HR zones from exercises[0].zones[ZONE_TYPE_HEART_RATE]
    z = [None, None, None, None, None]
    exercises = data.get("exercises") or []
    if exercises:
        for zone_group in exercises[0].get("zones") or []:
            if zone_group.get("type") == "ZONE_TYPE_HEART_RATE":
                hr_zones = zone_group.get("zones") or []
                for i, zone in enumerate(hr_zones[:5]):
                    in_zone_ms = zone.get("inZone", 0)
                    z[i] = int(in_zone_ms) // 1000  # ms → seconds
                break

    sport_id = str((data.get("sport") or {}).get("id") or "")

    return {
        "source": "polar_flow_export",
        "source_session_id": (data.get("identifier") or {}).get("id"),
        "session_date": start_time.date(),
        "start_time": start_time,
        "stop_time": parse_dt(data.get("stopTime")),
        "sport_id": sport_id or None,
        "sport_name": SPORT_NAMES.get(sport_id),
        "duration_minutes": duration_minutes,
        "hr_avg": data.get("hrAvg"),
        "hr_max": data.get("hrMax"),
        "calories": data.get("calories"),
        "cardio_load": cardio_load,
        "muscle_load": muscle_load,
        "recovery_hours": recovery_hours,
        "z1_seconds": z[0],
        "z2_seconds": z[1],
        "z3_seconds": z[2],
        "z4_seconds": z[3],
        "z5_seconds": z[4],
    }


def _session_label(fields: dict) -> str:
    """Human line for one parsed session — unchanged from the pre-refactor CLI."""
    return (
        f"{fields['session_date']}  "
        f"{fields['sport_name'] or fields['sport_id'] or '?':20s}  "
        f"load={str(fields['cardio_load'] or '—'):8s}  "
        f"hr_avg={fields['hr_avg'] or '—'}"
    )


def import_flow_export(
    db: Session,
    user_id: int,
    zip_source: ZipSource,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Ingest a Polar Flow ZIP export into `aerobic_sessions` for one user.

    The shared core behind both the CLI and the in-app upload endpoint. Parses the
    ZIP's `training-session_*.json` members (ignoring every other member), maps the
    Polar sport id to a name, and inserts one `AerobicSession` per session, SKIPPING
    any `source_session_id` already present in this user's `polar_flow_export` lane
    (existing dedup semantics, unchanged). `_parse_session` is used verbatim, so the
    parse is byte-for-byte identical to the pre-refactor script.

    `zip_source` may be raw bytes, a filesystem path, or a file-like object. With
    `dry_run` no rows are written and nothing is committed, but the would-insert set
    is still counted (and de-duplicated within the run) exactly as before.

    Returns a summary dict: `pre_existing` (polar_flow_export rows already stored),
    `found` (training-session members in the ZIP), `inserted` / `skipped` / `errors`,
    and a per-member `details` list (status + parsed identity) for logging / tests.
    """
    if isinstance(zip_source, (bytes, bytearray)):
        zip_source = io.BytesIO(zip_source)

    existing: set[str] = {
        row[0]
        for row in db.query(AerobicSession.source_session_id)
        .filter(
            AerobicSession.user_id == user_id,
            AerobicSession.source == "polar_flow_export",
        )
        .all()
    }
    pre_existing = len(existing)

    inserted = skipped = errors = 0
    details: list[dict[str, Any]] = []

    with zipfile.ZipFile(zip_source) as zf:
        names = sorted(
            n for n in zf.namelist()
            if n.startswith("training-session_") and n.endswith(".json")
        )
        for name in names:
            try:
                with zf.open(name) as f:
                    data = json.load(f)

                fields = _parse_session(data)
                if fields is None:
                    errors += 1
                    details.append({"name": name, "status": "unparseable"})
                    continue

                sid = fields["source_session_id"]
                if sid in existing:
                    skipped += 1
                    details.append({"name": name, "status": "skipped", "source_session_id": sid})
                    continue

                if not dry_run:
                    db.add(AerobicSession(user_id=user_id, **fields))
                existing.add(sid)
                inserted += 1
                details.append({
                    "name": name,
                    "status": "inserted",
                    "source_session_id": sid,
                    "label": _session_label(fields),
                })

            except Exception as exc:
                errors += 1
                details.append({"name": name, "status": "error", "error": str(exc)})

    if not dry_run and inserted:
        db.commit()

    return {
        "pre_existing": pre_existing,
        "found": len(names),
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Polar Flow export into aerobic_sessions")
    parser.add_argument("--zip", required=True, help="Path to polar-user-data-export.zip")
    parser.add_argument("--email", required=True, help="User email to attach sessions to")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print without writing")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == args.email).first()
        if not user:
            print(f"ERROR: no user found with email {args.email!r}")
            sys.exit(1)
        print(f"User: {user.email} (id={user.id})")

        summary = import_flow_export(db, user.id, args.zip, dry_run=args.dry_run)

        print(f"Already in DB: {summary['pre_existing']} polar_flow_export sessions")
        print(f"Found {summary['found']} training-session files in ZIP\n")
        for d in summary["details"]:
            if d["status"] == "unparseable":
                print(f"  SKIP (unparseable): {d['name']}")
            elif d["status"] == "error":
                print(f"  ERROR {d['name']}: {d['error']}")
            elif d["status"] == "inserted":
                print(f"  {'DRY' if args.dry_run else 'ADD'}  {d['label']}")

        if not args.dry_run and summary["inserted"]:
            print("\nCommitted.")

        print(
            f"\nResult: {summary['inserted']} inserted, "
            f"{summary['skipped']} skipped (already existed), {summary['errors']} errors"
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
