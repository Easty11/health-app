"""
Assembles the Claude system prompt from available user data.

Each integration is a self-contained section. To add a new source (Polar, MFP,
GameTraka, etc.) write a new async `_section_<name>` function that returns a
string block, then call it inside `build_system_prompt`.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytz

import models
from current_state import CurrentState, HRVBaseline
from hevy_format import format_set
from hevy_routine_format import format_routine_compact, format_routine_full  # shared renderers (#314)
# Write-shape vocab for the knowledge-update protocol text (#313), GENERATED not re-typed so
# the coach's instructions cannot drift from the validators. Acyclic: `routers.knowledge`
# imports engine.taxonomy / load_events_metabolic / models / auth / database / load_metrics —
# none import `context_builder`.
from routers.knowledge import (
    MACRO_MAX_CHARS,
    REVISED_BY_VALUES,
    SCHEDULE_ITEM_FIELDS,
    TRAINING_PLAN_FIELDS,
    TRAINING_PLAN_KEY,
    _SATISFIES_VALIDATORS,
)
# Week-planner derivation (#316), ONE definition shared with the chat consistency line —
# engine.week_plan imports resolver/load_metrics/models, never context_builder (acyclic).
from engine.week_plan import consistency_rows, schedule_sessions_per_week

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
        "- Specific days, or how many sessions a week if it floats\n"
        "- Time of day and whether same-day training is affected\n"
        "- Whether it replaces existing sessions or adds to them\n"
        "- Duration: ongoing / fixed weeks / unknown\n"
        "- Hard (fixed time) or soft (preference)\n"
        "- Expected load: light / moderate / heavy. ASK — never guess. This is a COST\n"
        "  fact and is separate from `hard`, which is only about immovability in the\n"
        "  calendar. A hard commitment can be light; a soft one can be heavy.\n"
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
        '    "sessions_per_week": null,\n'
        '    "hard": true,\n'
        '    "expected_load": "moderate",\n'
        '    "time_of_day": "morning",\n'
        '    "time_range": null,\n'
        '    "same_day_training": false,\n'
        '    "same_day_note": null,\n'
        '    "duration_weeks": null,\n'
        '    "season_end": null,\n'
        '    "supersedes": null,\n'
        '    "satisfies": null\n'
        "  },\n"
        '  "expires_at": null,\n'
        '  "notes": "[raw text from user]"\n'
        "}\n"
        "</knowledge_update>\n"
        "\n"
        "THE SHAPE IS VALIDATED AND CLOSED. A block that does not conform is REFUSED,\n"
        "not stored, and you will be told why. Rules:\n"
        f"- The stored fields, all of them: {', '.join(SCHEDULE_ITEM_FIELDS)}. No key outside\n"
        "  this set. If a fact has no field, say so — do not invent a key for it (that is how\n"
        "  `minimum_days` came to exist).\n"
        "- `days` holds weekday names only: monday…sunday, lowercase. A frequency like\n"
        '  "flexible" is NOT a day — it belongs in `sessions_per_week` (1-14).\n'
        "- At least one of `days` or `sessions_per_week` must be present.\n"
        "- `hard` and `same_day_training` are strict booleans. Constraint prose goes in\n"
        "  `same_day_note`, never in the boolean.\n"
        '- `expected_load` is required: "light", "moderate" or "heavy". Ask the user.\n'
        "- A multi-day row asserts ONE load for every day it names. If Tuesday is\n"
        "  moderate and Thursday is heavy, write TWO rows, not one.\n"
        "- `season_end` is YYYY-MM-DD or null. Nothing retires itself: a passed date is\n"
        "  a prompt to the user, never an automatic change of state.\n"
        "- `satisfies` (optional) LINKS this commitment to the quota slot it fills, so the\n"
        "  system states scheduled-vs-quota rather than guessing. Exactly one key, one of "
        f"{', '.join(sorted(_SATISFIES_VALIDATORS))}: "
        '`"satisfies": {"capacity": "stability"}` for a movement-quality slot, '
        '`"satisfies": {"load_window": "metabolic"}` for the conditioning window, or '
        '`"satisfies": {"activity": "pilates"}` for a device-evidenced activity slot. Omit it\n'
        "  (or null) when the commitment fills no declared quota slot — unlinked is fine.\n"
        "\n"
        "A DATED ONE-OFF — a commitment that happens ON a known date, not every week (a game,\n"
        "carnival, appointment, travel)\n"
        "Give it `event_date` (and `event_end` for a multi-day span) INSTEAD of "
        "`days`/`sessions_per_week`\n"
        "— they are mutually exclusive, and the validator refuses a row that mixes them. It is still\n"
        "a `schedule_item`, and `hard` is whatever the athlete states (a fixture is hard; an optional\n"
        "social match may be soft). Emit:\n"
        "\n"
        "<knowledge_update>\n"
        "{\n"
        '  "type": "schedule_item",\n'
        '  "key": "cup_final_2026_10",\n'
        '  "value": {\n'
        '    "activity": "cup final",\n'
        '    "event_date": "2026-10-17",\n'
        '    "event_end": "2026-10-18",\n'
        '    "hard": true,\n'
        '    "expected_load": "heavy",\n'
        '    "time_of_day": "unknown",\n'
        '    "same_day_training": false,\n'
        '    "duration_weeks": null,\n'
        '    "season_end": null\n'
        "  },\n"
        '  "notes": "regional cup final, Sat–Sun"\n'
        "}\n"
        "</knowledge_update>\n"
        "- `event_date` is YYYY-MM-DD; `event_end` is YYYY-MM-DD on or after it — omit `event_end`\n"
        "  for a single day. `event_end` without `event_date` is refused.\n"
        "- A dated one-off carries NO `days`/`sessions_per_week`. With `event_date` set, the week\n"
        "  planner marks those calendar days UNAVAILABLE (and the day after a heavy one cautioned).\n"
        "\n"
        "DATED COMMITMENT vs TEMPORAL STATE — the routing rule (do not confuse them)\n"
        "A commitment with a known DATE the athlete will plan AROUND (a game, carnival, appointment,\n"
        "travel) is a `schedule_item` with `event_date` (+ `event_end`), `hard` as the athlete states\n"
        "— NOT a `load_context`. A vague, undated state AFTER the fact (\"big weekend\", \"slept badly\",\n"
        "\"heavy session\") stays a `load_context` (see TEMPORAL EVENTS below): it expires on its own\n"
        "and blocks no future day. If it has a date and the athlete is planning around it, it is the\n"
        "former.\n"
        "\n"
        "SAME DAY, DIFFERENT TIME — no conflict\n"
        "Two commitments on the same weekday at non-overlapping times (work in the\n"
        "morning, gym at 16:30) coexist automatically. Just write the second row; it\n"
        "saves. Do NOT reach for `supersedes`/`distinct_from` merely because a day is\n"
        "shared — that is only for a genuine SAME-TIME collision.\n"
        "\n"
        "IF A WRITE IS REFUSED FOR OVERLAPPING AN EXISTING DAY *AND TIME*\n"
        "You will be told which rows it clashes with, by id (each with its time). This\n"
        "fires only when the times actually overlap, or when a time is unknown so the\n"
        "clash cannot be ruled out. Do NOT pick for the user. State the clash back to\n"
        "them in plain terms, ask whether this REPLACES those rows or is a separate\n"
        "commitment at the same time, then retry with either `\"supersedes\": <id>` or\n"
        '`"distinct_from": [<id>, ...]` in the value. Guessing is what produced duplicate\n'
        "rows for a single commitment.\n"
        "\n"
        "RETIRING A COMMITMENT (a commitment ends — \"physio is done\", \"stopped rugby\")\n"
        "Emit a knowledge_update whose `active` is false AT THE TOP LEVEL — a sibling of\n"
        "`type` and `key`, NOT inside `value`. `active` is not a `value` field; a block\n"
        "with it inside `value` is REFUSED. The whole block is just:\n"
        '  {"type": "schedule_item", "key": "<the key>", "active": false}\n'
        "`season_end` does NOT retire anything — a passed date is a prompt to the user,\n"
        "never an automatic state change; to take a commitment off the calendar now,\n"
        "deactivate it as above.\n"
        "\n"
        "WHO CONFIRMS THE SAVE — you request, the system reports\n"
        "Emitting a knowledge_update REQUESTS a write; it does not perform one. The system\n"
        "executes each write AFTER your message and appends the true per-entry outcome\n"
        "(✓ saved / ✗ not saved, with the reason). So describe what you are recording and\n"
        "its impact, but do NOT assert the write is done: never say \"saved\", \"logged\",\n"
        "\"updated\" or \"removed\" as accomplished fact. State it in the intent register\n"
        "(\"I'm recording…\", \"setting this to…\") and let the system's confirmation line\n"
        "carry completion. If a write is refused you will be told why — the system's line,\n"
        "not your prose, is the source of truth for what saved.\n"
        "Do NOT write a status or tally line yourself (for example a \"saved\"/\"N saved\" line):\n"
        "the system appends the single authoritative confirmation, so a line you add only\n"
        "duplicates it.\n"
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
        "\n"
        "UPDATING THE PLAN OF RECORD (the macro plan — the six-phase arc, buffer rule, gates)\n"
        "The macro plan is the single entry you read at the top of the prompt under \"Plan of\n"
        f"Record\": `type: \"training_plan\"`, key `\"{TRAINING_PLAN_KEY}\"`. Propose a rewrite ONLY\n"
        "when the athlete changes the macro plan itself — week-to-week facts are `schedule_item` /\n"
        "`load_context`, never this. Emit:\n"
        "\n"
        "<knowledge_update>\n"
        "{\n"
        '  "type": "training_plan",\n'
        f'  "key": "{TRAINING_PLAN_KEY}",\n'
        '  "value": {\n'
        '    "macro": "## Offseason\\nPhase 1 (base): rebuild aerobic base; buffer rule — '
        'sacrifice conditioning first; knee gate — if it flares, fall back to the bike.\\nPhase '
        '2 …",\n'
        '    "revised_on": "2026-09-19",\n'
        '    "revised_by": "coach"\n'
        "  }\n"
        "}\n"
        "</knowledge_update>\n"
        "\n"
        f"Value fields (ALL required): {', '.join(TRAINING_PLAN_FIELDS)}. Rules:\n"
        "- A rewrite SUPERSEDES the whole plan — it is NOT appended. Send the COMPLETE macro\n"
        "  every time, changing ONLY what the athlete asked to change; leave the rest verbatim.\n"
        "- When the athlete supplies the plan text, store it VERBATIM — do not paraphrase, reword,\n"
        "  or summarise it. On a PARTIAL change, edit only the affected line(s) and leave every\n"
        "  other line exactly as the athlete wrote it.\n"
        f"- `macro` is markdown, at most {MACRO_MAX_CHARS} characters (a longer write is refused).\n"
        f'- `revised_by` is one of {", ".join(REVISED_BY_VALUES)}: "coach" when you drafted the\n'
        '  change at the athlete\'s request, "operator" when they wrote it themselves.\n'
        "- `revised_on` is this revision's ISO date (YYYY-MM-DD).\n"
        "- Do NOT send `expires_at` — the plan supersedes by rewrite and never expires.\n"
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


# Full-detail token budget for the routines section (~2500 tokens, G0 ruling 2), measured in
# characters at ~4 chars/token. Working-set routines beyond it are named by title, never dropped.
_ROUTINES_FULL_CHAR_BUDGET = 10_000


def _mru_folder_id(routines: list[dict[str, Any]]) -> Any:
    """The folder_id of the most-recently-UPDATED routine — the fallback full-detail folder when
    no folder is declared for the current phase (#314, ruling 1)."""
    if not routines:
        return None
    return max(routines, key=lambda r: r.get("updated_at") or "").get("folder_id")


def _section_hevy_routines(
    data: dict[str, Any] | None,
    phase: dict[str, Any] | None,
    phase_folders: dict[str, Any] | None,
) -> str:
    """Render the athlete's Hevy routines (#314): a compact index of ALL routines (by name),
    plus the FULL contents of the working-set folder — the folder DECLARED for the current phase
    (`phase_folders[label]`), else a most-recently-used-folder FALLBACK that says so. Full detail
    is capped at ~2500 tokens; working-set routines beyond the cap are named by title, never
    silently dropped. A failed/timed-out fetch renders "unavailable" (or a stale cached copy
    marked with its age) — the chat never goes down for Hevy. No data (Hevy not connected) →
    empty string, so the section is omitted and the prompt is byte-identical."""
    if not data:
        return ""
    lines = ["## Hevy routines"]
    if data.get("unavailable"):
        lines.append(
            "Routines are unavailable right now — Hevy did not respond in time. Do NOT guess a "
            "routine's contents or claim to have changed one; say you can't see them this moment "
            "and try again shortly."
        )
        return "\n".join(lines)
    routines = data.get("routines") or []
    if not routines:
        lines.append("No routines found in Hevy.")
        return "\n".join(lines)
    if data.get("stale"):
        age = data.get("age_seconds")
        mins = age // 60 if isinstance(age, int) else "?"
        lines.append(f"(Cached copy ~{mins} min old — Hevy was slow to respond; may be slightly out of date.)")

    folders = data.get("folders") or []
    folder_title = {
        f.get("id"): (f.get("title") or f.get("name") or str(f.get("id")))
        for f in folders if isinstance(f, dict)
    }

    label = phase.get("label") if isinstance(phase, dict) else None
    declared = phase_folders.get(label) if (label and isinstance(phase_folders, dict)) else None
    if declared is not None:
        working_folder = declared
        working_note = f"declared for phase '{label}'"
    else:
        working_folder = _mru_folder_id(routines)
        working_note = (
            "FALLBACK: most-recently-used folder — no folder is declared for "
            + (f"phase '{label}'" if label else "the current phase")
            + "; declare one to pin the full-detail set"
        )

    lines.append("")
    lines.append(f"### All routines ({len(routines)}) — index")
    for r in routines:
        lines.extend(format_routine_compact(r, {}))

    working = sorted(
        [r for r in routines if r.get("folder_id") == working_folder],
        key=lambda r: r.get("updated_at") or "", reverse=True,
    )
    wf_name = folder_title.get(working_folder, "none" if working_folder is None else str(working_folder))
    lines.append("")
    lines.append(f"### Full detail — folder: {wf_name} ({working_note})")
    if not working:
        lines.append("(no routines in this folder)")
    used = 0
    any_full = False
    capped: list[str] = []
    for r in working:
        block = "\n".join(format_routine_full(r, {}))
        # Always render at least one full routine; then stop adding once the budget is spent and
        # name the rest by title (never silently drop — ruling 2).
        if any_full and used + len(block) > _ROUTINES_FULL_CHAR_BUDGET:
            capped.append(r.get("title") or "Untitled routine")
            continue
        lines.append(block)
        used += len(block)
        any_full = True
    if capped:
        lines.append(
            "(shown by title only — routines-section token cap: " + ", ".join(capped) + ")"
        )

    lines += [
        "",
        "These are the athlete's ACTUAL Hevy routines. To adjust a session, UPDATE the existing "
        "routine in place (see the routine-update block below); never ask the athlete to start or "
        "log a workout just to show you a routine.",
    ]
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
      "superset_id": null,
      "sets": [
        {"type": "normal", "weight_kg": 60, "reps": 8}
      ]
    }
  ]
}
</hevy_create_routine>

What you can see: the FULL Hevy exercise catalogue — every built-in exercise plus this
user's customs — is synced server-side and listed above. Title resolution runs against
all of it, NOT just exercises that appear in the workout history. So:
- You CAN answer whether any exercise exists in Hevy. Never say you can only confirm
  exercises from the workout history.
- Never offer to build, pull, or extend a Hevy catalogue integration. It exists and is
  live; the list above is its output.
- To check an exercise you are unsure about, just name it in the block. Resolution either
  matches it exactly or reports back ranked candidate titles for you to choose from — a
  miss is reported, never silently dropped, and nothing is created.

Rules for routine creation:
- ALWAYS confirm with the user before creating a routine. Ask them to confirm
  the exercises, sets, and weights first. Only include the <hevy_create_routine>
  block after the user explicitly says yes or asks you to go ahead.
- Identify each exercise by ONE of two fields — never both:
  - "exercise_template_id" — use this whenever the exercise appears in the
    workout history above, copying the ID shown there (e.g. "0222DB42").
  - "title" — use this when the exercise is NOT in the history above and you
    therefore have no ID for it. Spell it EXACTLY as the exercise is named above
    if it appears there; otherwise use the movement's standard Hevy name.
- NEVER invent or guess an exercise_template_id. An ID you did not read from the
  history above is always wrong.
- Titles are matched exactly against the user's Hevy exercise catalogue. A title
  that does not match is reported back to you and the routine is NOT created —
  it is never silently dropped or approximated, so name the movement rather than
  omitting it.
- An exercise marked [UNCATALOGUED] above is shown under the name it was logged
  with, which may no longer match the catalogue — prefer an exercise you can
  identify by ID, or expect the title to be reported back unmatched.
- set type must be one of: "normal", "warmup", "dropset", "failure".
- weight_kg, reps, distance_meters, duration_seconds are all optional — omit or
  set to null if not applicable for the exercise type.
- rest_seconds sits on the exercise, not the set.
- The block will be automatically removed from your visible response and replaced
  with a confirmation message once the routine is created.

Supersets (grouping exercises that are performed together or alternated):
- Add "superset_id" to an exercise to group it. Every exercise sharing the SAME
  integer is one superset — you perform them back-to-back, alternating. Different
  groups get different integers. Use null (or omit the field) for a standalone
  exercise that is not part of any superset.
- Unilateral pairing is the common case: to alternate the two sides of a single-arm
  or single-leg movement, put both sides in the same group so they share one
  superset_id. For example, a left-side and a right-side exercise both given
  "superset_id": 1 will alternate as a pair.
- "superset_id": 0 is a real group, distinct from null — 0 means "group zero", NOT
  "no group". Only null (or omitting the field) makes an exercise standalone.

Conventions — get these exactly right or the create is rejected or silently wrong:
- Every exercise needs at least one set. An empty "sets" list is invalid.
- Use snake_case for every field name, exactly as shown (exercise_template_id,
  rest_seconds, weight_kg, superset_id) — never camelCase.
- For a bodyweight set, OMIT weight_kg (or use null). Never send "weight_kg": 0 to
  mean "no weight" — 0 is a real load (an assisted or dead-hang zero), not "unweighted".
- rest_seconds defaults to 90 if you omit it.
- Do NOT put "rpe" on a routine set. RPE is a fact about a set you already performed,
  not a plan — Hevy ignores it on a routine, and it is dropped before the routine is
  sent regardless.
- Do NOT use the "@" character anywhere in "notes".
- The athlete's existing routines are listed in the `## Hevy routines` section above —
  read that to check whether a routine already exists before creating, so you don't mint a
  duplicate. A create with the same title in the same folder is refused (Hevy has no delete
  and its update REPLACES contents), so pick a distinct name, or UPDATE the existing routine
  instead of creating a new one.

## Updating a Hevy routine (adjusting an existing session)

To CHANGE a session, update its routine IN PLACE — do not create a new one (a near-duplicate is
permanent; Hevy has no routine delete). Embed a block with the routine's id and its COMPLETE new
contents (Hevy's update REPLACES the routine, so a partial body wipes the rest):

<hevy_update_routine>
{
  "routine_id": "ROUTINE_ID_FROM_THE_LIST_ABOVE",
  "title": "Existing routine title",
  "exercises": [
    {
      "exercise_template_id": "XXXXXXXX",
      "rest_seconds": 90,
      "superset_id": null,
      "sets": [
        {"type": "normal", "weight_kg": 60, "reps": 8}
      ]
    }
  ]
}
</hevy_update_routine>

- The `exercises`/`sets` shape is IDENTICAL to <hevy_create_routine> above (same id rules, same
  set fields; `rpe` is stripped either way). Copy the current contents from the `## Hevy routines`
  section and change ONLY what the athlete asked — every exercise/set you omit is deleted.
- `routine_id` is required and must match a routine in the list above.
- CONFIRM with the athlete before emitting the block — state exactly what will change. Only emit
  it after they say go.
- Do NOT send a `folder_id`: Hevy's update cannot move a routine between folders and a sent
  folder is ignored. If the athlete wants a routine MOVED, tell them it can't be done through the
  app and takes a few seconds in the Hevy app itself — never claim you moved it.
- The system re-reads the routine immediately before writing and reports the exact per-exercise
  change; if the routine changed in Hevy since you read it, the write is refused and you are
  re-shown the current version — do not describe a change as done until the system confirms it.

To adjust a session, UPDATE the existing routine; create a new one only for a genuinely NEW
session. Never ask the athlete to start or log a workout just to show you a routine. Never put a
weekday in a routine title — the schedule owns the day, not the title."""


def _section_exercise_catalogue(catalogue: list[tuple[str, bool]] | None) -> str:
    """The FULL synced Hevy catalogue — every default plus this user's customs.

    Takes the already-read rows, never a Session: `context_builder` is a pure formatter
    and performs no queries (the #43 parity-guard invariant). The read happens upstream in
    `chat.py`, exactly as `_annotate_canonical_titles` does for logged titles.

    Why the whole list rather than a lookup block: the model was answering catalogue
    questions from the ten recent workouts it could see, concluding it had no view of
    Hevy's built-ins, and offering to build the sync that shipped in #61. Handing it the
    real list kills that error class at the root, with no new mechanism and no extra turn.
    """
    if not catalogue:
        return ""
    defaults = [t for t, is_custom in catalogue if not is_custom]
    customs = [t for t, is_custom in catalogue if is_custom]

    lines = [
        "## Hevy Exercise Catalogue (complete, synced server-side)",
        "",
        f"This is the FULL catalogue: all {len(defaults)} Hevy built-in exercises plus "
        f"the {len(customs)} custom exercises in this user's account. It is synced to "
        "this app's database, not read from workout history.",
        "",
        "Use it directly to answer whether an exercise exists, whether a movement would "
        "be new, and what the user's own customs are. Do NOT say you can only see "
        "exercises that appear in the workout history — that is false. Do NOT offer to "
        "build, pull, or extend a catalogue integration; it already exists and this list "
        "is its output.",
        "",
        "Titles must be copied EXACTLY when you reference one — some contain unusual "
        "characters (e.g. a non-breaking hyphen) that look ordinary but do not match if "
        "retyped. Copy from this list rather than typing from memory.",
        "",
        f"### The user's custom exercises ({len(customs)})",
    ]
    lines += [f"- {t}" for t in customs] or ["- (none)"]
    lines += ["", f"### Hevy built-in exercises ({len(defaults)})"]
    lines += [f"- {t}" for t in defaults]
    return "\n".join(lines)


def _section_exercise_creation(connected: list[str]) -> str:
    """The <hevy_create_exercise> contract.

    Enum values are quoted from Hevy's live OpenAPI spec
    (`CreateCustomExerciseRequestBody`), not from the workout history above — the two
    vocabularies genuinely differ, which is why they are spelled out here rather than
    left to be inferred from the catalogue.
    """
    if "hevy" not in connected:
        return ""
    return """## Creating a Custom Hevy Exercise

If a movement the user wants is NOT in their Hevy exercise catalogue, you can mint it
as a custom exercise by embedding this block:

<hevy_create_exercise>
{
  "title": "Copenhagen Plank",
  "exercise_type": "duration",
  "equipment_category": "none",
  "muscle_group": "adductors",
  "other_muscles": ["abdominals"]
}
</hevy_create_exercise>

THIS IS PERMANENT AND CANNOT BE UNDONE. Hevy has no API to delete or edit an exercise
template. Every custom you create stays in the user's account forever, cluttering their
exercise picker, and a typo in the title is permanent too. This is a stronger bar than
routine creation, which the user can simply delete in the app.

- NEVER emit this block unless the user has explicitly asked for this exercise to be
  created, in this conversation, in response to you telling them it is permanent. An
  instruction to "build me a session" is NOT consent to mint exercises.
- Quote the exact title back and get a yes on the SPELLING before emitting the block.
- Prefer an existing catalogue exercise every time. If a title fails to resolve for a
  routine, the fix is almost always a different name for a movement Hevy already has —
  not a new custom. Check the suggestions reported back to you first.
- CHECK THE CATALOGUE LIST ABOVE BEFORE EMITTING THIS BLOCK. It is the complete set of
  built-ins plus the user's existing customs, so you can see for yourself whether the
  movement is genuinely absent. Creating a near-duplicate of something already there is
  permanent and cannot be undone. If it is already listed, say so instead — do not emit
  the block.
- If the exercise already exists, the block is a no-op and reports as such. It will not
  create a duplicate.

Field values — use ONLY these:
- exercise_type: weight_reps, reps_only, bodyweight_reps, bodyweight_assisted_reps,
  duration, weight_duration, distance_duration, short_distance_weight
- equipment_category: none, barbell, dumbbell, kettlebell, machine, plate,
  resistance_band, suspension, other
- muscle_group: abdominals, shoulders, biceps, triceps, forearms, quadriceps,
  hamstrings, calves, glutes, abductors, adductors, lats, upper_back, traps,
  lower_back, chest, cardio, neck, full_body, other
- other_muscles: optional list, same values as muscle_group

WARNING — the exercise_type values above are NOT the type values you see on exercises in
the workout history. Those come from a different Hevy schema and include names that are
INVALID here: bodyweight_assisted, bodyweight_weighted, floors_duration, steps_duration.
Note the near-miss: history shows "bodyweight_assisted", but creation requires
"bodyweight_assisted_reps". Copying a type from the history is a common way to get a
rejection. Use the list above.

- To use a newly created exercise in a routine in the SAME reply, put the
  <hevy_create_exercise> block first, then reference the exercise by "title" (spelled
  identically) in the <hevy_create_routine> block. The exercise is created before the
  routine is resolved, so the title will match. You will not know its ID — do not guess
  one.
- The block is removed from your visible response and replaced with a confirmation."""


def _hrv_today_lines(sel: Any) -> list[str]:
    """Current wake-day HRV, read LIVE by `select_wakeday_hrv(require_current_day=True)`
    (#327) — never the `passive_hrv_ms` denorm, and never a number for a prior day.
    Source-neutral copy: the value carries its source and date."""
    if sel is None:
        return []
    if sel.state == "value":
        p = sel.primary
        return [f"HRV (RMSSD) for {p['captured_at']}: {p['rmssd_ms']:.0f} ms — {p['source']}"]
    if sel.state == "pair":
        p, q = sel.primary, sel.secondary
        return [
            f"HRV (RMSSD) for {p['captured_at']}: {p['rmssd_ms']:.0f} ms — {p['source']} "
            f"(primary); {q['rmssd_ms']:.0f} ms — {q['source']} (Δ {sel.delta_ms:+d} ms, "
            "same night, two devices — not interchangeable)"
        ]
    if sel.state == "config_error":
        return ["HRV: no current-day HRV (more than two sources reported this night — "
                "unresolved, not shown)"]
    # absent | stale_withheld
    return ["HRV: no current-day HRV (today's reading has not landed; do not treat an "
            "earlier night's value as today's)"]


def _section_daily_record(record: Any, hrv_today: Any = None) -> str:
    """
    Descriptive section for the new two-moment daily record.
    MUST NOT contain prescriptive load instructions — descriptive only.

    `hrv_today` is the live current-wake-day `HrvSelection` (#327); the frozen
    `passive_hrv_ms` column is no longer rendered here.
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

        hrv_lines = _hrv_today_lines(hrv_today)
        sleep_min = _v("passive_sleep_min")
        if hrv_lines or sleep_min is not None:
            lines.append("")
            lines += hrv_lines
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


# Source-neutral HRV guidance (#327) — replaced a hard-coded line naming the Galaxy Ring as
# THE primary readiness signal, which let a dead ring's last reading read as current.
HRV_GUIDANCE_LINE = (
    "HRV is the PRIMARY readiness signal; sleep quality is the secondary input. Every "
    "HRV value above carries its source and date — only a value dated today is today's "
    "HRV; an older reading is history, never current readiness. Compare today's value "
    "against its own source's baseline, never across devices."
)


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
        lines.append(f"HRV baseline (rolling): {baseline.mean_ms:.0f} ms ({baseline.n} readings)")
        if baseline.diff_from_mean_ms is not None:
            direction = "above" if baseline.diff_from_mean_ms >= 0 else "below"
            src = f" ({baseline.source}, {today})" if getattr(baseline, "source", None) else ""
            lines.append(
                f"Today vs baseline{src}: {abs(baseline.diff_from_mean_ms):.0f}ms {direction} mean"
            )
        # #294/#295: flag an unsettled baseline so the number isn't read at face value.
        if baseline.baseline_state == "settling":
            lines.append(
                "Baseline unsettled — a recent training-phase change (deload / regime "
                "change); treat the HRV deviation as low-confidence while it settles."
            )
        elif baseline.baseline_state == "building":
            lines.append("Baseline still building — fewer than the mature-baseline nights.")

    # ----- last 7 readings -----
    lines.append("")
    lines.append("Last 7 readings (RMSSD):")
    for r in readings[:7]:
        d = _v(r, "captured_at")
        v = _v(r, "hrv_ms")
        lines.append(f"- {d}: {v} ms" if v is not None else f"- {d}: — ms")

    lines += ["", HRV_GUIDANCE_LINE]

    return "\n".join(lines)


_DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _section_schedule(entries: list[Any], now: datetime, suppress_hard_flags: bool = False) -> str:
    """Build a synthesised weekly schedule view from structured knowledge entries.

    `suppress_hard_flags` (#316): when the training-phase section is rendering the derived WEEK
    (hard-by-day + availability), the next-7-days "Hard commitment" / "Pre-event shadow" flag lines
    here are folded into that block — so they are dropped to state the week once, not twice. Default
    False keeps the pre-#316 output byte-identical (the #43 parity discipline, and the null-window
    case where no week block renders)."""
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
    # (activity, raw day string) for every day name this builder could not place.
    # Surfaced below rather than dropped -- see the two `unplaceable` appends.
    unplaceable: list[tuple[str, str]] = []

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
            else:
                # NOT silently skipped. The write path validates weekdays against a
                # closed set, so this is unreachable for anything written after that
                # landed -- but it stays reachable for rows written before it and for
                # any future writer that does not pass through `upsert_knowledge_entry`.
                # A day the schedule cannot place is a commitment the user stated and
                # the context never mentions, which reads downstream as a free day.
                unplaceable.append((activity, d))

    for day in _DAY_ORDER:
        items = day_map[day]
        marker = " ◀ today" if day == today_weekday else ""
        if items:
            lines.append(f"{day.capitalize()}: {', '.join(items)}{marker}")
        else:
            lines.append(f"{day.capitalize()}: rest{marker}")

    # THIS WEEK FLAGS
    flags: list[str] = []

    # Hard commitments in next 7 days. Folded into the #316 week block when it renders
    # (`suppress_hard_flags`), so the week is stated once; an unknown weekday is still caught by
    # the day-map loop above, so suppression drops no data-integrity report.
    for e in schedule_items if not suppress_hard_flags else []:
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
                # Second drop site, and a different mechanism from the day-map loop
                # above: that one skips a day it cannot place, this one swallows the
                # `_DAY_ORDER.index()` miss. Both made an unknown weekday vanish, so
                # both report now — a hard commitment that cannot be dated is exactly
                # the one worth naming.
                unplaceable.append((activity, d))

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

    # Unplaceable day names, deduped — a hard commitment trips both drop sites, and
    # reporting it twice would read as two separate faults.
    for activity, raw_day in dict.fromkeys(unplaceable):
        flags.append(
            f"Schedule not shown: {activity} lists {raw_day!r}, which is not a weekday "
            f"— this commitment is MISSING from the weekly schedule above"
        )

    if flags:
        lines.append("\nTHIS WEEK FLAGS")
        for f in flags:
            lines.append(f"- {f}")

    # Dated one-off commitments (#317/Q165) — `schedule_item`s with `event_date` (no weekday, so
    # absent from the grid above). Rendered only while the event has not passed (`event_end`, else
    # `event_date`, on or after today); a past one-off simply drops off (derive on read, nothing
    # retires itself). No dated items → nothing appended, so output stays byte-identical.
    dated: list[str] = []
    for e in schedule_items:
        val = _v(e, "value") or {}
        ev = val.get("event_date")
        if ev is None:
            continue
        try:
            start = date.fromisoformat(str(ev))
            end = date.fromisoformat(str(val["event_end"])) if val.get("event_end") else start
        except (ValueError, TypeError, KeyError):
            continue
        if end < today:
            continue
        activity = val.get("activity", "?")
        load = val.get("expected_load")
        tag = "hard" if val.get("hard") else "soft"
        tag = f"{tag}, {load}" if load and load != "none" else tag
        span = start.strftime("%a %d %b") if start == end else \
            f"{start.strftime('%a %d %b')}–{end.strftime('%a %d %b')}"
        dated.append(f"- {activity} ({tag}) — {span}")
    if dated:
        lines.append("\nDATED ONE-OFFS")
        lines.extend(dated)

    return "\n".join(lines)


# ---------- Adaptive Exposure Engine sections (Decision Support) ----------

# TEMPORARY (DECISIONS_LOG #60): #49's dedicated lab-interpretation view has not
# been built yet — "Labs" (/labs) is the closest existing screen (the lab surface
# split off /metrics in increment 4 STEP 0), and it does attach/extract/confirm plus
# a persisted read-back, not interpretation. This constant is a stand-in pointer, not
# a real destination; swap it for the real interpretation view's name the moment #49
# ships a UI, and drop this comment.
_LAB_INTERPRETATION_VIEW_LABEL = "Labs page"


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


def _slot_display_label(slot: dict[str, Any]) -> str:
    """A quota slot's label: a `load_window` conditioning slot is "Conditioning" (the metabolic
    window); an `activity` slot is its title-cased activity name (#315); a capacity slot is its
    title-cased capacity token. Mirrors the frontend `QuotaWindow`."""
    kind = slot.get("kind")
    if kind == "load_window":
        lw = slot.get("load_window")
        return "Conditioning" if lw == "metabolic" else _cap(lw)
    if kind == "activity":                       # #315 — the declared activity name
        return _cap(slot.get("activity"))
    return _cap(slot.get("capacity"))


def _slot_is_due(slot: dict[str, Any], due_slot: dict[str, Any] | None) -> bool:
    """True when `due_slot {kind, key}` names this slot — matched on kind + key. The key is the
    slot's own kind-value (capacity token / load_window / activity name), so `slot.get(kind)`
    reads it for all three kinds (#315). Reading `due_slot`, never `due_capacity` (capacity-only),
    is what lets the marker land on a conditioning or activity slot."""
    if not isinstance(due_slot, dict):
        return False
    kind = slot.get("kind")
    return due_slot.get("kind") == kind and due_slot.get("key") == slot.get(kind)


def _uncounted_phrase(u: dict[str, Any]) -> str:
    """One `uncounted` item in plain words. Hevy workouts carry `workout`; aerobic sessions
    carry `session`. An unknown reason falls back to itself."""
    reason = u.get("reason")
    if reason == "off_plan":
        return f"off-plan workout ({_cap(u.get('capacity'))})"
    if reason == "untagged":
        n = u.get("untagged_exercises")
        return f"untagged workout ({n} exercise{'' if n == 1 else 's'})"
    if reason == "concurrent_strength":
        return f"conditioning session overlapping a gym workout ({u.get('sport_name')})"
    if reason == "untimed":
        return f"untimed conditioning session ({u.get('sport_name')})"
    if reason == "unclaimed_session":            # #315 — a session no slot's sport claims
        if u.get("detail") == "no_sport":
            return "other activity (no recorded sport — set the sport in the app so it can count)"
        return f"other activity ({u.get('sport_name')})"
    return str(reason)


def _cap(s: Any) -> Any:
    return s[0].upper() + s[1:] if isinstance(s, str) and s else s


def _entry_value(e: Any) -> dict[str, Any]:
    """A knowledge entry's `value` dict, ORM or plain-dict alike (mirrors `_section_schedule`'s
    `_v`)."""
    v = getattr(e, "value", None) if hasattr(e, "value") else (e.get("value") if isinstance(e, dict) else None)
    return v or {}


def _entry_type(e: Any) -> Any:
    return getattr(e, "type", None) if hasattr(e, "type") else (e.get("type") if isinstance(e, dict) else None)


# One definition, in `engine.week_plan` (#316). Kept as a module-local alias for back-compat.
_schedule_sessions_per_week = schedule_sessions_per_week


def plan_of_record_stale(plan: dict[str, Any] | None, phase: dict[str, Any] | None) -> bool:
    """The SINGLE definition of the plan-of-record STALE flag (#312/#319): the plan was last
    revised BEFORE the open phase's review date AND that review date has passed — the phase's own
    `review_due`, so no second definition of "passed". ONE definition, two callers: the chat render
    (`_section_training_plan`) and `GET /engine/plan-of-record` (the Phase card, #319) — never
    re-derived client-side. False whenever an input is absent or unparseable (shown as not-stale,
    never a crash)."""
    if not isinstance(plan, dict) or not isinstance(phase, dict):
        return False
    revised_on = plan.get("revised_on")
    if not (phase.get("review_due") and phase.get("review_on") and revised_on):
        return False
    try:
        return date.fromisoformat(str(revised_on)) < date.fromisoformat(str(phase["review_on"]))
    except (ValueError, TypeError):
        return False


def _section_training_plan(plan: dict[str, Any] | None, phase: dict[str, Any] | None) -> str:
    """Render the PLAN OF RECORD (#312) — the macro plan the athlete is following, the coach's
    every-turn reference — directly ABOVE the training-phase section. `macro` is verbatim bounded
    markdown (its own section, rendered ONCE). A STALE line fires when the plan was last revised
    BEFORE the open phase's review date AND that date has passed (the phase's own `review_due`, so
    no second definition of "passed"): shown as stale, never silently dropped, never silently
    trusted. No plan → empty string (the section is omitted; context byte-identical to pre-#312)."""
    if not plan:
        return ""
    macro = plan.get("macro")
    if not isinstance(macro, str) or not macro.strip():
        return ""
    lines = ["## Plan of Record (the macro plan the athlete is following)"]
    revised_on = plan.get("revised_on")
    revised_by = plan.get("revised_by")
    meta = []
    if revised_on:
        meta.append(f"revised {revised_on}")
    if revised_by:
        meta.append(f"by {revised_by}")
    if meta:
        lines.append(f"- Last {', '.join(meta)}.")

    if plan_of_record_stale(plan, phase):
        lines.append(
            "- STALE — plan not revised since before the last phase review; treat the macro "
            "below as possibly out of date and prompt the athlete to confirm or revise it."
        )

    lines += ["", macro.strip()]
    return "\n".join(lines)


def _section_training_phase(
    phase: dict[str, Any] | None,
    resolver_position: dict[str, Any] | None = None,
    knowledge_entries: list[Any] | None = None,
    week_plan: dict[str, Any] | None = None,
) -> str:
    """Render the open training phase (Q112, #270) — DOING NOW, framing the profile's standing
    BUILDING TOWARD below it. Absent (baseline) → empty string. The `review_on` line is a BADGE,
    never a transition (#228).

    Under the phase, the QUOTA POSITION from the resolver (#308, completing #307 Amendment 1 A2):
    the same `resolve()` read the panel uses (`current_state.resolver_position`) — the current
    window, each slot's `{done}/{quota}` across BOTH kinds, the `due_slot` of either kind, the
    counted conditioning sessions, and the four `uncounted` reasons. Rendered only when the read
    succeeded AND its window is non-null; a null window (baseline) leaves the section byte-identical
    to the pre-#308 phase render. The section reports the resolver's numbers verbatim — it never
    recomputes (GUARD).

    When `week_plan` is supplied (the #316 derived read; None in the isolated #312 tests, so those
    stay byte-identical), the WEEK is folded in under the position: hard items by day → availability
    (with `caution: day after heavy`) → the #312 per-key consistency block → PLANNING NEEDED →
    one-off notes → the S3 coach rules. The next-7-days hard lines are then suppressed in
    `_section_schedule` so the week is stated once, not twice."""
    if not phase:
        return ""
    lines = ["## Training Phase (Adaptive Exposure Engine — doing now)"]
    lines.append(f"- Phase: {phase.get('label')} (entered {phase.get('entered_on')})")
    if phase.get("intent"):
        lines.append(f"  - Intent: {phase['intent']}")
    posture = phase.get("probe_posture")
    if posture:
        suppressed = posture == "suppressed"
        lines.append(
            f"- Probe posture: {posture}"
            + (" — probe budget forced to 0, mode is fortify this phase" if suppressed else "")
        )
    caps = phase.get("capacities")
    if caps is not None:
        lines.append(
            f"- Capacities live this phase: {', '.join(caps) if caps else 'none'} "
            f"(others removed from the probe queue; the Fortify target is never dropped)"
        )
    else:
        lines.append("- Capacities: all live (no phase restriction)")
    review_on = phase.get("review_on")
    if review_on:
        due = " ◀ REVIEW DUE — ask whether to open the next phase (a prompt, not a transition)" \
            if phase.get("review_due") else ""
        lines.append(f"- Review on: {review_on}{due}")

    window = resolver_position.get("window") if isinstance(resolver_position, dict) else None
    if window:
        slots = resolver_position.get("slots") or []
        due_slot = resolver_position.get("due_slot")
        uncounted = resolver_position.get("uncounted") or []
        lines.append(
            f"- Quota window: {window.get('label')} "
            f"({window.get('start_date')} → {window.get('end_date')}, source {window.get('source')})"
        )
        for slot in slots:
            marker = "  ◀ DUE" if _slot_is_due(slot, due_slot) else ""
            lines.append(f"  - {_slot_display_label(slot)} · {slot.get('done')}/{slot.get('quota')}{marker}")
            if slot.get("kind") in ("load_window", "activity"):   # #315 — both count sessions
                for cs in slot.get("sessions_counted") or []:
                    dur = cs.get("duration_minutes")
                    dur_str = f"{dur:g}min" if isinstance(dur, (int, float)) else "?min"
                    # "(unzoned)" is a load_window (conditioning) note only; activity slots are zero-load.
                    unzoned = " (unzoned)" if slot.get("kind") == "load_window" and not cs.get("trimp") else ""
                    lines.append(f"    · {cs.get('sport_name')} {dur_str}{unzoned}")
        if slots and all((s.get("quota") or 0) - (s.get("done") or 0) <= 0 for s in slots):
            lines.append("  - all quotas met this window — nothing due")
        if uncounted:
            lines.append("  - Not counted:")
            for u in uncounted:
                lines.append(f"    · {_uncounted_phrase(u)}")

        # ---- the WEEK, hard commitments first (#316) — one statement of the week -------------
        # Rendered only when the derived plan is supplied (None in the isolated #312 tests, so
        # those stay byte-identical). Hard items occupy their days; what is left is availability;
        # a `heavy` hard item the day before flags `caution: day after heavy` (advisory, never
        # blocking). Days are preferences (#275 untouched) — nothing here marks a session "missed".
        if week_plan is not None:
            lines.append("  - Week (hard commitments first, then availability):")
            for day in week_plan.get("days") or []:
                wd = (day.get("weekday") or "").capitalize()
                hard = day.get("hard") or []
                if hard:
                    parts = []
                    for h in hard:
                        el = h.get("expected_load")
                        load = f", {el}" if el else ""
                        sdt = ", same-day training OK" if h.get("same_day_training") else ""
                        parts.append(f"{h.get('activity')}{load}{sdt}")
                    hard_str = "; ".join(parts)
                else:
                    hard_str = "no hard commitment"
                avail = "available" if day.get("available") else "UNAVAILABLE"
                caution = f" ⚠ {day['caution']}" if day.get("caution") else ""
                flex = day.get("flexible") or []
                flex_str = (" · flexible: " + ", ".join(f.get("activity") or "?" for f in flex)) if flex else ""
                lines.append(f"    · {wd} {day.get('date')}: {hard_str} — {avail}{caution}{flex_str}")
            fr = week_plan.get("freshness") or {}
            hc = fr.get("hc_synced_at")
            polar = fr.get("polar_latest_session_at")
            lines.append(
                f"  - Data freshness: HC last synced {hc or 'never'}; newest Polar session received "
                f"{polar or 'never'} (no Polar pull timestamp is recorded — Q154)."
            )
            has_device_slot = any(s.get("kind") in ("load_window", "activity") for s in slots)
            if has_device_slot and (fr.get("hc_stale") or fr.get("polar_stale")):
                stale_src = [s for s, flag in
                             (("Health Connect", fr.get("hc_stale")), ("Polar", fr.get("polar_stale"))) if flag]
                lines.append(
                    "    ⚠ device-evidenced counts (activity/conditioning) may be INCOMPLETE — "
                    f"{' and '.join(stale_src)} has not reported since before this window began; "
                    "do not present a device-slot 'done' as settled fact."
                )

        # ---- schedule↔quota consistency, DERIVED on read (#312, S4) --------------------------
        # Per slot: `scheduled` (sessions/wk summed over ACTIVE linked schedule_items — those whose
        # `satisfies` names this slot's {kind,key}) vs `quota` (this leg) vs `done` (from resolve(),
        # never recounted). "Active" = the row is in `knowledge_entries` (already active=True;
        # `supersedes` resolves to active=False). MISMATCH/UNPLACED are claimed ONLY on a 7-day leg
        # (`sub_cycle_days == 7`, derived from the window span) — the one span where a per-week
        # `scheduled` and a per-leg `quota` share a unit; otherwise both numbers render with their
        # own units and NO mismatch is asserted. Rendered only when ≥1 active schedule_item exists,
        # so a user with none leaves the section byte-identical.
        schedule_items = [e for e in (knowledge_entries or []) if _entry_type(e) == "schedule_item"]
        if schedule_items:
            try:
                leg_days = (date.fromisoformat(window["end_date"])
                            - date.fromisoformat(window["start_date"])).days + 1
            except (ValueError, TypeError, KeyError):
                leg_days = None
            lines.append("  - Schedule vs quota (declared links):")
            # Numbers from the ONE shared derivation (#316), so the chat line and `plan_week` agree.
            rows = consistency_rows(slots, [_entry_value(e) for e in schedule_items])
            for slot, row in zip(slots, rows):
                scheduled = row["scheduled"]
                quota = row["quota"]
                done = row["done"]
                label = _slot_display_label(slot)
                if leg_days == 7:
                    line = f"    · {label} — scheduled {scheduled}/wk · quota {quota} · done {done}"
                    if scheduled > quota:
                        line += f" — MISMATCH: scheduled exceeds quota by {scheduled - quota}"
                    elif scheduled < quota:
                        d = quota - scheduled
                        line += f" — UNPLACED: {d} quota session{'' if d == 1 else 's'} has no scheduled slot"
                else:
                    leg_str = f"{leg_days}-day leg" if leg_days else "leg"
                    line = (f"    · {label} — scheduled {scheduled}/wk · quota {quota} per {leg_str} "
                            f"· done {done}")
                lines.append(line)
            unlinked = [
                _entry_value(e).get("activity") or "?"
                for e in schedule_items
                if _entry_value(e).get("satisfies") is None and _entry_value(e).get("hard") is False
            ]
            if unlinked:
                lines.append(
                    f"    · unlinked (soft, counted to no slot): {', '.join(unlinked)}"
                )

        # PLANNING NEEDED + one-off notes (#316) — after the per-key block, per the brief order.
        if week_plan is not None:
            if week_plan.get("needs_planning"):
                lines.append(
                    "  - PLANNING NEEDED — the phase declares a quota but NO schedule item is placed "
                    "against any slot. Planning is DUE: say so and point the athlete to the structured "
                    "phase-change flow; do NOT improvise the planning conversation. Until that flow "
                    "ships, list the hard commitments, the availability and the unplaced quota above, "
                    "and stop there."
                )
            for n in week_plan.get("one_off_notes") or []:
                exp = f" (expires {n['expires_at']})" if n.get("expires_at") else ""
                lines.append(f"  - One-off note (undated, from load context): {n.get('description')}{exp}")

        lines.append(
            "  - This is the AUTHORITATIVE count of what has been done against the declared plan "
            "this window: do not infer position from workout history when it is present, and if "
            "the user's stated intent for the week differs from the declared quota, say so rather "
            "than silently following either."
        )

    lines += [
        "",
        "The phase is HISTORY + CURRENT, never a plan. It records what is being run now; it "
        "does not schedule what comes next. Aerobic/metabolic posture lives in the intent prose "
        "above; a phase MAY declare a conditioning quota (a metabolic load_window slot, counted "
        "in the quota position above when present) that the resolver counts from aerobic sessions "
        "on read — but the engine still never SELECTS conditioning.",
        "",
        "### Plan of record, schedule and quota — how to read them (#312)",
        "- The Plan of Record above is the MACRO plan the athlete is following; the quota window "
        "is what the engine COUNTS. Routine TITLES and the phase `intent` prose are NEITHER — "
        "never derive what is \"due\" or what was \"done\" from a Hevy routine title or from intent "
        "prose.",
        "- When the schedule, the quota and the logged record disagree, NAME the disagreement with "
        "the numbers (scheduled vs quota vs done) and ASK — do not resolve it by silently picking a "
        "side.",
        "- Never assert a session HAPPENED unless the resolver counted it (the position above) or "
        "the athlete told you so. A scheduled or planned session is an intention, not a record.",
        "- Week facts go through the existing confirm flow, where they already belong: a one-off (a "
        "carnival, travel, illness) → a `load_context` entry; a recurring commitment → a "
        "`schedule_item` (add `satisfies` when it fills a quota slot). A change to the MACRO plan → "
        "propose a `training_plan` rewrite. You REQUEST the write; the system confirms it.",
        "- You may PROPOSE a phase change in words; you never write the phase ledger yourself.",
        "- Never put a weekday in a Hevy routine title — the schedule owns the day, not the title.",
    ]
    # S3 week-planner coach rules (#316) — rendered with the week (None in the isolated #312 tests).
    if week_plan is not None:
        lines += [
            "### Planning the week (#316)",
            "- Hard commitments are FIXED. Plan around them, never over them; a day marked "
            "UNAVAILABLE has a blocking hard commitment. A `caution: day after heavy` day is "
            "available but flag the carryover when you propose placing a hard session there.",
            "- Before you PROPOSE a session or CREATE a Hevy routine for a slot key, check that key's "
            "`done + still-scheduled` against its `quota` above. At or over quota → say so, give the "
            "numbers (scheduled / quota / done), and ASK. Never initiate silently — the athlete may "
            "still choose it, but it is their call, a prompt not a lock.",
            "- Counts are only as fresh as the last device ingest. When the freshness line flags a "
            "device-evidenced slot as possibly INCOMPLETE, do not treat its `done` as settled — say "
            "the platform may not have heard from the device yet.",
            "- When the phase review is DUE (the badge above), or PLANNING NEEDED is shown, SAY so "
            "and point the athlete to the Phase card to review or change the phase. Do NOT conduct "
            "the transition in chat, and NEVER write a phase, a microcycle or the Hevy phase-folder "
            "yourself — that is the form's single confirmed write, not a coach action (#317).",
        ]
    return "\n".join(lines)


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
        # A suppressed phase and a genuinely empty queue are DIFFERENT facts and must not
        # share a sentence: under suppression `probe` is `None` by design (the phase withheld
        # it, the queue may be full), so name the phase rather than implying the map is sampled.
        phase = selection.get("training_phase") or {}
        if phase.get("probe_posture") == "suppressed":
            lines.append(f"- PROBE: suppressed by training phase '{phase.get('label')}'")
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
    exercise_catalogue: list[tuple[str, bool]] | None = None,
    hevy_routines: dict[str, Any] | None = None,
) -> str:
    # Capture time once per request so all sections share the same "now"
    now = _now_aest()

    # Use new DailyRecord section when available; fall back to legacy check-in
    readiness_section = (
        _section_daily_record(daily_record, getattr(state, "hrv_today", None))
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

    # Plan of record (#312) sits directly ABOVE the training-phase section. Conditional append,
    # so with no plan the section list is byte-identical to pre-#312 (the #43 parity discipline).
    if getattr(state, "training_plan", None) is not None:
        plan_section = _section_training_plan(
            state.training_plan, getattr(state, "training_phase", None)
        )
        if plan_section:
            sections.append(plan_section)

    if getattr(state, "training_phase", None) is not None:
        phase_section = _section_training_phase(
            state.training_phase, getattr(state, "resolver_position", None),
            state.knowledge_entries, getattr(state, "week_plan", None),
        )
        if phase_section:
            sections.append(phase_section)

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
        # When the week block renders (a non-null resolver window → `week_plan` present), fold the
        # next-7-days hard lines into it rather than stating the week twice (#316).
        schedule_section = _section_schedule(
            state.knowledge_entries, now,
            suppress_hard_flags=getattr(state, "week_plan", None) is not None,
        )
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
        ring_section = _section_samsung_hrv(samsung_hrv, now, state.hrv_baseline)
        if ring_section:
            sections.append(ring_section)

    if hevy_data is not None:
        count = hevy_data.get("workout_count", 0)
        workouts = hevy_data.get("recent_workouts", [])
        sections.append(_section_hevy(count, workouts, now))

    # Sits directly after the workout history on purpose: the history is the ten recent
    # sessions, this is everything that EXISTS. Adjacent, the difference is obvious.
    # Conditionally appended, so with no catalogue nothing is added at all — which keeps
    # the section list byte-identical for the #43 parity guard rather than inserting an
    # empty string and a separator.
    if exercise_catalogue:
        catalogue_section = _section_exercise_catalogue(exercise_catalogue)
        if catalogue_section:
            sections.append(catalogue_section)

    # The athlete's Hevy routines (#314) — fetched (cached, budgeted) upstream in chat.py and
    # handed in, keeping this a pure formatter (#43). Empty string when Hevy is not connected, so
    # the section list stays byte-identical for the parity guard.
    routines_section = _section_hevy_routines(
        hevy_routines, state.training_phase, getattr(state, "phase_folders", None)
    )
    if routines_section:
        sections.append(routines_section)

    sections += [
        "",
        "When the user asks about their training, reference the data above directly. "
        "If data is missing or incomplete, say so and suggest what they could connect. "
        "Never fabricate workout details that are not in the context.",
        "",
        # The two Hevy authoring contracts share ONE slot. Both are gated on the same
        # `connected_integrations`, so when Hevy is absent both render "" and this slot
        # collapses to the single "" the pre-#43 builder emitted — keeping the section
        # list byte-identical for the parity guard in `test_current_state.py`, which
        # compares against a frozen copy with `connected_integrations=[]`. Giving the
        # exercise contract its own slot plus separator would break that guard on
        # whitespace alone, while changing nothing a model ever reads.
        "\n\n".join(s for s in (
            _section_routine_creation(connected_integrations),
            _section_exercise_creation(connected_integrations),
        ) if s),
        "",
        _section_knowledge_update(),
    ]

    return "\n".join(sections)
