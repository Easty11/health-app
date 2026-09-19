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
    "routers/health_connect.py": "Writer (HC exercise ingest); reads existing rows for mirror-drop/upsert.",
    "import_polar.py": "Writer (Polar Flow-export ZIP ingest).",
    "load_events_metabolic.py": "Sources rows via arbitrated_sessions (the door); the only direct query is the distinct-user-id worklist.",
    "cbti/replay.py": "Allow-listed: keeps its pre-migration raw-SQL isolation, and reads training_end DETERMINISTICALLY — MAX(stop_time) per session_date with source='health_connect' EXCLUDED (interim, Q162) — so no order-dependent wrong-pick and no HC ingest side effect on the sleep engine (#311).",
}
ALLOW_HEVY = {
    "reads/hevy_reads.py": "THE counted-workouts read-door.",
    "hevy_workouts.py": "Writer (Hevy ingest + dedup_flag/partner recompute).",
    "engine/resolver.py": "Fetches in-window candidates, partitions via counted_workouts (the door).",
    "reads/psychological_reads.py": "Fetches non-excluded candidates, filters via counted_workouts.",
    "routers/series.py": "Fetches non-excluded candidates, filters via counted_workouts.",
    "engine/region_exercise.py": "Fetches non-excluded candidates, filters via counted_workouts, then limits.",
    "load_events.py": "Fetches non-excluded candidates, filters via counted_workouts (byte-identical on adjudicated data).",
    "audit_bodyweight_templates.py": "Allow-listed: operator CLI; GROUP-BY aggregate — dupes move only the usage count/sort, never worklist membership.",
    "audit_laterality_coverage.py": "Allow-listed: operator CLI; GROUP-BY aggregate — dupes move only count/sort, never membership.",
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
