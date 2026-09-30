"""Shared Hevy payload formatting — the single source of truth for rendering a
raw Hevy *set* object.

Consumed by both `context_builder._section_hevy` and
`mcp_server.get_hevy_workouts`. The `get_hevy_workouts` `set_type` no-op bug
(DECISIONS_LOG #68) existed precisely because this set-parsing logic was
duplicated and one copy drifted — reading the set-type field as `set_type` while
the working path read `type`. Keeping it here means the two summarizers can never
diverge on field reading again.

Field names verified against a live raw `HevyClient.get_workouts()` payload
(Gate 0, #68): a set carries `type`, `weight_kg`, `reps`, `duration_seconds`,
`distance_meters`, `rpe` (all snake_case). The `hevy:*` third-party MCP renames
these (e.g. `weight_kg`→`weight`) and is NOT the authoritative shape here.
"""

from typing import Any


def format_duration(seconds: int) -> str:
    """Seconds → compact `Nm SSs` (or `SSs` under a minute)."""
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}m {secs:02d}s" if mins else f"{secs}s"


def format_set(s: dict[str, Any], idx: int, indent: str = "       ") -> str:
    """Format a single raw Hevy set into a compact readable line.

    Handles weight×reps, weight-only, reps-only (bodyweight), duration-only,
    distance, and RPE. Non-`normal` set types (`warmup`/`dropset`/`failure`) are
    labelled with a `[type]` tag. Reads the set-type field as **`type`** (never
    `set_type`). `rpe` decimals are preserved verbatim (data logs at half points).
    """
    parts: list[str] = []

    weight = s.get("weight_kg")
    reps = s.get("reps")
    duration = s.get("duration_seconds")
    distance = s.get("distance_meters")
    rpe = s.get("rpe")
    set_type = s.get("type", "normal")

    if weight is not None and reps is not None:
        parts.append(f"{weight}kg × {reps}")
    elif weight is not None:
        parts.append(f"{weight}kg")
    elif reps is not None:
        parts.append(f"{reps} reps")

    if duration is not None:
        parts.append(format_duration(duration))

    if distance is not None:
        parts.append(f"{distance}m")

    if rpe is not None:
        parts.append(f"RPE {rpe}")

    type_tag = f" [{set_type}]" if set_type != "normal" else ""
    body = " — ".join(parts) if parts else "no data"
    return f"{indent}Set {idx + 1}{type_tag}: {body}"


def format_workout_compact(w: dict[str, Any], when: str) -> str:
    """One raw Hevy workout as a single compact line, for a review's SURROUNDING-load window
    (`session_focus`, context scope) — where the point is what else was done, not the set-by-set
    detail the pinned session itself carries via `context_builder.render_workout`.

    Per exercise: the logged title, the working-set count (warmups excluded), the heaviest
    weight×reps working set and the highest RPE logged, when present. `when` is the caller's local
    date/time label. A workout with no exercises still renders (title + when), so a session never
    silently vanishes from the window."""
    title = w.get("title") or w.get("name") or "Untitled"
    parts: list[str] = []
    for ex in w.get("exercises") or []:
        name = ex.get("canonical_title") or ex.get("title") or ex.get("exercise_template_id") or "Unknown exercise"
        sets = [s for s in (ex.get("sets") or []) if s.get("type", "normal") != "warmup"]
        seg = f"{name} ×{len(sets)}"
        loaded = [s for s in sets if s.get("weight_kg") is not None and s.get("reps") is not None]
        if loaded:
            top = max(loaded, key=lambda s: (s["weight_kg"], s["reps"]))
            seg += f" (top {top['weight_kg']}kg × {top['reps']}"
            rpes = [s["rpe"] for s in sets if s.get("rpe") is not None]
            if rpes:
                seg += f", peak RPE {max(rpes)}"
            seg += ")"
        else:
            rpes = [s["rpe"] for s in sets if s.get("rpe") is not None]
            if rpes:
                seg += f" (peak RPE {max(rpes)})"
        parts.append(seg)
    body = "; ".join(parts) if parts else "no exercises logged"
    return f"{when} [hevy] {title}: {body}"
