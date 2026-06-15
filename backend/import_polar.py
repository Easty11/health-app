"""
One-off script: seed aerobic_sessions from a Polar Flow ZIP export.

Usage (from backend/, venv activated):
    python import_polar.py --zip /path/to/polar-user-data-export.zip --email user@example.com
    python import_polar.py --zip ... --email ... --dry-run
"""
import argparse
import json
import sys
import zipfile
from datetime import datetime, timedelta, timezone

from database import SessionLocal
from models import AerobicSession, User

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

        # Build set of already-imported source_session_ids so we can skip duplicates
        existing: set[str] = {
            row[0]
            for row in db.query(AerobicSession.source_session_id)
            .filter(
                AerobicSession.user_id == user.id,
                AerobicSession.source == "polar_flow_export",
            )
            .all()
        }
        print(f"Already in DB: {len(existing)} polar_flow_export sessions")

        inserted = skipped = errors = 0

        with zipfile.ZipFile(args.zip) as zf:
            names = sorted(n for n in zf.namelist() if n.startswith("training-session_") and n.endswith(".json"))
            print(f"Found {len(names)} training-session files in ZIP\n")

            for name in names:
                try:
                    with zf.open(name) as f:
                        data = json.load(f)

                    fields = _parse_session(data)
                    if fields is None:
                        print(f"  SKIP (unparseable): {name}")
                        errors += 1
                        continue

                    sid = fields["source_session_id"]
                    if sid in existing:
                        skipped += 1
                        continue

                    label = f"{fields['session_date']}  {fields['sport_name'] or fields['sport_id'] or '?':20s}  load={str(fields['cardio_load'] or '—'):8s}  hr_avg={fields['hr_avg'] or '—'}"
                    if args.dry_run:
                        print(f"  DRY  {label}")
                        inserted += 1
                        continue

                    db.add(AerobicSession(user_id=user.id, **fields))
                    existing.add(sid)
                    inserted += 1
                    print(f"  ADD  {label}")

                except Exception as exc:
                    errors += 1
                    print(f"  ERROR {name}: {exc}")

        if not args.dry_run and inserted:
            db.commit()
            print(f"\nCommitted.")

        print(f"\nResult: {inserted} inserted, {skipped} skipped (already existed), {errors} errors")

    finally:
        db.close()


if __name__ == "__main__":
    main()
