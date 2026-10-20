"""
Route (i) strength read (Q27 v1): estimated 1RM per side, derived from the Hevy log.

READ-ONLY. This module never writes `capability_observations`; it reads the logged sets through the
shared strength-read primitives (`reads/strength_reads.py`: the same Epley estimate, the same
working-set rule and the same AEST session-day as the See-test series - FEEDBACK 39, one helper not a
copy) and the `exercise_region_tags` map. The REP CAP is route (i)'s own, passed in by the caller
(`Ratio.log_rep_ceiling` for a ratio, `LOG_REP_CEILING` here for the per-region read): the See-test's
cap (10) is a different rule and is not applied on this path.

A region's templates are the tag rows with `role="primary"` for that region. A template's side is the
tag's DECLARED `side` column (`left` | `right`; NULL reads as `bilateral`) - never derived by stripping
" L" / " R" from a title. Per session-day and per side, the value is the best e1RM across that side's
templates, with the template that produced it.

A session-day on which a side's template has sets but none scores is reported, with the reason, as
`ineligible` rather than silently dropped: "not logged" (absent) and "logged but no usable e1RM" are
different facts about the log.

No label, no band and no threshold is produced here: a left/right index is a ratio and the lower side.
"""
from __future__ import annotations

from datetime import date
from typing import Any, NamedTuple

from sqlalchemy.orm import Session

import models
from reads import strength_reads
from . import observations as observations_mod
from . import taxonomy
from .taxonomy import SIDE_BILATERAL, SIDE_LEFT, SIDE_RIGHT

# The rep ceiling for the per-region route (i) read (`/engine/log-strength`). Same literal a `Ratio`
# defaults to (`taxonomy.DEFAULT_LOG_REP_CEILING`); not the See-test cap (`strength_reads.EPLEY_REP_CAP`).
LOG_REP_CEILING = taxonomy.DEFAULT_LOG_REP_CEILING


class SideReads(NamedTuple):
    """`series`: {side: [{day, e1rm_kg, top_set, template_id}]}, ascending by day - the scorable days.
    `ineligible`: {side: [{day, reason, template_id}]}, ascending by day - session-days where one of the
    side's templates has sets, none of the side's templates scored, and so the day is not in `series`.
    `reason` is one of `strength_reads.INELIGIBLE_REASONS`. A day with no sets for the side is in neither."""
    series: dict[str, list[dict[str, Any]]]
    ineligible: dict[str, list[dict[str, Any]]]


def _templates_by_side(db: Session, region_key: str) -> dict[str, str]:
    """{template_id: side} for the primary tags of `region_key` (NULL side -> bilateral)."""
    rows = (
        db.query(models.ExerciseRegionTag)
        .filter_by(region_key=region_key, role="primary")
        .all()
    )
    return {r.hevy_exercise_template_id: (r.side or SIDE_BILATERAL) for r in rows}


def e1rm_by_side(
    db: Session, user_id: int, region_key: str, *, rep_cap: int, since: date | None = None,
) -> SideReads:
    """The scorable e1RM series per side, and the days that had sets but no usable e1RM.

    `rep_cap` is REQUIRED with no default: a caller must say which rule it applies (a ratio passes its
    `log_rep_ceiling`; the See-test's 10 is not this path's). A session-day appears in `series` for a
    side only if one of that side's templates has a scorable set: an e1RM that is not None and above
    zero (a 0 kg set, e.g. an exposure logged unloaded, is not a strength reading). A template-day with
    sets and no scorable one is listed in `ineligible` with its reason - unless another template of the
    same side scored that day, in which case the day is scored and nothing is missing."""
    sides = _templates_by_side(db, region_key)
    if not sides:
        return SideReads({}, {})
    by_template = strength_reads.session_days_by_template(db, user_id, since or date.min)

    best: dict[str, dict[date, dict[str, Any]]] = {}
    refused: dict[str, dict[date, list[dict[str, Any]]]] = {}
    for tid, side in sides.items():
        for day, raw_sets in (by_template.get(tid) or {}).items():
            if not raw_sets:
                continue          # a block with no sets is "not logged", not "ineligible"
            agg = strength_reads.aggregate_session(raw_sets, rep_cap=rep_cap)
            e1rm = agg["e1rm_kg"] if agg is not None else None
            if e1rm is None or e1rm <= 0:
                refused.setdefault(side, {}).setdefault(day, []).append({
                    "day": day,
                    "reason": strength_reads.ineligible_reason(raw_sets, rep_cap=rep_cap),
                    "template_id": tid,
                })
                continue
            cur = best.setdefault(side, {}).get(day)
            if cur is None or e1rm > cur["e1rm_kg"]:
                best[side][day] = {
                    "day": day, "e1rm_kg": e1rm, "top_set": agg["top_set"],
                    "template_id": tid,
                }
    series = {side: [days[d] for d in sorted(days)] for side, days in best.items()}
    ineligible = {}
    for side, days in refused.items():
        rows = [e for d in sorted(days) if d not in best.get(side, {})
                for e in sorted(days[d], key=lambda x: x["template_id"])]
        if rows:
            ineligible[side] = rows
    return SideReads(series, ineligible)


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
    reads = e1rm_by_side(db, user_id, region_key, rep_cap=LOG_REP_CEILING, since=since)
    return {
        "region_key": region_key,
        "rep_ceiling": LOG_REP_CEILING,
        "source": f"hevy log (Epley e1RM, working sets, reps 1-{LOG_REP_CEILING})",
        "sides": {s: [point_as_dict(p) for p in pts] for s, pts in reads.series.items()},
        "symmetry": [{**r, "day": str(r["day"])} for r in symmetry_by_day(reads.series)],
        "ineligible": {s: [point_as_dict(e) for e in rows] for s, rows in reads.ineligible.items()},
    }
