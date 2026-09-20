"""Week planner — the schedule checked against the phase, hard items first (#316).

A pure, read-only derived read over stores that already exist. It answers three operator
behaviours from ONE read, introducing no new store and no persisted "plan state":

1. **Compare and push back.** Per slot key: `scheduled` (active linked `schedule_item`s) vs
   `quota` (this leg) vs `done` (from `resolve()`, never recounted). `excess`/`unplaced` are
   named so the coach can say so before initiating a session on an already-met key.
2. **Prompt planning at phase start.** `needs_planning` is true when the open phase declares a
   quota that NO schedule item is placed against (every key `scheduled == 0`).
3. **Hard items first, then availability.** Fixed commitments occupy their days; what is left is
   availability; flexible sessions are placed into availability.

Built over ALL THREE slot kinds (`capacity` | `load_window` | `activity`, #315) — a
`satisfies: {activity: …}` item counts exactly like the others.

GUARDs (operator, #316): the plan is DERIVED and STATELESS — no auto-written schedule items, no
ledger writes; it does not touch `resolve()`, the validators, or #275's free-order rule (days are
preferences, never deadlines; nothing here marks a session "missed" because it moved day). Quota is
a TARGET that triggers a prompt when exceeded, never a lock. `_local_day` is the SINGLE local-day
source (shared with the resolver); the render folds the next-7-days hard lines in rather than
stating the week twice.

Constrained-availability width is an operator prior (G0, 2026-09-20): the day OF a `heavy` hard
item is unavailable; the day AFTER is available but FLAGGED `caution: day after heavy` (advisory,
never blocking). `expected_load: "none"` items never constrain. Recorded here, not chosen by code.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from load_metrics import _local_day
from engine import resolver as resolver_mod

logger = logging.getLogger(__name__)

# Monday..Sunday, index-aligned with `datetime.date.weekday()` (Monday == 0).
_DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Polar rows carry one of these sources; the freshness read below maxes their ingest time.
_POLAR_SOURCES = ("polar_flow_export", "polar_v4")


def schedule_sessions_per_week(value: dict[str, Any]) -> int:
    """A `schedule_item`'s weekly session count (#312): `sessions_per_week` when present (days are
    CANDIDATES, not a count — "Mon/Wed/Fri, 2 a week" is 2), else the number of listed `days`.
    `validate_schedule_item` constrains neither against the other, so an item carrying BOTH is read
    as its declared count. One definition, shared by the #312 consistency line and `plan_week`."""
    spw = value.get("sessions_per_week")
    if isinstance(spw, int) and not isinstance(spw, bool):
        return spw
    days = value.get("days")
    return len(days) if isinstance(days, list) else 0


def consistency_rows(
    slots: list[dict[str, Any]], item_values: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The #312 schedule↔quota derivation, extracted so the chat consistency line and `plan_week`
    read ONE definition (the brief's "move it, one definition, two callers"). Per slot, in slot
    order: `scheduled` (sessions/wk summed over items whose `satisfies` names this slot's
    {kind,key}) vs `quota` (this leg) vs `done` (from `resolve()`, verbatim — never recounted),
    with `excess`/`unplaced` derived. Renders nothing itself; each caller decides wording
    (MISMATCH/UNPLACED is a 7-day-leg render concern, not computed here)."""
    rows: list[dict[str, Any]] = []
    for slot in slots:
        kind = slot.get("kind")
        key = slot.get(kind) if kind else None
        scheduled = sum(
            schedule_sessions_per_week(v)
            for v in item_values
            if isinstance(v.get("satisfies"), dict) and v["satisfies"].get(kind) == key
        )
        quota = slot.get("quota") or 0
        done = slot.get("done") or 0
        rows.append({
            "kind": kind, "key": key, "quota": quota, "done": done,
            "scheduled": scheduled,
            "excess": max(0, scheduled - quota),
            "unplaced": max(0, quota - scheduled),
        })
    return rows


def _actuals_by_day(db: Session, slots: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Attribute the sessions/workouts `resolve()` ALREADY counted to local days — a bounded lookup
    of exactly those ids (never a recount; `done` stays resolve()'s number). Capacity slots count
    Hevy workouts (`workouts_counted`, hevy ids); load_window/activity slots count aerobic sessions
    (`sessions_counted`, session ids). Each counted item is tagged with the slot key it counted for
    (from the resolver output), then placed on its `_local_day`."""
    workout_key: dict[str, tuple[str, Any]] = {}
    session_key: dict[int, tuple[str, Any]] = {}
    for slot in slots:
        kind = slot.get("kind")
        key = slot.get(kind) if kind else None
        for hid in slot.get("workouts_counted") or []:
            workout_key[hid] = (kind, key)
        for cs in slot.get("sessions_counted") or []:
            sid = cs.get("session")
            if sid is not None:
                session_key[sid] = (kind, key)

    by_day: dict[str, list[dict[str, Any]]] = {}
    if workout_key:
        rows = (
            db.query(models.HevyWorkout)
            .filter(models.HevyWorkout.hevy_id.in_(list(workout_key)))
            .all()
        )
        for w in rows:
            if w.start_time is None:
                continue
            kind, key = workout_key[w.hevy_id]
            day = _local_day(w.start_time).isoformat()
            by_day.setdefault(day, []).append(
                {"kind": kind, "key": key, "ref": w.hevy_id, "title": w.title}
            )
    if session_key:
        rows = (
            db.query(models.AerobicSession)
            .filter(models.AerobicSession.id.in_(list(session_key)))
            .all()
        )
        for s in rows:
            kind, key = session_key[s.id]
            day = (_local_day(s.start_time) if s.start_time is not None else s.session_date).isoformat()
            by_day.setdefault(day, []).append(
                {"kind": kind, "key": key, "ref": s.id, "sport_name": s.sport_name}
            )
    return by_day


def _freshness(db: Session, user_id: int, window_start: date) -> dict[str, Any]:
    """Age of the last device ingest, so device-evidenced counts are not presented as fact when the
    platform has not heard from the device this window (ruling 4).

    - HC = `max(HealthConnectSync.synced_at)` — "when did the phone last sync" (NOT
      `AerobicSession.created_at`, which is "when did a session last ARRIVE": a quiet-but-synced
      week would false-alarm and a sync with nothing new would never move it).
    - Polar has NO recorded last-successful-pull timestamp anywhere (the pull is manual, Q154), so
      this falls back to the newest Polar row's `created_at`, LABELLED "newest Polar session
      received" (not "last pull"). `polar_pull_ts_exists` is False so the render can say so.

    `*_stale` is true when the signal is absent OR its local day predates the window start — the
    condition under which counts "may be INCOMPLETE" (a same-day sync with zero new sessions is NOT
    stale)."""
    hc = (
        db.query(func.max(models.HealthConnectSync.synced_at))
        .filter(models.HealthConnectSync.user_id == user_id)
        .scalar()
    )
    polar = (
        db.query(func.max(models.AerobicSession.created_at))
        .filter(
            models.AerobicSession.user_id == user_id,
            models.AerobicSession.source.in_(_POLAR_SOURCES),
        )
        .scalar()
    )

    def _stale(ts: Any) -> bool:
        return ts is None or _local_day(ts) < window_start

    return {
        "hc_synced_at": hc.isoformat() if hc is not None else None,
        "hc_stale": _stale(hc),
        "polar_latest_session_at": polar.isoformat() if polar is not None else None,
        "polar_stale": _stale(polar),
        "polar_pull_ts_exists": False,   # no last-successful-pull timestamp is recorded (Q154)
    }


def plan_week(
    db: Session,
    user_id: int,
    today: date,
    *,
    entries: list[Any] | None = None,
    resolver_position: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """The derived week plan over the resolver's CURRENT window (the same window `resolve()`
    yields — never a second one). `None` at baseline (no phase microcycle, no weekly template →
    null window), so the render adds nothing and the context stays byte-identical (#272/#316 G3).

    `entries`/`resolver_position` may be passed by a caller that already has them (current_state)
    to avoid a second read; omitted, `plan_week` fetches its own — so `GET /engine/week-plan` can
    call it standalone."""
    pos = resolver_position if resolver_position is not None else resolver_mod.resolve(db, user_id, today=today)
    window = pos.get("window")
    if not window:
        return None

    start = date.fromisoformat(window["start_date"])
    end = date.fromisoformat(window["end_date"])
    slots = pos.get("slots") or []

    if entries is None:
        entries = (
            db.query(models.UserKnowledgeEntry)
            .filter_by(user_id=user_id, active=True)
            .all()
        )
    schedule_vals = [
        (e.value or {}) for e in entries if getattr(e, "type", None) == "schedule_item"
    ]
    load_ctx_vals = [
        (e.value or {}) for e in entries if getattr(e, "type", None) == "load_context"
    ]

    keys = consistency_rows(slots, schedule_vals)
    actuals = _actuals_by_day(db, slots)

    def _item_days(v: dict[str, Any]) -> list[str]:
        return [d.lower() for d in (v.get("days") or []) if isinstance(d, str)]

    # Precompute the weekdays a HEAVY hard item lands on, for the day-after caution.
    heavy_weekdays: set[str] = set()
    for v in schedule_vals:
        if v.get("hard") and v.get("expected_load") == "heavy":
            heavy_weekdays.update(_item_days(v))

    days: list[dict[str, Any]] = []
    d = start
    while d <= end:
        wd = _DAY_ORDER[d.weekday()]
        hard: list[dict[str, Any]] = []
        flexible: list[dict[str, Any]] = []
        for v in schedule_vals:
            if wd not in _item_days(v):
                continue
            if v.get("hard"):
                hard.append({
                    "activity": v.get("activity"),
                    "expected_load": v.get("expected_load"),
                    "same_day_training": bool(v.get("same_day_training")),
                })
            else:
                flexible.append({"activity": v.get("activity"), "satisfies": v.get("satisfies")})
        # A day is unavailable iff a hard item that day BLOCKS training: not same_day_training AND
        # not a zero-load item (ruling 1 — `expected_load: "none"` never constrains).
        constraining = [
            h for h in hard
            if not h["same_day_training"] and h["expected_load"] != "none"
        ]
        available = not constraining
        # Caution when the PREVIOUS day carried a heavy hard item (width = operator prior).
        prev_wd = _DAY_ORDER[(d - timedelta(days=1)).weekday()]
        caution = "day after heavy" if prev_wd in heavy_weekdays else None
        days.append({
            "date": d.isoformat(),
            "weekday": wd,
            "hard": hard,
            "flexible": flexible,
            "actual": actuals.get(d.isoformat(), []),
            "available": available,
            "caution": caution,
        })
        d += timedelta(days=1)

    unlinked_soft = [
        v.get("activity") or "?"
        for v in schedule_vals
        if v.get("satisfies") is None and v.get("hard") is False
    ]

    # One-off notes (ruling 3): active load_context entries surfaced BESIDE the week as undated
    # notes, so the coach sees them with the plan. A dated one-off hard item is deferred (Q165).
    one_off_notes = [
        {
            "description": v.get("description") or v.get("note") or "load context",
            "expires_at": v.get("expires_at"),
        }
        for v in load_ctx_vals
    ]

    needs_planning = bool(slots) and all(r["scheduled"] == 0 for r in keys)

    return {
        "window": {
            "start_date": window["start_date"],
            "end_date": window["end_date"],
            "label": window.get("label"),
            "source": window.get("source"),
        },
        "days": days,
        "keys": keys,
        "unlinked_soft": unlinked_soft,
        "one_off_notes": one_off_notes,
        "needs_planning": needs_planning,
        "freshness": _freshness(db, user_id, start),
    }
