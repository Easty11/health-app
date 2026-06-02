"""
Receives Health Connect data from the companion Android app and stores
it in health_connect_syncs — one row per user per date (upsert).
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/health-connect", tags=["health-connect"])

SLEEP_STAGE_DEEP  = 4   # Health Connect SleepStageType constants
SLEEP_STAGE_REM   = 5
SLEEP_STAGE_LIGHT = 2


# ---------- incoming payload schemas ----------

class SleepStage(BaseModel):
    stage: int          # Health Connect SleepStageType int
    startTime: str
    endTime: str


class SleepSession(BaseModel):
    startTime: str
    endTime: str
    durationMinutes: int
    stages: list[SleepStage] = []


class HRVReading(BaseModel):
    time: str
    hrv: float


class HeartRateReading(BaseModel):
    time: str
    bpm: Optional[int] = None


class StepsRecord(BaseModel):
    startTime: str
    endTime: str
    count: int


class WorkoutRecord(BaseModel):
    startTime: str
    endTime: str
    exerciseType: Optional[int] = None
    title: Optional[str] = None
    durationMinutes: int


class SyncPayload(BaseModel):
    syncedAt: str
    periodDays: int = 7
    sleep: list[SleepSession] = []
    hrv: list[HRVReading] = []
    heartRate: list[HeartRateReading] = []
    steps: list[StepsRecord] = []
    workouts: list[WorkoutRecord] = []
    errors: list[str] = []


# ---------- output schemas ----------

class HCSyncOut(BaseModel):
    id: int
    date: date
    synced_at: datetime
    steps: Optional[int]
    resting_heart_rate: Optional[float]
    hrv_rmssd: Optional[float]
    sleep_duration_minutes: Optional[int]
    sleep_score: Optional[int]
    deep_sleep_minutes: Optional[int]
    rem_sleep_minutes: Optional[int]
    light_sleep_minutes: Optional[int]
    active_calories: Optional[int]
    distance_meters: Optional[int]
    oxygen_saturation: Optional[float]
    respiratory_rate: Optional[float]

    model_config = {"from_attributes": True}


# ---------- helpers ----------

def _parse_date(iso: str) -> date:
    return datetime.fromisoformat(iso[:10]).date()


def _stage_minutes(stages: list[SleepStage], stage_type: int) -> int:
    total = 0
    for s in stages:
        if s.stage == stage_type:
            try:
                start = datetime.fromisoformat(s.startTime[:19])
                end = datetime.fromisoformat(s.endTime[:19])
                total += int((end - start).total_seconds() // 60)
            except (ValueError, AttributeError):
                pass
    return total


def _sleep_score(deep: int, rem: int, total: int) -> Optional[int]:
    """Simple 1-10 sleep score based on deep+REM proportion."""
    if total <= 0:
        return None
    quality_pct = (deep + rem) / total
    # Target: ≥35% deep+REM = 10, 0% = 1
    score = 1 + round(quality_pct / 0.35 * 9)
    return max(1, min(10, score))


def _aggregate_day(
    day: date,
    payload: SyncPayload,
) -> dict[str, Any]:
    """Aggregate all payload records for a given calendar date."""
    row: dict[str, Any] = {"date": day}

    # Steps — sum all records on this date
    day_steps = [r for r in payload.steps if _parse_date(r.startTime) == day]
    if day_steps:
        row["steps"] = sum(r.count for r in day_steps)

    # Heart rate — median bpm for the day
    day_hr = [r for r in payload.heartRate if _parse_date(r.time) == day and r.bpm]
    if day_hr:
        bpms = sorted(r.bpm for r in day_hr)
        row["resting_heart_rate"] = float(bpms[len(bpms) // 2])

    # HRV — average for the day
    day_hrv = [r for r in payload.hrv if _parse_date(r.time) == day]
    if day_hrv:
        row["hrv_rmssd"] = round(sum(r.hrv for r in day_hrv) / len(day_hrv), 1)

    # Sleep — longest session ending on this date (night before)
    day_sleep = [
        s for s in payload.sleep
        if _parse_date(s.endTime) == day or _parse_date(s.startTime) == day
    ]
    if day_sleep:
        best = max(day_sleep, key=lambda s: s.durationMinutes)
        deep = _stage_minutes(best.stages, SLEEP_STAGE_DEEP)
        rem = _stage_minutes(best.stages, SLEEP_STAGE_REM)
        light = _stage_minutes(best.stages, SLEEP_STAGE_LIGHT)
        total = best.durationMinutes
        row["sleep_duration_minutes"] = total
        row["deep_sleep_minutes"] = deep
        row["rem_sleep_minutes"] = rem
        row["light_sleep_minutes"] = light
        row["sleep_score"] = _sleep_score(deep, rem, total)

    return row


# ---------- endpoints ----------

@router.post("/sync", status_code=status.HTTP_200_OK)
def sync(
    payload: SyncPayload,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upsert one HealthConnectSync row per calendar date in the payload."""
    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=payload.periodDays)

    # Collect all unique dates in the payload
    dates: set[date] = set()
    for r in payload.steps:    dates.add(_parse_date(r.startTime))
    for r in payload.heartRate: dates.add(_parse_date(r.time))
    for r in payload.hrv:       dates.add(_parse_date(r.time))
    for r in payload.sleep:
        dates.add(_parse_date(r.endTime))
        dates.add(_parse_date(r.startTime))

    # Only persist dates within the reported period
    valid_dates = {d for d in dates if since <= d <= today}

    synced_dates = []
    for day in sorted(valid_dates):
        agg = _aggregate_day(day, payload)

        existing = (
            db.query(models.HealthConnectSync)
            .filter_by(user_id=current_user.id, date=day)
            .first()
        )
        if existing:
            for k, v in agg.items():
                if k != "date" and v is not None:
                    setattr(existing, k, v)
            existing.synced_at = datetime.now(timezone.utc)
        else:
            db.add(models.HealthConnectSync(
                user_id=current_user.id,
                synced_at=datetime.now(timezone.utc),
                **agg,
            ))
        synced_dates.append(str(day))

    db.commit()
    return {"synced": len(synced_dates), "dates": synced_dates}


@router.get("/latest", response_model=list[HCSyncOut])
def get_latest(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc).date() - timedelta(days=7)
    return (
        db.query(models.HealthConnectSync)
        .filter(
            models.HealthConnectSync.user_id == current_user.id,
            models.HealthConnectSync.date >= since,
        )
        .order_by(models.HealthConnectSync.date.desc())
        .all()
    )


@router.get("/status")
def get_status(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    latest = (
        db.query(models.HealthConnectSync)
        .filter_by(user_id=current_user.id)
        .order_by(models.HealthConnectSync.synced_at.desc())
        .first()
    )
    total = (
        db.query(models.HealthConnectSync)
        .filter_by(user_id=current_user.id)
        .count()
    )
    return {
        "last_sync": latest.synced_at.isoformat() if latest else None,
        "total_records": total,
    }
