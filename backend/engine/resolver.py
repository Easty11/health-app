"""Due-slot resolver — which sub-cycle leg is current, how far through its quota the
user is, and which slot is due next (Q106's week-to-date / due-slot half, #221-deferred,
#270-scoped).

A **quota window** is the unit this module resolves over: a dated span carrying an ordered
list of `{capacity, quota}` slots. Two producers, one precedence (mirrors phase-now over
profile-intent, #270):

    open phase WITH a microcycle  → the current A/B leg, quota = `sessions_per_cycle`
    else, a fortification profile → this Mon–Sun week,   quota = `sessions_per_week`
    neither                        → None (baseline; the endpoint returns a null window, 200)

Completion is **derived on read from Hevy**, never written back — a session counts because it
is in the record, not because anything marked it "taken". For each non-excluded, non-dedup
workout whose LOCAL day falls in the window, a dominant capacity is computed and, if it names
a slot, increments that slot's `done`.

Two rules the resolver turns on (operator-pinned, this session; not `infer_loaded_regions`,
which answers coverage, not "what was this session"):

  • **Rule 1 — dominant capacity.** The capacity with the most PRIMARY-tagged exercises in the
    workout (`exercise_region_tags.role == 'primary'` → `Region.capacity`). Secondary tags are
    ignored — they say what a movement also loads, not what the session was. Tie → the tied
    capacity that appears FIRST in the window's slot order. One workout, one slot.
  • **Rule 4 — due slot.** The first slot in DECLARED order with `remaining > 0`; None if every
    slot is met. Declared order is what the ordering is for — no fraction-remaining cleverness.

A workout with a derivable dominant capacity that is not a slot in the window is *off-plan*
(distinct from *untagged* = zero primary tags); both are surfaced in `uncounted[]` so the
position never silently under-reports. Neither counts toward a quota.

The slot session-length field that Q106 owns is never read here — Q106 stays open on it
alone. No schema, no scheduler, no calendar, no write-back.

Local-day indexing is the single-source `_local_day` (AEST/Australia/Brisbane, no DST): both
`today` and each workout's UTC `start_time` are bucketed to a Brisbane date before any date
arithmetic — the known trap a UTC `::date` bucket falls into.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

import models
from load_metrics import _local_day

from . import taxonomy
from .profile import get_profile
from .taxonomy import Capacity
from .training_phase import current_training_phase

# Sub-cycle labels when a leg carries none of its own: A, B, C, D by order.
_LEG_LABELS = ("A", "B", "C", "D")


@dataclass(frozen=True)
class Slot:
    """One quota line in a window: a capacity and how many sessions it wants."""
    capacity: Capacity
    quota: int


@dataclass
class QuotaWindow:
    start_date: date          # inclusive, local (Brisbane) day
    end_date: date            # inclusive, local (Brisbane) day
    label: str
    source: str               # "phase" | "weekly"
    slots: list[Slot] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Producers — pure over their inputs; `today` is always a local (Brisbane) day. #
# --------------------------------------------------------------------------- #

def _slots_from(raw_slots: list[dict[str, Any]], quota_key: str) -> list[Slot]:
    """Resolve each declared slot's capacity via `resolve_capacity` (Q105 — never compare a
    stored token to a string directly) and pair it with its quota. A slot whose capacity does
    not resolve is skipped defensively; validation refuses such a slot at write, so this is a
    guard, not a path."""
    out: list[Slot] = []
    for s in raw_slots:
        if not isinstance(s, dict):
            continue
        cap = taxonomy.resolve_capacity(s.get("capacity"))
        if cap is None:
            continue
        quota = s.get(quota_key)
        out.append(Slot(capacity=cap, quota=int(quota) if isinstance(quota, int) else 0))
    return out


def phase_window(phase: models.TrainingPhase, today: date) -> QuotaWindow | None:
    """The current A/B leg of an open phase's microcycle. `None` if the phase carries no
    microcycle (the caller then falls through to the weekly producer)."""
    micro = phase.microcycle
    if not isinstance(micro, dict):
        return None
    scd = micro.get("sub_cycle_days")
    sub_cycles = micro.get("sub_cycles")
    if not isinstance(scd, int) or scd <= 0 or not isinstance(sub_cycles, list) or not sub_cycles:
        return None

    # Leg indexing from `entered_on` in whole sub-cycle lengths. `entered_on <= today`
    # holds for an open phase (future entry is refused at write), so `elapsed >= 0`.
    elapsed = (today - phase.entered_on).days
    if elapsed < 0:
        elapsed = 0
    leg_ordinal = elapsed // scd                 # which leg overall (0-based)
    leg_index = leg_ordinal % len(sub_cycles)    # which sub-cycle it maps to
    start = phase.entered_on + timedelta(days=leg_ordinal * scd)
    end = start + timedelta(days=scd - 1)

    sc = sub_cycles[leg_index]
    if not isinstance(sc, dict):
        return None
    label = sc.get("label")
    if not (isinstance(label, str) and label.strip()):
        label = _LEG_LABELS[leg_index] if leg_index < len(_LEG_LABELS) else str(leg_index + 1)
    slots = _slots_from(sc.get("slots") or [], "sessions_per_cycle")
    return QuotaWindow(start_date=start, end_date=end, label=label, source="phase", slots=slots)


def weekly_window(profile: models.FortificationProfile, today: date) -> QuotaWindow | None:
    """The Mon–Sun week containing `today`, quotas from `weekly_template`. `None` if the
    profile declares no template slots."""
    template = profile.weekly_template
    if not isinstance(template, dict):
        return None
    raw_slots = template.get("slots")
    if not isinstance(raw_slots, list) or not raw_slots:
        return None
    monday = today - timedelta(days=today.weekday())   # Monday == weekday 0
    sunday = monday + timedelta(days=6)
    slots = _slots_from(raw_slots, "sessions_per_week")
    return QuotaWindow(
        start_date=monday, end_date=sunday,
        label=f"Week of {monday.isoformat()}", source="weekly", slots=slots,
    )


def resolve_window(db: Session, user_id: int, today: date) -> QuotaWindow | None:
    """Precedence: an open phase WITH a microcycle wins; else the weekly template; else None."""
    phase = current_training_phase(db, user_id)
    if phase is not None:
        w = phase_window(phase, today)
        if w is not None:
            return w
    profile = get_profile(db, user_id)
    if profile is not None:
        return weekly_window(profile, today)
    return None


# --------------------------------------------------------------------------- #
# Counting — dominant capacity (Rule 1) over in-window Hevy workouts.          #
# --------------------------------------------------------------------------- #

def _primary_caps_by_template(db: Session, template_ids: set[str]) -> dict[str, set[Capacity]]:
    """`template_id → {Capacity}` from PRIMARY region tags only (Rule 1 ignores secondary).
    An orphan `region_key` (no taxonomy entry) is skipped, mirroring `_tags_by_template`."""
    if not template_ids:
        return {}
    rows = (
        db.query(models.ExerciseRegionTag)
        .filter(
            models.ExerciseRegionTag.hevy_exercise_template_id.in_(template_ids),
            models.ExerciseRegionTag.role == "primary",
        )
        .all()
    )
    out: dict[str, set[Capacity]] = {}
    for r in rows:
        region = taxonomy.by_key(r.region_key)
        if region is None:
            continue
        out.setdefault(r.hevy_exercise_template_id, set()).add(region.capacity)
    return out


def _dominant_capacity(
    exercises: list[dict[str, Any]],
    caps_by_template: dict[str, set[Capacity]],
    slot_order: list[Capacity],
) -> tuple[Capacity | None, int]:
    """Rule 1. Returns `(dominant_capacity_or_None, untagged_exercise_count)`.

    `dominant` is None only when NO exercise yields a capacity (a zero-derivable workout).
    An exercise counts once toward every capacity it is primary-tagged for; the dominant is
    the highest count, ties broken by first appearance in `slot_order` (then taxonomy order,
    so an all-off-plan tie is still deterministic)."""
    counts: dict[Capacity, int] = {}
    untagged = 0
    for ex in exercises:
        tid = ex.get("exercise_template_id") if isinstance(ex, dict) else None
        caps = caps_by_template.get(tid) if tid else None
        if not caps:
            untagged += 1
            continue
        for c in caps:
            counts[c] = counts.get(c, 0) + 1
    if not counts:
        return None, untagged
    top = max(counts.values())
    tied = [c for c, n in counts.items() if n == top]
    if len(tied) == 1:
        return tied[0], untagged
    for c in slot_order:                       # tie → first in the window's slot order
        if c in tied:
            return c, untagged
    order = list(Capacity)                     # all-off-plan tie → deterministic taxonomy order
    return sorted(tied, key=order.index)[0], untagged


def _in_window_workouts(db: Session, user_id: int, window: QuotaWindow) -> list[models.HevyWorkout]:
    """Non-excluded, non-dedup workouts whose LOCAL (Brisbane) day is in the window. A UTC
    prefilter widened one day each side bounds the query; the precise bucket is `_local_day`
    (the +10h offset can push a late-UTC instant onto the next local day — the known trap)."""
    lo = datetime.combine(window.start_date - timedelta(days=1), time.min, tzinfo=timezone.utc)
    hi = datetime.combine(window.end_date + timedelta(days=1), time.max, tzinfo=timezone.utc)
    rows = (
        db.query(models.HevyWorkout)
        .filter(
            models.HevyWorkout.user_id == user_id,
            models.HevyWorkout.excluded_at.is_(None),
            models.HevyWorkout.dedup_flag.isnot(True),
            models.HevyWorkout.start_time.isnot(None),
            models.HevyWorkout.start_time >= lo,
            models.HevyWorkout.start_time <= hi,
        )
        .all()
    )
    return [w for w in rows if window.start_date <= _local_day(w.start_time) <= window.end_date]


# --------------------------------------------------------------------------- #
# Public: resolve → the endpoint/enforcement payload.                          #
# --------------------------------------------------------------------------- #

def resolve(db: Session, user_id: int, *, today: date | None = None) -> dict[str, Any]:
    """The full resolver read: window, per-slot position, the due capacity (Rule 4), and the
    surfaced `uncounted[]`. At baseline (no phase microcycle, no weekly template) `window` is
    null and the lists are empty — the #272 no-profile contract (200, degraded body)."""
    today = today or _local_day()
    window = resolve_window(db, user_id, today)
    if window is None:
        return {"window": None, "slots": [], "due_capacity": None, "uncounted": []}

    slot_order = [s.capacity for s in window.slots]
    done: dict[Capacity, int] = {s.capacity: 0 for s in window.slots}
    counted: dict[Capacity, list[str]] = {s.capacity: [] for s in window.slots}
    uncounted: list[dict[str, Any]] = []

    workouts = _in_window_workouts(db, user_id, window)
    all_tids: set[str] = set()
    for w in workouts:
        for ex in (w.raw or {}).get("exercises") or []:
            tid = ex.get("exercise_template_id") if isinstance(ex, dict) else None
            if tid:
                all_tids.add(tid)
    caps_by_template = _primary_caps_by_template(db, all_tids)

    slot_caps = set(slot_order)
    for w in workouts:
        exercises = (w.raw or {}).get("exercises") or []
        dominant, untagged = _dominant_capacity(exercises, caps_by_template, slot_order)
        if dominant is None:
            uncounted.append({"workout": w.hevy_id, "reason": "untagged",
                              "untagged_exercises": untagged})
        elif dominant in slot_caps:
            done[dominant] += 1
            counted[dominant].append(w.hevy_id)
        else:
            uncounted.append({"workout": w.hevy_id, "reason": "off_plan",
                              "capacity": dominant.value})

    slots_out: list[dict[str, Any]] = []
    due_capacity: Capacity | None = None
    for s in window.slots:
        remaining = max(s.quota - done[s.capacity], 0)
        if due_capacity is None and remaining > 0:      # Rule 4: first unmet in declared order
            due_capacity = s.capacity
        slots_out.append({
            "capacity": s.capacity.value,
            "quota": s.quota,
            "done": done[s.capacity],
            "remaining": remaining,
            "workouts_counted": counted[s.capacity],
        })

    return {
        "window": {
            "start_date": window.start_date.isoformat(),
            "end_date": window.end_date.isoformat(),
            "label": window.label,
            "source": window.source,
        },
        "slots": slots_out,
        "due_capacity": due_capacity.value if due_capacity is not None else None,
        "uncounted": uncounted,
    }


def due_capacity(db: Session, user_id: int, *, today: date | None = None) -> str | None:
    """The due slot's capacity value, or None — the enforcement hook for `/engine/next` when
    no explicit `capacity=` is supplied."""
    return resolve(db, user_id, today=today)["due_capacity"]
