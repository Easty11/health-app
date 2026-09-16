from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, or_, select
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


# Fidelity rank when two sources report the same night — the richer source wins the
# single headline figure (garmin carries the 5-min series + status band; samsung is
# nightly-only). Mirrors reads.recovery_reads._SOURCE_RANK; an unknown source ranks below
# both. NEVER used to blend: the picker returns ONE source's reading, labelled — raw ms of
# different instruments is never averaged (that offset is non-constant; see #292).
_HRV_SOURCE_RANK = {"garmin": 2, "samsung": 1}


def _pick_latest_hrv(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Newest HRV reading across sources, source-labelled — or None.

    `candidates`: dicts carrying at least `captured_at` (date) and `hrv_ms`, plus a
    `source` tag. The newest `captured_at` wins; a same-night tie breaks to the richer
    source (garmin > samsung > unknown), deterministic so a contested night always yields
    exactly one headline and neither source is silently dropped from the payload — the
    full multi-source set still travels in `trend`. Candidates without an `hrv_ms` are
    ignored (nothing to headline)."""
    usable = [c for c in candidates if c.get("hrv_ms") is not None]
    if not usable:
        return None
    return max(
        usable,
        key=lambda c: (c["captured_at"], _HRV_SOURCE_RANK.get(c.get("source") or "", 0)),
    )


# ── Card sleep: freshest staged sleep across sources, source-labelled ─────────────────
# The card's sleep block used to read ONLY the Samsung scraper table (samsung_hrv_readings),
# which froze when the Samsung ring died — so a live Garmin-only night showed sleep days
# stale. This repoints it to the NEWEST-available staged night across {samsung scraper,
# Health Connect aggregate}, source-labelled and dated. The check-in already reads the HC
# aggregate for sleep (checkin_v2._snapshot_passive); the card now agrees on source. NOT a
# blend and NOT ingestion — the HC data is already staged; this is a read-path repoint.
#
# Health Connect record identity (HC → package) as it actually arrives in
# health_connect_record_sources.source_package.
# Health Connect writer package → friendly source, as the packages actually arrive in
# health_connect_record_sources.source_package. Withings is here because it IS a real HC
# sleep writer historically (Q83) even though it is disabled on live nights — so a
# Samsung+Withings night is recognised as multi-source, not misattributed to Samsung.
_SLEEP_SOURCE_BY_PACKAGE = {
    "com.garmin.android.apps.connectmobile": "garmin",
    "com.sec.android.app.shealth": "samsung",
    "com.withings.wiscale2": "withings",
}
_SLEEP_SOURCE_LABELS = {"garmin": "Garmin", "samsung": "Samsung", "withings": "Withings"}


def _resolve_hc_sleep_source(db: Session, user_id: int, night: date) -> tuple[str, str]:
    """(source_key, display_label) for a Health-Connect sleep night, from the per-record
    writer identities in health_connect_record_sources.

    JOIN WINDOW — a sleep session's `record_start` is its START timestamp, whose local date
    is normally the calendar day BEFORE the wake-date that `health_connect_syncs` is keyed on
    (bedtime the prior evening). So match `record_start` on {night, night-1}, record_type
    'sleep'.

    Multiplicity is judged on DISTINCT REAL packages (the 'unknown' pre-cutover sentinel does
    not count as a source): two or more → the aggregate is a blend, 'Health Connect (multiple)'
    — never misattribute a blend to one device (Decision B; mirrors the HRV multi-source
    guard), and this holds even when only one of the two is a package we have a friendly name
    for. Exactly one real package → its chip if known, else generic 'Health Connect' (a real
    but unlabelled writer, honest: we know it is HC, not which device). None/only-'unknown' →
    generic 'Health Connect'."""
    days = [night.isoformat(), (night - timedelta(days=1)).isoformat()]
    rows = db.execute(
        select(models.HealthConnectRecordSource.source_package)
        .where(
            models.HealthConnectRecordSource.user_id == user_id,
            models.HealthConnectRecordSource.record_type == "sleep",
            func.substr(models.HealthConnectRecordSource.record_start, 1, 10).in_(days),
        )
        .distinct()
    ).all()
    packages = {pkg for (pkg,) in rows if pkg and pkg != "unknown"}
    if len(packages) >= 2:
        return "multiple", "Health Connect (multiple)"
    if len(packages) == 1:
        key = _SLEEP_SOURCE_BY_PACKAGE.get(next(iter(packages)))
        if key:
            return key, _SLEEP_SOURCE_LABELS[key]
    return "health_connect", "Health Connect"


def _build_latest_sleep(db: Session, user_id: int) -> dict[str, Any] | None:
    """Freshest staged sleep night across the Samsung scraper table and the Health Connect
    aggregate, source-labelled and dated. Newest wake-date wins; a same-night tie prefers the
    HC aggregate (richer, and honestly labelled including 'multiple').

    Fields the winning source does not carry are None — the card renders '—'. The HC aggregate
    stores only the asleep-union stages (deep/rem/light, summing to duration) plus a score, so
    efficiency %, awake/WASO, respiratory rate, sleep HR, SpO2 and bedtime/wake are genuinely
    absent for an HC night (no in-bed span is staged to derive WASO from) → '—', never mixed
    with another night's Samsung values under the same header."""
    hc = (
        db.query(models.HealthConnectSync)
        .filter(
            models.HealthConnectSync.user_id == user_id,
            models.HealthConnectSync.sleep_duration_minutes.isnot(None),
        )
        .order_by(models.HealthConnectSync.date.desc())
        .first()
    )
    samsung = (
        db.query(models.SamsungHRVReading)
        .filter(
            models.SamsungHRVReading.user_id == user_id,
            models.SamsungHRVReading.context != "session",
            or_(
                models.SamsungHRVReading.total_sleep_time_minutes.isnot(None),
                models.SamsungHRVReading.actual_sleep_time_minutes.isnot(None),
            ),
        )
        .order_by(models.SamsungHRVReading.captured_at.desc())
        .first()
    )

    hc_night = hc.date if hc else None
    samsung_night = samsung.captured_at if samsung else None

    # HC wins when it exists and is not older than the freshest Samsung night (tie → HC).
    if hc_night is not None and (samsung_night is None or hc_night >= samsung_night):
        source, label = _resolve_hc_sleep_source(db, user_id, hc_night)
        return {
            "night": hc_night.isoformat(),
            "source": source,
            "source_label": label,
            "duration_min": hc.sleep_duration_minutes,
            "deep_min": hc.deep_sleep_minutes,
            "rem_min": hc.rem_sleep_minutes,
            "light_min": hc.light_sleep_minutes,
            "score": hc.sleep_score,
            # Not staged by the HC aggregate → honest '—' (Decision A(a); no split-night mix):
            "efficiency_pct": None,
            "awake_min": None,
            "resp_rate": None,
            "sleep_hr_bpm": None,
            "spo2_pct": None,
            "bedtime": None,
            "wake_time": None,
        }
    if samsung_night is not None:
        return {
            "night": samsung_night.isoformat(),
            "source": "samsung",
            "source_label": "Samsung",
            "duration_min": (
                samsung.total_sleep_time_minutes
                if samsung.total_sleep_time_minutes is not None
                else samsung.actual_sleep_time_minutes
            ),
            "deep_min": samsung.deep_minutes,
            "rem_min": samsung.rem_minutes,
            "light_min": samsung.light_minutes,
            "score": None,
            "efficiency_pct": samsung.sleep_efficiency_pct,
            "awake_min": samsung.awake_minutes,
            "resp_rate": samsung.respiratory_rate,
            "sleep_hr_bpm": samsung.sleep_hr_bpm,
            "spo2_pct": samsung.spo2_average_pct,
            "bedtime": samsung.bedtime,
            "wake_time": samsung.wake_time,
        }
    return None


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
        "context": r.context,
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
        .filter(
            models.SamsungHRVReading.user_id == current_user.id,
            models.SamsungHRVReading.context != 'session',
        )
        .order_by(models.SamsungHRVReading.captured_at.desc())
        .limit(7)
        .all()
    )

    # ── Source-agnostic "latest HRV across sources" (Q130/#292) ──────────────────────
    # The Samsung `latest`/`trend`/baseline below stay exactly as they were — sleep
    # architecture and the samsung-native baseline are device data. This ADDS a headline
    # HRV figure that is the newest reading across every source (Garmin included), each
    # candidate carrying its `source` so the card can label provenance and never silently
    # prefer Samsung. Candidates: every `hrv_readings` row (Garmin, plus Samsung nights the
    # scraper mirror dual-writes) AND the newest Samsung device row — so a Samsung night
    # that predates the mirror (the backfill migration is held) is never dropped from the
    # headline. The pick is newest-wins, tie→richer source; it selects ONE labelled
    # reading and never blends raw ms across instruments.
    hrv_rows = (
        db.query(models.HrvReading)
        .filter(models.HrvReading.user_id == current_user.id)
        .order_by(models.HrvReading.captured_at.desc())
        .all()
    )
    hrv_candidates: list[dict[str, Any]] = [
        {
            "captured_at": r.captured_at,
            "hrv_ms": r.rmssd_ms,
            "source": r.source,
            "status": r.status,
            "baseline_low": r.baseline_low,
            "baseline_high": r.baseline_high,
        }
        for r in hrv_rows
    ]
    if readings and readings[0].hrv_ms is not None:
        hrv_candidates.append({
            "captured_at": readings[0].captured_at,
            "hrv_ms": readings[0].hrv_ms,
            "source": "samsung",
            "status": None,
            "baseline_low": None,
            "baseline_high": None,
        })
    picked = _pick_latest_hrv(hrv_candidates)
    latest_hrv = None
    if picked is not None:
        latest_hrv = {
            "captured_at": str(picked["captured_at"]),
            "hrv_ms": picked["hrv_ms"],
            "source": picked["source"],
            "status": picked["status"],
            "baseline_low": picked["baseline_low"],
            "baseline_high": picked["baseline_high"],
        }

    # Freshest staged sleep across sources (Garmin/HC + Samsung), source-labelled and dated —
    # independent of the Samsung-native HRV path above. Computed unconditionally so a
    # Garmin-only user (no Samsung device row) still gets last night's sleep.
    latest_sleep = _build_latest_sleep(db, current_user.id)

    if not readings:
        # No Samsung device row (sleep/baseline unavailable), but a source-agnostic HRV
        # reading may still exist (e.g. a Garmin-only user) — surface it, don't blank out.
        return {
            "latest": None, "trend": [], "baseline_hrv": None, "vs_baseline": None,
            "latest_hrv": latest_hrv, "latest_sleep": latest_sleep,
        }

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
        "latest_hrv": latest_hrv,
        "latest_sleep": latest_sleep,
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
                .filter(
                    models.SamsungHRVReading.user_id == current_user.id,
                    models.SamsungHRVReading.captured_at == date.fromisoformat(workout_date),
                    models.SamsungHRVReading.context != 'session',
                )
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
