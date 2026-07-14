"""
Assembles the Claude system prompt from available user data.

Each integration is a self-contained section. To add a new source (Polar, MFP,
GameTraka, etc.) write a new async `_section_<name>` function that returns a
string block, then call it inside `build_system_prompt`.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytz

import models
from current_state import CurrentState, HRVBaseline
from hevy_format import format_set

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

def _section_user_profile(device_profile: dict[str, Any] | None) -> str:
    """Device/method preferences, prepended to every system prompt.

    Identity is rendered dynamically by `_section_identity`. Injuries are
    rendered per-user by `_section_schedule` from `type="injury"` structured
    entries. The only per-user fact carried here is `current_state`'s
    `device_profile` — which device/tool the user logs each signal with.
    Absent that entry, this renders a neutral line; nothing is assumed.
    """
    if device_profile:
        profile_lines = "".join(f"- {k}: {v}\n" for k, v in device_profile.items())
    else:
        profile_lines = "- No device/method preferences recorded yet.\n"

    return (
        "## About the user\n"
        f"{profile_lines}"
        "\n"
        "---\n"
        "## SCHEDULE INTELLIGENCE\n"
        "\n"
        "When the user mentions anything implying a schedule change, new commitment, "
        "recovery activity, or injury management:\n"
        "\n"
        "STEP 1 — ASK BEFORE WRITING\n"
        "Do not write a knowledge entry until clarified. Ask targeted questions to establish:\n"
        "- Specific days (or is it flexible?)\n"
        "- Time of day and whether same-day training is affected\n"
        "- Whether it replaces existing sessions or adds to them\n"
        "- Duration: ongoing / fixed weeks / unknown\n"
        "- Hard (fixed time) or soft (preference)\n"
        "\n"
        "Keep questions brief — max 3-4, conversational, not a form. Ask them together in one message.\n"
        "\n"
        "STEP 2 — WRITE STRUCTURED ENTRY\n"
        "Once clarified, emit a knowledge update block:\n"
        "\n"
        "<knowledge_update>\n"
        "{\n"
        '  "type": "schedule_item",\n'
        '  "key": "[activity_yearmonth]",\n'
        '  "value": {\n'
        '    "activity": "[name]",\n'
        '    "days": ["monday", "thursday"],\n'
        '    "hard": true,\n'
        '    "time_of_day": "morning",\n'
        '    "same_day_training": false,\n'
        '    "duration_weeks": null\n'
        "  },\n"
        '  "source": "chat",\n'
        '  "expires_at": null,\n'
        '  "notes": "[raw text from user]"\n'
        "}\n"
        "</knowledge_update>\n"
        "\n"
        "STEP 3 — SYNTHESISE IMPACT\n"
        "After writing, immediately state:\n"
        "- Which existing schedule items are affected\n"
        "- Which training days change as a result\n"
        "- Any conflicts created\n"
        "- Any load distribution changes\n"
        "- Propose adjustments if needed, ask for confirmation\n"
        "\n"
        "TRIGGER PHRASES (not exhaustive):\n"
        "physio, rehab, coach has me, starting X, adding X,\n"
        "cutting back, taking X off, match moved, game on,\n"
        "tournament, appointment, session added, twice a week\n"
        "\n"
        "TEMPORAL EVENTS — capture without asking questions:\n"
        '"big weekend", "didn\'t sleep", "feeling off",\n'
        '"heavy session", "travelled", "sick", "stressful week"\n'
        '→ type: "load_context", expires_at: 2-3 days from today\n'
        "→ Just acknowledge and log — no clarifying questions\n"
        "\n"
        "CONTRADICTION HANDLING:\n"
        "If the user says something that contradicts an existing active schedule entry "
        '(e.g. "physio is done"):\n'
        '- Emit knowledge_update with active: false for that key\n'
        "- Confirm the removal and re-synthesise the week\n"
        "---"
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

        description = (w.get("description") or "").strip()
        if description:
            lines.append(f"   Note: {description}")

        lines.append("   Exercises:")

        exercises = w.get("exercises", [])  # all exercises, no truncation
        for ex_idx, ex in enumerate(exercises):
            # Render the CURRENT catalogue title (DECISIONS_LOG #81), annotated
            # upstream as `canonical_title` — Hevy's logged `title` is a snapshot
            # from when the workout was logged and drifts as Hevy renames its
            # templates, so a title echoed back from the log may resolve to
            # nothing. Fall back to the logged title only when the id is absent
            # from the catalogue, and mark that case: an unmarked fallback would
            # read as canonical and be echoed back as if resolvable.
            canonical = ex.get("canonical_title")
            logged = ex.get("title")
            template_id = ex.get("exercise_template_id", "")
            if canonical:
                ex_title = canonical
                uncatalogued_str = ""
            else:
                ex_title = logged or template_id or "Unknown exercise"
                uncatalogued_str = " [UNCATALOGUED — logged title, may not resolve]"

            notes = ex.get("notes", "").strip()
            rest = ex.get("rest_seconds")

            notes_str = f" — {notes}" if notes else ""
            rest_str = f" (rest {rest}s)" if rest else ""
            id_str = f" [ID: {template_id}]" if template_id else ""
            lines.append(
                f"   {ex_idx + 1}. {ex_title}{id_str}{uncatalogued_str}{notes_str}{rest_str}"
            )

            sets = ex.get("sets", [])
            for set_idx, s in enumerate(sets):
                lines.append(format_set(s, set_idx))

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


def _section_daily_record(record: Any) -> str:
    """
    Descriptive section for the new two-moment daily record.
    MUST NOT contain prescriptive load instructions — descriptive only.
    """
    def _v(field: str) -> Any:
        return getattr(record, field) if hasattr(record, field) else record.get(field)

    has_am = _v("am_timestamp") is not None
    has_pm = _v("pm_timestamp") is not None

    if not has_am and not has_pm:
        return (
            "## Today's Daily Record\n"
            "Morning check-in: not yet submitted today."
        )

    lines = ["## Today's Daily Record"]

    if has_am:
        lines.append("\n### Morning Check-in")
        mr = _v("morning_readiness")
        if mr is not None:
            lines.append(f"Morning readiness: {mr}/5 (subjective felt state)")
        sq = _v("sleep_quality")
        if sq is not None:
            lines.append(f"Sleep quality: {sq}/5")
        fatigue = _v("fatigue")
        if fatigue is not None:
            lines.append(f"Fatigue: {fatigue}/10")
        soreness = _v("soreness") or {}
        if soreness:
            sore_str = ", ".join(f"{k} {val}/5" for k, val in soreness.items())
            lines.append(f"Soreness: {sore_str}")
        motivation = _v("motivation")
        if motivation is not None:
            lines.append(f"Motivation: {motivation}/10")
        life_load = _v("life_load")
        if life_load is not None:
            lines.append(f"Life load (yesterday): {life_load}/5")
        alcohol_units = _v("alcohol_units")
        if alcohol_units is not None:
            finish = _v("alcohol_finish_time") or "unknown"
            lines.append(f"Alcohol last night: {alcohol_units} units, finished {finish}")

        hrv = _v("passive_hrv_ms")
        sleep_min = _v("passive_sleep_min")
        if hrv is not None or sleep_min is not None:
            lines.append("")
            if hrv is not None:
                lines.append(f"Ring HRV at capture: {hrv} ms")
            if sleep_min is not None:
                h, m = divmod(sleep_min, 60)
                lines.append(f"Sleep at capture: {h}h {m}m")

        nb = _v("naive_baseline")
        if nb is not None:
            lines.append(f"\nNaive baseline (frozen formula): {nb:.1f}/10")
        mf = _v("model_forecast")
        if mf is not None:
            lines.append(f"Model forecast [LOW-CONFIDENCE]: {mf:.1f}/10")
        else:
            lines.append("Model forecast: building baseline — insufficient history")

        lines += [
            "",
            "DESCRIPTIVE-ONLY GUARDRAIL: Reference trends and observations only.",
            "Do not issue prescriptive load instructions or present the score as",
            "authoritative. The model forecast remains low-confidence until it",
            "demonstrably beats the naive baseline on this user's data.",
        ]
    else:
        lines.append("Morning check-in: not yet submitted today.")

    if has_pm:
        lines.append("\n### Nightly Close-out")
        tr = _v("today_rating")
        if tr is not None:
            lines.append(f"Today rating: {tr}/5")
        sq_pm = _v("session_quality")
        if sq_pm is not None:
            lines.append(f"Session quality: {sq_pm}/5")
        rpe = _v("session_rpe")
        if rpe is not None:
            lines.append(f"Session RPE: {rpe}/10")
        mo = _v("mindfulness_occurred")
        if mo is not None:
            md = _v("mindfulness_duration_min")
            suffix = f" ({md} min)" if md else ""
            lines.append(f"Wind-down (mindfulness): {'Yes' if mo else 'No'}{suffix}")

    return "\n".join(lines)


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


def _section_onboarding_interview() -> str:
    return """## ONBOARDING INTERVIEW — this user has no structured profile yet

Before giving any training/health advice, run a short adaptive interview:

1. Ask what they want to use this assistant for (strength training, recovery/HRV
   tracking, general health, or a mix) — establish scope before eliciting anything
   else. Do not assume a domain.
2. Based on their answer, ask only about that domain's profile — devices/tools
   they log with, any current injuries or constraints, weekly schedule. Keep
   questions brief and conversational (a few at a time), same tone as SCHEDULE
   INTELLIGENCE below — do not turn this into a form.
3. As facts are confirmed, emit `<knowledge_update>` blocks using the structured
   schema documented in SCHEDULE INTELLIGENCE below (`type` one of
   `schedule_item | load_context | injury | preference`). Use `type="preference",
   key="device_profile"` for which device/tool they use for which signal (e.g.
   `{"hrv_source": "...", "strength_log_tool": "...", "aerobic_hr_source": "...",
   "readiness_primary_gate": "..."}` — include only what they actually tell you).
   Use `type="injury"` per injury (`value: {"body_part": ..., "restrictions": [...]}`).
4. Stay education-scoped throughout — this is not a clinical-advice path. Do not
   diagnose or prescribe treatment; if something sounds medical, suggest they see
   a professional and log it as context, not a directive.

Once basic scope + device profile are captured, proceed with the conversation
normally — you don't need every field before being useful."""


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
        # Deep alone is never a daily readiness term (unreliable deep/light
        # boundary); report combined deep+light, which is robust. REM unaffected.
        # See DECISIONS_LOG — HRV & Sleep Data Integrity brief, Task 4.
        dlh, dlm = divmod(deep + light, 60)
        rh, rm = divmod(rem, 60)
        lines.append(
            f"Sleep: {h}h {m}m total"
            + (f" (Deep+Light: {dlh}h {dlm}m, REM: {rh}h {rm}m)" if deep or light or rem else "")
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


def _section_samsung_hrv(readings: list[Any], now: datetime, baseline: HRVBaseline | None) -> str:
    """Inject the latest Galaxy Ring reading plus a rolling 7-day HRV baseline.

    `baseline` is computed-on-read by `current_state` (single source for the
    number); this section only formats it.
    """
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
    # Samsung Ring's deep/light boundary is not fit for daily use: the two classes
    # are mutually confused (observed deep ~3% / light ~70% vs typical 15-20% /
    # 50-55%, a complementary two-class confusion signature). Deep alone is never a
    # daily readiness term — but their SUM is robust because the confusion is
    # internal to the pair, so report combined deep+light. REM and awake are
    # unaffected. Deep alone is a long-run trend only (see get_recovery_metrics).
    # See DECISIONS_LOG — HRV & Sleep Data Integrity brief, Task 4.
    deep = _v(latest, "deep_minutes")
    light = _v(latest, "light_minutes")
    if deep is not None or light is not None:
        stages.append(f"Deep+Light {(deep or 0) + (light or 0)}m")
    if _v(latest, "rem_minutes") is not None:
        stages.append(f"REM {_v(latest, 'rem_minutes')}m")
    if _v(latest, "awake_minutes") is not None:
        stages.append(f"Awake {_v(latest, 'awake_minutes')}m")
    if stages:
        lines.append("Sleep stages: " + ", ".join(stages))

    if _v(latest, "bedtime") or _v(latest, "wake_time"):
        lines.append(f"Bedtime: {_v(latest, 'bedtime') or '—'}, Wake: {_v(latest, 'wake_time') or '—'}")

    # ----- rolling 7-day HRV baseline (computed by current_state) -----
    if baseline is not None:
        lines.append("")
        lines.append(f"7-day HRV baseline: {baseline.mean_ms:.0f} ms ({baseline.n} readings)")
        if baseline.diff_from_mean_ms is not None:
            direction = "above" if baseline.diff_from_mean_ms >= 0 else "below"
            lines.append(f"Today vs baseline: {abs(baseline.diff_from_mean_ms):.0f}ms {direction} mean")

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


_DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _section_schedule(entries: list[Any], now: datetime) -> str:
    """Build a synthesised weekly schedule view from structured knowledge entries."""
    if not entries:
        return ""

    today = now.date()
    next_7 = today + timedelta(days=7)
    today_weekday = today.strftime("%A").lower()

    schedule_items = [e for e in entries if (
        (getattr(e, "type", None) or e.get("type")) == "schedule_item"
    )]
    load_contexts = [e for e in entries if (
        (getattr(e, "type", None) or e.get("type")) == "load_context"
    )]
    injuries = [e for e in entries if (
        (getattr(e, "type", None) or e.get("type")) == "injury"
    )]

    def _v(entry: Any, field: str) -> Any:
        return getattr(entry, field) if hasattr(entry, field) else entry.get(field)

    lines = ["## Weekly Schedule"]

    # Build day → list of (activity, hard, source) mapping
    day_map: dict[str, list[str]] = {d: [] for d in _DAY_ORDER}
    hard_days: set[str] = set()

    for e in schedule_items:
        val = _v(e, "value") or {}
        activity = val.get("activity", "?")
        days = val.get("days", [])
        hard = val.get("hard", False)
        source = _v(e, "source") or "system"
        notes = _v(e, "notes") or ""
        tag = "hard" if hard else "soft"
        source_note = f" [{notes[:40]}]" if source == "chat" and notes else ""
        for d in days:
            d_lower = d.lower()
            if d_lower in day_map:
                day_map[d_lower].append(f"{activity} ({tag}){source_note}")
                if hard:
                    hard_days.add(d_lower)

    for day in _DAY_ORDER:
        items = day_map[day]
        marker = " ◀ today" if day == today_weekday else ""
        if items:
            lines.append(f"{day.capitalize()}: {', '.join(items)}{marker}")
        else:
            lines.append(f"{day.capitalize()}: rest{marker}")

    # THIS WEEK FLAGS
    flags: list[str] = []

    # Hard commitments in next 7 days
    for e in schedule_items:
        val = _v(e, "value") or {}
        if not val.get("hard"):
            continue
        activity = val.get("activity", "?")
        days = val.get("days", [])
        for d in days:
            # Map weekday name to next occurrence date
            try:
                target_idx = _DAY_ORDER.index(d.lower())
                today_idx = _DAY_ORDER.index(today_weekday)
                delta = (target_idx - today_idx) % 7
                occurrence = today + timedelta(days=delta)
                if today <= occurrence <= next_7:
                    flags.append(f"Hard commitment: {activity} on {occurrence.strftime('%A %d %b')}")
                    # Pre-event shadow: day before
                    shadow = occurrence - timedelta(days=1)
                    if shadow >= today:
                        flags.append(
                            f"Pre-event shadow: reduced load recommended on "
                            f"{shadow.strftime('%A %d %b')} (day before {activity})"
                        )
            except (ValueError, IndexError):
                pass

    # Active load_context entries
    for e in load_contexts:
        val = _v(e, "value") or {}
        desc = val.get("description", _v(e, "notes") or "load context")
        expires = _v(e, "expires_at")
        expires_str = f" — expires {expires}" if expires else ""
        flags.append(f"Load context: {desc}{expires_str}")

    # Active injury summary
    for e in injuries:
        val = _v(e, "value") or {}
        body_part = val.get("body_part", "unknown")
        restrictions = val.get("restrictions", [])
        r_str = f" (avoid: {', '.join(restrictions)})" if restrictions else ""
        flags.append(f"Injury: {body_part}{r_str}")

    if flags:
        lines.append("\nTHIS WEEK FLAGS")
        for f in flags:
            lines.append(f"- {f}")

    return "\n".join(lines)


# ---------- Adaptive Exposure Engine sections (Decision Support) ----------

# TEMPORARY (DECISIONS_LOG #60): #49's dedicated lab-interpretation view has not
# been built yet — "Metrics" (/metrics) is the closest existing screen, and today
# it only does attach/extract/confirm, not a persisted read-back. This constant
# is a stand-in pointer, not a real destination; swap it for the real interpretation
# view's name the moment #49 ships a UI, and drop this comment.
_LAB_INTERPRETATION_VIEW_LABEL = "Metrics page"


def _section_labs(labs: list[Any]) -> str:
    """Render latest-per-marker lab GENERALITY — render-policy FIREWALL (#60).

    Standing feed = generality only: marker + lab-asserted flag + availability.
    `value_num`, `unit_canonical`, `ref_low`/`ref_high`, `computed_flag`, deltas,
    and axis-verdicts are ALL withheld from this standing render — a value sitting
    in the standing prompt is reasoning substrate whether or not it was asked for,
    so the boundary here is structural (absent unless requested), not a
    behavioural "don't mention it" instruction over data that's already present.
    The numeric value relays only via `render_asked_lab_value`, request-scoped,
    triggered by an explicit single-marker ask (see chat.py). Unmapped markers
    (no canonical binding yet) get an availability line only. A derived marker
    older than the latest panel's collection date is tagged stale, since it was
    carried forward rather than freshly observed.
    """
    if not labs:
        return ""

    lines = ["## Lab Results (availability — generality only, no values here)"]

    latest_panel_date = max((l.collected_date for l in labs), default=None)

    for l in labs:
        if l.marker_canonical is None:
            lines.append(f"- {l.marker_name_raw}: available, unmapped (no canonical binding yet)")
            continue

        flag_str = f" [{l.lab_flag}, lab-asserted]" if l.lab_flag else ""

        stale_str = ""
        if l.is_derived and latest_panel_date is not None and l.collected_date < latest_panel_date:
            stale_str = " (stale — derived, carried from an earlier panel)"

        lines.append(f"- {l.marker_canonical}: measured{flag_str} — collected {l.collected_date}{stale_str}")

    lines += [
        "",
        "Do NOT state a numeric value or reference range for any marker above — you do "
        "not have them. If the user explicitly asks for a specific marker's number, that "
        "value (if available) will be supplied to you separately for that reply only; "
        "relay only what's explicitly given to you, never estimate or recall a number "
        f"from earlier in the conversation. Never interpret a lab result, compare it "
        f"across time, name a mechanism, or suggest an action — direct the user to the "
        f"{_LAB_INTERPRETATION_VIEW_LABEL} for that.",
    ]

    return "\n".join(lines)


def render_asked_lab_value(row: Any) -> str:
    """Request-scoped ONLY — appended to the system prompt for a single turn when
    the user explicitly named a marker they have on file (see
    `reads.labs_reads.find_marker` + chat.py's wiring). Never part of the standing
    `_section_labs` render and never persisted into a later turn's prompt; the
    value re-triggers only if the user asks again.

    Still withholds `computed_flag`, deltas, axis-verdicts, and levers (#60) —
    the value is a relay, not an interpretation.
    """
    if row.value_num is not None:
        value_str = f"{row.value_operator or ''}{row.value_num}"
    elif row.value_qualitative:
        value_str = row.value_qualitative
    else:
        value_str = "not recorded"

    unit_str = f" {row.unit_canonical}" if row.unit_canonical else ""

    ref_str = ""
    if row.ref_low is not None or row.ref_high is not None:
        lo = f"{'>' if row.ref_low_exclusive else '≥'}{row.ref_low}" if row.ref_low is not None else None
        hi = f"{'<' if row.ref_high_exclusive else '≤'}{row.ref_high}" if row.ref_high is not None else None
        bounds = "–".join(x for x in (lo, hi) if x)
        ref_str = f" (lab reference {bounds})"

    return (
        f"## Requested Lab Value — {row.marker_canonical or row.marker_name_raw}\n"
        "The user explicitly asked for this marker's number. You may relay it plainly:\n"
        f"{value_str}{unit_str}{ref_str} — collected {row.collected_date}.\n"
        "State only this value and reference range. Do not interpret it, compare it "
        "across time, name a mechanism, or suggest an action from it — direct the user "
        f"to the {_LAB_INTERPRETATION_VIEW_LABEL} for that."
    )


def _section_fortification(profile: dict[str, Any] | None) -> str:
    """Render the structured fortification-target profile (spec §9) — the object
    that replaces the hardcoded injury string. Lever, not directive."""
    if not profile:
        return ""
    lines = ["## Fortification Target (Adaptive Exposure Engine)"]

    floor = profile.get("floor") or {}
    if floor:
        tag = floor.get("tag")
        dem = floor.get("demonstrated")
        floor_str = " / ".join(x for x in (dem, f"tag: {tag}" if tag else None) if x)
        lines.append(f"- Floor (what you already survive, not Phase 1): {floor_str}")
    if profile.get("ceiling"):
        lines.append(f"- Ceiling: {profile['ceiling']}")
    if profile.get("horizon"):
        hd = profile.get("horizon_date")
        lines.append(f"- Horizon: {profile['horizon']}" + (f" ({hd})" if hd else ""))
    if profile.get("primary_target"):
        note = profile.get("primary_target_note")
        lines.append(f"- Primary target (Fortify bias): {profile['primary_target']}")
        if note:
            lines.append(f"  - {note}")

    for sig in profile.get("live_signals") or []:
        bits = [sig.get("signal", "signal")]
        if sig.get("side"):
            bits.append(f"{sig['side']}-side")
        if sig.get("status"):
            bits.append(sig["status"])
        line = f"- Live signal: {', '.join(bits)}"
        if sig.get("self_triage"):
            line += f" — self-triage: {sig['self_triage']}"
        lines.append(line)

    for hs in profile.get("hard_stops") or []:
        what = hs.get("region_key") or hs.get("pattern") or "pattern"
        side = hs.get("side")
        reason = hs.get("reason") or ""
        lines.append(f"- Hard stop: {what}" + (f" ({side})" if side else "") + (f" — {reason}" if reason else ""))

    if profile.get("vehicle_bias"):
        lines.append(f"- Vehicle bias (ranked): {', '.join(profile['vehicle_bias'])}")

    lines += [
        "",
        "This is a lever, not a directive. Interpretation of any formal screen is the "
        "practitioner's line — the engine probes and surfaces, it does not diagnose.",
    ]
    return "\n".join(lines)


def _section_probe(selection: dict[str, Any] | None) -> str:
    """Surface this session's one Probe suggestion + the Fortify recommendation
    (spec §2, §2.1). Education idiom; never presented as a verdict."""
    if not selection:
        return ""
    lines = ["## This Session — Engine Suggestion"]
    mode = selection.get("mode_recommended")
    budget = selection.get("budget") or {}
    if mode:
        lines.append(
            f"- Recommended mode: {mode.upper()} "
            f"(probe budget {budget.get('probe')}, never zero)"
        )

    fort = selection.get("fortify") or {}
    if fort.get("target"):
        lines.append(f"- FORTIFY (exploit) → {fort.get('target_label') or fort['target']}")
        vehicles = fort.get("vehicles") or []
        if vehicles:
            lines.append("  - Vehicles: " + "; ".join(v.get("label", v.get("key", "")) for v in vehicles[:4]))
        dosing = fort.get("dosing") or {}
        if dosing.get("windows"):
            lines.append(f"  - Load windows: {', '.join(dosing['windows'])}")

    probe = selection.get("probe")
    if probe:
        side = probe.get("side")
        side_str = f" ({side})" if side and side != "bilateral" else ""
        lines.append(f"- PROBE (explore) → {probe.get('label')}{side_str} [{probe.get('plane')}/{probe.get('capacity')}]")
        if probe.get("probing_test"):
            lines.append(f"  - Probing test: {probe['probing_test']}")
        if probe.get("expectation"):
            lines.append(f"  - Reference expectation (a flag, not a verdict): {probe['expectation']}")
        if probe.get("gated_note"):
            lines.append(f"  - {probe['gated_note']}")
        lines.append(
            "  - One probe this session only (clean attribution, §2.1). Enter at "
            "exploratory load. The user logs whether it felt unstable / asymmetric / "
            "hard — that report is the result. Pain = stop + refer."
        )
    else:
        lines.append("- PROBE: queue empty under current filters (well-sampled or hard-stopped).")

    for n in selection.get("notes") or []:
        lines.append(f"- Note: {n}")

    lines += [
        "",
        "### Logging a probe/fortify result (adaptation loop, §7)",
        "When the user reports how a probed or fortified pattern felt, record it by "
        "embedding ONE block per region. It is stripped from your visible reply:",
        "",
        "<capability_update>",
        '{"region_key": "single_leg_hop", "side": "right", "tag": "capability_revealed", '
        '"probe_result": "deficient", "signal_text": "felt unstable landing on the right"}',
        "</capability_update>",
        "",
        "- region_key must be one from the engine taxonomy (the PROBE/FORTIFY lines above).",
        "- tag ∈ absorbed_clean | symptom_carryover | flare | capability_revealed.",
        "- capability_revealed requires probe_result ∈ pass | deficient.",
        "- side ∈ left | right | bilateral.",
        "- Only log what the user actually reports. Pain = stop + refer, do not score.",
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
    state: CurrentState,
    hevy_data: dict[str, Any] | None = None,
    knowledge_entries: list[Any] | None = None,
    today_checkin: Any | None = None,
    health_connect_records: list[Any] | None = None,
    samsung_hrv: Any | None = None,
    daily_record: Any | None = None,
    engine_selection: dict[str, Any] | None = None,
) -> str:
    # Capture time once per request so all sections share the same "now"
    now = _now_aest()

    # Use new DailyRecord section when available; fall back to legacy check-in
    readiness_section = (
        _section_daily_record(daily_record)
        if daily_record is not None
        else _section_checkin(today_checkin, now)
    )

    sections: list[str] = [
        _section_user_profile(state.device_profile),
        "",
        "You are a personal health and performance assistant. Your job is to help the "
        "user understand their training, spot patterns, and give specific, actionable "
        "recommendations grounded in their actual data. Be direct and practical — avoid "
        "generic fitness advice when you have real numbers to work with.",
        "",
        _section_identity(user, now),
        readiness_section,
        _section_integrations(connected_integrations),
    ]

    if not state.knowledge_entries:
        sections.append(_section_onboarding_interview())

    if state.fortification_profile is not None:
        fort_section = _section_fortification(state.fortification_profile)
        if fort_section:
            sections.append(fort_section)

    if engine_selection is not None:
        probe_section = _section_probe(engine_selection)
        if probe_section:
            sections.append(probe_section)

    if knowledge_entries:
        sections.append(_section_knowledge(knowledge_entries))

    if state.knowledge_entries:
        schedule_section = _section_schedule(state.knowledge_entries, now)
        if schedule_section:
            sections.append(schedule_section)

    if state.labs:
        labs_section = _section_labs(state.labs)
        if labs_section:
            sections.append(labs_section)

    if health_connect_records:
        hc_section = _section_health_connect(health_connect_records, now)
        if hc_section:
            sections.append(hc_section)

    if samsung_hrv:
        ring_section = _section_samsung_hrv(samsung_hrv, now, state.hrv_baseline_7d)
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
