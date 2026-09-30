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

Pure read; no schema. The renderers are shared, never copied.
"""
from __future__ import annotations

import copy
import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Literal, Optional

import pytz
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
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


class FocusSession(BaseModel):
    """The request-only reference to the session under review (no schema, nothing persisted)."""
    kind: Literal["hevy", "aerobic"]
    id: str = Field(min_length=1, max_length=128)
    scope: Literal["session", "context"]


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
               annotate: Optional[Callable[[dict[str, Any], Session], Any]]):
    """(rendered_lines, anchor_date, focus_id) or None. The raw payload is deep-copied before
    annotation so the ORM row's JSON is never mutated."""
    row = (
        db.query(models.HevyWorkout)
        .filter(models.HevyWorkout.user_id == user_id, models.HevyWorkout.hevy_id == ident)
        .first()
    )
    if row is None:
        return None
    raw = copy.deepcopy(row.raw or {})
    if annotate is not None:
        annotate({"recent_workouts": [raw]}, db)
    started = _local(row.start_time) or _local(_parse_iso(raw.get("start_time")))
    anchor = started.date() if started else datetime.now(AEST).date()
    now = datetime.now(AEST)
    return render_workout(raw, now), anchor, row.hevy_id


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
    return [line], row.session_date, row.id


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
) -> str:
    """The pinned system-prompt block for `focus`, for the calling user only. Never raises for a
    missing/foreign session (the block says so); an unexpected failure is logged and reported inside
    the block, so the turn always proceeds."""
    try:
        if focus.kind == "hevy":
            loaded = _load_hevy(db, user_id, focus.id, annotate_hevy)
        else:
            loaded = _load_aerobic(db, user_id, focus.id)
        if loaded is None:
            return _not_found(focus.kind, focus.id)
        session_lines, anchor, focus_pk = loaded

        frame = _FRAME_CONTEXT if focus.scope == "context" else _FRAME_SESSION
        parts = ["## Session under review", frame, "", *session_lines]

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
