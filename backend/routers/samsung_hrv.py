"""
Receives Samsung Health HRV readings extracted via the accessibility
service on the companion Android app.

Upserts on (user_id, captured_at) — a re-run on the same day overwrites.
"""
import logging
from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, model_validator
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from connectors.garmin import _bounded_rmssd
from database import get_db
from routers.garmin import _upsert_hrv_day

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/samsung-hrv", tags=["samsung-hrv"])

HRVContext = Literal["passive_overnight", "calibration", "session"]

# Physiological / definitional bounds for one night of overnight biometrics.
# A value outside its range is corrupt at source, not a signal — the pipeline is
# faithful, the number is simply wrong before it reaches us (e.g. Samsung reported
# sleep efficiency 119% on 2026-06-28, a hard impossibility). Such a value is
# nulled at ingest and logged; the rest of the night's valid fields are kept.
# See DECISIONS_LOG — HRV & Sleep Data Integrity brief, Task 3.
_BOUNDS: dict[str, tuple[float, float]] = {
    "hrv_ms": (1, 400),
    "sleep_hr_bpm": (20, 200),
    "respiratory_rate": (4, 40),
    "sleep_efficiency_pct": (0, 100),
    "actual_sleep_time_minutes": (0, 1440),
    "total_sleep_time_minutes": (0, 1440),
    "awake_minutes": (0, 1440),
    "rem_minutes": (0, 1440),
    "light_minutes": (0, 1440),
    "deep_minutes": (0, 1440),
    "awake_pct": (0, 100),
    "rem_pct": (0, 100),
    "light_pct": (0, 100),
    "deep_pct": (0, 100),
    "spo2_average_pct": (0, 100),
}


class HRVReadingIn(BaseModel):
    captured_at: date
    hrv_ms: Optional[float] = None
    sleep_hr_bpm: Optional[int] = None
    respiratory_rate: Optional[float] = None
    sleep_efficiency_pct: Optional[int] = None
    actual_sleep_time_minutes: Optional[int] = None
    sleep_duration_home_tile: Optional[str] = None
    bedtime: Optional[str] = None
    wake_time: Optional[str] = None
    awake_minutes: Optional[int] = None
    rem_minutes: Optional[int] = None
    light_minutes: Optional[int] = None
    deep_minutes: Optional[int] = None
    awake_pct: Optional[int] = None
    rem_pct: Optional[int] = None
    light_pct: Optional[int] = None
    deep_pct: Optional[int] = None
    total_sleep_time_minutes: Optional[int] = None
    spo2_average_pct: Optional[float] = None
    extraction_method: str = "accessibility"
    context: HRVContext = "passive_overnight"

    @model_validator(mode="after")
    def _reject_out_of_range(self) -> "HRVReadingIn":
        for field, (lo, hi) in _BOUNDS.items():
            v = getattr(self, field)
            if v is not None and not (lo <= v <= hi):
                logger.warning(
                    "samsung-hrv ingest: rejected out-of-range %s=%s "
                    "(valid %s–%s) for captured_at=%s; nulled the field",
                    field, v, lo, hi, self.captured_at,
                )
                setattr(self, field, None)
        return self


def _mirror_passive_overnight_hrv(db: Session, user_id: int, r: "HRVReadingIn") -> None:
    """Dual-write a Samsung nightly HRV value into the source-agnostic `hrv_readings`
    store (source='samsung') so `reads.recovery_reads.canonical_hrv` sees it (Q130).

    Only the `passive_overnight` reading is a nightly HRV value; `calibration`/`session`
    are not mirrored. `hrv_ms` is revalidated through the connector's shared RMSSD bounds
    guard (a None/out-of-range value is skipped — the pydantic layer already nulls out-of
    range, this is belt-and-suspenders and the single reuse point). Samsung is nightly-only
    → `samples=[]`; `status`/`baseline`/`weekly_avg` stay NULL (Samsung supplies none).

    Additive: the `samsung_hrv_readings` write is unchanged. `_upsert_hrv_day` upserts the
    night in place, so a re-scrape updates the value without duplicating — and because a
    Samsung night carries no samples, the replace-on-reingest of samples has nothing to lose.
    """
    if r.context != "passive_overnight":
        return
    rmssd = _bounded_rmssd(r.hrv_ms, cdate=r.captured_at.isoformat(), field="samsung.hrv_ms")
    if rmssd is None:
        return
    _upsert_hrv_day(
        db, user_id, "samsung",
        {"captured_at": r.captured_at, "reading": {"rmssd_ms": rmssd}, "samples": []},
    )


class SyncRequest(BaseModel):
    readings: List[HRVReadingIn]


@router.post("/sync")
def sync_readings(
    body: SyncRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    for r in body.readings:
        values = {"user_id": current_user.id, **r.model_dump()}
        stmt = (
            insert(models.SamsungHRVReading)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_samsung_hrv_user_date_context",
                set_={
                    k: v for k, v in values.items()
                    if k not in ("user_id", "captured_at")
                },
            )
        )
        db.execute(stmt)
        # Dual-write the nightly HRV into the source-agnostic store (Q130). Additive —
        # the samsung_hrv_readings write above is unchanged.
        _mirror_passive_overnight_hrv(db, current_user.id, r)

    db.commit()
    return {"synced": len(body.readings)}
