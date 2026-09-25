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
from pydantic import BaseModel, ConfigDict
from sqlalchemy import null
from sqlalchemy.orm import Session

import models
from auth import create_access_token, get_current_user
from database import get_db
from load_metrics import _local_day     # operator-local (AEST) day — Q42 single source
from reads.aerobic_reads import HEALTH_CONNECT, writer_class, writer_class_rank

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


# Health Connect ExerciseSessionRecord.ExerciseType — the complete official enum,
# mirrored from the androidx source (androidx.health.connect.client.records
# .ExerciseSessionRecord, androidx-main): 61 defined values in [0, 83]; the gaps
# (1, 3, 6, 7, 12, 15, 17-24, 30, 40-43, 45, 49, 67, 77) are unassigned upstream
# and MUST stay unassigned here. Published with x-enum-varnames in main.py (same
# mechanism as SleepStageType) so the companion app can generate a contract file.
#
# This enum is a MAPPING helper, NOT a wire-validation type: the inbound
# ExerciseRecord.type field is a REQUIRED but lenient int (#234), so an integer
# this enum does not define is accepted and persisted with sport_id retained and
# sport_name NULL (see sport_name_for) — we never GUESS a sport for an unknown
# code, and a future upstream addition never 422-rejects a sync. Required-int
# rejects a missing or null `type` (the rename signal) without rejecting an
# unknown code; that is why the field is `int`, not `Any`.
class ExerciseSessionType(IntEnum):
    OTHER_WORKOUT                   = 0
    BADMINTON                       = 2
    BASEBALL                        = 4
    BASKETBALL                      = 5
    BIKING                          = 8
    BIKING_STATIONARY               = 9
    BOOT_CAMP                       = 10
    BOXING                          = 11
    CALISTHENICS                    = 13
    CRICKET                         = 14
    DANCING                         = 16
    ELLIPTICAL                      = 25
    EXERCISE_CLASS                  = 26
    FENCING                         = 27
    FOOTBALL_AMERICAN               = 28
    FOOTBALL_AUSTRALIAN             = 29
    FRISBEE_DISC                    = 31
    GOLF                            = 32
    GUIDED_BREATHING                = 33
    GYMNASTICS                      = 34
    HANDBALL                        = 35
    HIGH_INTENSITY_INTERVAL_TRAINING = 36
    HIKING                          = 37
    ICE_HOCKEY                      = 38
    ICE_SKATING                     = 39
    MARTIAL_ARTS                    = 44
    PADDLING                        = 46
    PARAGLIDING                     = 47
    PILATES                         = 48
    RACQUETBALL                     = 50
    ROCK_CLIMBING                   = 51
    ROLLER_HOCKEY                   = 52
    ROWING                          = 53
    ROWING_MACHINE                  = 54
    RUGBY                           = 55
    RUNNING                         = 56
    RUNNING_TREADMILL               = 57
    SAILING                         = 58
    SCUBA_DIVING                    = 59
    SKATING                         = 60
    SKIING                          = 61
    SNOWBOARDING                    = 62
    SNOWSHOEING                     = 63
    SOCCER                          = 64
    SOFTBALL                        = 65
    SQUASH                          = 66
    STAIR_CLIMBING                  = 68
    STAIR_CLIMBING_MACHINE          = 69
    STRENGTH_TRAINING               = 70
    STRETCHING                      = 71
    SURFING                         = 72
    SWIMMING_OPEN_WATER             = 73
    SWIMMING_POOL                   = 74
    TABLE_TENNIS                    = 75
    TENNIS                          = 76
    VOLLEYBALL                      = 78
    WALKING                         = 79
    WATER_POLO                      = 80
    WEIGHTLIFTING                   = 81
    WHEELCHAIR                      = 82
    YOGA                            = 83


def sport_name_for(exercise_type: Optional[int]) -> Optional[str]:
    """Human-readable sport name for a Health Connect exerciseType code.

    Returns Title Case (e.g. 56 -> "Running", 57 -> "Running Treadmill") for a
    code ExerciseSessionType defines; returns None for None or any unmapped int.
    A NULL sport_name is the DECIDED value for "code we do not recognise" — the
    row still persists with sport_id set to the raw code. Never raises, never
    guesses a sport for an unknown code (brief GUARD; cf. SleepStageType #20).
    """
    if exercise_type is None:
        return None
    try:
        member = ExerciseSessionType(exercise_type)
    except ValueError:
        return None
    return member.name.replace("_", " ").title()


# ---------- flexible incoming schemas ----------

class WriterIdentity(BaseModel):
    """Per-record writer identity, mixed into every HC record model.

    `sourcePackage` is the single canonical field: HCA's mappers thread
    `sourcePackage: r.metadata?.dataOrigin ?? null` from the library shape, so
    the flattened string is what arrives on the wire. The raw nested
    `dataOrigin.packageName` acceptance and its reconciler were removed at #234
    (the /health-connect/sync contract collapse) — one client, one mapped name.

    It stays OPTIONAL because identity is not GUARANTEED: historical rows
    predating the mapper change, record types HCA does not tag, and any future
    build regression all yield a missing identity, which
    _capture_record_sources coalesces to the literal 'unknown'. A required
    field would 422 those. (This is distinct from the canonical value fields
    #234 makes required — bpm/rmssd/date/type — where absence IS the rename
    signal; a missing writer is a known-tolerated state, not a broken contract.)

    Capture only — no filtering HERE. #175 adds admission filtering downstream
    in _aggregate_day, where 'unknown' must be a DECIDED value rather than a
    default that means exclude, or legitimately-unidentified records are
    dropped silently (Q83).

    extra="allow" (#234): a key a newer client adds is RETAINED in model_extra
    rather than dropped, so it is loggable on a rejected sibling record and
    never silently discarded. Inherited by every record subclass below — see
    SyncPayload and SleepStage, which set it independently (not WriterIdentity
    subclasses).
    """
    model_config = ConfigDict(extra="allow")

    sourcePackage: Optional[str] = None


class HeartRateRecord(WriterIdentity):
    time: str
    bpm: int                                # canonical, REQUIRED (#234) — typed int rejects null natively


class StepsRecord(WriterIdentity):
    endTime: Optional[str] = None           # neither half of a dual name; unread, left as-is
    date: str                               # canonical, REQUIRED (#234)
    count: int


class HRVRecord(WriterIdentity):
    time: str
    rmssd: float                            # canonical, REQUIRED (#234) — typed float rejects null natively


class SleepStage(BaseModel):
    # extra="allow" (#234): `stages` receives library-raw objects, the likeliest
    # place a newer client legitimately adds a key; retain rather than drop.
    model_config = ConfigDict(extra="allow")

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
    # canonical, REQUIRED (#234). `int`, not `Any`: a required Any accepts an
    # explicit null (key-present-but-null passes), and this is the one field
    # the collapse hardens whose native type would not reject it. `int`
    # preserves the enum's documented leniency (:57) — that defends unknown
    # CODES, not non-integer types, and `int` admits every unknown code exactly
    # as `Any` did. No runtime path reads it (sport_name_for is test-only), so
    # this is forward-protection for #189's ingestion lane, not a live path.
    type: int
    title: Optional[str] = None
    durationMinutes: Optional[int] = None
    # Health Connect record metadata (#234, Q118): declared Optional so they are
    # first-class attributes rather than model_extra, accept-and-drop. Persisting
    # them (id as the dedup UUID; recordingMethod/device for #175 admission) is
    # Q118. Samsung leaves recordingMethod/device at sentinel 0.
    id: Optional[str] = None
    recordingMethod: Optional[int] = None
    device: Optional[Any] = None


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


class ClientInfo(BaseModel):
    # The per-POST build fingerprint HCA sends under `client` (HCA DECISIONS #40).
    # extra="allow": a field a newer HCA build adds is retained, never a 422. Every
    # field optional/defaulted — an old build sends no `client` at all, which is
    # normal (SyncPayload.client stays None) and must not 422.
    model_config = ConfigDict(extra="allow")

    gitSha: Optional[str] = None        # `git describe --always --dirty`; may carry a "-dirty" suffix
    builtAt: Optional[str] = None
    appVersion: Optional[str] = None
    platform: Optional[str] = None


class FetchMetaEntry(BaseModel):
    # One entry per stream HCA fetched, under `fetchMeta` (HCA DECISIONS #40).
    # extra="allow" for the same forward-compat reason as ClientInfo.
    model_config = ConfigDict(extra="allow")

    received: int = 0
    oldestAt: Optional[str] = None      # null when received == 0
    newestAt: Optional[str] = None
    pages: int = 0
    truncated: bool = False
    endedOnFailure: bool = False


class SyncPayload(BaseModel):
    # extra="allow" (#234): the LOAD-BEARING one. An unknown TOP-LEVEL key is
    # retained in model_extra (the additive-key tolerance) and is what Step 4
    # logs on a rejected body. Set independently — SyncPayload is not a
    # WriterIdentity subclass and does not inherit its config.
    model_config = ConfigDict(extra="allow")

    syncedAt: Optional[str] = None
    periodDays: int = 7

    # Per-POST build fingerprint + fetch telemetry (HCA DECISIONS #40). Both
    # optional-defaulted so an old build (neither key) validates unchanged — absence
    # is normal, never a 422. Persisted one-row-per-POST to health_connect_sync_events;
    # capture only, feeds no aggregation or read path.
    client: Optional[ClientInfo] = None
    fetchMeta: dict[str, FetchMetaEntry] = {}

    # The five streams HCA ALWAYS posts are REQUIRED but emptyable (#234): no
    # default, so an omitted key 422s, while `[]` is valid. Envelope-required is
    # what catches a `workouts` -> `exercise` rename that required record fields
    # alone would not — a renamed list key would default to [] and report success.
    sleep: list[SleepSession]
    hrv: list[HRVRecord]
    heartRate: list[HeartRateRecord]
    steps: list[StepsRecord]
    workouts: list[ExerciseRecord]          # canonical envelope key (HCA sends `workouts`, never `exercise`)

    # The five HCA NEVER posts stay optional-defaulted — absence is normal, not a
    # rename signal.
    oxygenSaturation: list[OxygenSaturationRecord] = []
    respiratoryRate: list[RespiratoryRateRecord] = []
    weight: list[WeightRecord] = []
    distance: list[DistanceRecord] = []
    mindfulness: list[MindfulnessRecord] = []
    errors: list[str] = []

    # `exercise` (the dual envelope key) and `all_exercises()` removed at #234.
    # The helper existed solely to reconcile `workouts` + `exercise`; with one
    # key it is dead, and — reading the deleted field — it would be a NameError
    # in waiting if left. Deleted because the collapse breaks it, which is a
    # different rule from dead-code cleanup: get_kg()/sport_name_for stay.


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


def _parse_dt(iso: Optional[str]) -> Optional[datetime]:
    """Parse an HC ISO timestamp to a UTC-aware datetime for interval maths.

    Same normalisation as _wake_date (strip Android nanosecond fraction, map a
    trailing 'Z' to +00:00, treat a naive timestamp as UTC) so every segment is
    globally comparable regardless of the shape it arrived in. Returns None on a
    missing or unparseable value — the caller drops that segment rather than
    guessing a span (cf. F2 pre-2020 reject: a bad timestamp is never repaired)."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(_FRAC_SECONDS.sub("", iso).replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


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
    payload.steps = _filter(payload.steps, lambda r: r.date)
    payload.workouts = _filter(payload.workouts, lambda r: r.startTime)
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
    aggregation already ignores them).

    Returns (new_rows_inserted, unattributed): the second is the count of captured
    records this sync whose writer degraded to 'unknown' (#234/#235). It is tallied
    HERE, over the same pass, so the two numbers share one iteration and cannot
    disagree about what was captured. Attribution is an axis orthogonal to value:
    a record counts here whether or not it also aggregated into a DailyRecord.
    """
    captured: list[tuple[str, str, str]] = []
    unattributed = 0

    def _add(items, rtype: str, ts) -> None:
        nonlocal unattributed
        for r in items:
            t = ts(r)
            if t:
                pkg = r.sourcePackage or "unknown"
                if pkg == "unknown":
                    unattributed += 1
                captured.append((rtype, t, pkg))

    _add(payload.sleep, "sleep", lambda r: r.startTime)
    _add(payload.hrv, "hrv", lambda r: r.time)
    _add(payload.heartRate, "heart_rate", lambda r: r.time)
    _add(payload.steps, "steps", lambda r: r.date)
    _add(payload.workouts, "exercise", lambda r: r.startTime)
    _add(payload.oxygenSaturation, "oxygen_saturation", lambda r: r.time)
    _add(payload.respiratoryRate, "respiratory_rate", lambda r: r.time)
    _add(payload.weight, "weight", lambda r: r.time)
    _add(payload.distance, "distance", lambda r: r.startTime)
    _add(payload.mindfulness, "mindfulness", lambda r: r.startTime)

    if not captured:
        return 0, unattributed

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
    return inserted, unattributed


# `com.hevy` mirrors Hevy workouts into Health Connect, but the direct Hevy connector
# already owns those bouts (hevy_workouts). A Hevy-mirrored exercise record is dropped at
# admission — counted in the sync response, never ingested as an HC aerobic session
# (#309, Ruling 2). Distinct from the writer-class table (reads/aerobic_reads): those
# packages ARE ingested and only rank each other; com.hevy is excluded outright.
HEVY_PACKAGE = "com.hevy"


def _epoch(dt: Optional[datetime]) -> Optional[float]:
    """Epoch seconds for a start instant, naive treated as UTC — a hashable, tz-safe
    key for grouping records/rows by identical start (mirror detection)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _exercise_duration_minutes(
    start: Optional[datetime], stop: Optional[datetime], fallback: Optional[int]
) -> Optional[float]:
    """Minutes from start/stop when both are present and ordered; else the record's
    `durationMinutes` (S2 fallback); else None."""
    if start is not None and stop is not None and stop > start:
        return (stop - start).total_seconds() / 60.0
    return float(fallback) if fallback is not None else None


def _ingest_exercise_sessions(payload: "SyncPayload", user_id: int, db: Session) -> dict:
    """Stage-1 HC exercise ingest — discharges #189's hold (#309).

    Each surviving exercise record becomes ONE `aerobic_sessions` row
    (source='health_connect'), ZONELESS: every `z*_seconds` is NULL, not 0, so the
    metabolic transform reads "not measured" and stays fail-closed (INV-7) — a 0 would
    read as "measured, none". Zones are stage 2, out of scope.

    Admission (S1), write-time, drops two kinds of record — both COUNTED in the response,
    never silent:
      - `com.hevy` mirrors (the Hevy connector owns those bouts);
      - MIRRORS: a record whose start instant is identical to a higher-writer-class record
        in the same payload OR an existing `health_connect` row (Ruling 1 rank). Two
        INDEPENDENT detections of one bout (starts seconds apart) are NOT dropped here —
        read-time arbitration (`reads/aerobic_reads.arbitrate`) picks the canonical one,
        order-independently (S0(a): that is a real change to arbitrate(), not this path).

    Write (S2) upserts on the natural key `(user_id, 'health_connect', source_session_id)`
    with `source_session_id` = the HC record `id`, falling back to `package|startTime` when
    `id` is null (counted). Idempotent: re-syncing a payload updates rows in place, same ids.
    """
    counts = {"ingested": 0, "hevy_dropped": 0, "mirrors_dropped": 0,
              "id_fallback": 0, "unknown_writer": 0}

    # S1a — drop Hevy mirrors outright.
    survivors: list = []
    for r in payload.workouts:
        pkg = r.sourcePackage or "unknown"
        if pkg == HEVY_PACKAGE:
            counts["hevy_dropped"] += 1
            continue
        survivors.append(r)

    # All of the user's existing health_connect rows — needed for mirror detection (an
    # incoming record can mirror an already-stored row) and upsert-by-ssid. Loaded whole;
    # fine at personal/family scale. NOT bounded by the sync's date window on purpose:
    # `payload.workouts` is not window-filtered, so a survivor can fall outside it, and a
    # window bound would then miss that survivor's stored twin/row. A safe bound would key
    # off the survivors' own start-day range, not the sync window — deferred (non-blocking).
    existing = (
        db.query(models.AerobicSession)
        .filter(models.AerobicSession.user_id == user_id,
                models.AerobicSession.source == HEALTH_CONNECT)
        .all()
    )

    # S1b — mirror-drop by identical start instant. Highest writer-class rank at an instant
    # wins; a STRICTLY lower-rank record at that same instant is a mirror. Compared within
    # the payload AND against already-stored health_connect rows.
    best_rank_by_start: dict[float, int] = {}
    for e in existing:
        k = _epoch(e.start_time)
        if k is not None:
            best_rank_by_start[k] = max(best_rank_by_start.get(k, -1),
                                        writer_class_rank(e.source_package))
    for r in survivors:
        k = _epoch(_parse_dt(r.startTime))
        if k is not None:
            rk = writer_class_rank(r.sourcePackage or "unknown")
            best_rank_by_start[k] = max(best_rank_by_start.get(k, -1), rk)

    kept: list = []
    for r in survivors:
        k = _epoch(_parse_dt(r.startTime))
        rk = writer_class_rank(r.sourcePackage or "unknown")
        if k is not None and rk < best_rank_by_start.get(k, rk):
            counts["mirrors_dropped"] += 1
            continue
        kept.append(r)

    # S2 — write / upsert.
    existing_by_ssid = {e.source_session_id: e for e in existing}
    for r in kept:
        pkg = r.sourcePackage or "unknown"
        if writer_class(pkg) == "unknown":
            counts["unknown_writer"] += 1
        start = _parse_dt(r.startTime)
        stop = _parse_dt(r.endTime)
        ssid = r.id
        if ssid is None:
            counts["id_fallback"] += 1
            ssid = f"{pkg}|{r.startTime}"
        if start is not None:
            session_date = _local_day(start)
        elif stop is not None:
            session_date = _local_day(stop)
        else:
            session_date = _parse_date(r.startTime)
        fields = dict(
            session_date=session_date,
            start_time=start,
            stop_time=stop,
            sport_id=None if r.type is None else str(r.type),   # type is a required int, so defensive
            sport_name=sport_name_for(r.type),
            duration_minutes=_exercise_duration_minutes(start, stop, r.durationMinutes),
            source_package=pkg,
            recording_method=r.recordingMethod,
            # SQL NULL, not the column default 0 — INV-7 keys on "not measured" and a 0
            # would read as "measured, none". A plain None triggers the Python-side
            # default=0; sqlalchemy.null() forces the INSERT to write NULL instead.
            z1_seconds=null(), z2_seconds=null(), z3_seconds=null(),
            z4_seconds=null(), z5_seconds=null(),
        )
        row = existing_by_ssid.get(ssid)
        if row is None:
            row = models.AerobicSession(
                user_id=user_id, source=HEALTH_CONNECT, source_session_id=ssid, **fields,
            )
            db.add(row)
            existing_by_ssid[ssid] = row
        else:
            for key, val in fields.items():
                setattr(row, key, val)
        counts["ingested"] += 1

    return counts


# F3a — sleep aggregated as the UNION of asleep stage-intervals over the
# wake-date's session set, not the longest single session (DECISIONS_LOG #254).
# The asleep stages (LIGHT/DEEP/REM) that count toward total sleep time; AWAKE
# (in-bed or otherwise) and the non-asleep codes are excluded from TST.
_ASLEEP_STAGES = frozenset({
    int(SLEEP_STAGE_LIGHT), int(SLEEP_STAGE_DEEP), int(SLEEP_STAGE_REM),
})

# A gap wider than this (minutes) between a running period's coverage-end and the
# next segment's start opens a NEW sleep period. Within-night WASO/nocturia gaps
# are far below this; a night-vs-daytime-nap gap is far above it — so a same
# wake-date nap stays its own period and never merges into the night (the one
# thing the old longest-session selector got right, preserved).
SLEEP_PERIOD_GAP_MINUTES = 120


def _merge_intervals(
    intervals,
) -> list[tuple[datetime, datetime]]:
    """Merge overlapping/exactly-adjacent [start, end) intervals into a sorted
    list of disjoint (start, end) tuples. Empty and reversed spans are dropped."""
    spans = sorted((a, b) for a, b in intervals if b > a)
    merged: list[tuple[datetime, datetime]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:      # overlap or touch → extend coverage
            if b > merged[-1][1]:
                merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def _interval_seconds(intervals) -> float:
    """Total seconds spanned by (start, end) intervals — no merge, so callers pass
    disjoint intervals (e.g. the output of _merge_intervals) to avoid double-count."""
    return sum((b - a).total_seconds() for a, b in intervals)


def _subtract_intervals(
    base, claimed,
) -> list[tuple[datetime, datetime]]:
    """Coverage of `base` minus coverage of `claimed`, as disjoint (start, end)
    tuples. Both sides are merged first; the result is what `base` covers that
    `claimed` does not."""
    claimed_m = _merge_intervals(claimed)
    result: list[tuple[datetime, datetime]] = []
    for a, b in _merge_intervals(base):
        cur = a
        for ca, cb in claimed_m:
            if cb <= cur:                      # claimed piece entirely before cursor
                continue
            if ca >= b:                        # claimed piece past this base span
                break
            if ca > cur:                       # gap before the claimed piece is ours
                result.append((cur, ca))
            cur = max(cur, cb)                 # skip over the claimed piece
            if cur >= b:
                break
        if cur < b:
            result.append((cur, b))
    return result


def _union_minutes(intervals) -> int:
    """Total minutes covered by the union of [start, end) intervals.

    Overlapping and exactly-adjacent intervals merge, so overlapping sessions
    collapse to real covered time instead of summing (double-counting). Floors
    once at the end over the merged total — never per-segment, which would zero
    every sub-minute sliver (the DEEP-sliver fault _stage_minutes fixed, #20)."""
    return int(_interval_seconds(_merge_intervals(intervals)) // 60)


class _SyntheticSpan(tuple):
    """A stageless session's whole span, standing in as one LIGHT segment so its sleep
    time is not lost (#254). Unpacks exactly like a real segment tuple — every duration
    consumer is unchanged — but is distinguishable, so session-clock onset (#328) never
    reads a synthetic span as a real stage."""


def _period_clocks(period) -> dict:
    """Session clocks of a sleep period (#328), source-agnostic.

    sleep_start / sleep_end = earliest / latest segment edge, each with the writer package
    of the segment that supplies it (per-endpoint: a period can span two writers). On an
    exact tie, the lexically-first package wins (deterministic). sleep_onset = start of the
    first ASLEEP (LIGHT/DEEP/REM — the #254 TST set) segment from a REAL stage record;
    NULL when there is none. Instants are stored as timezone-aware UTC."""
    first = min(period, key=lambda s: (s[0], s[3]))
    end = max(s[1] for s in period)
    last = min((s for s in period if s[1] == end), key=lambda s: s[3])
    real_asleep = [s for s in period
                   if not isinstance(s, _SyntheticSpan) and s[2] in _ASLEEP_STAGES]
    onset = min((s[0] for s in real_asleep), default=None)

    def _utc(dt):
        return dt.astimezone(timezone.utc) if dt is not None else None

    return {
        "sleep_start": _utc(first[0]),
        "sleep_start_source_package": first[3],
        "sleep_end": _utc(last[1]),
        "sleep_end_source_package": last[3],
        "sleep_onset": _utc(onset),
    }


def _cluster_periods(
    segments: list[tuple[datetime, datetime, int, str]],
) -> list[list[tuple[datetime, datetime, int, str]]]:
    """Split stage segments into sleep periods by coverage continuity.

    Sort by start; a gap wider than SLEEP_PERIOD_GAP_MINUTES between the running
    coverage-end and the next segment's start opens a new period. Clustering uses
    ALL segments (asleep and awake) for coverage — an intra-night AWAKE bridges a
    WASO gap — while period SELECTION and TST count asleep only (see below)."""
    periods: list[list[tuple[datetime, datetime, int, str]]] = []
    cur: list[tuple[datetime, datetime, int, str]] = []
    cov_end: Optional[datetime] = None
    gap = timedelta(minutes=SLEEP_PERIOD_GAP_MINUTES)
    for seg in sorted(segments, key=lambda x: x[0]):
        start, end = seg[0], seg[1]
        if cur and cov_end is not None and start - cov_end > gap:
            periods.append(cur)
            cur = []
            cov_end = None
        cur.append(seg)
        cov_end = end if cov_end is None else max(cov_end, end)
    if cur:
        periods.append(cur)
    return periods


def _asleep_union_minutes(
    period: list[tuple[datetime, datetime, int, str]],
) -> int:
    """Union minutes of the asleep (LIGHT/DEEP/REM) segments in a period = TST."""
    return _union_minutes(
        (a, b) for (a, b, stg, _src) in period if stg in _ASLEEP_STAGES
    )


# Precedence for resolving a wall-clock minute that overlapping sessions label with
# different asleep stages: deeper / more-specific wins (DECISIONS_LOG #256, Luke's
# ruling — option (i) [DEEP, REM, LIGHT]). Applied source-agnostically; AWAKE sits
# below all asleep stages (excluded here, so any minute with an asleep segment
# resolves asleep — TST is untouched).
_STAGE_PRECEDENCE: tuple[int, ...] = (
    int(SLEEP_STAGE_DEEP), int(SLEEP_STAGE_REM), int(SLEEP_STAGE_LIGHT),
)


def _resolve_breakdown(
    period: list[tuple[datetime, datetime, int, str]],
    order: tuple[int, ...] = _STAGE_PRECEDENCE,
) -> dict[int, int]:
    """Partition the period's asleep coverage into one stage per wall-clock minute
    by precedence, so the deep/rem/light breakdown sums to the asleep union (== TST)
    by construction — never above it (the independent-per-stage-union fault, #256).

    Every minute covered by >=1 asleep segment is assigned to exactly one stage: the
    earliest in `order` whose segments claim it. A minute two overlapping sessions
    label differently (LIGHT in one, REM in another) goes to whichever stage precedes
    the other in `order`, so it is counted once, not in both buckets. Source-agnostic
    — a cross-source stage disagreement at a session seam resolves by the same
    precedence, so no dominant-source pick is needed.

    Coherence is structural: the stage intervals are an exact disjoint partition of
    the asleep union, and a cumulative floor over `order` makes the per-stage minute
    counts sum to floor(total asleep seconds / 60) exactly — matching
    _asleep_union_minutes regardless of sub-minute segment boundaries. Independent
    per-stage floors could drop a minute on such a boundary and reopen the very
    incoherence this resolves."""
    claimed: list[tuple[datetime, datetime]] = []
    stage_intervals: dict[int, list[tuple[datetime, datetime]]] = {}
    for stage in order:
        ivs = [(a, b) for (a, b, stg, _src) in period if stg == stage]
        unclaimed = _subtract_intervals(ivs, claimed)
        stage_intervals[stage] = unclaimed
        claimed = _merge_intervals(claimed + unclaimed)

    result: dict[int, int] = {}
    cum_seconds = 0.0
    prev_floor = 0
    for stage in order:
        cum_seconds += _interval_seconds(stage_intervals[stage])
        cur_floor = int(cum_seconds // 60)
        result[stage] = cur_floor - prev_floor
        prev_floor = cur_floor
    return result


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

    # Steps — sum all records on this date
    day_steps = [
        r for r in payload.steps
        if r.date and _parse_date(r.date) == day
    ]
    if day_steps:
        row["steps"] = sum(r.count for r in day_steps)

    # Heart rate — median bpm for the day
    day_hr = [
        r for r in payload.heartRate
        if r.bpm is not None and _parse_date(r.time) == day
    ]
    if day_hr:
        bpms = sorted(r.bpm for r in day_hr)
        row["resting_heart_rate"] = float(bpms[len(bpms) // 2])

    # HRV — average rmssd for the day
    day_hrv = [r for r in payload.hrv if _parse_date(r.time) == day and r.rmssd is not None]
    if day_hrv:
        row["hrv_rmssd"] = round(sum(r.rmssd for r in day_hrv) / len(day_hrv), 1)

    # Sleep — UNION of asleep stage-intervals over the wake-date's session set
    # (F3a, DECISIONS_LOG #254). Replaces longest-single-session selection: a
    # fragmented night (multiple overlapping/adjacent sessions) now reports true
    # total sleep time — the union of LIGHT/DEEP/REM intervals — instead of one
    # fragment's self-reported duration(). Computed from stage segments, never
    # from session.duration() (self-reported, overlaps its neighbours on a
    # fragmented night). Wake-date-only grouping is unchanged (Q4).
    day_sleep = [
        s for s in payload.sleep
        if _wake_date(s.endTime) == day
    ]
    if day_sleep:
        # Flatten every session to stage segments (start, end, stage, source).
        # A session with no stages contributes its whole span as one best-effort
        # LIGHT segment — no stage detail, so assume asleep (edge, noted).
        segments: list[tuple[datetime, datetime, int, str]] = []
        for s in day_sleep:
            src = s.sourcePackage or "unknown"
            if s.stages:
                for st in s.stages:
                    a, b = _parse_dt(st.startTime), _parse_dt(st.endTime)
                    if a and b and b > a:
                        segments.append((a, b, int(st.stage), src))
            else:
                a, b = _parse_dt(s.startTime), _parse_dt(s.endTime)
                if a and b and b > a:
                    segments.append(_SyntheticSpan((a, b, int(SLEEP_STAGE_LIGHT), src)))

        if segments:
            # Cluster into periods by coverage continuity; the main period is the
            # one with the largest asleep-union (a tiny night + long nap could
            # invert this — rare, and the diary is authoritative; note, not guard).
            periods = _cluster_periods(segments)
            main = max(periods, key=_asleep_union_minutes)
            tst = _asleep_union_minutes(main)

            # Stage breakdown: partition the main period's asleep coverage into one
            # stage per wall-clock minute by precedence (DEEP > REM > LIGHT), so
            # deep + rem + light == tst by construction (DECISIONS_LOG #256,
            # supersedes #254's independent per-stage unions). Source-agnostic — a
            # cross-source stage conflict at a session seam resolves by the same
            # precedence, retiring #254's dominant-source branch. The union TST is
            # unchanged (AWAKE sits below all asleep stages, so every asleep minute
            # still resolves asleep).
            bd = _resolve_breakdown(main, _STAGE_PRECEDENCE)
            deep = bd[int(SLEEP_STAGE_DEEP)]
            rem = bd[int(SLEEP_STAGE_REM)]
            light = bd[int(SLEEP_STAGE_LIGHT)]

            row["sleep_duration_minutes"] = tst
            row["deep_sleep_minutes"] = deep
            row["rem_sleep_minutes"] = rem
            row["light_sleep_minutes"] = light
            row["sleep_score"] = _sleep_score(deep, rem, tst)
            # Session clocks of the SAME main period (#328) — persisted source-agnostically;
            # no per-device branch. The meaning of `sleep_start` per source is ruled later
            # from evidence (S7) and nothing maps it to a diary entry-side field yet.
            row.update(_period_clocks(main))

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

    # `received` is counted AS POSTED — before _reject_pre2020 mutates the payload
    # in place — so the accounting reconciles: received = what arrived, and the
    # pre-2020 drops surface separately as rejected_pre_2020 (#235).
    received = {
        "sleep": len(payload.sleep),
        "hrv": len(payload.hrv),
        "heartRate": len(payload.heartRate),
        "steps": len(payload.steps),
        "workouts": len(payload.workouts),
    }

    # Persist ONE health_connect_sync_events row per POST — the client build
    # fingerprint + fetch telemetry (HCA DECISIONS #40). Written for EVERY POST,
    # including an old build's (neither `client` nor `fetchMeta`): git_sha NULL is
    # the "still on an old build" signal, not a gap. synced_at is the SERVER clock
    # (server_default now()), deliberately not the client's syncedAt. Capture only —
    # it rides the single db.commit() at the end and touches no aggregation.
    # Clip each string to its column width. Postgres enforces String(n) and would
    # RAISE on an over-length value — which, on this insert, would roll back the whole
    # sync. A telemetry field must never be able to fail the real work, so truncate
    # rather than trust the client's lengths. (SQLite does not enforce width, so the
    # unit tests cannot see this; the clip is what makes prod safe.) `is not None`
    # guards the slice and preserves an empty string as "", mapping only real None to NULL.
    client = payload.client
    db.add(models.HealthConnectSyncEvent(
        user_id=current_user.id,
        git_sha=(client.gitSha[:80] if client and client.gitSha is not None else None),
        built_at=(client.builtAt[:40] if client and client.builtAt is not None else None),
        app_version=(client.appVersion[:40] if client and client.appVersion is not None else None),
        platform=(client.platform[:40] if client and client.platform is not None else None),
        period_days=payload.periodDays,
        fetch_meta={k: v.model_dump() for k, v in payload.fetchMeta.items()} or None,
    ))

    # F2 — reject pre-2020 (epoch-zero) records before any aggregation (#35).
    rejected_pre_2020 = _reject_pre2020(payload)
    if rejected_pre_2020:
        logger.info(
            "HC sync user=%s dropped %d pre-2020 record(s)",
            current_user.id, rejected_pre_2020,
        )

    # Capture per-record writer identity before _aggregate_day collapses the
    # night — the backend enabler for source-priority dedup (#36/#37).
    sources_captured, unattributed = _capture_record_sources(payload, current_user.id, db)

    # Stage-1 HC exercise ingest (#189 discharged, #309): surviving exercise records
    # become health_connect `aerobic_sessions` rows (zoneless). Admission drops are
    # counted, never silent. Runs after pre-2020 reject (payload.workouts already filtered).
    exercise_ingest = _ingest_exercise_sessions(payload, current_user.id, db)

    # Collect all unique dates across all record types
    dates: set[date] = set()
    for r in payload.steps:
        if r.date:
            dates.add(_parse_date(r.date))
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

    # `aggregated` = records (post pre-2020 reject) whose date falls on a synced
    # date, i.e. that fed _aggregate_day for a persisted row (#235). Distinct from
    # `received`: an in-window-but-out-of-range record is received, not aggregated.
    # `workouts` is the real count of exercise records ingested into `aerobic_sessions`
    # this sync (#189's hold discharged, #309) — NOT a DailyRecord count (exercise feeds
    # the aerobic lane, a separate table). The admission drops (Hevy mirrors, writer-class
    # mirrors) are surfaced separately under `exercise_ingest`, so this number plus those
    # drops reconciles against `received["workouts"]` (minus any pre-2020 reject).
    aggregated = {
        "sleep": sum(1 for r in payload.sleep if _wake_date(r.endTime) in valid_dates),
        "hrv": sum(1 for r in payload.hrv if _parse_date(r.time) in valid_dates),
        "heartRate": sum(1 for r in payload.heartRate if _parse_date(r.time) in valid_dates),
        "steps": sum(1 for r in payload.steps if r.date and _parse_date(r.date) in valid_dates),
        "workouts": exercise_ingest["ingested"],
    }

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
    # Sliding renewal (#NEXT): a fresh access token on every SUCCESSFUL sync, minted
    # after the commit with the login route's exact claim set ({"sub": email}) and
    # lifetime (ACCESS_TOKEN_EXPIRE_MINUTES), so a companion syncing on a schedule
    # never reaches expiry. Any failure path (401/422/an exception before here)
    # returns no token. Additive key; clients that ignore it are unaffected.
    renewed_token = create_access_token({"sub": current_user.email})
    return {
        "synced": len(synced_dates),
        "dates": synced_dates,
        "rejected_pre_2020": rejected_pre_2020,
        "sources_captured": sources_captured,
        # Per-stream accounting (#235): what arrived vs what reached a DailyRecord,
        # plus the count whose writer degraded to 'unknown'. Additive — the four
        # fields above are unchanged. NOTE (landed != live): no client consumes
        # these yet — SyncScreen.js discards the sync response at 7a63b15; the
        # operator surface is logs and direct inspection until HCA reads them.
        "received": received,
        "aggregated": aggregated,
        "unattributed": unattributed,
        # Stage-1 HC exercise ingest accounting (#309): ingested rows plus the admission
        # drops (Hevy mirrors, writer-class mirrors), the null-id fallback count, and how
        # many surviving records carried a writer outside the class table (Ruling 2).
        "exercise_ingest": exercise_ingest,
        "renewed_token": renewed_token,
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
