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
            # Not "settling": the neural limiter is gated on the lumbar source; nothing
            # in the current plan predicts it clearing on its own, so "settling" would
            # generate a false divergence flag. "stable" is the honest expectation — a
            # sustained move in either direction is a legitimate surprise to surface.
            "trajectory": {
                "shape": "stable",
                "declared_on": "2026-07-13",
            },
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
            # The injury that motivated the mechanism. Expected to settle (1-2 wks).
            # review_when fires the symptom-gated review once point tenderness (soreness)
            # sits at 1 (=None) for 3 sustained days — "looks resolved, revisit the plan".
            "trajectory": {
                "shape": "settling",
                "declared_on": "2026-07-13",
                "review_when": {
                    "metric": "soreness", "op": "<=", "threshold": 1, "sustained_days": 3,
                },
            },
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


# ---------------------------------------------------------------------------
# Declared-state ledger — the user's current stack as structured rows.
#
# USER-CONFIRMED CLINICAL DATA, not inferred. This corrects Clinical_Protocol.md,
# an orientation doc flagged unreliable: HGH was recorded active but was NEVER
# used or sourced; CJC-1295/Ipamorelin + IGF-1 LR3 are EPISODIC (ad-hoc), not
# discontinued; GLOW is BPC-157 + TB-500 + GHK-Cu, not the mis-recorded KPV.
#
# Each row is an active DECLARATION (active=True on the row). `value["active"]`
# carries whether the user is currently TAKING the factor — see declared_state.py
# for why the two must not be collapsed.
#
# Per-factor lab confounders are recorded in `detail` deliberately: that tagging
# is the capability this ledger unlocks for 4b's "already in play" lever
# curation (#49).
# ---------------------------------------------------------------------------

_PROTOCOL_SEED = [
    {
        "key": "trt",
        "value": {
            "active": True, "continuity": "continuous", "phase": "steady",
            "detail": ("Testosterone cypionate ~122.5 mg/wk (0.10 ml daily subQ, 175 mg/ml MCT). "
                       "Steady; next move (hold vs reduce) is E2-gated pending next bloods."),
            "relevant_date": "2026-06-09",
        },
    },
    {
        "key": "tirzepatide",
        "value": {
            "active": False, "continuity": "stopped", "phase": "washout",
            # The date is TRIANGULATED (HRV step-change + Monday constraint +
            # recollection), NOT a dosing log. Flagged so it is never counted
            # twice as evidence for the Q17 washout hypothesis it partly derives from.
            "detail": ("GLP-1/GIP. Last shot Mon 22 Jun 2026 — triangulated (HRV step + Monday "
                       "constraint + recollection), not a dosing log."),
            "relevant_date": "2026-06-22",
        },
    },
    {
        "key": "cjc_ipamorelin",
        "value": {
            "active": True, "continuity": "episodic", "phase": "episodic",
            "detail": ("CJC-1295 (no DAC) + Ipamorelin, ad-hoc big-gym-days only. Not scheduled, "
                       "not discontinued. Not assumable present at any draw."),
            "relevant_date": None,
        },
    },
    {
        "key": "igf1_lr3",
        "value": {
            "active": True, "continuity": "episodic", "phase": "episodic",
            "detail": "IGF-1 LR3, ad-hoc big-gym-days only. Not assumable present at any draw.",
            "relevant_date": None,
        },
    },
    {
        "key": "glow",
        "value": {
            "active": False, "continuity": "stopped", "phase": "stopped",
            "detail": "GLOW = BPC-157 + TB-500 + GHK-Cu. Stopped; stop date not recorded.",
            "relevant_date": None,
        },
    },
    {
        "key": "hgh",
        "value": {
            "active": False, "continuity": "never", "phase": None,
            "detail": ("Somatropin — NEVER used, never sourced (discussion-stage only). "
                       "Corrects Clinical_Protocol.md."),
            "relevant_date": None,
        },
    },
]

_SUPPLEMENT_SEED = [
    {
        "key": "boron",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": "Boron 5 mg. HPG: modestly raises free-T / lowers SHBG / shifts E2.",
            "relevant_date": None,
        },
    },
    {
        "key": "vit_d3_k2",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": ("Vitamin D3 4000 IU + K2 100 mcg. Directly maintains 25-OH vitamin D; "
                       "K2 -> calcium handling."),
            "relevant_date": None,
        },
    },
    {
        "key": "ashwagandha",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": ("Ashwagandha 1500 mg. Thyroid-relevant (may raise T3/T4); lowers cortisol; "
                       "sleep/stress."),
            "relevant_date": None,
        },
    },
    {
        "key": "selenium",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": "Selenium 150 mcg. Thyroid cofactor (T4->T3).",
            "relevant_date": None,
        },
    },
    {
        "key": "zinc",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": ("Zinc picolinate 50 mg. Aromatase/E2 modulation; chronic high dose -> copper "
                       "depletion (watch Cu). Cumulative with multivitamin Zn (2 sources)."),
            "relevant_date": None,
        },
    },
    {
        "key": "mg_glycinate",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": ("Mg glycinate: 400 mg bedtime tablet + 105 mg in Bioglan PM Calm + AM Ethical "
                       "Nutrients Mega Magnesium scoop. Bedtime ~505 mg + AM scoop across 3 sources. "
                       "Lab: Mg plasma/RBC — read against low-normal plasma Mg history (GLP-1 wasting "
                       "driver now removed)."),
            "relevant_date": None,
        },
    },
    {
        "key": "b_complex",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": ("B-complex. Raises B12 / active B12 / folate, lowers homocysteine — explains "
                       "high active B12 as repletion, not pathology."),
            "relevant_date": None,
        },
    },
    {
        "key": "berberine",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": ("Berberine. Lowers glucose/HbA1c + LDL/TG/total-chol (metformin-like) — major "
                       "metabolic-panel confounder."),
            "relevant_date": None,
        },
    },
    {
        "key": "swisse_mens_multi",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": ("Swisse Men's Multivitamin 50+. Broad micronutrients; additive to standalone "
                       "Zn/D/B — watch cumulative totals."),
            "relevant_date": None,
        },
    },
    {
        "key": "prebiotic_fibre",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": ("PHGG + GOS + Inulin (gut/microbiome). Estrobolome -> beta-glucuronidase -> E2 "
                       "enterohepatic clearance — an HPG axis clearance-side lever (distinct from "
                       "aromatase production-side); mild SCFA lipid/glycaemic effect."),
            "relevant_date": None,
        },
    },
    {
        "key": "apigenin",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": ("Apigenin 50 mg. Mild aromatase inhibition (E2 down — maps to HPG "
                       "aromatase_inhibition lever); sleep stack."),
            "relevant_date": None,
        },
    },
    {
        "key": "l_theanine_pm",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": ("Bioglan L-Theanine PM Calm, bedtime — contains 105 mg Mg glycinate (counted in "
                       "mg_glycinate total). Replaced Ultra Muscleze Night. Sleep stack."),
            "relevant_date": None,
        },
    },
    {
        # Supersession history: the row is an active DECLARATION of an inactive
        # factor. It is kept because it is a historical Mg contributor.
        "key": "ultra_muscleze_night",
        "value": {
            "active": False, "continuity": "continuous", "phase": None,
            "detail": ("Ultra Muscleze Night + L-Theanine — ran out, superseded by l_theanine_pm "
                       "(which superseded standalone L-theanine). Historical Mg contributor."),
            "relevant_date": None,
        },
    },
    {
        "key": "creatine",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": ("5 g/day + creatine in AM Mega-Mag scoop. Raises serum creatinine — confounder "
                       "for creatinine/eGFR (surface once creatinine is grouped + a creatine lever "
                       "exists)."),
            "relevant_date": None,
        },
    },
    {
        "key": "glycine",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": ("Glycine 3 g ~1 hr pre-bed (plus incidental glycine from 3 Mg-glycinate "
                       "sources). Sleep stack (CBT-I adjunct)."),
            "relevant_date": None,
        },
    },
    {
        "key": "leucine_protein",
        "value": {
            "active": True, "continuity": "continuous", "phase": None,
            "detail": ("Leucine-spiked protein, 32 g / 4 g leucine per serve, 3-4x/day. High protein "
                       "load -> raises urea/BUN, contributes to creatinine (renal-marker confounder "
                       "alongside creatine)."),
            "relevant_date": None,
        },
    },
]

_BEHAVIOURAL_SEED = [
    {
        "key": "cbt_i",
        "value": {
            "active": True, "continuity": "continuous", "phase": "re_entering",
            "detail": ("CBT-I sleep protocol. Re-entered after a pause (paused while shoulder pain "
                       "disrupted sleep; cause lifted — shoulder unchanged as a long-term managed "
                       "injury, just no longer the sleep disruptor). Wake anchor 5:45am."),
            "relevant_date": "2026-07-19",
        },
    },
]

_DECLARED_STATE_SEED = (
    [("protocol", e) for e in _PROTOCOL_SEED]
    + [("supplement", e) for e in _SUPPLEMENT_SEED]
    + [("behavioural", e) for e in _BEHAVIOURAL_SEED]
)


def _seed_declared_state(db, user_id: int) -> int:
    """Mirrors _seed_injuries: add-only, skip-if-present, source="system",
    notes=detail. Returns rows written.

    Every row is written active=True — the row flag means "this DECLARATION is
    current", not "the user takes this". A factor the user has stopped, or never
    took, is still a currently-true declaration, and must stay queryable:
    current_state loads active=True rows only, so a row-level-inactive factor
    would silently vanish from declared_state and its phase (washout/stopped)
    would be underivable. See declared_state.py.
    """
    written = 0
    for entry_type, factor in _DECLARED_STATE_SEED:
        existing = (
            db.query(models.UserKnowledgeEntry)
            .filter_by(user_id=user_id, key=factor["key"], active=True)
            .first()
        )
        if existing is not None:
            continue
        db.add(models.UserKnowledgeEntry(
            user_id=user_id, type=entry_type, key=factor["key"],
            value=factor["value"], source="system", active=True,
            notes=factor["value"].get("detail"),
        ))
        written += 1
    db.commit()
    return written


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
        decl_rows = _seed_declared_state(db, user.id)

        print(f"Seeded engine for user {user.id} ({user.email}):")
        print(f"  fortification profile: target={profile.primary_target}, "
              f"probe_budget={profile.probe_budget}")
        print(f"  capability_state rows written: {cap_rows}")
        print(f"  injury ledger rows written:    {inj_rows}")
        print(f"  device profile rows written:   {dev_rows}")
        print(f"  declared-state rows written:   {decl_rows}")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMAIL)
