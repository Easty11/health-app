"""Usage-joined laterality-coverage audit (DECISIONS_LOG #74/#76/#79; brief step 3).

READ-ONLY. Never writes: no db.add, no db.commit. It measures which IN-USE Hevy
exercise templates still lack a `laterality` tag, and emits the worklist.

Why usage-JOINED, and why it closes a hole the template-only audit could not see:
the laterality tag is load-bearing for the D-E session pairing rule (a unilateral
movement logs as two sided blocks and must be halved at system level). The
existing coverage question — "which templates are untagged?" — was answered over
the template CATALOGUE alone. But a template can be logged in `hevy_sets` while
being absent from `hevy_exercise_templates` entirely (a Hevy DEFAULT that was
never pulled into this user's catalogue, or a logged id that drifted). Those ids
are invisible to a catalogue scan yet fully present in the load path — the
"default-template hole" found 2026-08-25. Joining the AUDIT to actual usage in
`hevy_sets` surfaces both failure modes:

  * untagged   — id IS in the catalogue, `laterality IS NULL` (e.g. Kneeling Leg
                 Curl, a known member).
  * uncatalogued — id is used in `hevy_sets` but absent from the catalogue; its
                 laterality cannot even be asked until the template is synced.

Duplicate custom templates (same title, two ids) are reported as SEPARATE rows —
D-E/#76: tag both copies, never merge. Keyed on `exercise_template_id`, NEVER
title (#79).

    python backend/audit_laterality_coverage.py [--user N] [--strict]

Exit 0 by default (diagnostic). `--strict` exits 1 when any in-use movement is
untagged or uncatalogued, so this can gate a pipeline later.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LateralityGap:
    """One in-use template that needs a laterality tag."""
    exercise_template_id: str
    title: str | None          # catalogue title, or None when uncatalogued
    reason: str                # "untagged" | "uncatalogued"
    set_count: int             # how many persisted sets reference this id
    workout_count: int         # how many distinct workouts reference this id


def audit_laterality_coverage(
    db: Session, *, user_id: int | None = None
) -> list[LateralityGap]:
    """The worklist: every distinct in-use `exercise_template_id` whose laterality is
    unresolved. Sorted by descending usage (most-logged gaps first), then id.

    "In use" = referenced by a row in `hevy_sets`. When `user_id` is given, scope to
    that user's workouts (join through `hevy_workouts`); otherwise all users. A
    template is a gap when it is absent from `hevy_exercise_templates` (uncatalogued)
    or present with `laterality IS NULL` (untagged). A template present WITH a
    laterality is resolved and never listed.
    """
    Set = models.HevySet
    Tmpl = models.HevyExerciseTemplate

    stmt = (
        select(
            Set.exercise_template_id,
            func.count(Set.id).label("set_count"),
            func.count(func.distinct(Set.workout_id)).label("workout_count"),
        )
        .group_by(Set.exercise_template_id)
    )
    if user_id is not None:
        Workout = models.HevyWorkout
        stmt = stmt.join(Workout, Set.workout_id == Workout.hevy_id).where(
            Workout.user_id == user_id
        )

    usage = db.execute(stmt).all()

    # Catalogue lookup: id -> (present?, laterality). One query, no per-id round trip.
    catalogue = {
        row.id: row.laterality
        for row in db.execute(select(Tmpl.id, Tmpl.laterality, Tmpl.title)).all()
    }
    titles = {
        row.id: row.title
        for row in db.execute(select(Tmpl.id, Tmpl.title)).all()
    }

    gaps: list[LateralityGap] = []
    for row in usage:
        tid = row.exercise_template_id
        if tid not in catalogue:
            reason = "uncatalogued"
        elif catalogue[tid] is None:
            reason = "untagged"
        else:
            continue  # resolved — has a laterality
        gaps.append(
            LateralityGap(
                exercise_template_id=tid,
                title=titles.get(tid),
                reason=reason,
                set_count=int(row.set_count),
                workout_count=int(row.workout_count),
            )
        )

    gaps.sort(key=lambda g: (-g.set_count, g.exercise_template_id))
    return gaps


def format_worklist(gaps: list[LateralityGap]) -> str:
    if not gaps:
        return "Laterality coverage: COMPLETE — every in-use template is tagged."
    lines = [
        f"Laterality worklist — {len(gaps)} in-use template(s) need a tag:",
        "",
        f"{'sets':>5}  {'wkts':>4}  {'reason':<12}  id / title",
    ]
    for g in gaps:
        title = g.title if g.title is not None else "(absent from catalogue)"
        lines.append(
            f"{g.set_count:>5}  {g.workout_count:>4}  {g.reason:<12}  {g.exercise_template_id}  {title}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", type=int, default=None, help="scope to one user id")
    parser.add_argument(
        "--strict", action="store_true",
        help="exit 1 if any in-use movement is untagged/uncatalogued",
    )
    args = parser.parse_args(argv)

    from database import SessionLocal

    db = SessionLocal()
    try:
        gaps = audit_laterality_coverage(db, user_id=args.user)
    finally:
        db.close()

    print(format_worklist(gaps))
    return 1 if (args.strict and gaps) else 0


if __name__ == "__main__":
    sys.exit(main())
