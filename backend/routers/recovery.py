"""
Aggregated recovery/health summary for the dashboard HealthPanel:
  - latest Samsung Galaxy Ring scraper reading (today's readiness)
  - 7-day HRV trend + rolling mean/SD baseline
  - latest Health Connect daily-aggregate sync

Note: Health Connect is stored as one daily-aggregate row per date
(health_connect_syncs), so per-type sample/session/workout *counts* are not
available — the aggregate metrics that ARE stored are returned instead.
"""
from datetime import datetime as _dt, timedelta
from statistics import mean, pstdev

import pytz
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/recovery", tags=["recovery"])

AEST = pytz.timezone("Australia/Brisbane")


@router.get("/summary")
def get_summary(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = _dt.now(AEST).date()

    # ----- Samsung Galaxy Ring: last 7 days + latest -----
    week_start = today - timedelta(days=7)
    readings = (
        db.query(models.SamsungHRVReading)
        .filter(
            models.SamsungHRVReading.user_id == current_user.id,
            models.SamsungHRVReading.captured_at >= week_start,
            models.SamsungHRVReading.context != 'session',
        )
        .order_by(models.SamsungHRVReading.captured_at.desc())
        .all()
    )
    # Fall back to the most recent reading even if it's older than 7 days.
    latest = readings[0] if readings else (
        db.query(models.SamsungHRVReading)
        .filter(
            models.SamsungHRVReading.user_id == current_user.id,
            models.SamsungHRVReading.context != 'session',
        )
        .order_by(models.SamsungHRVReading.captured_at.desc())
        .first()
    )

    samsung_today = None
    if latest is not None:
        samsung_today = {
            "captured_at": latest.captured_at,
            "hrv_ms": latest.hrv_ms,
            "sleep_hr_bpm": latest.sleep_hr_bpm,
            "respiratory_rate": latest.respiratory_rate,
            "spo2_average_pct": latest.spo2_average_pct,
            "sleep_efficiency_pct": latest.sleep_efficiency_pct,
            "sleep_duration_minutes": (
                latest.total_sleep_time_minutes or latest.actual_sleep_time_minutes
            ),
            "deep_minutes": latest.deep_minutes,
            "rem_minutes": latest.rem_minutes,
            "light_minutes": latest.light_minutes,
            "awake_minutes": latest.awake_minutes,
            "bedtime": latest.bedtime,
            "wake_time": latest.wake_time,
        }

    trend = [{"date": r.captured_at, "rmssd": r.hrv_ms} for r in readings]
    rmssd_values = [r.hrv_ms for r in readings if r.hrv_ms is not None]
    baseline_mean = round(mean(rmssd_values), 1) if rmssd_values else None
    baseline_sd = round(pstdev(rmssd_values), 1) if len(rmssd_values) >= 2 else None

    # ----- Health Connect: latest daily-aggregate sync -----
    hc_latest = (
        db.query(models.HealthConnectSync)
        .filter_by(user_id=current_user.id)
        .order_by(models.HealthConnectSync.date.desc())
        .first()
    )
    hc_total = (
        db.query(models.HealthConnectSync)
        .filter_by(user_id=current_user.id)
        .count()
    )
    health_connect = None
    if hc_latest is not None:
        health_connect = {
            "last_synced": hc_latest.synced_at.isoformat() if hc_latest.synced_at else None,
            "date": hc_latest.date,
            "steps": hc_latest.steps,
            "resting_heart_rate": hc_latest.resting_heart_rate,
            "hrv_rmssd": hc_latest.hrv_rmssd,
            "sleep_duration_minutes": hc_latest.sleep_duration_minutes,
            "sleep_score": hc_latest.sleep_score,
            "total_days_synced": hc_total,
        }

    return {
        "samsung": {
            "today": samsung_today,
            "trend": trend,
            "baseline_mean": baseline_mean,
            "baseline_sd": baseline_sd,
            "baseline_n": len(rmssd_values),
        },
        "health_connect": health_connect,
        "has_data": bool(samsung_today or health_connect),
    }
