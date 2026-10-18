"""
Route (i) strength read (Q27 v1): estimated 1RM per side, derived from the Hevy log.

READ-ONLY. This module never writes `capability_observations`; it reads the logged sets through the
shared strength-read primitives (`reads/strength_reads.py`: the same Epley estimate, the same rep cap,
the same working-set rule and the same AEST session-day as the See-test series - FEEDBACK 39, one helper
not a copy) and the `exercise_region_tags` map.

A region's templates are the tag rows with `role="primary"` for that region. A template's side is the
tag's DECLARED `side` column (`left` | `right`; NULL reads as `bilateral`) - never derived by stripping
" L" / " R" from a title. Per session-day and per side, the value is the best e1RM across that side's
templates, with the template that produced it.

No label, no band and no threshold is produced here: a left/right index is a ratio and the lower side.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

import models
from reads import strength_reads
from . import observations as observations_mod
from .taxonomy import SIDE_BILATERAL, SIDE_LEFT, SIDE_RIGHT


def _templates_by_side(db: Session, region_key: str) -> dict[str, str]:
    """{template_id: side} for the primary tags of `region_key` (NULL side -> bilateral)."""
    rows = (
        db.query(models.ExerciseRegionTag)
        .filter_by(region_key=region_key, role="primary")
        .all()
    )
    return {r.hevy_exercise_template_id: (r.side or SIDE_BILATERAL) for r in rows}


def e1rm_by_side(
    db: Session, user_id: int, region_key: str, since: date | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """{side: [{day, e1rm_kg, top_set, template_id}]}, ascending by day. A session-day appears for a
    side only if one of that side's templates has a scorable set (e1RM not None)."""
    sides = _templates_by_side(db, region_key)
    if not sides:
        return {}
    by_template = strength_reads.session_days_by_template(db, user_id, since or date.min)

    best: dict[str, dict[date, dict[str, Any]]] = {}
    for tid, side in sides.items():
        for day, raw_sets in (by_template.get(tid) or {}).items():
            agg = strength_reads.aggregate_session(raw_sets)
            if agg is None or agg["e1rm_kg"] is None:
                continue
            cur = best.setdefault(side, {}).get(day)
            if cur is None or agg["e1rm_kg"] > cur["e1rm_kg"]:
                best[side][day] = {
                    "day": day, "e1rm_kg": agg["e1rm_kg"], "top_set": agg["top_set"],
                    "template_id": tid,
                }
    return {side: [days[d] for d in sorted(days)] for side, days in best.items()}


def symmetry_by_day(series: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Per session-day where BOTH `left` and `right` have an e1RM: the ratio and the lower side
    (the shape of `observations.symmetry`). Same-day only; no threshold."""
    left = {p["day"]: p for p in series.get(SIDE_LEFT, [])}
    right = {p["day"]: p for p in series.get(SIDE_RIGHT, [])}
    out = []
    for day in sorted(set(left) & set(right)):
        index_pct, lower = observations_mod.left_right_index(left[day]["e1rm_kg"], right[day]["e1rm_kg"])
        out.append({
            "day": day, "left_e1rm_kg": left[day]["e1rm_kg"], "right_e1rm_kg": right[day]["e1rm_kg"],
            "index_pct": index_pct, "lower_side": lower,
        })
    return out


def point_as_dict(p: dict[str, Any]) -> dict[str, Any]:
    return {**p, "day": str(p["day"])}


def log_strength_as_dict(
    db: Session, user_id: int, region_key: str, since: date | None = None,
) -> dict[str, Any]:
    series = e1rm_by_side(db, user_id, region_key, since)
    return {
        "region_key": region_key,
        "source": "hevy log (Epley e1RM, working sets, reps 1-10)",
        "sides": {s: [point_as_dict(p) for p in pts] for s, pts in series.items()},
        "symmetry": [{**r, "day": str(r["day"])} for r in symmetry_by_day(series)],
    }
