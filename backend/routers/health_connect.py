"""
Receives Health Connect data from the companion Android app and stores
it in health_connect_syncs — one row per user per date (upsert).

Schemas are intentionally flexible to accept both the raw library shapes
and any field names used by the JS mapping layer.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from enum import IntEnum
import logging
import re

import pytz

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/health-connect", tags=["health-connect"])

logger = logging.getLogger(__name__)

# Health Connect SleepSessionRecord.StageType — complete official enum.
# Samsung Health writes 1/4/5/6; other devices may emit 0/2/3/7.
# Defining all 8 values prevents 422 rejections on valid-but-uncommon stages.
# See DECISIONS_LOG #20 for the earlier mapping correction (DEEP/REM/LIGHT mislabelling).
class SleepStageType(IntEnum):
    UNKNOWN     = 0
    AWAKE       = 1
    SLEEPING    = 2
    OUT_OF_BED  = 3
    LIGHT       = 4
    DEEP        = 5
    REM         = 6
    AWAKE_IN_BED = 7

SLEEP_STAGE_AWAKE = SleepStageType.AWAKE
SLEEP_STAGE_LIGHT = SleepStageType.LIGHT
SLEEP_STAGE_DEEP  = SleepStageType.DEEP
SLEEP_STAGE_REM   = SleepStageType.REM


# ---------- flexible incoming schemas ----------

class DataOrigin(BaseModel):
    """Health Connect Record.metadata.dataOrigin — the writing app's identity."""
    packageName: Optional[str] = None


class WriterIdentity(BaseModel):
    """Per-record writer identity, mixed into every HC record model.

    Dual-field per the #24 house pattern (raw library field + mapped alias):
      dataOrigin.packageName — raw Health Connect shape (#36 wire contract)
      sourcePackage          — flattened alias the JS mapping layer may emit

    Optional/nullable everywhere: current HCA builds send no dataOrigin, so a
    required field would 422 every live sync (#36). Capture only — no filtering.
    """
    dataOrigin: Optional[DataOrigin] = None   # raw library field
    sourcePackage: Optional[str] = None        # mapped field

    def get_source_package(self) -> Optional[str]:
        if self.sourcePackage:
            return self.sourcePackage
        if self.dataOrigin:
            return self.dataOrigin.packageName
        return None


class HeartRateRecord(WriterIdentity):
    time: str
    beatsPerMinute: Optional[int] = None   # raw library field
    bpm: Optional[int] = None               # mapped field

    def get_bpm(self) -> Optional[int]:
        return self.bpm or self.beatsPerMinute


class StepsRecord(WriterIdentity):
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    date: Optional[str] = None              # mapped field (date: r.startTime)
    count: int

    def get_start(self) -> Optional[str]:
        return self.startTime or self.date


class HRVRecord(WriterIdentity):
    time: str
    heartRateVariabilityMillis: Optional[float] = None  # raw library field
    rmssd: Optional[float] = None                        # mapped field

    def get_rmssd(self) -> Optional[float]:
        return self.rmssd or self.heartRateVariabilityMillis


class SleepStage(BaseModel):
    stage: SleepStageType
    startTime: str
    endTime: str


class SleepSession(WriterIdentity):
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


class ExerciseRecord(WriterIdentity):
    startTime: str
    endTime: str
    exerciseType: Optional[int] = None
    type: Optional[Any] = None              # mapped field (type: r.exerciseType)
    title: Optional[str] = None
    durationMinutes: Optional[int] = None


class OxygenSaturationRecord(WriterIdentity):
    time: str
    percentage: Optional[float] = None


class RespiratoryRateRecord(WriterIdentity):
    time: str
    rate: Optional[float] = None


class WeightRecord(WriterIdentity):
    time: str
    weight: Optional[dict] = None
    inKilograms: Optional[float] = None

    def get_kg(self) -> Optional[float]:
        if self.inKilograms is not None:
            return self.inKilograms
        if isinstance(self.weight, dict):
            return self.weight.get("inKilograms")
        return None


class DistanceRecord(WriterIdentity):
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


class MindfulnessRecord(WriterIdentity):
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


# Sleep is attributed to its LOCAL wake-date, matching the scraper's convention
# (samsung_hrv_readings keys the wake-date). HC timestamps are UTC (naive ones
# are treated as UTC — the same normalisation context_builder applies to health
# timestamps); a naive `[:10]` slice mis-dates the night by one calendar day
# under UTC, which is the whole of OPEN_QUESTIONS Q4. Converting to
# Australia/Brisbane (UTC+10, no DST) before taking the date is correct whether
# the string is UTC-with-Z, UTC-naive, offset-aware, or local-naive — so it
# settles Q4's tz fork regardless of which shape the payload actually carries.
_AEST = pytz.timezone("Australia/Brisbane")

# Android/Health Connect emits nanosecond fractional seconds that
# datetime.fromisoformat cannot parse; strip the fraction but PRESERVE any
# trailing 'Z'/offset so an offset-aware timestamp keeps its zone.
_FRAC_SECONDS = re.compile(r"\.\d+")


def _wake_date(iso: str) -> date:
    """Local (AEST) calendar date of a sleep session's endTime."""
    dt = datetime.fromisoformat(_FRAC_SECONDS.sub("", iso).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_AEST).date()


def _now_aest_date() -> date:
    return datetime.now(_AEST).date()


# F2 — pre-2020 timestamp reject (DECISIONS_LOG #35).
# Epoch-zero starts (1970 in Polar RHR, 1969 in cbti diary) were observed in the
# 28 Jun HC export. A record with a 1970 startTime and a valid endTime would
# otherwise be picked by the longest-session selector and corrupt the computed
# sleep duration (a decades-long span). The record is unrecoverable, so it is
# dropped — not repaired — and the dropped count is surfaced per sync.
_MIN_VALID_DATE = date(2020, 1, 1)


def _is_pre2020(iso: Optional[str]) -> bool:
    """True if a timestamp predates 2020-01-01, or is present-but-unparseable.
    A missing (None) optional timestamp is NOT rejected here — existing
    aggregation already skips records with no usable date."""
    if not iso:
        return False
    try:
        return datetime.fromisoformat(iso[:10]).date() < _MIN_VALID_DATE
    except (ValueError, AttributeError):
        return True


def _reject_pre2020(payload: SyncPayload) -> int:
    """Drop every record whose primary timestamp predates 2020-01-01, in place.
    Returns the total number of records dropped across all record types."""
    total = 0

    def _filter(items, ts):
        nonlocal total
        kept = [r for r in items if not _is_pre2020(ts(r))]
        total += len(items) - len(kept)
        return kept

    payload.sleep = _filter(payload.sleep, lambda r: r.startTime)
    payload.hrv = _filter(payload.hrv, lambda r: r.time)
    payload.heartRate = _filter(payload.heartRate, lambda r: r.time)
    payload.steps = _filter(payload.steps, lambda r: r.get_start())
    payload.workouts = _filter(payload.workouts, lambda r: r.startTime)
    payload.exercise = _filter(payload.exercise, lambda r: r.startTime)
    payload.oxygenSaturation = _filter(payload.oxygenSaturation, lambda r: r.time)
    payload.respiratoryRate = _filter(payload.respiratoryRate, lambda r: r.time)
    payload.weight = _filter(payload.weight, lambda r: r.time)
    payload.distance = _filter(payload.distance, lambda r: r.startTime)
    payload.mindfulness = _filter(payload.mindfulness, lambda r: r.startTime)
    return total


def _capture_record_sources(payload: SyncPayload, user_id: int, db: Session) -> int:
    """Persist per-record writer identity BEFORE _aggregate_day collapses the night.

    Captures one (record_type, record_start, source_package) per inbound record
    into health_connect_record_sources. A missing identity is coalesced to the
    literal 'unknown' so the value is never NULL — source_package is part of the
    uq_hc_record_source key, and a NULL there is UNIQUE-distinct on both SQLite
    and Postgres, which would defeat both dedup and re-sync idempotency.

    Two apps writing the same (type, timestamp) now persist as two distinct rows
    (the multi-writer signal F1 needs); re-syncing the same (type, timestamp,
    package) refreshes synced_at rather than duplicating. Capture only — no
    filtering, and the aggregated row is untouched (#36/#37).

    Records with no primary timestamp are skipped (they carry no usable key and
    aggregation already ignores them). Returns the number of NEW rows inserted.
    """
    captured: list[tuple[str, str, str]] = []

    def _add(items, rtype: str, ts) -> None:
        for r in items:
            t = ts(r)
            if t:
                captured.append((rtype, t, r.get_source_package() or "unknown"))

    _add(payload.sleep, "sleep", lambda r: r.startTime)
    _add(payload.hrv, "hrv", lambda r: r.time)
    _add(payload.heartRate, "heart_rate", lambda r: r.time)
    _add(payload.steps, "steps", lambda r: r.get_start())
    _add(payload.workouts, "exercise", lambda r: r.startTime)
    _add(payload.exercise, "exercise", lambda r: r.startTime)
    _add(payload.oxygenSaturation, "oxygen_saturation", lambda r: r.time)
    _add(payload.respiratoryRate, "respiratory_rate", lambda r: r.time)
    _add(payload.weight, "weight", lambda r: r.time)
    _add(payload.distance, "distance", lambda r: r.startTime)
    _add(payload.mindfulness, "mindfulness", lambda r: r.startTime)

    if not captured:
        return 0

    # One query for this user's existing keys; upsert in memory (dialect-agnostic —
    # local is SQLite, prod Postgres). At personal/family scale this table is small.
    existing = {
        (o.record_type, o.record_start, o.source_package): o
        for o in db.query(models.HealthConnectRecordSource)
                   .filter_by(user_id=user_id)
                   .all()
    }
    now = datetime.now(timezone.utc)
    inserted = 0
    seen: set[tuple[str, str, str]] = set()
    for rtype, rstart, pkg in captured:
        key = (rtype, rstart, pkg)
        if key in seen:
            continue                       # collapse intra-payload key collisions
        seen.add(key)
        obj = existing.get(key)
        if obj:
            obj.synced_at = now            # same writer re-synced — refresh only
        else:
            db.add(models.HealthConnectRecordSource(
                user_id=user_id,
                record_type=rtype,
                record_start=rstart,
                source_package=pkg,
                synced_at=now,
            ))
            inserted += 1
    return inserted


def _stage_minutes(stages: list[SleepStage], stage_type: int) -> int:
    # Sum total seconds across matching segments, then floor once. The previous
    # per-segment int() floor zeroed every sub-minute sliver — and deep sleep is
    # mostly slivers (gate showed ~26 of 30 deep segments <3 min). See
    # DECISIONS_LOG #20 / OPEN_QUESTIONS Q1.
    total_seconds = 0.0
    for s in stages:
        if s.stage == stage_type:
            try:
                start = datetime.fromisoformat(s.startTime[:19])
                end = datetime.fromisoformat(s.endTime[:19])
                total_seconds += (end - start).total_seconds()
            except (ValueError, AttributeError):
                pass
    return int(total_seconds // 60)


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

    # Sleep — longest session whose LOCAL wake-date (endTime) is this day.
    # Wake-date only (Q4): the former startTime/bed-date clause split one
    # physical night across two rows. A same-day nap cannot displace the main
    # night because the max() tiebreak below still picks the longest session.
    day_sleep = [
        s for s in payload.sleep
        if _wake_date(s.endTime) == day
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
    # Sleep wake-dates are AEST-local (see _wake_date) and can be one day ahead
    # of UTC `today`; use an AEST upper bound so last night is not dropped as
    # "future". Lower bound stays UTC-wide so no backfill day is narrowed.
    today_local = _now_aest_date()

    # F2 — reject pre-2020 (epoch-zero) records before any aggregation (#35).
    rejected_pre_2020 = _reject_pre2020(payload)
    if rejected_pre_2020:
        logger.info(
            "HC sync user=%s dropped %d pre-2020 record(s)",
            current_user.id, rejected_pre_2020,
        )

    # Capture per-record writer identity before _aggregate_day collapses the
    # night — the backend enabler for source-priority dedup (#36/#37).
    sources_captured = _capture_record_sources(payload, current_user.id, db)

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
        dates.add(_wake_date(r.endTime))
    for r in payload.oxygenSaturation:
        dates.add(_parse_date(r.time))
    for r in payload.respiratoryRate:
        dates.add(_parse_date(r.time))
    for r in payload.distance:
        dates.add(_parse_date(r.startTime))

    valid_dates = {d for d in dates if since <= d <= max(today, today_local)}

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
    return {
        "synced": len(synced_dates),
        "dates": synced_dates,
        "rejected_pre_2020": rejected_pre_2020,
        "sources_captured": sources_captured,
    }


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
