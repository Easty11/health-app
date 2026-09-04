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
from reads.recovery_reads import canonical_hrv

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

    # ----- Source-agnostic HRV: canonical nightly readings (Q130) -----
    # Sourced from reads.recovery_reads.canonical_hrv over hrv_readings (Garmin +,
    # after the Samsung unification, Samsung). Additive sibling of the device blocks —
    # `samsung` and `health_connect` above are left exactly as they are.
    hrv_week = [r for r in canonical_hrv(current_user.id, db, since=week_start) if r.canonical]
    # Fall back to the newest canonical night even if older than 7 days (mirrors the
    # samsung block's fallback), so a user who hasn't synced this week still sees `latest`.
    if hrv_week:
        hrv_latest_row = hrv_week[0]  # canonical_hrv returns captured_at desc
    else:
        hrv_latest_row = next(
            (r for r in canonical_hrv(current_user.id, db) if r.canonical), None
        )

    hrv_latest = None
    if hrv_latest_row is not None:
        hrv_latest = {
            "captured_at": hrv_latest_row.captured_at,
            "rmssd_ms": hrv_latest_row.rmssd_ms,
            "source": hrv_latest_row.source,
            "status": hrv_latest_row.status,
            "baseline_low": hrv_latest_row.baseline_low,
            "baseline_high": hrv_latest_row.baseline_high,
        }

    hrv_trend = [{"date": r.captured_at, "rmssd": r.rmssd_ms} for r in hrv_week]
    hrv_values = [r.rmssd_ms for r in hrv_week if r.rmssd_ms is not None]
    hrv_baseline_mean = round(mean(hrv_values), 1) if hrv_values else None
    hrv_baseline_sd = round(pstdev(hrv_values), 1) if len(hrv_values) >= 2 else None

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
        "hrv": {
            "latest": hrv_latest,
            "trend": hrv_trend,
            "baseline_mean": hrv_baseline_mean,
            "baseline_sd": hrv_baseline_sd,
            "baseline_n": len(hrv_values),
        },
        "has_data": bool(samsung_today or health_connect),
    }
