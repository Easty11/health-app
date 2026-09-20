"""Shared Hevy-routine renderers — ONE renderer, two callers (#314).

Moved verbatim from `mcp_server.py` (the MCP routine tools) so the in-app chat context
(`context_builder._section_hevy_routines`) renders routines identically to the external MCP
tools, rather than a second copy drifting. These are PURE functions over a routine dict plus a
`fallback` title map; they touch no DB, no MCP context, no HevyClient — the only dependency is
`format_set`, itself already the shared set renderer used by both callers.

The DB-touching `_routine_title_fallback` (which builds the `fallback` map from the local
template store) deliberately stays with its caller: `context_builder` is a pure formatter that
gets no Session (#43), so it is handed a pre-built `fallback`, exactly as it is handed
`exercise_catalogue`.
"""
from __future__ import annotations

from hevy_format import format_set


def exercise_display_title(ex: dict, fallback: dict[str, str]) -> str:
    """Human title for a routine exercise: payload `title` first, then the store fallback,
    then the raw id as a last resort (never crash, never blank)."""
    tid = ex.get("exercise_template_id")
    return ex.get("title") or fallback.get(tid) or tid or "Unknown exercise"


def format_routine_header(routine: dict) -> str:
    folder = routine.get("folder_id")
    folder_str = folder if folder is not None else "none"
    title = routine.get("title") or "Untitled routine"
    return f"## {title}  (id: {routine.get('id')}, folder: {folder_str})"


def format_routine_compact(routine: dict, fallback: dict[str, str]) -> list[str]:
    """Compact rendering: header + exercise count + exercise titles. NO set detail
    (the list must stay context-small)."""
    exercises = routine.get("exercises", []) or []
    lines = [format_routine_header(routine)]
    if not exercises:
        lines.append("   (no exercises)")
        return lines
    titles = ", ".join(exercise_display_title(ex, fallback) for ex in exercises)
    lines.append(f"   {len(exercises)} exercise(s): {titles}")
    return lines


def format_routine_full(routine: dict, fallback: dict[str, str]) -> list[str]:
    """Full rendering: header, then each exercise IN PAYLOAD ORDER with superset grouping,
    rest, notes, and every set. Superset membership is surfaced as a `[superset N]` tag so
    grouped writes are verifiable."""
    lines = [format_routine_header(routine)]

    notes = (routine.get("notes") or "").strip()
    if notes:
        lines.append(f"   Notes: {notes}")

    exercises = routine.get("exercises", []) or []
    if not exercises:
        lines.append("   (no exercises)")
        return lines

    for ex in exercises:
        title = exercise_display_title(ex, fallback)
        superset_id = ex.get("superset_id")
        superset_tag = f"  [superset {superset_id}]" if superset_id is not None else ""
        lines.append(f"  {title}{superset_tag}")

        rest = ex.get("rest_seconds")
        if rest is not None:
            lines.append(f"     rest: {rest}s")

        ex_notes = (ex.get("notes") or "").strip()
        if ex_notes:
            for note_line in ex_notes.split("\n"):
                note_line = note_line.strip()
                if note_line:
                    lines.append(f"     note: {note_line}")

        sets = ex.get("sets", []) or []
        if not sets:
            lines.append("     (no sets)")
        for set_idx, s in enumerate(sets):
            lines.append(format_set(s, set_idx))

    return lines
