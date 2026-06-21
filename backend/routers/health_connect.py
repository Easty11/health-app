"""
Receives Health Connect data from the companion Android app and stores
it in health_connect_syncs — one row per user per date (upsert).

Schemas are intentionally flexible to accept both the raw library shapes
and any field names used by the JS mapping layer.
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

# Health Connect SleepSessionRecord.StageType — official enum, confirmed on-device
# 2026-06-22 (SM-S921B); Samsung Health writes 1/4/5/6. See DECISIONS_LOG #20.
# Previously DEEP=4/REM=5/LIGHT=2, which mislabelled LIGHT as deep, DEEP as REM,
# dropped REM, and left light always 0 (stage 2 is never emitted).
SLEEP_STAGE_AWAKE = 1
SLEEP_STAGE_LIGHT = 4
SLEEP_STAGE_DEEP  = 5
SLEEP_STAGE_REM   = 6


# ---------- flexible incoming schemas ----------

class HeartRateRecord(BaseModel):
    time: str
    beatsPerMinute: Optional[int] = None   # raw library field
    bpm: Optional[int] = None               # mapped field

    def get_bpm(self) -> Optional[int]:
        return self.bpm or self.beatsPerMinute


class StepsRecord(BaseModel):
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    date: Optional[str] = None              # mapped field (date: r.startTime)
    count: int

    def get_start(self) -> Optional[str]:
        return self.startTime or self.date


class HRVRecord(BaseModel):
    time: str
    heartRateVariabilityMillis: Optional[float] = None  # raw library field
    rmssd: Optional[float] = None                        # mapped field

    def get_rmssd(self) -> Optional[float]:
        return self.rmssd or self.heartRateVariabilityMillis


class SleepStage(BaseModel):
    stage: int
    startTime: str
    endTime: str


class SleepSession(BaseModel):
    startTime: str
    endTime: str
    durationMinutes: Optional[int] = None
    stages: list[SleepStage] = []

    def duration(self) -> int:
        if self.durationMinutes is not None:
            return self.durationMinutes
        try:
            return int((
                datetime.fromisoformat(self.endTime[:19]) -
                datetime.fromisoformat(self.startTime[:19])
            ).total_seconds() // 60)
        except (ValueError, AttributeError):
            return 0


class ExerciseRecord(BaseModel):
    startTime: str
    endTime: str
    exerciseType: Optional[int] = None
    type: Optional[Any] = None              # mapped field (type: r.exerciseType)
    title: Optional[str] = None
    durationMinutes: Optional[int] = None


class OxygenSaturationRecord(BaseModel):
    time: str
    percentage: Optional[float] = None


class RespiratoryRateRecord(BaseModel):
    time: str
    rate: Optional[float] = None


class WeightRecord(BaseModel):
    time: str
    weight: Optional[dict] = None
    inKilograms: Optional[float] = None

    def get_kg(self) -> Optional[float]:
        if self.inKilograms is not None:
            return self.inKilograms
        if isinstance(self.weight, dict):
            return self.weight.get("inKilograms")
        return None


class DistanceRecord(BaseModel):
    startTime: str
    endTime: str
    distance: Optional[dict] = None
    inMeters: Optional[float] = None

    def get_meters(self) -> Optional[float]:
        if self.inMeters is not None:
            return self.inMeters
        if isinstance(self.distance, dict):
            return self.distance.get("inMeters")
        return None


class MindfulnessRecord(BaseModel):
    startTime: str
    endTime: str
    durationMinutes: Optional[int] = None

    def duration(self) -> int:
        if self.durationMinutes is not None:
            return self.durationMinutes
        try:
            return int((
                datetime.fromisoformat(self.endTime[:19]) -
                datetime.fromisoformat(self.startTime[:19])
            ).total_seconds() // 60)
        except (ValueError, AttributeError):
            return 0


class SyncPayload(BaseModel):
    syncedAt: Optional[str] = None
    periodDays: int = 7
    sleep: list[SleepSession] = []
    hrv: list[HRVRecord] = []
    heartRate: list[HeartRateRecord] = []
    steps: list[StepsRecord] = []
    workouts: list[ExerciseRecord] = []     # old field name
    exercise: list[ExerciseRecord] = []     # new field name
    oxygenSaturation: list[OxygenSaturationRecord] = []
    respiratoryRate: list[RespiratoryRateRecord] = []
    weight: list[WeightRecord] = []
    distance: list[DistanceRecord] = []
    mindfulness: list[MindfulnessRecord] = []
    errors: list[str] = []

    def all_exercises(self) -> list[ExerciseRecord]:
        return self.workouts + self.exercise


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
    if total <= 0:
        return None
    quality_pct = (deep + rem) / total
    score = 1 + round(quality_pct / 0.35 * 9)
    return max(1, min(10, score))


def _aggregate_day(day: date, payload: SyncPayload) -> dict[str, Any]:
    row: dict[str, Any] = {"date": day}

    # Steps — sum all records on this date (accept both startTime and date fields)
    day_steps = [
        r for r in payload.steps
        if r.get_start() and _parse_date(r.get_start()) == day
    ]
    if day_steps:
        row["steps"] = sum(r.count for r in day_steps)

    # Heart rate — median bpm for the day
    day_hr = [
        r for r in payload.heartRate
        if r.get_bpm() is not None and _parse_date(r.time) == day
    ]
    if day_hr:
        bpms = sorted(r.get_bpm() for r in day_hr)
        row["resting_heart_rate"] = float(bpms[len(bpms) // 2])

    # HRV — average rmssd for the day
    day_hrv = [r for r in payload.hrv if _parse_date(r.time) == day and r.get_rmssd() is not None]
    if day_hrv:
        row["hrv_rmssd"] = round(sum(r.get_rmssd() for r in day_hrv) / len(day_hrv), 1)

    # Sleep — longest session overlapping this date
    day_sleep = [
        s for s in payload.sleep
        if _parse_date(s.endTime) == day or _parse_date(s.startTime) == day
    ]
    if day_sleep:
        best = max(day_sleep, key=lambda s: s.duration())
        deep = _stage_minutes(best.stages, SLEEP_STAGE_DEEP)
        rem = _stage_minutes(best.stages, SLEEP_STAGE_REM)
        light = _stage_minutes(best.stages, SLEEP_STAGE_LIGHT)
        total = best.duration()
        row["sleep_duration_minutes"] = total
        row["deep_sleep_minutes"] = deep
        row["rem_sleep_minutes"] = rem
        row["light_sleep_minutes"] = light
        row["sleep_score"] = _sleep_score(deep, rem, total)

    # Oxygen saturation — average for the day
    day_spo2 = [r for r in payload.oxygenSaturation if r.percentage and _parse_date(r.time) == day]
    if day_spo2:
        row["oxygen_saturation"] = round(sum(r.percentage for r in day_spo2) / len(day_spo2), 1)

    # Respiratory rate — average for the day
    day_rr = [r for r in payload.respiratoryRate if r.rate and _parse_date(r.time) == day]
    if day_rr:
        row["respiratory_rate"] = round(sum(r.rate for r in day_rr) / len(day_rr), 1)

    # Distance — sum for the day
    day_dist = [r for r in payload.distance if r.get_meters() and _parse_date(r.startTime) == day]
    if day_dist:
        row["distance_meters"] = int(sum(r.get_meters() for r in day_dist))

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

    # Collect all unique dates across all record types
    dates: set[date] = set()
    for r in payload.steps:
        s = r.get_start()
        if s:
            dates.add(_parse_date(s))
    for r in payload.heartRate:
        dates.add(_parse_date(r.time))
    for r in payload.hrv:
        dates.add(_parse_date(r.time))
    for r in payload.sleep:
        dates.add(_parse_date(r.endTime))
        dates.add(_parse_date(r.startTime))
    for r in payload.oxygenSaturation:
        dates.add(_parse_date(r.time))
    for r in payload.respiratoryRate:
        dates.add(_parse_date(r.time))
    for r in payload.distance:
        dates.add(_parse_date(r.startTime))

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

    # Backfill DailyRecord.mindfulness_occurred from MindfulnessSession records.
    # Only updates rows that already exist (AM check-in must precede mindfulness write).
    if payload.mindfulness:
        mindfulness_by_date: dict[date, list[MindfulnessRecord]] = {}
        for m in payload.mindfulness:
            try:
                d = _parse_date(m.startTime)
                mindfulness_by_date.setdefault(d, []).append(m)
            except Exception:
                pass
        for m_date, sessions in mindfulness_by_date.items():
            if since <= m_date <= today:
                daily_rec = (
                    db.query(models.DailyRecord)
                    .filter_by(user_id=current_user.id, date=m_date)
                    .first()
                )
                if daily_rec:
                    daily_rec.mindfulness_occurred = True
                    daily_rec.mindfulness_duration_min = sum(s.duration() for s in sessions)

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
