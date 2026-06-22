"""
Fortification-target profile (spec §9) — load, serialise, upsert, and seed.

The profile is the structured object that replaces the hardcoded injury string in
context_builder. `probe_queue` is computed at request time (selection.py), never
stored, so it does not live on this object.

The seed encodes the first instance — Luke / back-resilience (spec §10) — which
exists to prove the engine generalises from a real profile rather than a
hardcoded one.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

import models
from . import taxonomy


def get_profile(db: Session, user_id: int) -> models.FortificationProfile | None:
    return (
        db.query(models.FortificationProfile)
        .filter_by(user_id=user_id)
        .first()
    )


def profile_to_dict(p: models.FortificationProfile | None) -> dict[str, Any] | None:
    if p is None:
        return None
    return {
        "floor": p.floor,
        "ceiling": p.ceiling,
        "horizon": p.horizon,
        "horizon_date": str(p.horizon_date) if p.horizon_date else None,
        "primary_target": p.primary_target,
        "primary_target_note": p.primary_target_note,
        "live_signals": p.live_signals or [],
        "hard_stops": p.hard_stops or [],
        "vehicle_bias": p.vehicle_bias or [],
        "probe_budget": p.probe_budget,
        "notes": p.notes,
    }


_UPSERTABLE = (
    "floor", "ceiling", "horizon", "horizon_date", "primary_target",
    "primary_target_note", "live_signals", "hard_stops", "vehicle_bias",
    "probe_budget", "notes",
)


def upsert_profile(db: Session, user_id: int, data: dict[str, Any]) -> models.FortificationProfile:
    p = get_profile(db, user_id)
    if p is None:
        p = models.FortificationProfile(user_id=user_id)
        db.add(p)
    for field in _UPSERTABLE:
        if field in data and data[field] is not None:
            setattr(p, field, data[field])
    db.commit()
    db.refresh(p)
    return p


# --------------------------------------------------------------------------- #
# Seed — first instance, Luke / back-resilience (spec §10).                    #
# --------------------------------------------------------------------------- #

LUKE_PROFILE_SEED: dict[str, Any] = {
    "floor": {
        "demonstrated": "trap-bar 120 kg, grade-level scrum",
        "tag": "managed",  # clean-but-managing — what you already survive, not Phase 1
    },
    "ceiling": "breadth",          # not scrum-peak; scrum demotes to a time-boxed stress-test
    "horizon": "life",             # functional durability
    "primary_target": "anti_lateral_flexion",
    "primary_target_note": (
        "Frontal/transverse trunk control as the right-side asymmetry corrective — "
        "the limiter the bar named (oblique/QL/glute-med/erector tension at 120, legs "
        "in reserve = control cap, not strength cap). Same object as the longevity "
        "priority and the 30-year right-side through-line."
    ),
    "live_signals": [{
        "signal": "flank tension",
        "side": "right",
        "branch_param": "stabiliser_ceiling_vs_guard",
        "status": "unresolved",   # default branch: train it (mechanical-dominant, no travelling pain at 120)
        "self_triage": "warms-up-and-clears → train it; stays-and-sharpens → assess first",
    }],
    "hard_stops": [
        {"pattern": "radicular", "scope": "provoking pattern", "side": "right",
         "reason": "radicular signs = stop the provoking pattern; Probe never samples that region"},
        {"pattern": "ra_flare", "scope": "both-ends",
         "reason": "RA flare = base + grip compromised"},
    ],
    "vehicle_bias": [
        "pilates_clinical", "offset_carry", "unilateral_lifting",
        "swim", "hike", "barbell_floor_hold",
    ],
    "probe_budget": 0.25,
    "notes": "First-instance profile (spec §10). Proves the engine runs off a profile, not a hardcoded string.",
}

# Capability-state seed: the demonstrated sagittal-strength floor is already
# well-sampled (needs loading, not probing) → pass/history. The primary-target
# region is the active Fortify focus → fortifying. Everything else stays untested
# (no row) so the map self-builds via Probe (§2.1).
_FLOOR_PASS_REGIONS = ("hinge", "squat", "horizontal_push", "vertical_pull", "horizontal_pull")
_FORTIFYING_REGIONS = ("anti_lateral_flexion", "frontal_single_leg_stability", "anti_rotation")


def seed_capability_state(db: Session, user_id: int) -> int:
    """Idempotent seed of the demonstrated floor + active fortify target. Returns
    the number of rows written. Leaves all other regions untested by design."""
    written = 0

    def _ensure(region_key: str, side: str, status: str, source: str) -> None:
        nonlocal written
        existing = (
            db.query(models.CapabilityState)
            .filter_by(user_id=user_id, region_key=region_key, side=side)
            .first()
        )
        if existing is not None:
            return
        db.add(models.CapabilityState(
            user_id=user_id, region_key=region_key, side=side,
            status=status, source=source, taxonomy_version=taxonomy.TAXONOMY_VERSION,
            detail={"seeded": True},
        ))
        written += 1

    for key in _FLOOR_PASS_REGIONS:
        region = taxonomy.by_key(key)
        if region is None:
            continue
        for side in region.sides():
            _ensure(key, side, "pass", "history")

    for key in _FORTIFYING_REGIONS:
        region = taxonomy.by_key(key)
        if region is None:
            continue
        for side in region.sides():
            _ensure(key, side, "fortifying", "fortify")

    db.commit()
    return written
