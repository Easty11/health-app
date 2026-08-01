"""GET /interpretation — the lab-interpretation output for the authenticated user.

TRIGGER RESOLUTION IS A DRAW, NOT A REPORT (#147). One blood draw prints several reports sharing
a `collected_date`, so a single-report trigger is ambiguous — the 2026-05-30 draw alone produced
seven reports. The trigger is the newest `collected_date`; the comparison is the next DISTINCT
date back. `build_foundation` reads only panel identity (`collected_date`, `panel_name_raw`,
`overall_confidence`) off the row, so which report from the draw is passed does not change the
output beyond the panel label; it is pinned to the lowest id for determinism.

#42 — EVERY read is user-scoped, and the scoping is in three places, not one:
  * the trigger / prior panel queries below filter `LabReport.user_id == current_user.id`;
  * `marker_series` filters `LabReport.user_id` inside the read (`labs_reads.py`);
  * `current_state`, reached through `_protocol_context_snapshot`, filters `user_id` on
    `UserKnowledgeEntry`.
The endpoint never takes a user id from the request. `test_interpretation_endpoint.py` asserts
the isolation against a second seeded user rather than asserting the filters exist.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db
from interpretation.producer import build_foundation

router = APIRouter(prefix="/interpretation", tags=["interpretation"])


def _panel_for(db: Session, user_id: int, collected: date) -> models.LabReport:
    """Lowest-id report from a draw — a stable representative, not a meaningful choice."""
    return (
        db.query(models.LabReport)
        .filter(models.LabReport.user_id == user_id,                 # #42
                models.LabReport.collected_date == collected)
        .order_by(models.LabReport.id)
        .first()
    )


@router.get("")
def get_interpretation(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The interpretation of the user's newest draw, compared against the previous one.

    404 when the user has no lab reports at all — an empty interpretation would be
    indistinguishable from a broken one, and the view has nothing to render either way.

    A user with exactly ONE draw is NOT an error: `prior_panel=None` is the first-ever-panel
    case the producer already handles (`meta.first_ever_panel`), and every marker resolves
    `no_prior_first_observation`.
    """
    dates = [
        row[0]
        for row in db.query(models.LabReport.collected_date)
        .filter(models.LabReport.user_id == current_user.id)          # #42
        .distinct()
        .order_by(models.LabReport.collected_date.desc())
        .all()
    ]
    if not dates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No lab reports have been confirmed for this user yet.",
        )

    trigger = _panel_for(db, current_user.id, dates[0])
    prior = _panel_for(db, current_user.id, dates[1]) if len(dates) > 1 else None
    return build_foundation(current_user.id, db, trigger_panel=trigger, prior_panel=prior)
