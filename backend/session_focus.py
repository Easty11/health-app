"""Session focus — the pinned block an operator's session review carries into chat (Brief A, A1).

`ChatRequest.focus_session = {kind, id, scope}` is a REFERENCE, never a rendering: the client names
the session and the scope, and THIS module loads the session for the calling user and renders it
with the backend's own renderers. The client no longer formats a session (the lossy
`formatHevyMessage` / `formatPolarMessage` are gone — they dropped RPE, exercise notes, set types,
carries/distance/duration, and the workout description).

    kind   "hevy"     → `hevy_workouts.raw` by `hevy_id`, rendered by `context_builder.render_workout`
                        (the `_section_hevy` path, i.e. `hevy_format.format_set` per set)
           "aerobic"  → the `aerobic_sessions` row by id, rendered by
                        `aerobic_format.format_aerobic_session` (the MCP tool's renderer)
    scope  "session"  → "Session under review": the session alone, framed as a review of its EXECUTION
           "context"  → the same pinned session PLUS a guaranteed window — every canonical aerobic
                        session and every counted Hevy workout, and the schedule items, in the window
                        [session's local day - 7, session's local day + 3] — the SAME DAY INCLUDED, the
                        focused session itself the only exclusion — framed as a review judged against the
                        phase, the surrounding load and what is coming next

The block is appended to the system prompt on that turn only, regardless of the ten-workout window the
standing history carries. A session that is not found or not this user's yields a block that SAYS so and the
turn proceeds — never an error, never a foreign user's data.

WHAT THE STANDING CONTEXT ALREADY CARRIES (so context scope pins only what is missing):
  - the active phase and resolver position (`_section_training_phase`, with the derived week block)   → carried
  - the weekly schedule grid, hard commitments and dated one-offs (`_section_schedule`)               → carried,
    but as a weekday grid: no date-resolved list, and soft items appear only in the grid
  - typed constraints and findings (`_section_constraints`, `_section_findings`)                       → carried
  - the ten most recent Hevy workouts                                                                  → carried
  - aerobic sessions of any kind                                                                       → NOT carried
So context scope pins the surrounding performed sessions (aerobic + Hevy) and the date-resolved
schedule over the window, and does not restate phase or constraints.

EXTRAS (both scopes, Hevy and aerobic focus alike): the focus block always adds what a review cannot
otherwise see — the same-AEST-day canonical aerobic sessions (context scope already lists them in its
window, so only session scope adds the block), the previous two counted Hevy workouts of the same
routine (`raw.routine_id`), and an inline flag for every confirmed constraint whose scope text names an
exercise in the session. A Hevy session missing from `hevy_workouts` is rendered from a live fetch by
id when the caller supplies one (`live_hevy`).

SHARE-URL AUTO-FOCUS: `focus_from_share_url` reads a `hevy.com/workout/<uuid>` link out of the chat
message and names it as a session-scope Hevy focus when the client pinned none.

Pure read; no schema. The renderers are shared, never copied.
"""
from __future__ import annotations

import copy
import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Literal, Optional

import pytz
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
import typed_entries
from aerobic_format import format_aerobic_session
from context_builder import render_workout
from engine.week_plan import item_covers
from hevy_format import format_workout_compact
from reads.aerobic_reads import arbitrated_sessions
from reads.hevy_reads import counted_workouts

logger = logging.getLogger(__name__)

AEST = pytz.timezone("Australia/Brisbane")

# Context scope's guaranteed window (operator ruling on #354, 30 Sep): [anchor - 7, anchor + 3] LOCAL
# days, the anchor's own day INCLUDED, for completed sessions (both lanes; canonical aerobic, counted
# Hevy) and for scheduled items alike. Only the focused session itself is excluded — the reference case
# is gym then pilates the same day, so another session on the anchor day, before or after the focused
# one, is in. The window is a calendar-day range, so a later day is included whether or not it has
# happened yet (a review of an old session sees what followed it).
CONTEXT_PRIOR_DAYS = 7
CONTEXT_NEXT_DAYS = 3

# How many earlier workouts of the same Hevy routine the focus block adds, and how far back (in rows) the
# scan for them reaches — `raw.routine_id` is JSON, so the match is made in Python over a bounded read.
SAME_ROUTINE_PRIOR = 2
SAME_ROUTINE_SCAN_ROWS = 120

# Constraint-flag matching: an exercise title shorter than this is too generic to match on ("Row",
# "Fly") and is skipped — a deliberate false-NEGATIVE trade against the false-positive risk.
FLAG_MIN_TITLE_CHARS = 4

_HEVY_SHARE_RE = re.compile(
    r"hevy\.com/workout/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.IGNORECASE
)


class FocusSession(BaseModel):
    """The request-only reference to the session under review (no schema, nothing persisted)."""
    kind: Literal["hevy", "aerobic"]
    id: str = Field(min_length=1, max_length=128)
    scope: Literal["session", "context"]


def focus_from_share_url(message: Optional[str]) -> Optional[FocusSession]:
    """A session-scope Hevy focus for the first `hevy.com/workout/<uuid>` link in `message`, or None.
    The caller applies it only when the client pinned no focus of its own."""
    m = _HEVY_SHARE_RE.search(message or "")
    if m is None:
        return None
    return FocusSession(kind="hevy", id=m.group(1).lower(), scope="session")


def needs_live_hevy(db: Session, user_id: int, focus: FocusSession) -> bool:
    """True when `focus` names a Hevy workout that is not in this user's `hevy_workouts` — the one case
    the caller fetches live (by id) and hands to `build_focus_block`."""
    if focus.kind != "hevy":
        return False
    return (
        db.query(models.HevyWorkout.hevy_id)
        .filter(models.HevyWorkout.user_id == user_id, models.HevyWorkout.hevy_id == focus.id)
        .first()
    ) is None


def _local(dt: Optional[datetime]) -> Optional[datetime]:
    """An instant as a local (AEST) aware datetime; a naive value is treated as UTC (the
    stored-instant convention — `load_metrics._local_day`)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(AEST)


def _parse_iso(s: Any) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _local_day_start_utc(d: date) -> datetime:
    """UTC instant of local midnight at the start of `d`."""
    return AEST.localize(datetime.combine(d, time.min)).astimezone(timezone.utc)


def _hhmm(dt: Optional[datetime]) -> str:
    return dt.strftime("%H:%M") if dt is not None else ""


# ── the session under review ──────────────────────────────────────────────────

def _not_found(kind: str, ident: str) -> str:
    where = ("the user's synced Hevy workouts (`hevy_workouts`)" if kind == "hevy"
             else "the user's aerobic sessions")
    return (f"## Session under review\n"
            f"The operator asked to review a {kind} session (id {ident}), but it was not found in {where}. "
            f"There is no session data to review — say so plainly, and do not describe or invent a session.")


def _load_hevy(db: Session, user_id: int, ident: str,
               annotate: Optional[Callable[[dict[str, Any], Session], Any]],
               live: Optional[dict[str, Any]] = None):
    """(rendered_lines, anchor_date, focus_id, raw) or None. The raw payload is deep-copied before
    annotation so the ORM row's JSON is never mutated. When the local row is missing and the caller
    fetched the workout live (`live`, the Hevy payload by id), that payload stands in for the row — it is
    the same shape the sync stores in `raw`."""
    row = (
        db.query(models.HevyWorkout)
        .filter(models.HevyWorkout.user_id == user_id, models.HevyWorkout.hevy_id == ident)
        .first()
    )
    if row is None and not live:
        return None
    raw = copy.deepcopy(row.raw if row is not None else live) or {}
    if annotate is not None:
        annotate({"recent_workouts": [raw]}, db)
    started = (_local(row.start_time) if row is not None else None) or _local(_parse_iso(raw.get("start_time")))
    anchor = started.date() if started else datetime.now(AEST).date()
    now = datetime.now(AEST)
    return render_workout(raw, now), anchor, (row.hevy_id if row is not None else ident), raw


def _load_aerobic(db: Session, user_id: int, ident: str):
    try:
        pk = int(ident)
    except ValueError:
        return None
    row = (
        db.query(models.AerobicSession)
        .filter(models.AerobicSession.user_id == user_id, models.AerobicSession.id == pk)
        .first()
    )
    if row is None:
        return None
    started = _local(row.start_time)
    line = "AEROBIC SESSION: " + format_aerobic_session(row)
    if started is not None:
        line += f" (started {_hhmm(started)} local)"
    return [line], row.session_date, row.id, None


# ── context scope: the surrounding window ─────────────────────────────────────

def _window_bounds(anchor: date) -> tuple[date, date]:
    """The context window's first and last local day (both inclusive)."""
    return anchor - timedelta(days=CONTEXT_PRIOR_DAYS), anchor + timedelta(days=CONTEXT_NEXT_DAYS)


def _completed_window(db: Session, user_id: int, anchor: date, *, exclude_hevy: Optional[str],
                      exclude_aerobic: Optional[int]) -> list[str]:
    """Every canonical aerobic session and every counted Hevy workout in the window, oldest first,
    the focus session itself the only exclusion."""
    start_day, end_day = _window_bounds(anchor)
    items: list[tuple[str, str, str]] = []   # (iso date, hh:mm, line) — sorted, then rendered

    for s in arbitrated_sessions(user_id, db, since=start_day):
        if not getattr(s, "canonical", True) or s.session_date > end_day:
            continue
        if exclude_aerobic is not None and s.id == exclude_aerobic:
            continue
        started = _local(s.start_time)
        line = format_aerobic_session(s)
        if started is not None:
            line += f" (start {_hhmm(started)})"
        items.append((s.session_date.isoformat(), _hhmm(started), line))

    lo, hi = _local_day_start_utc(start_day), _local_day_start_utc(end_day + timedelta(days=1))
    candidates = (
        db.query(models.HevyWorkout)
        .filter(models.HevyWorkout.user_id == user_id,
                models.HevyWorkout.start_time >= lo, models.HevyWorkout.start_time < hi)
        .all()
    )
    counted, _unadjudicated = counted_workouts(db, user_id, candidates)
    for w in counted:
        if exclude_hevy is not None and w.hevy_id == exclude_hevy:
            continue
        started = _local(w.start_time)
        day = started.date().isoformat() if started else ""
        items.append((day, _hhmm(started), format_workout_compact(w.raw or {}, f"{day} {_hhmm(started)}".strip())))

    items.sort(key=lambda t: (t[0], t[1]))
    return [f"- {line}" for _d, _t, line in items]


def _scheduled_window(db: Session, user_id: int, anchor: date) -> list[str]:
    """Schedule items falling on each local day of the window, date-resolved (weekday items and dated
    one-offs through the same `item_covers` the week planner uses), soft items included. The whole
    window, as ruled: days before the anchor show what was planned then, beside what was done."""
    entries = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=user_id, type="schedule_item", active=True)
        .all()
    )
    lines: list[str] = []
    start_day, end_day = _window_bounds(anchor)
    for offset in range((end_day - start_day).days + 1):
        d = start_day + timedelta(days=offset)
        for e in entries:
            v = e.value or {}
            if not item_covers(v, d):
                continue
            tag = "hard" if v.get("hard") else "soft"
            load = v.get("expected_load")
            if load and load != "none":
                tag = f"{tag}, {load}"
            when = v.get("time_range") or v.get("time_of_day")
            when_s = f" [{when}]" if when and when != "unknown" else ""
            lines.append(f"- {d.isoformat()} ({d.strftime('%a')}): {v.get('activity', '?')} ({tag}){when_s}")
    return lines


# ── extras: what a review cannot otherwise see ────────────────────────────────

def _same_day_aerobic(db: Session, user_id: int, anchor: date, *, exclude_aerobic: Optional[int]) -> list[str]:
    """Canonical aerobic sessions on the anchor's local day, one compact line each (sport, start,
    duration, avg HR, source) — the focused session itself excluded."""
    lines: list[tuple[str, str]] = []
    for s in arbitrated_sessions(user_id, db, since=anchor):
        if not getattr(s, "canonical", True) or s.session_date != anchor:
            continue
        if exclude_aerobic is not None and s.id == exclude_aerobic:
            continue
        started = _local(s.start_time)
        bits = [s.sport_name or "aerobic"]
        bits.append(f"start {_hhmm(started)}" if started is not None else "start not recorded")
        bits.append(f"{round(s.duration_minutes)} min" if s.duration_minutes is not None else "duration not recorded")
        bits.append(f"avg HR {s.hr_avg}" if s.hr_avg is not None else "avg HR not recorded")
        bits.append(f"source {s.source}")
        lines.append((_hhmm(started), "- " + ", ".join(bits)))
    lines.sort()
    return [line for _t, line in lines]


def _previous_same_routine(db: Session, user_id: int, raw: dict[str, Any], focus_id: str) -> list[str]:
    """The previous `SAME_ROUTINE_PRIOR` counted Hevy workouts sharing the focus workout's `routine_id`,
    newest first, in the compact form. Empty when the focus has no routine id. The scan reads a bounded
    number of the user's earlier workouts and matches `raw.routine_id` in Python (JSON on Postgres and
    SQLite alike)."""
    routine_id = raw.get("routine_id")
    if not routine_id:
        return []
    started = _parse_iso(raw.get("start_time"))
    q = db.query(models.HevyWorkout).filter(models.HevyWorkout.user_id == user_id,
                                            models.HevyWorkout.hevy_id != focus_id)
    if started is not None:
        q = q.filter(models.HevyWorkout.start_time < started)
    candidates = q.order_by(models.HevyWorkout.start_time.desc()).limit(SAME_ROUTINE_SCAN_ROWS).all()
    same = [w for w in candidates if (w.raw or {}).get("routine_id") == routine_id]
    counted, _unadjudicated = counted_workouts(db, user_id, same)
    counted.sort(key=lambda w: w.start_time or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    out = []
    for w in counted[:SAME_ROUTINE_PRIOR]:
        local = _local(w.start_time)
        day = local.date().isoformat() if local else ""
        out.append("- " + format_workout_compact(w.raw or {}, f"{day} {_hhmm(local)}".strip()))
    return out


def _session_exercise_titles(raw: dict[str, Any]) -> list[str]:
    """The distinct exercise titles in a Hevy payload — the catalogue title when annotated, plus the
    logged one (either may be the name a constraint's scope text uses)."""
    seen: dict[str, None] = {}
    for ex in raw.get("exercises") or []:
        for t in (ex.get("canonical_title"), ex.get("title")):
            if isinstance(t, str) and t.strip():
                seen.setdefault(t.strip(), None)
    return list(seen)


def _constraint_flags(db: Session, user_id: int, raw: dict[str, Any], today: date) -> list[str]:
    """One inline flag per confirmed constraint whose SCOPE TEXT names an exercise in the session.

    Match: case-insensitive, whole-phrase (word-boundary) occurrence of an exercise title in
    `scope.text`; titles under `FLAG_MIN_TITLE_CHARS` are skipped. Known limits, both ways: a title that
    is a common word inside a longer one ("Press" in "Overhead Press") can match a constraint about a
    different lift (false positive, bounded by the whole-phrase rule); a scope that names the lift
    differently from Hevy's title, or an engine-tier constraint (scope carries `region_keys`, no text),
    never matches (false negative) — the Constraints section above still carries those."""
    titles = _session_exercise_titles(raw)
    if not titles:
        return []
    entries = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=user_id, active=True)
        .all()
    )
    live_keys = typed_entries.active_keys(entries)
    flags: list[str] = []
    for c in typed_entries.lift_constraints(entries):
        text = str((c.get("scope") or {}).get("text") or "")
        if not text:
            continue
        named = [t for t in titles
                 if len(t) >= FLAG_MIN_TITLE_CHARS
                 and re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", text, re.IGNORECASE)]
        if named:
            flags.append(f"- FLAG — names {', '.join(named)} in this session: "
                         + typed_entries.constraint_line(c, live_keys, today).removeprefix("- "))
    return flags


def _extras(db: Session, user_id: int, focus: "FocusSession", anchor: date, focus_pk: Any,
            raw: Optional[dict[str, Any]]) -> list[str]:
    parts: list[str] = []
    if focus.scope == "session":
        same_day = _same_day_aerobic(db, user_id, anchor, exclude_aerobic=focus_pk if focus.kind == "aerobic" else None)
        parts += ["", f"## Same day — canonical aerobic sessions on {anchor.isoformat()}",
                  *(same_day or ["- None recorded on this day."])]
    if raw is not None:
        prior = _previous_same_routine(db, user_id, raw, str(focus_pk))
        if raw.get("routine_id"):
            parts += ["", f"## Previous {SAME_ROUTINE_PRIOR} workouts of the same routine (newest first)",
                      *(prior or ["- No earlier workout of this routine recorded."])]
        flags = _constraint_flags(db, user_id, raw, datetime.now(AEST).date())
        if flags:
            parts += ["", "## Constraint flags — confirmed constraints that name an exercise in this session", *flags]
    return parts


# ── entry point ───────────────────────────────────────────────────────────────

_FRAME_SESSION = (
    "The operator has asked for a review of THIS session's execution. Judge how it was performed, "
    "from the record below only — loads, reps, RPE, set types, exercise notes, distances and durations "
    "for a strength session; duration, heart rate and zone time for an aerobic one. If a field is not "
    "in the record, say it is not recorded; do not infer or invent it."
)
_FRAME_CONTEXT = (
    "The operator has asked for a review of this session IN CONTEXT. Judge it against the active phase, "
    "the surrounding load, and what is coming next: the phase, weekly schedule and constraints are in "
    "the sections above; the sessions performed and the items scheduled in the days around it, including "
    "the same day, follow the session. Judge from the record only — if something is not recorded, say so."
)


def build_focus_block(
    db: Session,
    user_id: int,
    focus: FocusSession,
    *,
    annotate_hevy: Optional[Callable[[dict[str, Any], Session], Any]] = None,
    live_hevy: Optional[dict[str, Any]] = None,
) -> str:
    """The pinned system-prompt block for `focus`, for the calling user only. Never raises for a
    missing/foreign session (the block says so); an unexpected failure is logged and reported inside
    the block, so the turn always proceeds. `live_hevy` is the Hevy payload fetched by id for a
    workout missing from `hevy_workouts` (see `needs_live_hevy`)."""
    try:
        if focus.kind == "hevy":
            loaded = _load_hevy(db, user_id, focus.id, annotate_hevy, live_hevy)
        else:
            loaded = _load_aerobic(db, user_id, focus.id)
        if loaded is None:
            return _not_found(focus.kind, focus.id)
        session_lines, anchor, focus_pk, raw = loaded

        frame = _FRAME_CONTEXT if focus.scope == "context" else _FRAME_SESSION
        parts = ["## Session under review", frame, "", *session_lines]
        parts += _extras(db, user_id, focus, anchor, focus_pk, raw)

        if focus.scope == "context":
            done = _completed_window(
                db, user_id, anchor,
                exclude_hevy=focus_pk if focus.kind == "hevy" else None,
                exclude_aerobic=focus_pk if focus.kind == "aerobic" else None,
            )
            first, last = _window_bounds(anchor)
            parts += [
                "",
                f"## Surrounding load — {first.isoformat()} to {last.isoformat()}, the session's day included "
                "(canonical aerobic sessions and counted Hevy workouts; the session above excluded)",
                *(done or ["- None recorded in this window."]),
            ]
            planned = _scheduled_window(db, user_id, anchor)
            parts += [
                "",
                f"## Scheduled — {first.isoformat()} to {last.isoformat()}, the session's day included",
                *(planned or ["- No schedule items fall in this window."]),
            ]
        return "\n".join(parts)
    except Exception:  # noqa: BLE001 — the review turn must proceed; the failure is loud in the block
        logger.exception("session focus failed to load (kind=%s scope=%s)", focus.kind, focus.scope)
        return ("## Session under review\n"
                "The operator asked to review a session, but loading it failed on the server. There is no "
                "session data to review — say so plainly, and do not describe or invent a session.")
