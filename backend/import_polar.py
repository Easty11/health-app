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

# Polar sport ID -> human name: the Polar Flow sport-id list (ids 1-142), names verbatim. This is the
# id space the v4 `sport.id` and the Flow-export `sport.id` both carry (live-confirmed on id 4 =
# "Jogging" and id 55 = "Cross-trainer"). Source: Polar Flow's sports settings page
# (flow.polar.com/settings/sports), as reproduced at
# https://github.com/pcolby/bipolar/wiki/Polar-Sport-Types - a secondary copy; verify against
# /v4/data/sports/list at the next Polar re-auth (OPEN_QUESTIONS). Ids absent from the list (21, 26,
# 31, 37, 72-82, 93, 97-99, 106) and any id Polar adds later keep sport_name NULL, never guessed.
SPORT_NAMES: dict[str, str] = {
    "1": "Running",
    "2": "Cycling",
    "3": "Walking",
    "4": "Jogging",
    "5": "Mountain biking",
    "6": "Skiing",
    "7": "Downhill skiing",
    "8": "Rowing",
    "9": "Nordic walking",
    "10": "Skating",
    "11": "Hiking",
    "12": "Tennis",
    "13": "Squash",
    "14": "Badminton",
    "15": "Strength training",
    "16": "Other outdoor",
    "17": "Treadmill running",
    "18": "Indoor cycling",
    "19": "Road running",
    "20": "Circuit training",
    "22": "Snowboarding",
    "23": "Swimming",
    "24": "Freestyle XC skiing",
    "25": "Classic XC skiing",
    "27": "Trail running",
    "28": "Ice skating",
    "29": "Inline skating",
    "30": "Roller skating",
    "32": "Group exercise",
    "33": "Yoga",
    "34": "Crossfit",
    "35": "Golf",
    "36": "Track&field running",
    "38": "Road cycling",
    "39": "Soccer",
    "40": "Cricket",
    "41": "Basketball",
    "42": "Baseball",
    "43": "Rugby",
    "44": "Field hockey",
    "45": "Volleyball",
    "46": "Ice hockey",
    "47": "Football",
    "48": "Handball",
    "49": "Beach volley",
    "50": "Futsal",
    "51": "Floorball",
    "52": "Dancing",
    "53": "Trotting",
    "54": "Riding",
    "55": "Cross-trainer",
    "56": "Fitness martial arts",
    "57": "Functional training",
    "58": "Bootcamp",
    "59": "Freestyle roller skiing",
    "60": "Classic roller skiing",
    "61": "Aerobics",
    "62": "Aqua fitness",
    "63": "Step workout",
    "64": "Body&Mind",
    "65": "Pilates",
    "66": "Stretching",
    "67": "Fitness dancing",
    "68": "Triathlon",
    "69": "Duathlon",
    "70": "Off-road triathlon",
    "71": "Off-road duathlon",
    "83": "Other indoor",
    "84": "Orienteering",
    "85": "Ski orienteering",
    "86": "Mountain bike orienteering",
    "87": "Biathlon",
    "88": "Sailing",
    "89": "Wheelchair racing",
    "90": "Disc golf",
    "91": "Table tennis",
    "92": "Ultra running",
    "94": "Climbing (indoor)",
    "95": "Kayaking",
    "96": "Canoeing",
    "100": "Kitesurfing",
    "101": "Windsurfing",
    "102": "Surfing",
    "103": "Pool swimming",
    "104": "Finnish baseball",
    "105": "Open water swimming",
    "107": "Wakeboarding",
    "108": "Water skiing",
    "109": "Boxing",
    "110": "Kickboxing",
    "111": "Mobility (dynamic)",
    "112": "Telemark skiing",
    "113": "Backcountry skiing",
    "114": "Gymnastics",
    "115": "Judo",
    "116": "Snowshoe trekking",
    "117": "Indoor rowing",
    "118": "Spinning",
    "119": "Street",
    "120": "Latin",
    "121": "Show",
    "122": "Ballet",
    "123": "Jazz",
    "124": "Modern",
    "125": "Ballroom",
    "126": "Core",
    "127": "Mobility (static)",
    "128": "LES MILLS BODYPUMP",
    "129": "LES MILLS BODYATTACK",
    "130": "LES MILLS BODYCOMBAT",
    "131": "LES MILLS GRIT Cardio",
    "132": "LES MILLS GRIT Strength",
    "133": "LES MILLS GRIT Plyo",
    "134": "LES MILLS SH'BAM",
    "135": "LES MILLS RPM",
    "136": "LES MILLS BODYJAM",
    "137": "LES MILLS BODYSTEP",
    "138": "LES MILLS SPRINT",
    "139": "LES MILLS BODYVIVE",
    "140": "LES MILLS BODYBALANCE",
    "141": "LES MILLS THE TRIP",
    "142": "LES MILLS CXWORX",
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
