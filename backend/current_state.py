"""
current_state(user_id, db, today) -> CurrentState

Compute-on-read read model over stores that already exist: active
`user_knowledge_entries`, `fortification_profiles`, `capability_state`,
plus baselines computed at read time (v1: the 7-day HRV rolling baseline).
Introduces no new schema.

Resolves OPEN_QUESTIONS Q8 / DECISIONS_LOG #43 — this is the queryable
replacement for state that previously existed only as `context_builder`
prompt text. `context_builder` consumes this module as a formatter;
Decision Support and the appointment brief can query it directly instead
of re-deriving current state from raw tables.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

import models
from declared_state import lift_declared_state
from engine import profile as profile_mod
from reads.labs_reads import LabRow, latest_lab_results


@dataclass
class HRVBaseline:
    mean_ms: float
    n: int
    latest_ms: float | None
    diff_from_mean_ms: float | None


@dataclass
class CurrentState:
    knowledge_entries: list[models.UserKnowledgeEntry] = field(default_factory=list)
    device_profile: dict | None = None
    # The user's declared stack, keyed by type (protocol/supplement/behavioural),
    # each factor carrying its phase derived as_of today. What 4b's phase-aware
    # gates and the contract's protocol_context_snapshot consume. Reads empty
    # until the Railway seed runs (§8 — landed != live).
    declared_state: dict = field(default_factory=dict)
    fortification_profile: dict | None = None
    fortification_profile_orm: models.FortificationProfile | None = None
    capability_state: list[models.CapabilityState] = field(default_factory=list)
    hrv_baseline_7d: HRVBaseline | None = None
    labs: list[LabRow] = field(default_factory=list)


def current_state(user_id: int, db: Session, today: date) -> CurrentState:
    entries = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=user_id, active=True)
        .order_by(models.UserKnowledgeEntry.added_at.desc())
        .all()
    )

    device_profile = None
    for e in entries:
        if e.type == "preference" and e.key == "device_profile":
            device_profile = e.value
            break

    fort_profile_orm = profile_mod.get_profile(db, user_id)

    capability_rows = db.query(models.CapabilityState).filter_by(user_id=user_id).all()

    window_start = today - timedelta(days=7)
    hrv_readings = (
        db.query(models.SamsungHRVReading)
        .filter(
            models.SamsungHRVReading.user_id == user_id,
            models.SamsungHRVReading.captured_at >= window_start,
            models.SamsungHRVReading.context != "session",
        )
        .order_by(models.SamsungHRVReading.captured_at.desc())
        .all()
    )
    hrv_values = [r.hrv_ms for r in hrv_readings if r.hrv_ms is not None]
    hrv_baseline = None
    if hrv_values:
        mean = sum(hrv_values) / len(hrv_values)
        latest_ms = hrv_readings[0].hrv_ms
        hrv_baseline = HRVBaseline(
            mean_ms=mean,
            n=len(hrv_values),
            latest_ms=latest_ms,
            diff_from_mean_ms=(latest_ms - mean) if latest_ms is not None else None,
        )

    labs = latest_lab_results(user_id, db)

    return CurrentState(
        knowledge_entries=entries,
        device_profile=device_profile,
        declared_state=lift_declared_state(entries, today),
        fortification_profile=profile_mod.profile_to_dict(fort_profile_orm),
        fortification_profile_orm=fort_profile_orm,
        capability_state=capability_rows,
        hrv_baseline_7d=hrv_baseline,
        labs=labs,
    )
