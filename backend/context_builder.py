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

def _section_user_profile() -> str:
    """Static athlete profile, prepended to every system prompt."""
    return (
        "## About the user\n"
        "- The user is Luke (\"Easty\"). Primary device is a Samsung Galaxy Ring.\n"
        "- HRV is captured from the Ring via an accessibility scraper, NOT Health Connect.\n"
        "- Strength training is logged in Hevy.\n"
        "- Aerobic sessions use a Polar H10 chest strap.\n"
        "- Active injuries:\n"
        "  - Left little finger\n"
        "  - Right shoulder — caution with horizontal adduction and overhead work\n"
        "  - Left hamstring — provoked by striding/sprinting\n"
        "- Readiness algorithm: RMSSD vs the 7-day baseline is the PRIMARY gate; "
        "sleep quality is secondary."
    )


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


def _section_checkin(checkin: Any | None, now: datetime) -> str:
    if checkin is None:
        return (
            "## Today's Readiness\n"
            "The user has NOT completed their morning check-in today. "
            "If they ask about training or programming a session, gently remind them "
            "to complete their check-in first so you can factor in their readiness."
        )

    date_str = now.strftime("%A %d %B %Y")

    def _val(field: str) -> Any:
        return getattr(checkin, field) if hasattr(checkin, field) else checkin.get(field)

    score = _val("readiness_score") or 5
    rugby = "Yes" if _val("rugby_session_yesterday") else "No"
    notes = _val("notes") or ""
    notes_line = f"\nNotes: {notes}" if notes else ""

    # Coaching load guidance based on readiness
    if score >= 8:
        guidance = "Full prescribed loads — no restrictions."
    elif score >= 6:
        guidance = "Reduce loads 10-20%, RPE cap 7."
    elif score >= 4:
        guidance = "Reduce loads 20-30%, RPE cap 6. Consider a recovery session."
    else:
        guidance = "Recovery only — no strength work today."

    return (
        f"## Today's Readiness Score: {score}/10\n"
        f"Date: {date_str}\n"
        f"Sleep quality: {_val('sleep_quality')}/10\n"
        f"Fatigue: {_val('fatigue')}/10\n"
        f"Shoulder pain: {_val('shoulder_pain')}/10\n"
        f"Motivation: {_val('motivation')}/10\n"
        f"Rugby session yesterday: {rugby}"
        f"{notes_line}\n"
        f"\nLoad guidance: {guidance}\n"
        f"\nCoaching rules based on readiness:\n"
        f"- Score 8-10: full prescribed loads\n"
        f"- Score 6-7: reduce loads 10-20%, RPE cap 7\n"
        f"- Score 4-5: reduce loads 20-30%, RPE cap 6, consider recovery session\n"
        f"- Score 1-3: recovery only, no strength work"
    )


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


def _section_health_connect(records: list[Any], now: datetime) -> str:
    """Inject today's or yesterday's Health Connect data into the system prompt."""
    if not records:
        return ""

    today = now.date()
    yesterday = today - __import__("datetime").timedelta(days=1)

    # Prefer today, fall back to yesterday
    record = None
    for r in records:
        rec_date = r.date if hasattr(r, "date") else r.get("date")
        if rec_date == today:
            record = r
            break
        if rec_date == yesterday and record is None:
            record = r

    if record is None:
        return ""

    def _v(field: str) -> Any:
        return getattr(record, field) if hasattr(record, field) else record.get(field)

    rec_date = _v("date")
    date_label = "Today" if rec_date == today else "Yesterday"
    lines = [f"## Health Connect Data ({date_label} — {rec_date})"]

    if _v("steps") is not None:
        lines.append(f"Steps: {_v('steps'):,}")
    if _v("resting_heart_rate") is not None:
        lines.append(f"Resting HR: {round(_v('resting_heart_rate'))} bpm")
    if _v("hrv_rmssd") is not None:
        lines.append(f"HRV (RMSSD): {_v('hrv_rmssd')} ms")

    if _v("sleep_duration_minutes") is not None:
        total = _v("sleep_duration_minutes")
        h, m = divmod(total, 60)
        deep = _v("deep_sleep_minutes") or 0
        rem = _v("rem_sleep_minutes") or 0
        light = _v("light_sleep_minutes") or 0
        dh, dm = divmod(deep, 60)
        rh, rm = divmod(rem, 60)
        lh, lm = divmod(light, 60)
        lines.append(
            f"Sleep: {h}h {m}m total"
            + (f" (Deep: {dh}h {dm}m, REM: {rh}h {rm}m, Light: {lh}h {lm}m)" if deep or rem else "")
        )
        if _v("sleep_score") is not None:
            lines.append(f"Sleep score: {_v('sleep_score')}/10")

    if _v("active_calories") is not None:
        lines.append(f"Active calories: {_v('active_calories'):,}")
    if _v("oxygen_saturation") is not None:
        lines.append(f"SpO2: {_v('oxygen_saturation'):.1f}%")
    if _v("respiratory_rate") is not None:
        lines.append(f"Respiratory rate: {_v('respiratory_rate'):.1f} breaths/min")

    lines += [
        "",
        "Use this data to inform readiness assessment and session programming:",
        "- High HRV (>60ms) + good sleep (>7h, sleep score ≥7) → athlete is well recovered",
        "- Low HRV (<40ms) or poor sleep (<6h or score ≤4) → treat as lower readiness",
        "- Apply coaching load rules from the readiness score section above.",
    ]

    return "\n".join(lines)


def _section_samsung_hrv(readings: list[Any], now: datetime) -> str:
    """Inject the latest Galaxy Ring reading plus a rolling 7-day HRV baseline."""
    if not readings:
        return ""

    def _v(reading: Any, field: str) -> Any:
        return getattr(reading, field) if hasattr(reading, field) else reading.get(field)

    latest = readings[0]  # readings are ordered captured_at DESC
    rec_date = _v(latest, "captured_at")
    today = now.date()
    yesterday = today - __import__("datetime").timedelta(days=1)
    if rec_date == today:
        date_label = f"Today — {rec_date}"
    elif rec_date == yesterday:
        date_label = f"Yesterday — {rec_date}"
    else:
        date_label = str(rec_date)

    lines = [f"## Samsung Galaxy Ring (accessibility scraper — {date_label})"]

    if _v(latest, "hrv_ms") is not None:
        lines.append(f"HRV (RMSSD): {_v(latest, 'hrv_ms')} ms")
    if _v(latest, "sleep_hr_bpm") is not None:
        lines.append(f"Sleep HR: {_v(latest, 'sleep_hr_bpm')} bpm")
    if _v(latest, "respiratory_rate") is not None:
        lines.append(f"Respiratory rate: {_v(latest, 'respiratory_rate'):.1f} breaths/min")
    if _v(latest, "spo2_average_pct") is not None:
        lines.append(f"SpO2 (avg): {_v(latest, 'spo2_average_pct'):.1f}%")
    if _v(latest, "sleep_efficiency_pct") is not None:
        lines.append(f"Sleep efficiency: {_v(latest, 'sleep_efficiency_pct')}%")

    duration = _v(latest, "total_sleep_time_minutes") or _v(latest, "actual_sleep_time_minutes")
    if duration is not None:
        h, m = divmod(duration, 60)
        lines.append(f"Sleep duration: {h}h {m}m")

    stages: list[str] = []
    if _v(latest, "deep_minutes") is not None:
        stages.append(f"Deep {_v(latest, 'deep_minutes')}m")
    if _v(latest, "rem_minutes") is not None:
        stages.append(f"REM {_v(latest, 'rem_minutes')}m")
    if _v(latest, "light_minutes") is not None:
        stages.append(f"Light {_v(latest, 'light_minutes')}m")
    if _v(latest, "awake_minutes") is not None:
        stages.append(f"Awake {_v(latest, 'awake_minutes')}m")
    if stages:
        lines.append("Sleep stages: " + ", ".join(stages))

    if _v(latest, "bedtime") or _v(latest, "wake_time"):
        lines.append(f"Bedtime: {_v(latest, 'bedtime') or '—'}, Wake: {_v(latest, 'wake_time') or '—'}")

    # ----- rolling 7-day HRV baseline -----
    rmssd_values = [_v(r, "hrv_ms") for r in readings if _v(r, "hrv_ms") is not None]
    if rmssd_values:
        baseline = sum(rmssd_values) / len(rmssd_values)
        lines.append("")
        lines.append(f"7-day HRV baseline: {baseline:.0f} ms ({len(rmssd_values)} readings)")
        today_rmssd = _v(latest, "hrv_ms")
        if today_rmssd is not None:
            diff = today_rmssd - baseline
            direction = "above" if diff >= 0 else "below"
            lines.append(f"Today vs baseline: {abs(diff):.0f}ms {direction} mean")

    # ----- last 7 readings -----
    lines.append("")
    lines.append("Last 7 readings (RMSSD):")
    for r in readings[:7]:
        d = _v(r, "captured_at")
        v = _v(r, "hrv_ms")
        lines.append(f"- {d}: {v} ms" if v is not None else f"- {d}: — ms")

    lines += [
        "",
        "This Ring HRV is the PRIMARY readiness signal (the Galaxy Ring does not expose "
        "HRV through Health Connect, hence the scraper). Compare RMSSD against the 7-day "
        "baseline first; treat sleep quality as the secondary input.",
    ]

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
    knowledge_entries: list[Any] | None = None,
    today_checkin: Any | None = None,
    health_connect_records: list[Any] | None = None,
    samsung_hrv: Any | None = None,
) -> str:
    # Capture time once per request so all sections share the same "now"
    now = _now_aest()

    sections: list[str] = [
        _section_user_profile(),
        "",
        "You are a personal health and performance assistant. Your job is to help the "
        "user understand their training, spot patterns, and give specific, actionable "
        "recommendations grounded in their actual data. Be direct and practical — avoid "
        "generic fitness advice when you have real numbers to work with.",
        "",
        _section_identity(user, now),
        _section_checkin(today_checkin, now),
        _section_integrations(connected_integrations),
    ]

    if knowledge_entries:
        sections.append(_section_knowledge(knowledge_entries))

    if health_connect_records:
        hc_section = _section_health_connect(health_connect_records, now)
        if hc_section:
            sections.append(hc_section)

    if samsung_hrv:
        ring_section = _section_samsung_hrv(samsung_hrv, now)
        if ring_section:
            sections.append(ring_section)

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
