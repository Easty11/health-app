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

import logging
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

import models
from declared_state import lift_declared_state
from engine import profile as profile_mod
from engine import resolver as resolver_mod
from engine import training_phase as training_phase_mod

logger = logging.getLogger(__name__)
from reads.labs_reads import LabRow, latest_lab_results
from reads.recovery_reads import hrv_deviation, representative_source


@dataclass
class HRVBaseline:
    mean_ms: float
    n: int
    latest_ms: float | None
    diff_from_mean_ms: float | None
    # Deviation-reader verdict on baseline trust (#292): "normal" | "settling" |
    # "building". "settling" = within SETTLING_NIGHTS of an active training-phase change
    # (#294/#295) — the deviation is real but its confidence is capped; a consumer
    # surfacing the number should flag it. None only for legacy callers that predate #295.
    baseline_state: str | None = None


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
    # The open training phase (Q112, #270) — DOING-NOW to the profile's BUILDING-TOWARD.
    # None = baseline (zero-open). `review_due` is folded into the dict at read time.
    training_phase: dict | None = None
    training_phase_orm: models.TrainingPhase | None = None
    # The plan of record (#312) — the macro plan the coach reads every turn, its `value`
    # (macro/revised_on/revised_by). None = no plan → the render section is omitted (context
    # byte-identical to pre-#312). Exactly one active row per user (fixed key, enforced at write).
    training_plan: dict | None = None
    # Phase→Hevy-folder declaration (#314) — a `type=preference` entry, `value` = {phase_label:
    # folder_id}, mapping which Hevy routine folder holds a phase's full-detail working set. None
    # = undeclared → the routines section falls back to the most-recently-used folder and says so.
    # No migration (JSON in user_knowledge_entries).
    phase_folders: dict | None = None
    # The due-slot resolver's read (#276/#307), from the SAME `resolve()` call the panel uses
    # (#308, completing #307 Amendment 1 A2): current window, per-slot done/quota, `due_slot`,
    # `uncounted`. None = the resolver read failed (logged) — the chat context omits the
    # position rather than going down. `{"window": None, ...}` = baseline (no plan).
    resolver_position: dict | None = None
    capability_state: list[models.CapabilityState] = field(default_factory=list)
    hrv_baseline: HRVBaseline | None = None   # per-source rolling baseline (#292)
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

    # The plan of record (#312) — at most one active `training_plan` row (fixed key, enforced
    # at write); newest-first is a defence, not a need. Its `value` is what the render section
    # formats; None = no plan.
    training_plan = next((e.value for e in entries if e.type == "training_plan"), None)

    # Phase→Hevy-folder declaration (#314) — a `preference` entry keyed `phase_folders`.
    phase_folders = next(
        (e.value for e in entries if e.type == "preference" and e.key == "phase_folders"), None
    )

    fort_profile_orm = profile_mod.get_profile(db, user_id)
    phase_orm = training_phase_mod.current_training_phase(db, user_id)

    capability_rows = db.query(models.CapabilityState).filter_by(user_id=user_id).all()

    # Source-agnostic HRV baseline (Q130 → #292): derived from the per-source-normalised
    # deviation model, NOT `.canonical` arbitration (§ #292 all-or-nothing migration).
    # The representative source (highest weight) supplies a single source's own rolling
    # baseline — never a cross-source blend of raw ms (the offset is non-constant). The
    # baseline window is the deviation reader's rolling window (28d), so this is no longer
    # a fixed 7-night mean. Every `hrv_readings` row is passive-overnight-equivalent by
    # construction, so no `context != 'session'` analogue is needed.
    # #294/#295: feed the active training-phase change date so a mid-deload / regime
    # change makes the deviation reader flag an unsettled baseline (baseline_state
    # "settling", confidence capped) instead of crying wolf. `phase_orm` is the one open
    # phase (read above); no open phase → phase_change_date None → settling off → prior
    # behaviour. `baseline_state` is surfaced on HRVBaseline so it reaches the context
    # this state feeds (context_builder), where the scalar alone would hide the caveat.
    _dev = hrv_deviation(
        user_id, db, for_date=today,
        phase_change_date=phase_orm.entered_on if phase_orm is not None else None,
    )
    rep = representative_source(_dev)
    hrv_baseline = None
    if rep is not None and rep["baseline_n"] > 0:
        mean = rep["baseline_mean"]
        latest_ms = rep["rmssd"]
        hrv_baseline = HRVBaseline(
            mean_ms=mean,
            n=rep["baseline_n"],
            latest_ms=latest_ms,
            diff_from_mean_ms=(latest_ms - mean) if latest_ms is not None else None,
            baseline_state=_dev["baseline_state"],
        )

    labs = latest_lab_results(user_id, db)

    # The resolver position (#308, #307 A2), from the SAME local `today` the phase read uses.
    # A resolver failure must never take the chat down (G4): catch, log, leave None so the
    # context builder omits the position block.
    try:
        resolver_position = resolver_mod.resolve(db, user_id, today=today)
    except Exception:
        logger.exception("resolver position read failed for user %s — omitting from context", user_id)
        resolver_position = None

    return CurrentState(
        knowledge_entries=entries,
        device_profile=device_profile,
        declared_state=lift_declared_state(entries, today),
        fortification_profile=profile_mod.profile_to_dict(fort_profile_orm),
        fortification_profile_orm=fort_profile_orm,
        training_phase=training_phase_mod.phase_to_dict(phase_orm, on=today),
        training_phase_orm=phase_orm,
        training_plan=training_plan,
        phase_folders=phase_folders,
        capability_state=capability_rows,
        hrv_baseline=hrv_baseline,
        labs=labs,
        resolver_position=resolver_position,
    )
