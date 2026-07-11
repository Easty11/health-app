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
