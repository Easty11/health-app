"""
Seed the Adaptive Exposure Engine first instance — Luke / back-resilience (spec §10).

Idempotent. Run once locally / after deploy:

    python seed_engine.py [user_email]

Writes, for the target user:
  1. The fortification-target profile (engine.profile.LUKE_PROFILE_SEED).
  2. Capability-state seed — the demonstrated sagittal-strength floor (pass) and
     the active fortify target (fortifying). Everything else stays untested so the
     map self-builds via Probe (§2.1).
  3. The three known injuries into the structured ledger (UserKnowledgeEntry
     type='injury'), so they surface in the schedule section AND drive the engine's
     §8 contraindication filters — replacing the hardcoded injury string honestly.
"""
from __future__ import annotations

import sys

import models
from database import SessionLocal
from engine import profile as profile_mod

DEFAULT_EMAIL = "Luke.eastlake@outlook.com"

# Real injuries, structured for both surfacing and §8 contraindication logic.
_INJURY_SEED = [
    {
        "key": "injury_finger_left",
        "value": {
            "body_part": "finger",
            "side": "left",
            "signal_type": "mechanical",
            "restrictions": ["heavy gripping"],
            "detail": "Left little finger",
        },
    },
    {
        "key": "injury_shoulder_right",
        "value": {
            "body_part": "shoulder",
            "side": "right",
            "signal_type": "mechanical",
            "restrictions": ["horizontal adduction", "overhead work"],
            "detail": "Right shoulder — caution with horizontal adduction and overhead work",
        },
    },
    {
        "key": "injury_hamstring_left",
        "value": {
            "body_part": "hamstring",
            "side": "left",
            "signal_type": "mechanical",
            "restrictions": ["striding", "sprinting"],
            "detail": "Left hamstring — provoked by striding/sprinting",
        },
    },
    {
        # Distinct from the left hamstring (functional, velocity-gated). This is the
        # imaged, structural right injury. signal_type stays "mechanical" (not
        # "neural") by decision: "neural" fires selection.py's signal-wide radicular
        # block (hinge/rotation/carry/gait), which would kill the SL-RDL — the very
        # neural-desensitisation lane that is tolerated and wanted. The neural finding
        # is carried in `detail` (surfaced), not encoded as an engine hard-stop; the
        # actual aggravator (static end-range stretching) is not a taxonomy region and
        # cannot be gated regardless. See DECISIONS_LOG (restrictions set at onset;
        # check-in monitors, does not gate).
        "key": "injury_hamstring_right",
        "value": {
            "body_part": "hamstring",
            "side": "right",
            "signal_type": "mechanical",
            "restrictions": ["striding", "sprinting", "static end-range hamstring stretching"],
            "detail": (
                "Right proximal semimembranosus — full-thickness partial-width rupture "
                "(US Aug 2025, 3.3×1.6cm, retracted fibres). Current limiter is NEURAL, "
                "not the tear: positive right slump w/ cervical differentiation, S1-pattern "
                "referral behind-knee→calf, central L5-S1. Symptoms distal; tear proximal. "
                "Loaded hinge (SL-RDL 28–32kg @ 7.5–8 RPE) is tolerated and WANTED — it is "
                "the desensitisation lane. Aggravator is passive end-range tension, not load."
            ),
        },
    },
    {
        # Current, active irritation. signal_type "mechanical"; body_part "pes anserine"
        # matches no _ACUTE_TISSUE_BLOCKS key, so no engine hard-stop — the restrictions
        # (adductor tension / deep-flexion) are surfaced, not gated (no matching taxonomy
        # region). Expiry is symptom-gated on point tenderness — carried in `detail` until
        # the trajectory/review schema (Step 3) formalises it.
        "key": "injury_pes_anserine_left",
        "value": {
            "body_part": "pes anserine",
            "side": "left",
            "signal_type": "mechanical",
            "restrictions": ["adductor tension (Copenhagens)", "deep-flexion unilateral"],
            "detail": (
                "Left pes anserine insertional irritation. Return path: short-lever "
                "Copenhagens, progress one notch. Review symptom-gated on point tenderness "
                "(not date-gated)."
            ),
        },
    },
]


def _seed_injuries(db, user_id: int) -> int:
    written = 0
    for inj in _INJURY_SEED:
        existing = (
            db.query(models.UserKnowledgeEntry)
            .filter_by(user_id=user_id, key=inj["key"], active=True)
            .first()
        )
        if existing is not None:
            continue
        db.add(models.UserKnowledgeEntry(
            user_id=user_id, type="injury", key=inj["key"],
            value=inj["value"], source="system", active=True,
            notes=inj["value"].get("detail"),
        ))
        written += 1
    db.commit()
    return written


# Device/method mapping — the last per-user fact still hardcoded in
# context_builder before this seed, now the structured ledger source for
# _section_user_profile's `type="preference", key="device_profile"` lookup.
_DEVICE_PROFILE_SEED = {
    "hrv_source": "Samsung Galaxy Ring (accessibility scraper, not Health Connect)",
    "strength_log_tool": "Hevy",
    "aerobic_hr_source": "Polar H10 chest strap",
    "readiness_primary_gate": "RMSSD vs 7-day baseline; sleep quality secondary",
}


def _seed_device_profile(db, user_id: int) -> int:
    existing = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=user_id, key="device_profile", active=True)
        .first()
    )
    if existing is not None:
        return 0
    db.add(models.UserKnowledgeEntry(
        user_id=user_id, type="preference", key="device_profile",
        value=_DEVICE_PROFILE_SEED, source="system", active=True,
    ))
    db.commit()
    return 1


def main(email: str) -> None:
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email.ilike(email)).first()
        if user is None:
            user = db.query(models.User).order_by(models.User.id).first()
            if user is None:
                print("No users in the database — nothing to seed.")
                return
            print(f"No user '{email}'; falling back to first user: {user.email}")

        profile = profile_mod.upsert_profile(db, user.id, profile_mod.LUKE_PROFILE_SEED)
        cap_rows = profile_mod.seed_capability_state(db, user.id)
        inj_rows = _seed_injuries(db, user.id)
        dev_rows = _seed_device_profile(db, user.id)

        print(f"Seeded engine for user {user.id} ({user.email}):")
        print(f"  fortification profile: target={profile.primary_target}, "
              f"probe_budget={profile.probe_budget}")
        print(f"  capability_state rows written: {cap_rows}")
        print(f"  injury ledger rows written:    {inj_rows}")
        print(f"  device profile rows written:   {dev_rows}")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMAIL)
