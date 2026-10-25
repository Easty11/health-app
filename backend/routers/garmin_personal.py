"""Garmin Personal API integration routes (S1) -- the official lane.

  POST   /integrations/garmin-personal/key     -> verify + store the key (Fernet-encrypted) with the expiry date
                                                   the operator read off the key's creation
  GET    /integrations/garmin-personal/status  -> {connected, key_expires_on, days_to_expiry, lanes}
  DELETE /integrations/garmin-personal         -> disconnect (drop the key and its cached token)

The key is only ever in the request body (never a query string, never logged). The same-account guard is
`garmin_personal_lanes.attach_key`: 409 when the Garmin account is connected to a DIFFERENT user (either
provider), 409 (distinct message) when it differs from this user's own DI connection, 503 FAIL CLOSED when
the account cannot be resolved, 424 when Garmin refuses the key. Garmin emails the key's owner before it
expires, not the operator, so `days_to_expiry` here (and on the freshness card) is the operator's warning.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import garmin_personal_lanes as gpl
import models
from auth import get_current_user
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/garmin-personal", tags=["garmin"])

_CODE_TO_HTTP = {
    "empty_key": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "bad_expiry": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "refused": status.HTTP_424_FAILED_DEPENDENCY,
    "unverified": status.HTTP_503_SERVICE_UNAVAILABLE,
    "conflict": status.HTTP_409_CONFLICT,
    "own_mismatch": status.HTTP_409_CONFLICT,
}


class GarminPersonalKeyIn(BaseModel):
    api_key: str
    key_expires_on: date


def _today() -> date:
    return datetime.now(timezone.utc).date()


@router.post("/key", status_code=status.HTTP_201_CREATED)
def connect_garmin_personal_key(
    body: GarminPersonalKeyIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        out = gpl.attach_key(db, current_user.id, body.api_key, body.key_expires_on, today=_today())
    except gpl.AttachError as exc:
        raise HTTPException(status_code=_CODE_TO_HTTP[exc.code], detail=str(exc))
    return {"detail": "Garmin Personal API key saved", **out}


@router.get("/status")
def garmin_personal_status(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = gpl.get_row(db, current_user.id)
    lanes = {
        r.lane: {"outcome": r.outcome, "last_attempt_at": r.last_attempt_at.isoformat(),
                 "last_success_at": r.last_success_at.isoformat() if r.last_success_at else None,
                 "reason": r.reason}
        for r in db.query(models.IntegrationLaneStatus).filter_by(user_id=current_user.id).all()
    }
    if row is None:
        return {"connected": False, "key_expires_on": None, "days_to_expiry": None, "lanes": lanes}
    exp = row.key_expires_on
    return {"connected": True, "key_expires_on": exp.isoformat() if exp else None,
            "days_to_expiry": (exp - _today()).days if exp else None, "lanes": lanes}


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_garmin_personal(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = gpl.get_row(db, current_user.id)
    if row:
        db.delete(row)
        db.commit()
