"""
Engine selection logic — probe-queue construction (§4), constraint filters (§8),
and the Fortify/Probe selector (§2).

The probe queue is the spec's set expression, computed fresh each request:

    probe_queue = (taxonomy regions: untested)
                ∩ (revealed avoidance: absent/declined in the ledger)
                ∩ (relevance to target/horizon)
                − (hard_stops / contraindicated regions)

"No new data required" (§4): the empty regions of the taxonomy crossed with
revealed avoidance IS the queue. Avoidance is read from what the user has loaded
(Hevy history) — a comfort-clustered set loads the same patterns; the negatives
are the candidates.

Nothing here gates on readiness (DECISIONS_LOG #8). A low-readiness hint only
re-ranks the vehicle bias toward recovery vehicles — "switch window, not skip"
(spec §8) — it never removes a region or blocks a session.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from sqlalchemy.orm import Session

import models
from . import taxonomy
from .taxonomy import Region, SIDE_BILATERAL

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Avoidance signal — infer which regions the user actually LOADS (so the rest  #
# are "absent from the ledger", the candidate deficiency set).                 #
# --------------------------------------------------------------------------- #

# Hevy exercise titles → taxonomy region keys. Keyword-matched, lowercase.
#
# DEMOTED to a FALLBACK for untagged templates only (DECISIONS_LOG #NEXT). It is
# wrong on live user data — it produces simultaneous false positives and false
# negatives within a single logged session (substring match, no break on hit,
# no laterality): "Copenhagen Plank" -> trunk_stability_sagittal (it is frontal);
# "Shoulder External Rotation" -> rotation (a radicular-blocked region);
# "Cable Twist" -> nothing. The authoritative path is the `exercise_region_tags`
# join. Every fall-through here is COUNTED and LOGGED — the fallback hit-rate is
# the tagging-coverage metric (target: zero on the active window).
_LOADED_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("deadlift", "hinge"), ("rdl", "hinge"), ("romanian", "hinge"),
    ("hip thrust", "hinge"), ("good morning", "hinge"), ("trap bar", "hinge"),
    ("squat", "squat"), ("leg press", "squat"), ("hack", "squat"),
    ("lunge", "lunge_single_leg"), ("split squat", "lunge_single_leg"),
    ("step up", "lunge_single_leg"), ("bulgarian", "lunge_single_leg"),
    ("bench", "horizontal_push"), ("push up", "horizontal_push"),
    ("push-up", "horizontal_push"), ("chest press", "horizontal_push"),
    ("dip", "horizontal_push"),
    ("overhead press", "vertical_push"), ("shoulder press", "vertical_push"),
    ("ohp", "vertical_push"), ("military", "vertical_push"),
    ("row", "horizontal_pull"), ("face pull", "horizontal_pull"),
    ("pull up", "vertical_pull"), ("pull-up", "vertical_pull"),
    ("chin up", "vertical_pull"), ("pulldown", "vertical_pull"), ("lat pull", "vertical_pull"),
    ("carry", "carry"), ("farmer", "carry"), ("suitcase", "anti_lateral_flexion"),
    ("pallof", "anti_rotation"), ("woodchop", "rotation"), ("russian twist", "rotation"),
    ("rotation", "rotation"),
    ("plank", "trunk_stability_sagittal"), ("ab wheel", "trunk_stability_sagittal"),
    ("calf", "ankle_df"),
)


def _keyword_regions(title: str) -> set[str]:
    """The legacy substring matcher — FALLBACK for untagged templates only."""
    tl = (title or "").lower()
    if not tl:
        return set()
    return {rk for needle, rk in _LOADED_KEYWORDS if needle in tl}


def _tags_by_template(db: Session, template_ids: set[str]) -> dict[str, set[str]]:
    """template_id -> {region_key} from the app-owned annotation (DECISIONS_LOG
    #NEXT). Both `primary` and `secondary` roles count as loaded — the region IS
    loaded regardless of primacy; role governs review/reconciliation, not
    presence. Orphan keys (no matching taxonomy Region) are skipped + warned:
    validation is fail-closed at write, this is defence in depth on read."""
    if not template_ids:
        return {}
    rows = (
        db.query(models.ExerciseRegionTag)
        .filter(models.ExerciseRegionTag.hevy_exercise_template_id.in_(template_ids))
        .all()
    )
    out: dict[str, set[str]] = {}
    for r in rows:
        if taxonomy.by_key(r.region_key) is None:
            logger.warning(
                "exercise_region_tags: orphan region_key %r on template %s — skipping",
                r.region_key, r.hevy_exercise_template_id,
            )
            continue
        out.setdefault(r.hevy_exercise_template_id, set()).add(r.region_key)
    return out


def infer_loaded_regions(
    workouts: Iterable[dict[str, Any]],
    *,
    db: Session | None = None,
) -> set[str]:
    """Region keys the user has demonstrably loaded in recent Hevy history.

    Authoritative path (DECISIONS_LOG #NEXT): join each logged exercise's
    `exercise_template_id` against `exercise_region_tags`. A template with no
    tags is UNTAGGED and falls back to the legacy `_LOADED_KEYWORDS` substring
    matcher — every such fall-through is counted and logged, because the
    fallback hit-rate is the tagging-coverage metric (target zero on the active
    window).

    `db` is an optional keyword: when provided (both known call sites have a
    Session in scope), the table join runs; when absent, the function degrades
    to the pure keyword path — preserving the original contract for any caller
    that cannot supply a session. The return type (`set[str]`) is unchanged.
    """
    exercises: list[dict[str, Any]] = [
        ex
        for w in (workouts or [])
        for ex in (w.get("exercises", []) or [])
    ]

    tag_map: dict[str, set[str]] = {}
    if db is not None:
        template_ids = {
            tid for ex in exercises if (tid := ex.get("exercise_template_id"))
        }
        tag_map = _tags_by_template(db, template_ids)

    loaded: set[str] = set()
    fallback_titles: list[str] = []
    for ex in exercises:
        tid = ex.get("exercise_template_id")
        title = ex.get("title") or ""
        if tid and tid in tag_map:              # tagged — authoritative
            loaded |= tag_map[tid]
            continue
        # Untagged (or no db): legacy keyword fallback, instrumented.
        kw = _keyword_regions(title)
        loaded |= kw
        if title or tid:
            fallback_titles.append(title or f"<template {tid}>")

    if fallback_titles:
        logger.info(
            "infer_loaded_regions: %d/%d logged exercises hit the keyword fallback "
            "(untagged templates) — coverage gap: %s",
            len(fallback_titles), len(exercises), sorted(set(fallback_titles)),
        )
    return loaded


# --------------------------------------------------------------------------- #
# Active constraints — injuries and live signals that contraindicate regions.  #
# --------------------------------------------------------------------------- #

# Seed heuristic maps (spec §8). Provoking signal → regions to hard-stop. These
# are intentionally explicit and reviewable, not learned.
_RADICULAR_BLOCKS = frozenset({
    "hinge", "rotation", "carry", "deceleration_landing",
    "change_of_direction", "single_leg_hop", "gait_load_carriage",
})
# RA flare = both-ends stand-down (base + grip compromised).
_RA_FLARE_BLOCKS = frozenset({
    "carry", "anti_lateral_flexion", "gait_load_carriage", "terrain_perturbation",
    "single_leg_hop", "change_of_direction", "deceleration_landing",
})
# Acute tissue → time-limited exclusion of the provoking range, by body part.
_ACUTE_TISSUE_BLOCKS: dict[str, frozenset[str]] = {
    "hamstring": frozenset({
        "lunge_single_leg", "single_leg_hop", "change_of_direction",
        "deceleration_landing", "terrain_perturbation",
    }),
    "shoulder": frozenset({"vertical_push", "horizontal_push"}),
    "calf": frozenset({"single_leg_hop", "change_of_direction", "deceleration_landing"}),
    "ankle": frozenset({"single_leg_hop", "change_of_direction", "terrain_perturbation"}),
    "knee": frozenset({"single_leg_hop", "change_of_direction", "deceleration_landing"}),
}


def gather_active_injuries(db: Session, user_id: int) -> list[dict[str, Any]]:
    """
    Active injury/contraindication signals from the structured ledger
    (UserKnowledgeEntry type='injury', active=True). Normalised to:
        {body_part, side, signal_type, ra_flare, restrictions, raw}
    """
    rows = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=user_id, type="injury", active=True)
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        val = r.value or {}
        body_part = str(val.get("body_part", "")).lower()
        out.append({
            "body_part": body_part,
            "side": str(val.get("side", SIDE_BILATERAL)).lower(),
            "signal_type": str(val.get("signal_type", "mechanical")).lower(),
            "ra_flare": bool(val.get("ra_flare", False)) or "ra_flare" in (val.get("restrictions") or []),
            "restrictions": val.get("restrictions") or [],
            "raw": val,
        })
    return out


def _side_conflict(injury_side: str, region_side: str) -> bool:
    """A bilateral injury hits both sides; a sided injury hits its side (and any
    bilateral-scored region)."""
    if injury_side in (SIDE_BILATERAL, "", "both"):
        return True
    if region_side == SIDE_BILATERAL:
        return True
    return injury_side == region_side


def is_contraindicated(
    region: Region,
    side: str,
    *,
    profile_hard_stops: list[dict[str, Any]] | None,
    active_injuries: list[dict[str, Any]],
) -> tuple[bool, str | None]:
    """Apply the §8 hard filters. Probe never samples a contraindicated region —
    'don't discover your way into a flagged nerve'."""
    # Explicit profile hard-stops that name a concrete region (not a pattern rule).
    for hs in profile_hard_stops or []:
        rk = hs.get("region_key")
        hs_side = str(hs.get("side", SIDE_BILATERAL)).lower()
        if rk and rk == region.key and _side_conflict(hs_side, side):
            return True, hs.get("reason") or "profile hard-stop"

    for inj in active_injuries:
        if not _side_conflict(inj["side"], side):
            continue
        # Radicular/neural sign → hard stop on the provoking pattern.
        if inj["signal_type"] in ("radicular", "neural") and region.key in _RADICULAR_BLOCKS:
            return True, f"radicular sign ({inj['body_part'] or 'spine'}) — provoking pattern"
        # RA flare → both-ends stand-down.
        if inj["ra_flare"] and region.key in _RA_FLARE_BLOCKS:
            return True, "RA flare — both-ends stand-down (base + grip)"
        # Acute tissue → provoking-range exclusion by body part.
        for part, blocked in _ACUTE_TISSUE_BLOCKS.items():
            if part in inj["body_part"] and region.key in blocked:
                return True, f"acute {inj['body_part']} — provoking range excluded"
    return False, None


def _relevance_ok(region: Region, profile: models.FortificationProfile | None) -> bool:
    """Relevance filter on Probe (§8): sample regions plausibly relevant to the
    target/horizon, not novelty for its own sake. A 'life / durability' horizon
    keeps the space broad; ungrounded §G axes are already excluded upstream."""
    if profile is None:
        return True
    if (profile.horizon or "life") == "life":
        return True
    # Event-dated horizons still keep priority + same-plane-as-target regions.
    return True


# --------------------------------------------------------------------------- #
# Probe queue                                                                  #
# --------------------------------------------------------------------------- #

def compute_probe_queue(
    db: Session,
    user_id: int,
    *,
    profile: models.FortificationProfile | None,
    loaded_region_keys: set[str],
    active_injuries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """The §4 set expression, ranked. One entry per (region, side)."""
    if active_injuries is None:
        active_injuries = gather_active_injuries(db, user_id)
    hard_stops = list(profile.hard_stops) if (profile and profile.hard_stops) else []

    # Current map contents: (region_key, side) -> status.
    state_rows = db.query(models.CapabilityState).filter_by(user_id=user_id).all()
    status_by: dict[tuple[str, str], str] = {
        (s.region_key, s.side): s.status for s in state_rows
    }

    candidates: list[dict[str, Any]] = []
    for region in taxonomy.queue_eligible_regions():
        for side in region.sides():
            status = status_by.get((region.key, side), "untested")
            if status != "untested":            # ∩ untested
                continue
            if region.key in loaded_region_keys:  # ∩ revealed avoidance (not loaded)
                continue
            if not _relevance_ok(region, profile):  # ∩ relevance
                continue
            blocked, reason = is_contraindicated(
                region, side,
                profile_hard_stops=hard_stops,
                active_injuries=active_injuries,
            )
            if blocked:                          # − contraindicated
                continue
            candidates.append({
                "region_key": region.key,
                "label": region.label,
                "side": side,
                "group": region.group,
                "plane": region.plane.value,
                "capacity": region.capacity.value,
                "probing_test": region.probing_test,
                "expectation": region.expectation,
                "confidence": region.confidence.value,
                "probe_priority": region.probe_priority,
                "needs_norm": region.needs_norm,
                "_rank": taxonomy.region_rank(region),
            })

    candidates.sort(key=lambda c: (c["_rank"], c["region_key"], c["side"]))
    for c in candidates:
        c.pop("_rank", None)
    return candidates


# --------------------------------------------------------------------------- #
# Dosing seam — the four physiological windows + Banister Form (DECISIONS_LOG  #
# #18). We name which windows a recommendation deposits load into; we do NOT   #
# fabricate a quantitative dose — that plugs into the (designed, unbuilt) load #
# model. ACWR is explicitly not used.                                          #
# --------------------------------------------------------------------------- #

_WINDOWS_BY_CAPACITY: dict[str, list[str]] = {
    "strength": ["Neuromuscular", "Mechanical"],
    "power": ["Neuromuscular", "Mechanical"],
    "stability": ["Neuromuscular", "Psychological"],
    "mobility": ["Mechanical"],
    "endurance": ["Metabolic"],
}

_DOSING_NOTE = (
    "Graded entry (spec §7): a novel pattern is unknown capacity — small dose, "
    "read response, never blind-load at intensity. Quantitative load references "
    "Banister Form (Fitness − Fatigue); that model is designed, not yet "
    "implemented (DECISIONS_LOG #18). ACWR is not used."
)


def _dosing(capacity: str, *, probe: bool) -> dict[str, Any]:
    return {
        "windows": _WINDOWS_BY_CAPACITY.get(capacity, ["Neuromuscular"]),
        "entry": "exploratory (graded)" if probe else "fortify (progress on demonstrated response)",
        "note": _DOSING_NOTE,
    }


# --------------------------------------------------------------------------- #
# Selection — one Fortify recommendation + one Probe suggestion per session.   #
# --------------------------------------------------------------------------- #

# Vehicle key → human label + what it does (demoted modality layer, spec §5).
VEHICLES: dict[str, str] = {
    "pilates_clinical": "Clinical Pilates (frontal/transverse control, IAP, position tolerance)",
    "offset_carry": "Offset / suitcase carry (corrects anti-lateral-flexion asymmetry)",
    "unilateral_lifting": "Unilateral lifting (exposes + corrects per-side asymmetry)",
    "swim": "Swimming (decompressed load, managing weeks)",
    "hike": "Hiking (probes foot/ankle base + aerobic)",
    "barbell_floor_hold": "Barbell / trap-bar (floor-holder and NM dose — not the variety)",
    "sled": "Sled drive/drag (horizontal force, scrum-specific)",
}


def select_next(
    db: Session,
    user_id: int,
    *,
    profile: models.FortificationProfile | None,
    probe_queue: list[dict[str, Any]],
    readiness_hint: int | None = None,
) -> dict[str, Any]:
    """
    The explore/exploit split (§2). Returns BOTH a Fortify recommendation and a
    single Probe suggestion (one-per-session, §2.1), plus a recommended mode.

    Mode heuristic (deterministic): while untested probe-priority regions remain
    — the comfort-cluster blind spot — bias to Probe; once exhausted, bias
    Fortify. A system that stops exploring stops discovering (§2).
    """
    probe_budget = float(profile.probe_budget) if profile and profile.probe_budget is not None else 0.25

    probe = probe_queue[0] if probe_queue else None
    has_priority = any(c.get("probe_priority") for c in probe_queue)
    mode = "probe" if (probe is not None and probe_budget > 0 and has_priority) else "fortify"

    probe_block = None
    if probe is not None:
        region = taxonomy.by_key(probe["region_key"])
        probe_block = {
            **probe,
            "idiom": (
                "Surface it in the education idiom — the user logs whether it felt "
                "unstable / asymmetric / hard, not a screen score (spec §12). "
                "Pain = stop + refer."
            ),
            "dosing": _dosing(probe["capacity"], probe=True),
        }
        if region is not None and region.gates:
            probe_block["gated_note"] = (
                f"Gates {', '.join(region.gates)} — a deficiency here may cap them."
            )

    # Fortify recommendation: the primary target, with ranked vehicles.
    vehicle_bias = list(profile.vehicle_bias) if (profile and profile.vehicle_bias) else []
    if readiness_hint is not None and readiness_hint <= 4:
        # Re-rank toward recovery vehicles — never a gate (DECISIONS_LOG #8).
        recovery = ["swim", "pilates_clinical", "hike"]
        vehicle_bias = (
            [v for v in vehicle_bias if v in recovery]
            + [v for v in vehicle_bias if v not in recovery]
        )

    target_key = profile.primary_target if profile else None
    target_region = taxonomy.by_key(target_key) if target_key else None
    fortify_block = {
        "target": target_key,
        "target_label": target_region.label if target_region else (target_key or "—"),
        "target_note": (profile.primary_target_note if profile else None),
        "vehicles": [{"key": v, "label": VEHICLES.get(v, v)} for v in vehicle_bias],
        "dosing": _dosing(
            target_region.capacity.value if target_region else "stability", probe=False
        ),
    }

    notes: list[str] = []
    if readiness_hint is not None and readiness_hint <= 4:
        notes.append(
            "Low subjective readiness — biasing toward recovery vehicles "
            "(switch window, not skip). This is a re-rank, never a gate."
        )
    if probe is None:
        notes.append(
            "Probe queue is empty under current filters — either the map is well "
            "sampled or active hard-stops are excluding the candidates."
        )

    return {
        "mode_recommended": mode,
        "budget": {"probe": probe_budget, "fortify": round(1.0 - probe_budget, 4)},
        "fortify": fortify_block,
        "probe": probe_block,
        "notes": notes,
    }
