"""
Assembles the Claude system prompt from available user data.

Each integration is a self-contained section. To add a new source (Polar, MFP,
GameTraka, etc.) write a new async `_section_<name>` function that returns a
string block, then call it inside `build_system_prompt`.
"""

from datetime import date
from typing import Any

import models


# ---------- individual context sections ----------

def _section_identity(user: models.User) -> str:
    name = user.full_name or user.email
    return f"The user's name is {name}. Today's date is {date.today().isoformat()}."


def _section_integrations(connected: list[str]) -> str:
    if not connected:
        return "The user has no fitness integrations connected yet."
    joined = ", ".join(connected)
    return f"The user has the following integrations connected: {joined}."


def _section_hevy(workout_count: int, recent_workouts: list[dict[str, Any]]) -> str:
    lines = [f"## Hevy (strength training)", f"Total workouts logged: {workout_count}"]

    if not recent_workouts:
        lines.append("No recent workouts found.")
        return "\n".join(lines)

    lines.append(f"\nThe {len(recent_workouts)} most recent workouts:")
    for w in recent_workouts:
        title = w.get("title") or w.get("name") or "Untitled"
        start = w.get("start_time") or w.get("created_at") or ""
        # Trim to date portion if ISO timestamp
        start_short = start[:10] if start else "unknown date"

        exercise_names: list[str] = []
        for ex in w.get("exercises", []):
            ex_title = ex.get("title") or ex.get("exercise_template_id") or ""
            if ex_title and ex_title not in exercise_names:
                exercise_names.append(ex_title)

        sets_summary = ""
        if exercise_names:
            sets_summary = f" — {', '.join(exercise_names[:6])}"
            if len(exercise_names) > 6:
                sets_summary += f" (+{len(exercise_names) - 6} more)"

        lines.append(f"  • {start_short}: {title}{sets_summary}")

    return "\n".join(lines)


# ---------- add future sections here ----------
# async def _section_mfp(nutrition_data) -> str: ...
# async def _section_polar(activity_data) -> str: ...
# async def _section_gametraka(match_data) -> str: ...


# ---------- main builder ----------

def build_system_prompt(
    user: models.User,
    connected_integrations: list[str],
    hevy_data: dict[str, Any] | None = None,
) -> str:
    sections: list[str] = [
        "You are a personal health and performance assistant. Your job is to help the "
        "user understand their training, spot patterns, and give specific, actionable "
        "recommendations grounded in their actual data. Be direct and practical — avoid "
        "generic fitness advice when you have real numbers to work with.",
        "",
        _section_identity(user),
        _section_integrations(connected_integrations),
    ]

    if hevy_data is not None:
        count = hevy_data.get("workout_count", 0)
        workouts = hevy_data.get("recent_workouts", [])
        sections.append(_section_hevy(count, workouts))

    sections += [
        "",
        "When the user asks about their training, reference the data above directly. "
        "If data is missing or incomplete, say so and suggest what they could connect. "
        "Never fabricate workout details that are not in the context.",
    ]

    return "\n".join(sections)
