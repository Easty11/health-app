"""Guard: Garmin's activity metrics are DISPLAY ONLY. Nothing in the load or readiness path reads them.

Training Effect and Garmin load are vendor composites (SCHEMA.md: vendor composites are never algorithm
inputs). `garmin_activity_metrics` may be written by the self-evaluation lane and the backfill, and read
only through `reads.garmin_metrics_reads`, by the sessions API (`routers/polar.get_aerobic_sessions`) and
the MCP session list (`mcp_server.get_recent_sessions`). This fails if the metabolic transform, the load
rollups, the zoning, the readiness reads or any other module starts reading the table or the read module.
"""
import ast
import re
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
PATTERN = re.compile(r"GarminActivityMetric|garmin_activity_metrics|garmin_metrics_reads|garmin_metrics_by_session")

# The only files allowed to name the table, the model or the read door.
ALLOWED = {
    "models.py",                                              # the model
    "garmin_activity_metrics.py",                             # the writer (summary upsert + stream mark)
    "garmin_selfeval.py",                                     # calls the summary upsert on the same detail
    "scripts/garmin_sync.py",                                 # runs the stream pass in the selfeval lane
    "scripts/garmin_activity_backfill.py",                    # the operator backfill
    "reads/garmin_metrics_reads.py",                          # the one read door
    "routers/polar.py",                                       # the sessions API (display)
    "mcp_server.py",                                          # get_recent_sessions (display)
    "migrations/versions/a9d3f5b7c2e4_add_garmin_activity_metrics.py",
}

# Named explicitly, so the intent survives an edit to the allowlist: the metabolic load, the rollups,
# the zoning and every readiness input.
NEVER = ("load_events_metabolic.py", "load_events.py", "load_metrics.py", "load_sweep.py", "metabolic_cascade.py",
         "hr_zones.py", "hc_zone_enrich.py", "current_state.py", "context_builder.py",
         "reads/snapshot_reads.py", "reads/engine_reads.py", "reads/psychological_reads.py",
         "reads/recovery_night.py", "reads/zone_reads.py", "reads/srpe_reads.py", "reads/freshness_reads.py",
         "routers/checkin.py", "routers/checkin_v2.py", "routers/recovery.py", "routers/engine.py")


def _py_files():
    for f in _BACKEND.rglob("*.py"):
        rel = f.relative_to(_BACKEND).as_posix()
        if rel.startswith(("tests/", ".venv/")) or "/tests/" in rel or rel == "conftest.py":
            continue
        yield rel, f


def test_no_module_outside_the_allowlist_names_the_metrics():
    offenders = [rel for rel, f in _py_files() if rel not in ALLOWED and PATTERN.search(f.read_text(encoding="utf-8"))]
    assert offenders == [], f"read garmin_activity_metrics outside the display path: {offenders}"


def test_the_load_and_readiness_path_never_reads_the_metrics():
    for rel in NEVER:
        f = _BACKEND / rel
        if f.exists():
            assert not PATTERN.search(f.read_text(encoding="utf-8")), f"{rel} reads Garmin activity metrics"
    for sub in ("engine", "cbti", "interpretation"):
        for f in (_BACKEND / sub).rglob("*.py"):
            assert not PATTERN.search(f.read_text(encoding="utf-8")), f"{f} reads Garmin activity metrics"


def _functions_naming(rel: str) -> set[str]:
    tree = ast.parse((_BACKEND / rel).read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and PATTERN.search(ast.unparse(node)):
            out.add(node.name)
    return out


def test_inside_the_shared_display_files_only_the_session_lists_read_them():
    """`mcp_server.py` also holds `get_readiness_snapshot` and `get_training_load`; `routers/polar.py` holds the
    sync routes. Only the session-list functions may touch the metrics."""
    assert _functions_naming("mcp_server.py") == {"get_recent_sessions"}
    assert _functions_naming("routers/polar.py") == {"get_aerobic_sessions"}


def test_the_writers_never_feed_the_metrics_into_a_session_row():
    """The summary upsert writes its own table only: never `aerobic_sessions` (calories, cardio_load, zones),
    `load_events` or any other load input."""
    src = (_BACKEND / "garmin_activity_metrics.py").read_text(encoding="utf-8")
    assert "AerobicSession" not in src and "LoadEvent" not in src and "load_events" not in src
