from datetime import date
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db
from routers.knowledge import KnowledgeEntryIn, upsert_knowledge_entry

router = APIRouter(tags=["health"])


# ---------- schemas ----------

class AnalyseSessionBody(BaseModel):
    workout_id: str
    workout_data: dict[str, Any]


# ---------- helpers ----------

def _epley_1rm(weight_kg: float, reps: int) -> float:
    return round(weight_kg * (1 + reps / 30), 1)


def _serialize_reading(r: models.SamsungHRVReading) -> dict[str, Any]:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "captured_at": str(r.captured_at) if r.captured_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "hrv_ms": r.hrv_ms,
        "sleep_hr_bpm": r.sleep_hr_bpm,
        "respiratory_rate": r.respiratory_rate,
        "sleep_efficiency_pct": r.sleep_efficiency_pct,
        "actual_sleep_time_minutes": r.actual_sleep_time_minutes,
        "sleep_duration_home_tile": r.sleep_duration_home_tile,
        "bedtime": r.bedtime,
        "wake_time": r.wake_time,
        "awake_minutes": r.awake_minutes,
        "rem_minutes": r.rem_minutes,
        "light_minutes": r.light_minutes,
        "deep_minutes": r.deep_minutes,
        "awake_pct": r.awake_pct,
        "rem_pct": r.rem_pct,
        "light_pct": r.light_pct,
        "deep_pct": r.deep_pct,
        "total_sleep_time_minutes": r.total_sleep_time_minutes,
        "spo2_average_pct": r.spo2_average_pct,
        "extraction_method": r.extraction_method,
    }


def _compute_workout_stats(workout_data: dict[str, Any]) -> dict[str, Any]:
    exercises = workout_data.get("exercises", [])
    muscle_groups: list[str] = []
    total_volume_kg = 0.0
    total_sets = 0
    top_1rm: dict[str, float] = {}

    for ex in exercises:
        title = (ex.get("title") or ex.get("exercise_template_id") or "Unknown").strip()
        if title not in muscle_groups:
            muscle_groups.append(title)

        for s in ex.get("sets", []):
            if s.get("type") == "warmup":
                continue
            total_sets += 1
            weight = s.get("weight_kg")
            reps = s.get("reps")
            if weight and reps and weight > 0 and reps > 0:
                total_volume_kg += weight * reps
                rm = _epley_1rm(weight, reps)
                if title not in top_1rm or rm > top_1rm[title]:
                    top_1rm[title] = rm

    return {
        "muscle_groups": muscle_groups,
        "total_volume_kg": round(total_volume_kg, 1),
        "total_sets": total_sets,
        "top_1rm": top_1rm,
    }


# ---------- endpoints ----------

@router.get("/summary")
def get_health_summary(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    readings = (
        db.query(models.SamsungHRVReading)
        .filter_by(user_id=current_user.id)
        .order_by(models.SamsungHRVReading.captured_at.desc())
        .limit(7)
        .all()
    )

    if not readings:
        return {"latest": None, "trend": [], "baseline_hrv": None, "vs_baseline": None}

    latest = readings[0]
    trend = [
        {"captured_at": str(r.captured_at), "hrv_ms": r.hrv_ms}
        for r in readings
    ]
    hrv_values = [r.hrv_ms for r in readings if r.hrv_ms is not None]
    baseline_hrv = round(sum(hrv_values) / len(hrv_values), 1) if hrv_values else None
    vs_baseline = (
        round(latest.hrv_ms - baseline_hrv, 1)
        if baseline_hrv is not None and latest.hrv_ms is not None
        else None
    )

    return {
        "latest": _serialize_reading(latest),
        "trend": trend,
        "baseline_hrv": baseline_hrv,
        "vs_baseline": vs_baseline,
    }


@router.post("/analyse-session")
def analyse_session(
    body: AnalyseSessionBody,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workout_data = body.workout_data
    workout_title = (workout_data.get("title") or workout_data.get("name") or "Untitled").strip()
    raw_date = workout_data.get("start_time") or workout_data.get("created_at") or ""
    workout_date = raw_date[:10] if raw_date else None

    readiness_context = None
    if workout_date:
        try:
            hrv_row = (
                db.query(models.SamsungHRVReading)
                .filter_by(user_id=current_user.id, captured_at=date.fromisoformat(workout_date))
                .first()
            )
            if hrv_row:
                readiness_context = {
                    "hrv_ms": hrv_row.hrv_ms,
                    "sleep_efficiency_pct": hrv_row.sleep_efficiency_pct,
                }
        except ValueError:
            pass

    stats = _compute_workout_stats(workout_data)

    entry_value: dict[str, Any] = {
        "workout_id": body.workout_id,
        "workout_title": workout_title,
        "workout_date": workout_date,
        "muscle_groups": stats["muscle_groups"],
        "total_volume_kg": stats["total_volume_kg"],
        "total_sets": stats["total_sets"],
        "top_1rm": stats["top_1rm"],
        "readiness_context": readiness_context,
    }

    entry_in = KnowledgeEntryIn(
        type="session_analysis",
        key=f"session_{body.workout_id}",
        value=entry_value,
        source="system",
        expires_at=None,
        notes=None,
    )
    new_entry = upsert_knowledge_entry(current_user.id, entry_in, db)
    return new_entry.value


@router.get("/session-analysis/{workout_id}")
def get_session_analysis(
    workout_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(
            user_id=current_user.id,
            key=f"session_{workout_id}",
            type="session_analysis",
            active=True,
        )
        .first()
    )
    return entry.value if entry else None


@router.get("/latest-session-analysis")
def get_latest_session_analysis(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=current_user.id, type="session_analysis", active=True)
        .order_by(models.UserKnowledgeEntry.added_at.desc())
        .first()
    )
    return entry.value if entry else None
