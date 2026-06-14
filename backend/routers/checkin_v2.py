"""
Two-moment daily record system (AM check-in + nightly close-out).
Replaces DailyCheckIn as primary capture surface.
DailyCheckIn is retained for backward-compat with existing routes.

naive_baseline is the old formula frozen at AM capture time:
  sleep_quality (1-5) → ×2 → 2-10
  shoulder soreness (1-5) → (v-1)×2.5 → 0-10
  fatigue (0-10) and motivation (0-10) pass through unchanged.
  formula: sleep×0.3 + (10-fatigue)×0.3 + (10-shoulder)×0.2 + motivation×0.2
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import pytz
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/checkin-v2", tags=["checkin-v2"])

AEST = pytz.timezone("Australia/Brisbane")


def _today_aest() -> date:
    return datetime.now(AEST).date()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── naive baseline ─────────────────────────────────────────────────────────────

def calc_naive_baseline(
    sleep_quality: int,
    fatigue: int,
    soreness: dict[str, Any] | None,
    motivation: int,
) -> float:
    sleep_s = sleep_quality * 2                          # 1-5 → 2-10
    shoulder_raw = (soreness or {}).get("shoulder", 3)
    shoulder_s = (shoulder_raw - 1) * 2.5               # 1-5 → 0-10
    raw = (
        sleep_s * 0.30
        + (10 - fatigue) * 0.30
        + (10 - shoulder_s) * 0.20
        + motivation * 0.20
    )
    return round(max(1.0, min(10.0, raw)), 2)


# ── passive snapshot ──────────────────────────────────────────────────────────

def _snapshot_passive(user_id: int, for_date: date, db: Session) -> dict[str, Any]:
    """Latest Samsung HRV and HC sleep at the moment of AM capture."""
    hrv_row = (
        db.query(models.SamsungHRVReading)
        .filter(
            models.SamsungHRVReading.user_id == user_id,
            models.SamsungHRVReading.captured_at <= for_date,
        )
        .order_by(models.SamsungHRVReading.captured_at.desc())
        .first()
    )
    hc_row = (
        db.query(models.HealthConnectSync)
        .filter(
            models.HealthConnectSync.user_id == user_id,
            models.HealthConnectSync.date <= for_date,
        )
        .order_by(models.HealthConnectSync.date.desc())
        .first()
    )
    return {
        "passive_hrv_ms": hrv_row.hrv_ms if hrv_row else None,
        "passive_sleep_min": hc_row.sleep_duration_minutes if hc_row else None,
    }


# ── schemas ────────────────────────────────────────────────────────────────────

class AMCheckInIn(BaseModel):
    morning_readiness: int = Field(..., ge=1, le=5)
    sleep_quality: int = Field(..., ge=1, le=5)
    fatigue: int = Field(..., ge=0, le=10)
    soreness: dict[str, int] = Field(default_factory=dict)   # {"shoulder": 2, ...}
    motivation: int = Field(..., ge=0, le=10)
    life_load: int = Field(..., ge=1, le=5)
    drank_last_night: bool = False
    alcohol_units: Optional[int] = None
    alcohol_finish_time: Optional[str] = None   # "22:30"


class NightlyCloseOutIn(BaseModel):
    today_rating: int = Field(..., ge=1, le=5)
    trained_today: bool = False
    session_quality: Optional[int] = Field(None, ge=1, le=5)
    session_rpe: Optional[float] = Field(None, ge=0, le=10)


class DailyRecordOut(BaseModel):
    id: int
    date: date
    am_timestamp: Optional[datetime] = None
    morning_readiness: Optional[int] = None
    sleep_quality: Optional[int] = None
    fatigue: Optional[int] = None
    soreness: Optional[dict] = None
    motivation: Optional[int] = None
    life_load: Optional[int] = None
    alcohol_units: Optional[int] = None
    alcohol_finish_time: Optional[str] = None
    pm_timestamp: Optional[datetime] = None
    today_rating: Optional[int] = None
    session_quality: Optional[int] = None
    session_rpe: Optional[float] = None
    mindfulness_occurred: Optional[bool] = None
    mindfulness_duration_min: Optional[int] = None
    naive_baseline: Optional[float] = None
    model_forecast: Optional[float] = None
    model_confidence: Optional[float] = None
    passive_hrv_ms: Optional[float] = None
    passive_sleep_min: Optional[int] = None

    model_config = {"from_attributes": True}


class AMPrefillOut(BaseModel):
    hrv_ms: Optional[float] = None
    hrv_vs_baseline: Optional[float] = None
    sleep_min: Optional[int] = None
    morning_readiness: int = 3
    sleep_quality: int = 3
    fatigue: int = 5
    soreness: dict = Field(default_factory=lambda: {"shoulder": 2, "hamstring": 1})
    motivation: int = 5
    life_load: int = 3
    # Today's record if it already exists (allows re-entry pre-PM)
    existing: Optional[DailyRecordOut] = None


# ── helper ─────────────────────────────────────────────────────────────────────

def _get_or_create(user_id: int, for_date: date, db: Session) -> models.DailyRecord:
    record = db.query(models.DailyRecord).filter_by(user_id=user_id, date=for_date).first()
    if not record:
        record = models.DailyRecord(user_id=user_id, date=for_date)
        db.add(record)
        db.flush()
    return record


# ── endpoints ──────────────────────────────────────────────────────────────────

@router.get("/prefill", response_model=AMPrefillOut)
def get_prefill(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = _today_aest()
    existing = db.query(models.DailyRecord).filter_by(user_id=current_user.id, date=today).first()
    passive = _snapshot_passive(current_user.id, today, db)

    hrv_ms = passive["passive_hrv_ms"]
    hrv_baseline_rows = (
        db.query(models.SamsungHRVReading)
        .filter(
            models.SamsungHRVReading.user_id == current_user.id,
            models.SamsungHRVReading.captured_at <= today,
        )
        .order_by(models.SamsungHRVReading.captured_at.desc())
        .limit(7)
        .all()
    )
    hrv_values = [r.hrv_ms for r in hrv_baseline_rows if r.hrv_ms is not None]
    baseline = sum(hrv_values) / len(hrv_values) if hrv_values else None
    vs_baseline = round(hrv_ms - baseline, 1) if (hrv_ms and baseline) else None

    return AMPrefillOut(
        hrv_ms=hrv_ms,
        hrv_vs_baseline=vs_baseline,
        sleep_min=passive["passive_sleep_min"],
        existing=existing,
    )


@router.post("/am", response_model=DailyRecordOut)
def submit_am(
    body: AMCheckInIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = _today_aest()
    record = _get_or_create(current_user.id, today, db)

    record.am_timestamp = _now_utc()
    record.morning_readiness = body.morning_readiness
    record.sleep_quality = body.sleep_quality
    record.fatigue = body.fatigue
    record.soreness = body.soreness
    record.motivation = body.motivation
    record.life_load = body.life_load
    record.alcohol_units = body.alcohol_units if body.drank_last_night else None
    record.alcohol_finish_time = body.alcohol_finish_time if body.drank_last_night else None

    # Freeze naive_baseline and passive refs at this moment — never recomputed
    record.naive_baseline = calc_naive_baseline(
        body.sleep_quality, body.fatigue, body.soreness, body.motivation
    )
    passive = _snapshot_passive(current_user.id, today, db)
    record.passive_hrv_ms = passive["passive_hrv_ms"]
    record.passive_sleep_min = passive["passive_sleep_min"]

    db.commit()
    db.refresh(record)
    return record


@router.post("/pm", response_model=DailyRecordOut)
def submit_pm(
    body: NightlyCloseOutIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = _today_aest()
    record = _get_or_create(current_user.id, today, db)

    record.pm_timestamp = _now_utc()
    record.today_rating = body.today_rating
    record.session_quality = body.session_quality if body.trained_today else None
    record.session_rpe = body.session_rpe if body.trained_today else None

    db.commit()
    db.refresh(record)
    return record


@router.get("/today", response_model=Optional[DailyRecordOut])
def get_today(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(models.DailyRecord).filter_by(
        user_id=current_user.id, date=_today_aest()
    ).first()


@router.get("/history", response_model=list[DailyRecordOut])
def get_history(
    days: int = 14,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = _today_aest()
    since = today - timedelta(days=days)
    return (
        db.query(models.DailyRecord)
        .filter(
            models.DailyRecord.user_id == current_user.id,
            models.DailyRecord.date >= since,
        )
        .order_by(models.DailyRecord.date.desc())
        .all()
    )
