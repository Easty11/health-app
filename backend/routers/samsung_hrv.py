"""
Receives Samsung Health HRV readings extracted via the accessibility
service on the companion Android app.

Upserts on (user_id, captured_at) — a re-run on the same day overwrites.
"""
from datetime import date
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/samsung-hrv", tags=["samsung-hrv"])

HRVContext = Literal["passive_overnight", "calibration", "session"]


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
