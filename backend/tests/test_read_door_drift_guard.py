"""Read-door drift guard (#Q161).

Every reader of `aerobic_sessions` / `hevy_workouts` must go through the ONE read-door per
table — `reads.aerobic_reads.arbitrated_sessions` (canonical) and
`reads.hevy_reads.counted_workouts` (excluded + adjudicated-dedup). Otherwise a reader
silently double-counts a same-bout twin, or drops the retained log of an adjudicated dedup
pair (the #276 bug). This test FAILS when any NON-test, NON-migration `.py` file under
`backend/` references either table's model/table name and is not on the allow-list below —
so reader N+1 cannot repeat the mistake unnoticed. A new toucher must EITHER route through
the door (and fetch its candidates), OR be added here with a written reason.

Detection is deliberately broad: the CamelCase model class (any import style) or the table
name in a SQL keyword context. The allow-list is exact — a stale entry (a file that no
longer touches the table) also fails, keeping the list honest.
"""
import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent

_AEROBIC_RE = re.compile(r"\bAerobicSession\b|(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+aerobic_sessions")
_HEVY_RE = re.compile(r"\bHevyWorkout\b|(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+hevy_workouts")

# path -> reason. Every allowed toucher is THE door, a writer, a candidate-fetcher that then
# applies the door, or a reasoned exception.
ALLOW_AEROBIC = {
    "reads/aerobic_reads.py": "THE canonical read-door (arbitrated_sessions + arbitrate).",
    "routers/polar.py": "Writer (Polar v4 sync / Flow-export); its GET reads via the door.",
    "polar_ingest.py": "Writer (Polar v4 sync core, Q154 — moved out of routers/polar.py); reads existing rows only for source_session_id dedup and to target zoneless v4 rows for enrichment, never a count.",
    "routers/health_connect.py": "Writer (HC exercise ingest); reads existing rows for mirror-drop/upsert.",
    "import_polar.py": "Writer (Polar Flow-export ZIP ingest).",
    "load_events_metabolic.py": "Sources rows via arbitrated_sessions (the door); the only direct query is the distinct-user-id worklist.",
    "cbti/replay.py": "Allow-listed: keeps its pre-migration raw-SQL isolation, and reads training_end DETERMINISTICALLY — MAX(stop_time) per session_date with non-training sports (sport_classes.NON_TRAINING_SPORTS) EXCLUDED, all sources (#322, closing Q162) — so no order-dependent wrong-pick (#311). Hevy mirrors (a Garmin/Strava copy of a Hevy bout) are dropped from it through the door's column-light `hevy_mirror_session_ids` (A3.2), the same predicate arbitrated_sessions uses.",
    "engine/week_plan.py": "Derived week plan (#316) does NOT count — every `done` is resolve()'s (doored). Its only direct aerobic reads are day-attribution of the exact session ids resolve() ALREADY counted (never a membership/count decision) and the freshness aggregate max(created_at) for Polar rows, which no door exposes (ruling 4).",
    "session_focus.py": "Session focus (Brief A A1): the ONE row the operator asked to review, fetched by (user_id, id) — a lookup, never a membership/count decision. Its surrounding window goes through arbitrated_sessions (the door) and drops non-canonical rows.",
    "hc_zone_enrich.py": "Writer (HC zone fill, Q159 stage 2): fetches ALL of the user's health_connect rows — canonical or not, by design, so a new HRmax reflows every row — and writes only their z*_seconds / hr_avg / hr_max. Never a count or membership decision for any reader, and it reads no other source's rows (a canonical-only fetch would leave a non-canonical twin unzoned and flip arbitration the moment its twin changed).",
    "scripts/set_hrmax.py": "Operator CLI (Q159 stage 2): a read-only preview of the health_connect rows whose HRmax in force changes when a value is recorded. Never a count or membership decision for any reader; its only write is the append-only user_hrmax insert.",
    "scripts/polar_sport_backfill.py": "Operator CLI (polar-sport-map): relabels polar_v4 / polar_flow_export rows' sport_name from the retained sport_id after the id map was corrected. Report-only by default; its single write (--apply) sets sport_name and nothing else. Never a count or membership decision for any reader.",
    "scripts/arbitration_flip_report.py": "Read-only dry run for the A6 tier (Brief A): it needs the user's FULL raw set so it can run the door's own pure core (`reads.aerobic_reads.arbitrate`) twice, with and without the data tier, and list the bouts that flip. Writes nothing; never a count or membership decision for any reader.",
}
ALLOW_HEVY = {
    "reads/hevy_reads.py": "THE counted-workouts read-door.",
    "reads/aerobic_reads.py": "Hevy-mirror test (A3.2, amended): fetches EVERY Hevy workout near the Health Connect rows being read, excluded and unadjudicated-duplicate rows included, and compares overlap. Deliberately not the door: it is a membership decision about AEROBIC rows (is this row a copy of a Hevy workout, whether or not that workout still counts?), never about which Hevy workouts count.",
    "hevy_workouts.py": "Writer (Hevy ingest + dedup_flag/partner recompute).",
    "engine/resolver.py": "Fetches in-window candidates, partitions via counted_workouts (the door).",
    "reads/psychological_reads.py": "Fetches non-excluded candidates, filters via counted_workouts.",
    "routers/series.py": "Fetches non-excluded candidates, filters via counted_workouts.",
    "engine/region_exercise.py": "Fetches non-excluded candidates, filters via counted_workouts, then limits.",
    "load_events.py": "Fetches non-excluded candidates, filters via counted_workouts (byte-identical on adjudicated data).",
    "audit_bodyweight_templates.py": "Allow-listed: operator CLI; GROUP-BY aggregate — dupes move only the usage count/sort, never worklist membership.",
    "audit_laterality_coverage.py": "Allow-listed: operator CLI; GROUP-BY aggregate — dupes move only count/sort, never membership.",
    "scripts/retire_user.py": "Account-retirement inventory: a read-only GROUP-BY-owner count of hevy_workouts INCLUDING excluded/dedup-flagged rows ON PURPOSE — it reports what a cascade delete would destroy, and the door would hide exactly those rows. Never a count or membership decision for any reader; the only write is the guarded DELETE of the user row (cascade).",
    "engine/week_plan.py": "Derived week plan (#316) does NOT count — every `done` is resolve()'s (doored). Its only direct hevy read is day-attribution of the exact workout ids resolve() ALREADY counted via counted_workouts (the door); never a membership/count decision of its own.",
    "session_focus.py": "Session focus (Brief A A1): the ONE workout the operator asked to review, fetched by (user_id, hevy_id) — a lookup, never a membership/count decision. Its surrounding window fetches in-window candidates and partitions them via counted_workouts (the door).",
}


def _touchers(regex: re.Pattern) -> set[str]:
    found: set[str] = set()
    for p in _BACKEND.rglob("*.py"):
        rel = p.relative_to(_BACKEND).as_posix()
        if rel.startswith(("tests/", "migrations/")) or rel == "models.py":
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if regex.search(text):
            found.add(rel)
    return found


def _report(found: set[str], allow: dict[str, str], table: str) -> str:
    added = sorted(found - set(allow))
    stale = sorted(set(allow) - found)
    msg = [f"Read-door drift on `{table}`."]
    if added:
        msg.append(
            "NEW un-doored toucher(s) — route through the read-door (fetch candidates, then "
            "arbitrated_sessions/counted_workouts) OR add to the allow-list with a reason: "
            + ", ".join(added))
    if stale:
        msg.append("STALE allow-list entr(y/ies) — no longer touches the table, remove: "
                   + ", ".join(stale))
    return " ".join(msg)


def test_every_aerobic_reader_goes_through_the_door():
    found = _touchers(_AEROBIC_RE)
    assert found == set(ALLOW_AEROBIC), _report(found, ALLOW_AEROBIC, "aerobic_sessions")


def test_every_hevy_reader_goes_through_the_door():
    found = _touchers(_HEVY_RE)
    assert found == set(ALLOW_HEVY), _report(found, ALLOW_HEVY, "hevy_workouts")
