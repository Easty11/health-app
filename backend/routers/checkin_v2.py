"""
Two-moment daily record system (AM check-in + nightly close-out).
Replaces DailyCheckIn as primary capture surface.
DailyCheckIn is retained for backward-compat with existing routes.

naive_baseline is the old formula frozen at AM capture time:
  sleep_quality (1-5) → ×2 → 2-10
  soreness = MAX across reported items (1-5) → (v-1)×2.5 → 0-10
  fatigue (0-10) and motivation (0-10) pass through unchanged.
  formula: sleep×0.3 + (10-fatigue)×0.3 + (10-soreness)×0.2 + motivation×0.2
"""
import datetime as _dt
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import pytz
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from cbti.timeutil import clock_delta_minutes
from database import get_db
from injury_trajectory import injury_soreness_key

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
    # Soreness term generalised from shoulder-only to MAX across all reported
    # soreness items — the score was structurally blind to every injury but
    # shoulder (hamstring etc. were captured and never scored). Max, not mean:
    # mean dilutes (a severe single site averaged against quiet sites under-reads);
    # the scalar answers "how beat up overall", movement-specificity lives in
    # restrictions[]. Default 3 (neutral) when nothing is reported preserves prior
    # behaviour. Introduces a discontinuity vs frozen historical (shoulder-only)
    # naive_baseline values — those are NOT recomputed (frozen at capture).
    sleep_s = sleep_quality * 2                          # 1-5 → 2-10
    vals = [v for v in (soreness or {}).values() if isinstance(v, (int, float))]
    soreness_raw = max(vals) if vals else 3              # 1-5
    soreness_s = (soreness_raw - 1) * 2.5               # 1-5 → 0-10
    raw = (
        sleep_s * 0.30
        + (10 - fatigue) * 0.30
        + (10 - soreness_s) * 0.20
        + motivation * 0.20
    )
    return round(max(1.0, min(10.0, raw)), 2)


# ── soreness items ← active injuries (FEEDBACK 2.6) ─────────────────────────────

def derive_soreness_items(user_id: int, db: Session) -> dict[str, int]:
    """AM soreness items derived from the active injury ledger — one item per active
    `type='injury'` entry, defaulted to 1 (=None on the 1-5 scale). Replaces the
    hardcoded {shoulder, hamstring}. Empty when no active injuries."""
    rows = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=user_id, type="injury", active=True)
        .order_by(models.UserKnowledgeEntry.added_at.desc())
        .all()
    )
    items: dict[str, int] = {}
    for r in rows:
        items[injury_soreness_key(r.value or {})] = 1
    return items


# ── passive snapshot ──────────────────────────────────────────────────────────

def _snapshot_passive(user_id: int, for_date: date, db: Session) -> dict[str, Any]:
    """Latest Samsung HRV and HC sleep at the moment of AM capture."""
    hrv_row = (
        db.query(models.SamsungHRVReading)
        .filter(
            models.SamsungHRVReading.user_id == user_id,
            models.SamsungHRVReading.captured_at <= for_date,
            models.SamsungHRVReading.context != 'session',
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


class CBTIContextOut(BaseModel):
    """Whether a CBT-I block is open, and the prescription in force for a date.

    Drives conditional render: the diary fields appear only while `block_open` is
    true (#108 — the fields are sparse by design, legended by the prescription's
    effective_from/to). Read-only projection of the append-only ledger; nothing
    here writes, and the titration engine is not involved in serving it.
    """
    block_open: bool = False
    block_id: Optional[int] = None
    wake_anchor: Optional[str] = None
    prescribed_lights_out: Optional[str] = None
    window_minutes: Optional[int] = None
    effective_from: Optional[date] = None


def _cbti_context(user_id: int, for_date: date, db: Session) -> CBTIContextOut:
    """Open block for this user, plus the prescription covering `for_date`.

    A block is open when `closed_on IS NULL`. The prescription in force is the
    latest one whose `effective_from <= for_date` and whose `effective_to` is
    either null or on/after it — the ledger is append-only and supersession is
    recorded rather than deleted, so "latest effective" is a query, not a flag.
    """
    block = (
        db.query(models.CBTIBlock)
        .filter(models.CBTIBlock.user_id == user_id,
                models.CBTIBlock.closed_on.is_(None))
        .order_by(models.CBTIBlock.opened_on.desc())
        .first()
    )
    if block is None:
        return CBTIContextOut()

    rx = (
        db.query(models.CBTIPrescription)
        .filter(models.CBTIPrescription.block_id == block.id,
                models.CBTIPrescription.effective_from <= for_date)
        .order_by(models.CBTIPrescription.effective_from.desc())
        .first()
    )
    return CBTIContextOut(
        block_open=True,
        block_id=block.id,
        wake_anchor=block.wake_anchor,
        prescribed_lights_out=rx.prescribed_lights_out if rx else None,
        window_minutes=rx.window_minutes if rx else None,
        effective_from=rx.effective_from if rx else None,
    )


# A prefill this far from the prescription is not a late night — it is a corrupt
# source clock. The scraper captures (\d+:\d+) from a Samsung content-desc, so a
# phone set to 12-hour stores "10:12 pm" as "10:12" — a 12-hour (720 min) error
# (#117). 4h is comfortably wider than any real bedtime drift and comfortably
# narrower than that corruption, so it separates the two without a false reject.
PREFILL_GATE_MAX_DELTA_MIN = 240


class DiaryPrefillOut(BaseModel):
    """Editable clock defaults for the AM diary, sourced from Samsung and gated.

    Prefills ONLY clock positions — the four times a consumer device tracks
    competently. `sleep_latency_min` / `waso_min` are never here: the device
    systematically under-scores wakefulness, and a prefilled-low WASO inflates
    diary SE, opening the window before the sleep it is opened for exists (#117).
    Those two stay manual by design.

    `gate_rejected` distinguishes "no device data" (all None, flag False) from
    "device data suppressed as implausible" (all None, flag True) so the surface
    can say which — a rejected prefill leaves the fields empty for manual entry
    and never degrades to the raw device value.
    """
    got_into_bed: Optional[str] = None
    lights_out: Optional[str] = None
    final_wake: Optional[str] = None
    out_of_bed: Optional[str] = None
    gate_rejected: bool = False


def _diary_prefill(
    bedtime: Optional[str],
    wake_time: Optional[str],
    prescribed_lights_out: Optional[str],
) -> DiaryPrefillOut:
    """Map Samsung clock values to diary defaults, gated against the prescription.

    `bedtime` maps to `got_into_bed` — VERIFIED bed-entry, not sleep onset: over 31
    real passive-overnight nights the span (wake − bedtime) exceeded scored sleep by
    a median +35 min (30/31 positive), which is the latency + WASO you would expect
    if bedtime is when you got INTO bed. `lights_out` defaults to `got_into_bed`
    (#117); the operator edits it down on nights the two diverge, and because that
    edit moves the SE denominator the diary self-corrects even if this default is
    wrong. `wake_time` defaults both wake-side fields — the device emits one wake
    clock, and `out_of_bed`/`final_wake` are refined by hand.

    THE GATE (#110 — a gate proves nothing without a demonstrated rejection): if the
    prefilled lights-out is more than 4h from the prescription, the source clock is
    corrupt (12-hour format), so EVERY clock prefill is suppressed — the corruption
    is global to the phone clock, not local to one field. Suppression returns empty
    fields flagged `gate_rejected`; it never falls back to the raw device value.
    With no prescription in force there is no reference to gate against, so values
    pass ungated — recoverable, since these are editable defaults, not stored values.
    """
    got = bedtime
    if got is not None and prescribed_lights_out is not None:
        delta = clock_delta_minutes(got, prescribed_lights_out)
        if delta is not None and abs(delta) > PREFILL_GATE_MAX_DELTA_MIN:
            return DiaryPrefillOut(gate_rejected=True)
    return DiaryPrefillOut(
        got_into_bed=got,
        lights_out=got,          # default to got_into_bed (#117)
        final_wake=wake_time,
        out_of_bed=wake_time,
    )


class TodayOut(BaseModel):
    """PM close-out's view: today's record if it exists, plus the CBT-I context.

    Every record field is optional and the endpoint ALWAYS returns an object —
    previously it returned the record or null. PM must display the prescribed
    lights-out on a day with no AM check-in yet, and a null response cannot carry
    it. The record fields stay FLAT rather than nested under a `record` key
    because `NightlyCloseOut.jsx` reads them as `data?.pm_timestamp` etc.;
    flattening keeps those reads working and makes `cbti` a purely additive
    sibling key.
    """
    id: Optional[int] = None
    # `_dt.date`, NOT `date`: this file has no `from __future__ import annotations`,
    # so annotations evaluate EAGERLY at class-body time. CPython binds a field's
    # default into the class namespace BEFORE evaluating its annotation, so
    # `date: Optional[date] = None` first lands `date = None`, then the annotation's
    # `LOAD_NAME date` finds that None instead of datetime.date — the field collapses
    # to Optional[None] and rejects every real record. The corruption is POSITIONAL:
    # this line and any LATER `date`-annotated field in this body would break; fields
    # declared earlier are fine. DailyRecordOut escapes it only because `date: date`
    # has no default, so nothing is bound. Caught by the flat-field shape test.
    date: Optional[_dt.date] = None
    am_timestamp: Optional[datetime] = None
    pm_timestamp: Optional[datetime] = None
    today_rating: Optional[int] = None
    session_quality: Optional[int] = None
    session_rpe: Optional[float] = None
    cbti: CBTIContextOut = Field(default_factory=CBTIContextOut)

    model_config = {"from_attributes": True}


class AMPrefillOut(BaseModel):
    hrv_ms: Optional[float] = None
    hrv_vs_baseline: Optional[float] = None
    sleep_min: Optional[int] = None
    morning_readiness: int = 3
    sleep_quality: int = 3
    fatigue: int = 5
    soreness: dict = Field(default_factory=dict)   # derived from active injuries at request time
    motivation: int = 5
    life_load: int = 3
    # Today's record if it already exists (allows re-entry pre-PM)
    existing: Optional[DailyRecordOut] = None
    # CBT-I block status + prescription in force. Additive: CheckInAM.jsx reads
    # flat keys off this object, so a new sibling key breaks nothing.
    cbti: CBTIContextOut = Field(default_factory=CBTIContextOut)
    # Editable clock defaults for the diary, gated against the prescription. Empty
    # (and unrendered) unless a block is open. Additive sibling, same as `cbti`.
    diary_prefill: DiaryPrefillOut = Field(default_factory=DiaryPrefillOut)


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
            models.SamsungHRVReading.context != 'session',
        )
        .order_by(models.SamsungHRVReading.captured_at.desc())
        .limit(7)
        .all()
    )
    hrv_values = [r.hrv_ms for r in hrv_baseline_rows if r.hrv_ms is not None]
    baseline = sum(hrv_values) / len(hrv_values) if hrv_values else None
    vs_baseline = round(hrv_ms - baseline, 1) if (hrv_ms and baseline) else None

    cbti_ctx = _cbti_context(current_user.id, today, db)
    diary_prefill = DiaryPrefillOut()
    if cbti_ctx.block_open:
        # Fresh read on the `passive_overnight` ALLOWLIST — not the `!= 'session'`
        # denylist the readiness snapshot uses (that admits `calibration`; see the
        # guard row in ROADMAP). The diary must not be seeded from a non-overnight
        # reading.
        sam = (
            db.query(models.SamsungHRVReading)
            .filter(
                models.SamsungHRVReading.user_id == current_user.id,
                models.SamsungHRVReading.captured_at <= today,
                models.SamsungHRVReading.context == 'passive_overnight',
                models.SamsungHRVReading.bedtime.isnot(None),
            )
            .order_by(models.SamsungHRVReading.captured_at.desc())
            .first()
        )
        if sam is not None:
            diary_prefill = _diary_prefill(
                sam.bedtime, sam.wake_time, cbti_ctx.prescribed_lights_out
            )

    return AMPrefillOut(
        hrv_ms=hrv_ms,
        hrv_vs_baseline=vs_baseline,
        sleep_min=passive["passive_sleep_min"],
        soreness=derive_soreness_items(current_user.id, db),
        existing=existing,
        cbti=cbti_ctx,
        diary_prefill=diary_prefill,
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


@router.get("/today", response_model=TodayOut)
def get_today(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Always returns an object, never null — see TodayOut. The prescribed
    lights-out must be displayable on a day with no AM check-in yet."""
    today = _today_aest()
    record = db.query(models.DailyRecord).filter_by(
        user_id=current_user.id, date=today
    ).first()
    out = TodayOut.model_validate(record) if record is not None else TodayOut()
    out.cbti = _cbti_context(current_user.id, today, db)
    return out


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
