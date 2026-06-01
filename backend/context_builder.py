"""
Assembles the Claude system prompt from available user data.

Each integration is a self-contained section. To add a new source (Polar, MFP,
GameTraka, etc.) write a new async `_section_<name>` function that returns a
string block, then call it inside `build_system_prompt`.
"""

from datetime import datetime, timezone
from typing import Any

import pytz

import models

AEST = pytz.timezone("Australia/Brisbane")


def _now_aest() -> datetime:
    return datetime.now(AEST)


def _days_ago_label(start_str: str, today: datetime) -> str:
    """Return a human label like 'today', 'yesterday', '3 days ago' etc."""
    if not start_str:
        return "unknown date"
    try:
        # Parse ISO timestamp — may be naive or offset-aware
        raw = start_str[:19]  # strip sub-seconds and tz suffix for parsing
        workout_dt = datetime.fromisoformat(raw)
        if workout_dt.tzinfo is None:
            workout_dt = workout_dt.replace(tzinfo=timezone.utc)
        workout_date = workout_dt.astimezone(AEST).date()
        today_date = today.date()
        delta = (today_date - workout_date).days
        if delta == 0:
            return f"{workout_date.strftime('%d %b')} (today)"
        elif delta == 1:
            return f"{workout_date.strftime('%d %b')} (yesterday)"
        elif delta < 7:
            return f"{workout_date.strftime('%d %b')} ({delta} days ago)"
        elif delta < 14:
            return f"{workout_date.strftime('%d %b')} (last week)"
        else:
            weeks = delta // 7
            return f"{workout_date.strftime('%d %b')} ({weeks} weeks ago)"
    except (ValueError, AttributeError):
        return start_str[:10] if len(start_str) >= 10 else start_str


# ---------- individual context sections ----------

def _section_identity(user: models.User, now: datetime) -> str:
    name = user.full_name or user.email
    current_date = now.strftime("%A, %d %B %Y")
    current_time = now.strftime("%I:%M %p")
    return (
        f"The user's name is {name}. "
        f"Today is {current_date}. Current time is {current_time} AEST."
    )


def _section_integrations(connected: list[str]) -> str:
    if not connected:
        return "The user has no fitness integrations connected yet."
    joined = ", ".join(connected)
    return f"The user has the following integrations connected: {joined}."


def _format_set(s: dict[str, Any], idx: int) -> str:
    """Format a single set into a compact readable string."""
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
        mins, secs = divmod(int(duration), 60)
        parts.append(f"{mins}m {secs:02d}s" if mins else f"{secs}s")

    if distance is not None:
        parts.append(f"{distance}m")

    if rpe is not None:
        parts.append(f"RPE {rpe}")

    type_tag = f" [{set_type}]" if set_type != "normal" else ""
    body = " — ".join(parts) if parts else "no data"
    return f"       Set {idx + 1}{type_tag}: {body}"


def _section_hevy(
    workout_count: int,
    recent_workouts: list[dict[str, Any]],
    now: datetime,
) -> str:
    lines = ["## Hevy (strength training)", f"Total workouts logged: {workout_count}"]

    if not recent_workouts:
        lines.append("No recent workouts found.")
        return "\n".join(lines)

    lines.append(f"\nThe {len(recent_workouts)} most recent workouts:\n")

    for w in recent_workouts:
        title = w.get("title") or w.get("name") or "Untitled"
        start = w.get("start_time") or w.get("created_at") or ""
        end = w.get("end_time") or ""
        date_label = _days_ago_label(start, now)
        date_short = start[:10] if start else "unknown"

        # Duration
        duration_str = ""
        if start and end:
            try:
                s_dt = datetime.fromisoformat(start[:19])
                e_dt = datetime.fromisoformat(end[:19])
                mins = int((e_dt - s_dt).total_seconds() // 60)
                duration_str = f"\n   Duration: {mins} minutes"
            except (ValueError, AttributeError):
                pass

        lines.append(f"WORKOUT: {title} — {date_label} ({date_short}){duration_str}")
        lines.append("   Exercises:")

        exercises = w.get("exercises", [])  # all exercises, no truncation
        for ex_idx, ex in enumerate(exercises):
            ex_title = ex.get("title") or ex.get("exercise_template_id") or "Unknown exercise"
            notes = ex.get("notes", "").strip()
            rest = ex.get("rest_seconds")
            template_id = ex.get("exercise_template_id", "")

            notes_str = f" — {notes}" if notes else ""
            rest_str = f" (rest {rest}s)" if rest else ""
            id_str = f" [ID: {template_id}]" if template_id else ""
            lines.append(f"   {ex_idx + 1}. {ex_title}{id_str}{notes_str}{rest_str}")

            sets = ex.get("sets", [])
            for set_idx, s in enumerate(sets):
                lines.append(_format_set(s, set_idx))

        lines.append("")  # blank line between workouts

    return "\n".join(lines)


def _section_knowledge(entries: list[Any]) -> str:
    if not entries:
        return ""
    lines = ["## Athlete Knowledge Base"]
    # Group by category
    grouped: dict[str, list[str]] = {}
    for e in entries:
        cat = e.category if hasattr(e, "category") else e.get("category", "Other")
        content = e.content if hasattr(e, "content") else e.get("content", "")
        grouped.setdefault(cat, []).append(content)
    for category, items in grouped.items():
        lines.append(f"\n### {category}")
        for item in items:
            lines.append(f"- {item}")
    return "\n".join(lines)


def _section_routine_creation(connected: list[str]) -> str:
    if "hevy" not in connected:
        return ""
    return """## Creating Hevy Routines

You can create a routine directly in the user's Hevy account by embedding a
JSON block in your response using this exact format:

<hevy_create_routine>
{
  "title": "Routine Name",
  "exercises": [
    {
      "exercise_template_id": "XXXXXXXX",
      "notes": "optional notes",
      "rest_seconds": 90,
      "sets": [
        {"type": "normal", "weight_kg": 60, "reps": 8}
      ]
    }
  ]
}
</hevy_create_routine>

Rules for routine creation:
- ALWAYS confirm with the user before creating a routine. Ask them to confirm
  the exercises, sets, and weights first. Only include the <hevy_create_routine>
  block after the user explicitly says yes or asks you to go ahead.
- Use real exercise_template_ids from the user's workout history where possible
  (they appear as uppercase hex IDs in the workout data above, e.g. "0222DB42").
- If you don't know the template ID for an exercise, say so — never guess an ID.
- set type must be one of: "normal", "warmup", "dropset", "failure".
- weight_kg, reps, distance_meters, duration_seconds are all optional — omit or
  set to null if not applicable for the exercise type.
- rest_seconds sits on the exercise, not the set.
- The block will be automatically removed from your visible response and replaced
  with a confirmation message once the routine is created."""


def _section_knowledge_update() -> str:
    return """## Updating the Knowledge Base

You can save new information about the user to their knowledge base by embedding
a JSON block anywhere in your response:

<knowledge_update>
{"category": "Injury History", "content": "new detail to save"}
</knowledge_update>

Valid categories: Injury History, Training Background, Goals, Constraints,
Nutrition, Recovery, Other.

Use this proactively — whenever the user mentions something new about their
training, body, or preferences, save it without being asked. Examples:
- They mention a niggling pain → save to "Injury History"
- They share a new goal or target → save to "Goals"
- They discover an exercise they can't do → save to "Constraints"
- They describe what works well for recovery → save to "Recovery"

If an entry for that category already exists, the new content will be appended.
The block will be removed from your visible response and replaced with a
confirmation line. You do not need to ask permission to save — just do it and
mention what you saved in your reply."""


# ---------- add future sections here ----------
# async def _section_mfp(nutrition_data) -> str: ...
# async def _section_polar(activity_data) -> str: ...
# async def _section_gametraka(match_data) -> str: ...


# ---------- main builder ----------

def build_system_prompt(
    user: models.User,
    connected_integrations: list[str],
    hevy_data: dict[str, Any] | None = None,
    knowledge_entries: list[Any] | None = None,
) -> str:
    # Capture time once per request so all sections share the same "now"
    now = _now_aest()

    sections: list[str] = [
        "You are a personal health and performance assistant. Your job is to help the "
        "user understand their training, spot patterns, and give specific, actionable "
        "recommendations grounded in their actual data. Be direct and practical — avoid "
        "generic fitness advice when you have real numbers to work with.",
        "",
        _section_identity(user, now),
        _section_integrations(connected_integrations),
    ]

    if knowledge_entries:
        sections.append(_section_knowledge(knowledge_entries))

    if hevy_data is not None:
        count = hevy_data.get("workout_count", 0)
        workouts = hevy_data.get("recent_workouts", [])
        sections.append(_section_hevy(count, workouts, now))

    sections += [
        "",
        "When the user asks about their training, reference the data above directly. "
        "If data is missing or incomplete, say so and suggest what they could connect. "
        "Never fabricate workout details that are not in the context.",
        "",
        _section_routine_creation(connected_integrations),
        "",
        _section_knowledge_update(),
    ]

    return "\n".join(sections)
