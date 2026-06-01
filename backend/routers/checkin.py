from datetime import date, timedelta
from typing import Optional

import pytz
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/checkin", tags=["checkin"])

AEST = pytz.timezone("Australia/Brisbane")


def _today_aest() -> date:
    import datetime as dt
    return dt.datetime.now(AEST).date()


# ---------- schemas ----------

class CheckInIn(BaseModel):
    sleep_quality: int = Field(..., ge=1, le=10)
    fatigue: int = Field(..., ge=1, le=10)
    shoulder_pain: int = Field(..., ge=0, le=10)
    motivation: int = Field(..., ge=1, le=10)
    rugby_session_yesterday: bool = False
    notes: Optional[str] = None


class CheckInOut(BaseModel):
    id: int
    date: date
    sleep_quality: int
    fatigue: int
    shoulder_pain: int
    motivation: int
    rugby_session_yesterday: bool
    notes: Optional[str]

    model_config = {"from_attributes": True}


# ---------- endpoints ----------

@router.post("", response_model=CheckInOut, status_code=status.HTTP_201_CREATED)
def submit_checkin(
    body: CheckInIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = _today_aest()

    # Upsert — if already checked in today, update it
    existing = (
        db.query(models.DailyCheckIn)
        .filter_by(user_id=current_user.id, date=today)
        .first()
    )
    if existing:
        for field, value in body.model_dump().items():
            setattr(existing, field, value)
        db.commit()
        db.refresh(existing)
        return existing

    checkin = models.DailyCheckIn(
        user_id=current_user.id,
        date=today,
        **body.model_dump(),
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)
    return checkin


@router.get("/today", response_model=Optional[CheckInOut])
def get_today_checkin(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = _today_aest()
    return (
        db.query(models.DailyCheckIn)
        .filter_by(user_id=current_user.id, date=today)
        .first()
    )


@router.get("/history", response_model=list[CheckInOut])
def get_checkin_history(
    days: int = 14,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = _today_aest()
    since = today - timedelta(days=days)
    return (
        db.query(models.DailyCheckIn)
        .filter(
            models.DailyCheckIn.user_id == current_user.id,
            models.DailyCheckIn.date >= since,
        )
        .order_by(models.DailyCheckIn.date.desc())
        .all()
    )
