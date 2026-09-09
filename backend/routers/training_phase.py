"""Training-phase ledger API (Q112, #270) — the exposure engine's DOING-NOW axis.

Endpoints (mounted at /engine/phase):
  POST /engine/phase          — open a phase (closes the current open row in one txn)
  POST /engine/phase/close    — close the current open phase to zero-open baseline
  GET  /engine/phase          — the current open phase | null, with review_due
  GET  /engine/phase/history  — every phase for the user, newest first

Write paths are fail-closed (422 on shape, 404 on close-with-nothing-open). The ledger is
append-only: the only mutation any of these performs is setting `closed_on` / `close_reason`
at closure. Selection reads the open phase in `/engine/next` (see `routers/engine.py`); this
router owns authorship and history.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db
from engine import training_phase as phase_mod

router = APIRouter(prefix="/engine/phase", tags=["engine"])


class PhaseIn(BaseModel):
    """The STORE fields minus id/closed_on/close_reason/created_at/updated_at, plus the
    optional `close_prior_reason` control. `source` and `asserted_by` are mandatory with no
    defaults (#227/#230); `entered_on` defaults to the operator-local day when omitted."""
    label: str
    intent: str | None = None
    probe_posture: str
    capacities: list[str] | None = None
    microcycle: dict[str, Any] | None = None
    entered_on: str | None = None
    review_on: str | None = None
    asserted_by: str
    asserted_on: str
    source: str
    # Closing note for the phase this open supersedes; default "opened <label>".
    close_prior_reason: str | None = None


class CloseIn(BaseModel):
    close_reason: str


@router.post("", status_code=status.HTTP_201_CREATED)
def open_phase(
    body: PhaseIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        phase = phase_mod.open_phase(
            db, current_user.id, body.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return {"training_phase": phase_mod.phase_to_dict(phase)}


@router.post("/close")
def close_phase(
    body: CloseIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        phase = phase_mod.close_phase(db, current_user.id, body.close_reason)
    except phase_mod.NoOpenPhase as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return {"training_phase": phase_mod.phase_to_dict(phase)}


@router.get("")
def get_current_phase(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    phase = phase_mod.current_training_phase(db, current_user.id)
    return {"training_phase": phase_mod.phase_to_dict(phase)}


@router.get("/history")
def get_phase_history(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.TrainingPhase)
        .filter_by(user_id=current_user.id)
        .order_by(
            models.TrainingPhase.entered_on.desc(),
            models.TrainingPhase.id.desc(),
        )
        .all()
    )
    return {"history": [phase_mod.phase_to_dict(r) for r in rows]}
