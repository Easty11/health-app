"""Appointments (#345) — read routes for the appointment brief.

The appointment row itself is written through `POST /knowledge/entry` (`type="appointment"`,
validated in `upsert_knowledge_entry`); these routes only read. The brief is assembled by
`appointment_brief.load_appointment_brief` — the same function the MCP tool calls.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import appointment_brief
import models
from auth import get_current_user
from database import get_db
from routers.knowledge import APPOINTMENT_STATUS_VALUES

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("")
def list_appointments(
    status_filter: str | None = Query(None, alias="status"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Active appointments, soonest first; `?status=planned` is the hub doorway's read."""
    if status_filter is not None and status_filter not in APPOINTMENT_STATUS_VALUES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"status must be one of: {', '.join(APPOINTMENT_STATUS_VALUES)}",
        )
    return appointment_brief.list_appointments(db, current_user.id, status_filter)


@router.get("/{key}/brief")
def get_appointment_brief(
    key: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The assembled brief for one active appointment (JSON). Derived on read, never stored."""
    brief = appointment_brief.load_appointment_brief(db, current_user.id, key)
    if brief is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    return brief
