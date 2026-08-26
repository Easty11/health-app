"""Bodyweight-template worklist — the tagging surface for `bw_fraction` (DECISIONS_LOG #245).

READ-ONLY. Never writes (no db.add, no db.commit). Emits the operator's tagging surface:
every IN-USE Hevy exercise template that has ever logged a **rep-based set with weight_kg
NULL or 0**, with its usage count. Those are the only templates whose `bw_fraction` matters —
the transform prices a 0/NULL-weight rep set at `BODYWEIGHT_KG × COALESCE(bw_fraction, 1.0)`,
so an untagged (NULL) bodyweight movement silently scores at full bodyweight (×1.0). Anything
that always logs a real `weight_kg > 0` is priced on that load and needs no tag.

Usage-JOINED, mirroring `audit_laterality_coverage`: a template id can appear in `hevy_sets`
while absent from `hevy_exercise_templates` (a Hevy default never pulled into the catalogue,
#79/#81). The LEFT join surfaces both:
  * catalogued   — id IS in the catalogue; shows its current `bw_fraction` (None = untagged).
  * uncatalogued — id used in `hevy_sets` but absent from the catalogue; cannot be tagged
                   until the template is synced.
Keyed on `exercise_template_id`, NEVER title (#79). Non-rep sets (distance/duration, no reps)
are excluded — those already score zero at Tier 0 (D-D) and carry no bw_fraction.

    python backend/audit_bodyweight_templates.py [--user N] [--strict]

Exit 0 by default (diagnostic). `--strict` exits 1 when any in-use bodyweight movement is
untagged or uncatalogued, so this can gate the recompute later.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)


@dataclass
class Row:
    template_id: str
    title: str | None          # None → uncatalogued
    bw_fraction: float | None
    bodyweight_sets: int        # rep-based sets with weight_kg NULL or 0
    catalogued: bool

    @property
    def needs_tag(self) -> bool:
        # An in-use bodyweight movement needs a tag when it is uncatalogued, or catalogued
        # but still NULL (scoring at full ×1.0 bodyweight by default).
        return (not self.catalogued) or self.bw_fraction is None


def audit(db: Session, *, only_user_id: int | None = None) -> list[Row]:
    """One Row per template that has logged a 0/NULL-weight rep-based set, count desc."""
    Set_, WO, T = models.HevySet, models.HevyWorkout, models.HevyExerciseTemplate
    q = (
        select(
            Set_.exercise_template_id,
            T.title,
            T.bw_fraction,
            func.count().label("n"),
        )
        .join(WO, Set_.workout_id == WO.hevy_id)
        .join(T, T.id == Set_.exercise_template_id, isouter=True)   # LEFT: keep uncatalogued
        .where(
            Set_.reps.isnot(None),
            or_(Set_.weight_kg.is_(None), Set_.weight_kg == 0),
            WO.excluded_at.is_(None),                               # exclude adjudicated-out (D-G)
        )
        .group_by(Set_.exercise_template_id, T.title, T.bw_fraction)
        .order_by(func.count().desc())
    )
    if only_user_id is not None:
        q = q.where(WO.user_id == only_user_id)

    return [
        Row(template_id=r.exercise_template_id, title=r.title, bw_fraction=r.bw_fraction,
            bodyweight_sets=int(r.n), catalogued=r.title is not None)
        for r in db.execute(q).all()
    ]


def format_report(rows: list[Row]) -> str:
    if not rows:
        return "No in-use templates log a 0/NULL-weight rep-based set — nothing to tag."
    lines = [f"{len(rows)} in-use template(s) with 0/NULL-weight rep sets "
             f"({sum(r.needs_tag for r in rows)} need a bw_fraction tag):", ""]
    for r in rows:
        if not r.catalogued:
            tag = "UNCATALOGUED (sync template first)"
        elif r.bw_fraction is None:
            tag = "UNTAGGED (bw_fraction NULL → ×1.0)"
        else:
            tag = f"tagged {r.bw_fraction}"
        lines.append(f"  {r.bodyweight_sets:>5} sets  {(r.title or r.template_id):<40} [{tag}]  id={r.template_id}")
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Bodyweight-template tagging worklist (#245).")
    parser.add_argument("--user", type=int, default=None, help="only this user id")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any movement needs a tag")
    args = parser.parse_args()

    from database import SessionLocal

    _db = SessionLocal()
    try:
        _rows = audit(_db, only_user_id=args.user)
        print(format_report(_rows))
        if args.strict and any(r.needs_tag for r in _rows):
            sys.exit(1)
    finally:
        _db.close()
