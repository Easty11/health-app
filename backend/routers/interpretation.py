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
import os
from datetime import date

import anthropic
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db
from interpretation.presentation import presentation_hash, render_base_text, serialize
from interpretation.producer import build_foundation
from interpretation.rephrase import generate_plain

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


def _resolve_payload(db: Session, user: models.User) -> dict:
    """The interpretation payload for a user's newest draw vs the previous one.

    404 when the user has no lab reports at all — an empty interpretation would be
    indistinguishable from a broken one, and the view has nothing to render either way.
    A user with exactly ONE draw is NOT an error: `prior_panel=None` is the first-ever-panel
    case the producer already handles."""
    dates = [
        row[0]
        for row in db.query(models.LabReport.collected_date)
        .filter(models.LabReport.user_id == user.id)                  # #42
        .distinct()
        .order_by(models.LabReport.collected_date.desc())
        .all()
    ]
    if not dates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No lab reports have been confirmed for this user yet.",
        )
    trigger = _panel_for(db, user.id, dates[0])
    prior = _panel_for(db, user.id, dates[1]) if len(dates) > 1 else None
    return build_foundation(user.id, db, trigger_panel=trigger, prior_panel=prior)


@router.get("")
def get_interpretation(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The structured interpretation of the user's newest draw. The record (#202 clause 2)."""
    return _resolve_payload(db, current_user)


def _plain_row(db: Session, payload_hash: str) -> models.InterpretationRephrase | None:
    return (
        db.query(models.InterpretationRephrase)
        .filter_by(payload_hash=payload_hash, register="plain")
        .first()
    )


@router.get("/presentation")
def get_presentation(
    register: str = "clinical",
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The rendered presentation for a register (#202, increment 2).

    `register=clinical` (default) returns the deterministic base text — the record's render,
    always available. `register=plain` returns the promoted plain-language overlay IF one
    has been human-verified for this exact base text; otherwise it serves the clinical
    template (the eligibility gate is unconditional and server-side — the toggle is a
    preference, the server decides) and returns the pending `ai_draft` for review.

    Fail-closed throughout (#202 clause 4): a missing `ANTHROPIC_API_KEY`, a model error, or
    a validator rejection all resolve to the template. No draft is stored unless the generator
    actually produced a validated rephrase.
    """
    payload = _resolve_payload(db, current_user)
    fragments = serialize(payload)
    base_text = render_base_text(fragments)
    payload_hash = presentation_hash(fragments)

    if register != "plain":
        return {"register_requested": register, "register_served": "clinical",
                "payload_hash": payload_hash, "text": base_text, "draft": None}

    row = _plain_row(db, payload_hash)
    if row is not None and row.status == "human_verified":
        return {"register_requested": "plain", "register_served": "plain",
                "payload_hash": payload_hash, "text": row.text,
                "draft": {"id": row.id, "status": row.status}}

    # Un-promoted: generate an ai_draft once (cache miss only), then serve the template.
    if row is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        client = anthropic.Anthropic(api_key=api_key) if api_key else None
        generated = generate_plain(fragments, client=client)
        if generated["any_rephrased"]:  # nothing worth caching if it all fell back to template
            row = models.InterpretationRephrase(
                payload_hash=payload_hash, register="plain",
                text=generated["text"], status="ai_draft",
            )
            db.add(row)
            try:
                db.commit()
                db.refresh(row)
            except IntegrityError:      # concurrent generation won the unique key — read it back
                db.rollback()
                row = _plain_row(db, payload_hash)

    draft = ({"id": row.id, "status": row.status, "text": row.text} if row else None)
    return {"register_requested": "plain", "register_served": "clinical",
            "payload_hash": payload_hash, "text": base_text, "draft": draft}


@router.post("/presentation/{rephrase_id}/promote")
def promote_presentation(
    rephrase_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Promote an `ai_draft` plain rephrase to `human_verified` — the training-wheels gate
    (#202 step 6, reusing the #194 promotion vocabulary). After this, `register=plain`
    requests for the same base text serve the overlay instead of the template."""
    row = db.query(models.InterpretationRephrase).filter_by(id=rephrase_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such rephrase.")
    row.status = "human_verified"
    db.commit()
    db.refresh(row)
    return {"id": row.id, "status": row.status, "payload_hash": row.payload_hash}
