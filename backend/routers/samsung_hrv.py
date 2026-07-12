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
from database import get_db

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

    db.commit()
    return {"synced": len(body.readings)}
