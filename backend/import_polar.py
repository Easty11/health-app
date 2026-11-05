"""
Polar Flow ZIP-export ingest into aerobic_sessions (+ the export's per-second HR into hr_samples).

The parsing / sport-name mapping / dedup core lives in `import_flow_export`, a
per-user callable shared by the in-app upload endpoint (`routers/polar.py`) and by
this CLI. The CLI is retained for ops / backfill runs; `--email` resolution is
CLI-only (the endpoint keys on the authenticated user, never an email parameter).

The export's HR samples (design 0010 row 6 rescoped: the export already holds them) are written
to `hr_samples` as `source = source_package = 'polar_flow_export'` (`EXPORT_SAMPLE_SOURCE`),
insert-or-ignore on `uq_hr_sample`, bpm as received (plausibility stays at zone time), in the same
transaction as the row -- and for a session whose row already exists too, so a re-upload of an
export that predates this ingest fills the samples without touching the row. The zoning step
(`hc_zone_enrich`, `POLAR_SAMPLE_WRITERS`) then re-zones the Polar row on the model instead of
keeping Polar's own zone totals.

The sample path is `exercises[0].samples.samples[]`, a list of streams `{type, intervalMillis,
values}` (`_hr_samples`); the `HEART_RATE` stream's `values[i]` is the bpm at `startTime +
i * intervalMillis`, `startTime` being local and taking the session's `timezoneOffsetMinutes`
exactly as the row's own `start_time` does. This is the shape the operator's `--keys` probe read
off the real export on 2026-11-06 (the first member: `HEART_RATE`, 1000 ms, 793 floats for
792463 ms); the path #506 first shipped (`exercises[0].samples.heartRate[].{dateTime, value}`)
was a guess the probe disproved, and it is gone, not kept as a fallback. A member with no
`HEART_RATE` stream writes none, loudly: the summary's `hr_samples_found` is 0 while `found` is
not, and the row keeps the vendor fallback. `--keys` prints the key NAMES the first session
carries (top level, `exercises[0]`, and the sample block) and, for EVERY member, each stream's
type, `intervalMillis`, value count and null count (never a value), so the next shape drift is
visible in one run.

Usage (from backend/, venv activated):
    python import_polar.py --zip /path/to/polar-user-data-export.zip --email user@example.com
    python import_polar.py --zip ... --email ... --dry-run
    python import_polar.py --zip ... --keys          (no database, no email: key names only)
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
from models import AerobicSession, HrSample, User

# A ZIP source the shared core accepts: raw bytes, a filesystem path, or a
# file-like object — anything `zipfile.ZipFile` opens, plus bytes (wrapped here).
ZipSource = Union[bytes, bytearray, str, BinaryIO]

# `hr_samples.source` AND `.source_package` of a sample read from the export: the writer is the
# export itself (no Health Connect package stands behind it), so one name serves both columns.
EXPORT_SAMPLE_SOURCE = "polar_flow_export"
# Insert chunk: 1000 rows x 5 bound params stays under both engines' parameter limits
# (the same bound `routers/health_connect.HR_SAMPLE_CHUNK` uses).
HR_SAMPLE_CHUNK = 1000

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


def _session_tz(data: dict) -> timezone:
    """The session's local offset: `timezoneOffsetMinutes`, 0 when absent."""
    return timezone(timedelta(minutes=int(data.get("timezoneOffsetMinutes", 0))))


def _local_dt(s: str | None, tz: timezone) -> datetime | None:
    """THE conversion of an export clock string to a stored instant: a naive string is local and
    takes the session's offset `tz`; a string carrying its own offset keeps it. `_parse_session`
    stores the row's `start_time` / `stop_time` through this, and `_hr_samples` anchors every
    sample on the same call, so the samples and the row share one clock form: one instant on
    Postgres (timestamptz), and on the SQLite suite, which stores an aware value naive WITHOUT
    converting (FEEDBACK section 49), the same naive local clock as the row they must fall inside."""
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt


def _parse_session(data: dict) -> dict | None:
    """Return a dict of AerobicSession field values, or None if unparseable."""
    tz = _session_tz(data)

    def parse_dt(s: str | None) -> datetime | None:
        return _local_dt(s, tz)

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


HR_STREAM_TYPE = "HEART_RATE"


def _sample_streams(data: dict) -> list[dict]:
    """The stream dicts under `exercises[0].samples.samples[]` (`{type, intervalMillis, values}` each,
    as the real export carries them); `[]` when the path is absent or shaped otherwise. Non-dict
    entries are dropped here; the type / interval / values checks are the callers'."""
    exercises = data.get("exercises") or []
    if not exercises or not isinstance(exercises[0], dict):
        return []
    block = exercises[0].get("samples")
    if not isinstance(block, dict):
        return []
    streams = block.get("samples")
    if not isinstance(streams, list):
        return []
    return [s for s in streams if isinstance(s, dict)]


def _hr_samples(data: dict) -> list[tuple[datetime, int]]:
    """The per-sample HR of one export session as `(aware time, bpm)`, from the `HEART_RATE` stream
    of `exercises[0].samples.samples[]`: `values[i]` is the bpm at `startTime + i * intervalMillis`.
    `[]` when the path is absent, the member has no `HEART_RATE` stream, or `startTime` is missing;
    never an error. Every other stream type is ignored.

    The anchor is the session's `startTime` through `_local_dt` with the session's offset, the very
    call `_parse_session` stores the row's `start_time` with, so each sample is aware in the row's own
    offset (one instant on Postgres; the row's naive clock on SQLite, FEEDBACK section 49). A `None`
    entry (Polar's dropout) or a non-numeric one is skipped and its index still advances, so the
    samples after it keep their place. Bpm is stored as received (`int()` of the float; 0 and other
    implausible readings stay: plausibility is applied at zone time). A stream whose `intervalMillis`
    is missing or not a positive number is skipped whole. Fractional seconds are stripped so two
    samples inside one second collapse to one (the UNIQUE key is per second); the LAST one wins.
    The list is sorted by time."""
    streams = [s for s in _sample_streams(data) if s.get("type") == HR_STREAM_TYPE]
    if not streams:
        return []
    start = _local_dt(data.get("startTime"), _session_tz(data))
    if start is None:
        return []
    out: dict[datetime, int] = {}
    for stream in streams:
        interval, values = stream.get("intervalMillis"), stream.get("values")
        if (isinstance(interval, bool) or not isinstance(interval, (int, float)) or interval <= 0
                or not isinstance(values, list)):
            continue
        for i, raw_v in enumerate(values):
            if raw_v is None or isinstance(raw_v, bool) or not isinstance(raw_v, (int, float)):
                continue
            t = (start + timedelta(milliseconds=i * interval)).replace(microsecond=0)
            out[t] = int(raw_v)
    return sorted(out.items())


def session_sample_streams(data: dict) -> list[dict[str, Any]]:
    """Per stream under `exercises[0].samples.samples[]`: its `type`, `intervalMillis`, the number of
    entries and the number of null entries. Counts and the interval, never a value; the per-member
    half of the `--keys` probe, so a member without a `HEART_RATE` stream, a new type or a changed
    interval shows in one run."""
    out = []
    for s in _sample_streams(data):
        values = s.get("values")
        n = len(values) if isinstance(values, list) else None
        nulls = sum(1 for v in values if v is None) if isinstance(values, list) else None
        out.append({"type": s.get("type") if isinstance(s.get("type"), str) else f"<{type(s.get('type')).__name__}>",
                    "intervalMillis": s.get("intervalMillis"), "count": n, "nulls": nulls})
    return out


def session_key_names(data: dict) -> dict[str, list[str]]:
    """Key NAMES only (no value of any kind) of one export session: the top level, `exercises[0]`,
    and each group under `exercises[0].samples` with the keys of its first item. The `--keys` probe:
    enough to confirm or correct the sample path against a real export, nothing more."""
    out: dict[str, list[str]] = {"top": sorted(str(k) for k in data) if isinstance(data, dict) else []}
    exercises = data.get("exercises") if isinstance(data, dict) else None
    ex0 = exercises[0] if isinstance(exercises, list) and exercises and isinstance(exercises[0], dict) else None
    out["exercises[0]"] = sorted(str(k) for k in ex0) if ex0 is not None else []
    samples = ex0.get("samples") if ex0 is not None else None
    if isinstance(samples, dict):
        out["exercises[0].samples"] = sorted(str(k) for k in samples)
        for name, group in sorted(samples.items(), key=lambda kv: str(kv[0])):
            first = group[0] if isinstance(group, list) and group else group
            out[f"exercises[0].samples.{name}[0]"] = (
                sorted(str(k) for k in first) if isinstance(first, dict) else [f"<{type(first).__name__}>"])
    elif isinstance(samples, list):
        out["exercises[0].samples"] = [f"<list of {len(samples)}>"]
        for i, item in enumerate(samples[:12]):
            out[f"exercises[0].samples[{i}]"] = (
                sorted(str(k) for k in item) if isinstance(item, dict) else [f"<{type(item).__name__}>"])
    else:
        out["exercises[0].samples"] = [] if samples is None else [f"<{type(samples).__name__}>"]
    return out


def _dialect_insert(db: Session):
    """The ON CONFLICT-capable `insert` for this session's engine: Postgres in prod, SQLite in the
    suite (the same lookup `routers/health_connect._dialect_insert` makes)."""
    from sqlalchemy.dialects import postgresql, sqlite
    return postgresql.insert if db.get_bind().dialect.name == "postgresql" else sqlite.insert


def _store_export_samples(db: Session, user_id: int, samples: list[tuple[datetime, int]]) -> int:
    """`hr_samples` insert-or-ignore on `uq_hr_sample` for the export's samples; returns the rows
    actually inserted (a re-import inserts none). Same session, same transaction as the rows."""
    if not samples:
        return 0
    insert = _dialect_insert(db)
    table = HrSample.__table__
    values = [{"user_id": user_id, "sample_time": t, "bpm": b,
               "source": EXPORT_SAMPLE_SOURCE, "source_package": EXPORT_SAMPLE_SOURCE} for t, b in samples]
    stored = 0
    for i in range(0, len(values), HR_SAMPLE_CHUNK):
        stmt = (insert(table).values(values[i:i + HR_SAMPLE_CHUNK])
                .on_conflict_do_nothing(index_elements=["user_id", "sample_time", "source", "source_package"]))
        stored += max(db.execute(stmt).rowcount, 0)
    return stored


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

    The export's HR samples (`_hr_samples`) are written to `hr_samples` for EVERY parsed
    session, inserted or skipped (a skipped row's samples may be new: an export imported before
    this ingest existed), insert-or-ignore, in the same transaction as the rows. A session
    whose export carries no samples writes none and is counted in `sessions_without_samples`.

    Returns a summary dict: `pre_existing` (polar_flow_export rows already stored),
    `found` (training-session members in the ZIP), `inserted` / `skipped` / `errors`,
    `hr_samples_found` (samples parsed from the ZIP), `hr_samples_stored` (rows actually
    inserted; 0 on a re-import and on a dry run), `sessions_with_samples` /
    `sessions_without_samples`, and a per-member `details` list (status + parsed identity +
    `hr_samples`) for logging / tests.
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
    samples_found = samples_stored = with_samples = without_samples = 0
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

                samples = _hr_samples(data)
                samples_found += len(samples)
                if samples:
                    with_samples += 1
                else:
                    without_samples += 1

                sid = fields["source_session_id"]
                if sid in existing:
                    skipped += 1
                    if not dry_run:
                        samples_stored += _store_export_samples(db, user_id, samples)
                    details.append({"name": name, "status": "skipped", "source_session_id": sid,
                                    "hr_samples": len(samples)})
                    continue

                if not dry_run:
                    db.add(AerobicSession(user_id=user_id, **fields))
                    samples_stored += _store_export_samples(db, user_id, samples)
                existing.add(sid)
                inserted += 1
                details.append({
                    "name": name,
                    "status": "inserted",
                    "source_session_id": sid,
                    "label": _session_label(fields),
                    "hr_samples": len(samples),
                })

            except Exception as exc:
                errors += 1
                details.append({"name": name, "status": "error", "error": str(exc)})

    if not dry_run and (inserted or samples_stored):
        db.commit()

    return {
        "pre_existing": pre_existing,
        "found": len(names),
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
        "hr_samples_found": samples_found,
        "hr_samples_stored": samples_stored,
        "sessions_with_samples": with_samples,
        "sessions_without_samples": without_samples,
        "details": details,
    }


def export_key_names(zip_source: ZipSource) -> dict[str, Any]:
    """`--keys`: the key names of the FIRST `training-session_*.json` member (`session_key_names`),
    the member count, and for EVERY member its sample streams (`session_sample_streams`: type,
    interval, count, nulls); no database, no value printed. Empty when the ZIP has no session. A
    member that does not parse as JSON is listed with its error class, not raised."""
    if isinstance(zip_source, (bytes, bytearray)):
        zip_source = io.BytesIO(zip_source)
    with zipfile.ZipFile(zip_source) as zf:
        names = sorted(n for n in zf.namelist() if n.startswith("training-session_") and n.endswith(".json"))
        if not names:
            return {"found": 0, "member": None, "keys": {}, "members": []}
        keys: dict[str, list[str]] = {}
        members: list[dict[str, Any]] = []
        for i, name in enumerate(names):
            try:
                with zf.open(name) as f:
                    data = json.load(f)
            except Exception as exc:
                members.append({"member": name, "error": type(exc).__name__, "streams": []})
                continue
            if i == 0:
                keys = session_key_names(data)
            members.append({"member": name, "streams": session_sample_streams(data)})
    return {"found": len(names), "member": names[0], "keys": keys, "members": members}


def _format_stream(s: dict[str, Any]) -> str:
    return f"{s['type']} @{s['intervalMillis']}ms n={s['count']} null={s['nulls']}"


def format_key_names(report: dict[str, Any]) -> str:
    lines = [f"training-session members: {report['found']}"]
    if report["member"] is None:
        return "\n".join(lines)
    lines.append(f"first member: {report['member']}")
    for path, keys in report["keys"].items():
        lines.append(f"  {path}: {', '.join(keys) if keys else '(none)'}")
    lines.append(f"sample streams per member (type @intervalMillis n=count null=nulls; a {HR_STREAM_TYPE} stream is what zones):")
    for m in report.get("members", []):
        if m.get("error"):
            lines.append(f"  {m['member']}: (unreadable: {m['error']})")
        elif not m["streams"]:
            lines.append(f"  {m['member']}: (no sample stream)")
        else:
            lines.append(f"  {m['member']}: " + "; ".join(_format_stream(s) for s in m["streams"]))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Polar Flow export into aerobic_sessions")
    parser.add_argument("--zip", required=True, help="Path to polar-user-data-export.zip")
    parser.add_argument("--email", help="User email to attach sessions to (required unless --keys)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print without writing")
    parser.add_argument("--keys", action="store_true",
                        help="Print the key NAMES of the first training session (no values, no database) and exit")
    args = parser.parse_args()

    if args.keys:
        print(format_key_names(export_key_names(args.zip)))
        return
    if not args.email:
        parser.error("--email is required unless --keys")

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

        if not args.dry_run and (summary["inserted"] or summary["hr_samples_stored"]):
            print("\nCommitted.")

        print(
            f"\nResult: {summary['inserted']} inserted, "
            f"{summary['skipped']} skipped (already existed), {summary['errors']} errors; "
            f"HR samples: {summary['hr_samples_found']} found, {summary['hr_samples_stored']} stored "
            f"({summary['sessions_with_samples']} sessions with samples, "
            f"{summary['sessions_without_samples']} without)"
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
