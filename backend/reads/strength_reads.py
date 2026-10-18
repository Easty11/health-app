"""Strength-read primitives shared by the See-test series and route (i) (Q27 v1).

Moved verbatim from `routers/series.py` (no behaviour change) so the log-derived strength read
(`engine/log_strength.py`) reuses the ONE Epley / working-set / session-day helper rather than a
copy that could drift (FEEDBACK 39). `routers/series.py` imports these and keeps its old private
names as aliases, so `series._aggregate_session is strength_reads.aggregate_session`.

Day grain is `load_metrics._local_day` (the rollup's AEST day, Q42), imported not re-derived.
"""
from __future__ import annotations

from datetime import datetime

import pytz
from sqlalchemy.orm import Session

import models
from load_metrics import _local_day
from reads.hevy_reads import counted_workouts   # the counted-workouts read-door (#Q161)

_AEST = pytz.timezone("Australia/Brisbane")


def _today_aest():
    return datetime.now(_AEST).date()


# Working set types (D3): everything except `warmup`. An untyped set defaults to `normal`
# (the `load_events` transform convention), so it counts — only an explicit `warmup` is cut.
EPLEY_REP_CAP = 10  # reps > cap do not contribute to e1RM (D1); they still count to volume.


def epley_e1rm(weight_kg: float, reps: int) -> float:
    """Epley one-rep-max estimate: weight × (1 + reps/30). Pure; the strength signal (D1)."""
    return weight_kg * (1.0 + reps / 30.0)


def is_working_set(raw_set: dict) -> bool:
    """A working set (D3): any set NOT typed `warmup`. Matches the transform's default-normal
    reading of an absent type (`load_events._set_line`)."""
    return (raw_set.get("type") or "normal").lower() != "warmup"


def aggregate_session(raw_sets: list[dict]) -> dict | None:
    """Collapse one template's sets on ONE session-day to a point, or None if no working set.

    e1RM is the max Epley over working sets with reps in [1, cap] and a logged weight (D1);
    None when none qualifies. Volume sums weight×reps over ALL working sets that carry both
    (a reps>cap set is excluded from e1RM but included here, D1/D2). `top_set` is the set that
    produced the max e1RM. `working_sets` counts every non-warmup set, scorable or not."""
    working = [s for s in raw_sets if is_working_set(s)]
    if not working:
        return None

    volume = 0.0
    best_e1rm: float | None = None
    top_set: dict | None = None
    for s in working:
        weight = s.get("weight_kg")
        reps = s.get("reps")
        if weight is None or reps is None:
            continue
        weight = float(weight)
        reps = int(reps)
        volume += weight * reps
        if 1 <= reps <= EPLEY_REP_CAP:
            e = epley_e1rm(weight, reps)
            if best_e1rm is None or e > best_e1rm:
                best_e1rm = e
                top_set = {"weight_kg": weight, "reps": reps}

    return {
        "e1rm_kg": best_e1rm,
        "top_set": top_set,
        "volume_kg_reps": volume,
        "working_sets": len(working),
    }


def session_days_by_template(
    db: Session, user_id: int, since, *, template_id: str | None = None
) -> dict[str, dict]:
    """{template_id: {day: [raw_set, ...]}} for the user's in-range, COUNTED workouts. Grouped
    by `_local_day` so multiple same-day workouts collapse onto one session-day (brief step 2).
    `template_id` narrows to a single template when given.

    Counting goes through the shared `reads.hevy_reads.counted_workouts` door (#Q161): the old
    `dedup_flag IS NOT TRUE` filter (mirroring the resolver's pre-#309 D3) dropped the RETAINED
    performed log of an adjudicated pair too — both members are flagged. The door keeps the
    retained log and drops only the artifact / an unadjudicated pair. The local-day bound is
    applied in Python off `_local_day` (the resolver does the same)."""
    today = _today_aest()
    candidates = (
        db.query(models.HevyWorkout)
        .filter(
            models.HevyWorkout.user_id == user_id,
            models.HevyWorkout.excluded_at.is_(None),
        )
        .all()
    )
    rows, _unadjudicated = counted_workouts(db, user_id, candidates)

    by_template: dict[str, dict] = {}
    for w in rows:
        if w.start_time is None:
            continue
        day = _local_day(w.start_time)
        if not (since <= day <= today):
            continue
        for ex in (w.raw or {}).get("exercises", []) or []:
            tid = ex.get("exercise_template_id")
            if not tid:
                continue  # #79 — a block with no template id has nothing to key on
            if template_id is not None and tid != template_id:
                continue
            day_sets = by_template.setdefault(tid, {}).setdefault(day, [])
            day_sets.extend(ex.get("sets", []) or [])

    return by_template


def title_map(db: Session, template_ids) -> dict[str, str]:
    """template_id → catalogue title for the given ids. A template absent from the local
    catalogue (#79 hole) is simply not in the map; the caller falls back to the id."""
    if not template_ids:
        return {}
    rows = (
        db.query(models.HevyExerciseTemplate.id, models.HevyExerciseTemplate.title)
        .filter(models.HevyExerciseTemplate.id.in_(list(template_ids)))
        .all()
    )
    return {tid: title for tid, title in rows}
