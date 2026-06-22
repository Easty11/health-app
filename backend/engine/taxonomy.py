"""
Capability taxonomy — the externally-grounded axis list (Capability_Taxonomy_v0).

This is the "what regions exist" half of the v2.1 split (spec §3). It caps what
Probe mode can ever discover: Probe only samples regions already on this list, so
an unlisted capability is never queued. It is deliberately external-authority and
versioned — grounded in movement-screen / ortho literature (FMS / SFMA, the
weight-bearing-lunge dorsiflexion work, return-to-sport LSI) so its breadth does
not inherit the user's blind spots.

It holds NO user data. A user's score per region (untested / pass / deficient)
lives in the `capability_state` table (the "map contents" half), which self-builds
one probe per session (§2.1).

Reading the `expectation` field — important (taxonomy doc, "How to read"):
expectations are FLAGS, not verdicts. A probe scoring below a reference norm flags
a region to watch and possibly fortify — it never diagnoses, and the engine never
presents it as a verdict. The one hard line the whole system agrees on is
pain = stop + refer. The governing signal remains the user's own demonstrated
capability and their response to load.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Matches the companion doc Capability_Taxonomy_v0.md. Bump when the axis list
# changes so capability_state rows can record which version scored them.
TAXONOMY_VERSION = "v0"


class Plane(str, Enum):
    SAGITTAL = "sagittal"
    FRONTAL = "frontal"
    TRANSVERSE = "transverse"
    MULTI = "multi"


class Capacity(str, Enum):
    MOBILITY = "mobility"        # have the range
    STABILITY = "stability"     # own the range under load (stability / control)
    STRENGTH = "strength"       # load it
    POWER = "power"             # load it fast / absorb it (power / reactive)
    ENDURANCE = "endurance"     # repeat it (endurance / capacity)


class Confidence(str, Enum):
    CERTAIN = "certain"
    LIKELY = "likely"
    GUESSING = "guessing"       # norms not yet grounded ("populate")


# Side values used across the engine (§F symmetry layer). A region that is not
# read per-side uses BILATERAL only.
SIDE_BILATERAL = "bilateral"
SIDE_LEFT = "left"
SIDE_RIGHT = "right"


@dataclass(frozen=True)
class Region:
    key: str                    # stable id, e.g. "hinge", "ankle_df"
    label: str
    group: str                  # A..G section of the taxonomy doc
    capacity: Capacity
    plane: Plane
    probing_test: str
    expectation: str            # reference expectation — a FLAG, not a verdict
    confidence: Confidence
    per_side: bool = True       # readable per-side (§F)
    gates: tuple[str, ...] = () # region keys this one gates (mobility reserves, §B)
    probe_priority: bool = False  # §E + the seed comfort-gap — Probe targets first
    needs_norm: bool = False    # normative grounding still missing ("populate")
    # §G longevity-end axes are flagged but "need normative grounding before they
    # enter the queue" — excluded from the probe queue until grounded, non-blocking.
    queue_eligible: bool = True

    def sides(self) -> list[str]:
        return [SIDE_LEFT, SIDE_RIGHT] if self.per_side else [SIDE_BILATERAL]


# Ordering used when ranking the probe queue: the comfort-cluster blind spot (E)
# and the under-trained transverse/frontal patterns come first.
GROUP_PRIORITY = {"E": 0, "A": 1, "C": 2, "B": 3, "D": 4, "F": 5, "G": 6}


# --------------------------------------------------------------------------- #
# The axis list. Grouped A–G exactly as the companion doc.                    #
# --------------------------------------------------------------------------- #

_REGIONS: tuple[Region, ...] = (
    # ---- A. Loaded movement patterns (strength axes) ----
    Region("hinge", "Hinge (hip-dominant)", "A", Capacity.STRENGTH, Plane.SAGITTAL,
           "Loaded RDL / trap-bar through range, neutral spine held",
           "Self-referenced load + clean bracing; L/R symmetry", Confidence.LIKELY),
    Region("squat", "Squat (knee-dominant)", "A", Capacity.STRENGTH, Plane.SAGITTAL,
           "Deep squat (FMS pattern 1) / loaded squat",
           "Heels-down full-depth dowel-overhead = clean; compensations flag ankle/T-spine",
           Confidence.LIKELY),
    Region("lunge_single_leg", "Lunge / single-leg", "A", Capacity.STRENGTH, Plane.SAGITTAL,
           "In-line lunge (FMS); split squat under load",
           "Symmetry L/R is the signal, not absolute load", Confidence.LIKELY),
    Region("horizontal_push", "Horizontal push", "A", Capacity.STRENGTH, Plane.SAGITTAL,
           "Press / trunk-stability push-up (FMS)",
           "Control through range; no trunk sag", Confidence.LIKELY, per_side=False),
    Region("vertical_push", "Vertical push", "A", Capacity.STRENGTH, Plane.SAGITTAL,
           "Overhead press (gated by shoulder mobility)",
           "Range achieved without rib-flare / lumbar compensation", Confidence.LIKELY,
           per_side=False),
    Region("horizontal_pull", "Horizontal pull", "A", Capacity.STRENGTH, Plane.SAGITTAL,
           "Row variants", "Symmetry; scapular control", Confidence.LIKELY),
    Region("vertical_pull", "Vertical pull", "A", Capacity.STRENGTH, Plane.SAGITTAL,
           "Pull-up / pulldown", "Self-referenced", Confidence.LIKELY, per_side=False),
    Region("carry", "Carry", "A", Capacity.STRENGTH, Plane.FRONTAL,
           "Farmer / offset carry",
           "Offset version probes anti-lateral-flexion asymmetry directly",
           Confidence.LIKELY, probe_priority=True),
    Region("rotation", "Rotation", "A", Capacity.POWER, Plane.TRANSVERSE,
           "Loaded rotation (controlled)",
           "Under-trained; probe cautiously", Confidence.LIKELY, probe_priority=True),
    Region("anti_rotation", "Anti-rotation", "A", Capacity.STABILITY, Plane.TRANSVERSE,
           "Pallof / rotary-stability (FMS pattern 7)",
           "Resist rotation under load symmetrically", Confidence.LIKELY),

    # ---- B. Mobility reserves (ROM gates — these gate the patterns above) ----
    Region("ankle_df", "Ankle dorsiflexion", "B", Capacity.MOBILITY, Plane.SAGITTAL,
           "Weight-bearing lunge / knee-to-wall (cm, heel down)",
           "Functional target ~9-10 cm; L/R difference is the more reliable signal",
           Confidence.LIKELY, gates=("squat",)),
    Region("hip_flexion_pc_length", "Hip flexion / posterior-chain length", "B",
           Capacity.MOBILITY, Plane.SAGITTAL, "Active straight-leg raise (FMS)",
           "Symmetry L/R; gates hinge depth", Confidence.LIKELY, gates=("hinge",)),
    Region("hip_ir_er", "Hip IR / ER", "B", Capacity.MOBILITY, Plane.TRANSVERSE,
           "Seated / prone rotation ROM",
           "Asymmetry flags the side bias", Confidence.GUESSING, needs_norm=True),
    Region("tspine_rotation", "T-spine rotation", "B", Capacity.MOBILITY, Plane.TRANSVERSE,
           "Seated rotation",
           "Stiffness here forces lumbar compensation", Confidence.LIKELY, per_side=False,
           gates=("rotation",)),
    Region("shoulder_mobility", "Shoulder mobility", "B", Capacity.MOBILITY, Plane.MULTI,
           "FMS shoulder reach (fists behind back)",
           "Bilateral; combines IR+add / ER+abd", Confidence.LIKELY,
           gates=("vertical_push",)),

    # ---- C. Stability / motor control ----
    Region("trunk_stability_sagittal", "Trunk stability (sagittal)", "C",
           Capacity.STABILITY, Plane.SAGITTAL, "Trunk-stability push-up (FMS)",
           "Body moves as one unit, no lumbar sag", Confidence.LIKELY, per_side=False),
    Region("rotary_stability", "Rotary stability", "C", Capacity.STABILITY, Plane.TRANSVERSE,
           "Quadruped rotary-stability (FMS)",
           "Contralateral control; lowest-reliability FMS item — read loosely",
           Confidence.LIKELY),
    Region("frontal_single_leg_stability", "Frontal-plane / single-leg stability", "C",
           Capacity.STABILITY, Plane.FRONTAL, "Single-leg stance (eyes open/closed, timed)",
           "Age-referenced balance norms", Confidence.GUESSING, needs_norm=True),
    Region("anti_lateral_flexion", "Anti-lateral-flexion", "C", Capacity.STABILITY,
           Plane.FRONTAL, "Offset carry / suitcase hold",
           "Symmetry under unilateral load", Confidence.LIKELY),

    # ---- D. Locomotion & energy-system capacity ----
    Region("gait_load_carriage", "Gait / load-carriage", "D", Capacity.ENDURANCE,
           Plane.MULTI, "Loaded carry distance, ruck / hike tolerance",
           "Self-referenced", Confidence.LIKELY, per_side=False),
    Region("terrain_perturbation", "Terrain / perturbation", "D", Capacity.STABILITY,
           Plane.MULTI, "Uneven-ground hiking",
           "Probes foot/ankle base + reactive balance", Confidence.LIKELY, per_side=False),
    Region("aerobic_base", "Aerobic base", "D", Capacity.ENDURANCE, Plane.MULTI,
           "Submax HR / pace test", "Age-referenced VO2 norms", Confidence.GUESSING,
           per_side=False, needs_norm=True),
    Region("repeat_effort", "Repeat-effort", "D", Capacity.ENDURANCE, Plane.MULTI,
           "Interval tolerance", "Self-referenced", Confidence.LIKELY, per_side=False),

    # ---- E. Power / reactive / deceleration (the comfort-cluster blind spot) ----
    Region("single_leg_hop", "Single-leg hop (distance)", "E", Capacity.POWER, Plane.MULTI,
           "Single / triple / crossover hop",
           "Limb Symmetry Index >=90% as the return-to-sport reference — rarely met "
           "even uninjured, so treat as direction-of-travel", Confidence.CERTAIN,
           probe_priority=True),
    Region("deceleration_landing", "Deceleration / landing control", "E", Capacity.POWER,
           Plane.MULTI, "Drop-landing, controlled decel",
           "Quality of absorption; asymmetry", Confidence.LIKELY, probe_priority=True),
    Region("change_of_direction", "Change of direction", "E", Capacity.POWER, Plane.MULTI,
           "COD drills (controlled)",
           "Explicitly absent from FMS; the under-probed region", Confidence.CERTAIN,
           probe_priority=True),

    # ---- G. Longevity-end axes (flagged; need norms before they enter the queue) ----
    Region("sit_to_rise", "Sit-to-rise / floor-transfer", "G", Capacity.MOBILITY,
           Plane.MULTI, "Sit-to-rise test",
           "Needs normative grounding before queueing", Confidence.GUESSING, per_side=False,
           needs_norm=True, queue_eligible=False),
    Region("gait_speed", "Gait speed", "G", Capacity.ENDURANCE, Plane.SAGITTAL,
           "Timed walk", "Age-referenced; all-cause-mortality correlate",
           Confidence.GUESSING, per_side=False, needs_norm=True, queue_eligible=False),
    Region("grip_strength", "Grip strength", "G", Capacity.STRENGTH, Plane.MULTI,
           "Dynamometer", "Age/sex-referenced; strong all-cause-mortality correlate",
           Confidence.GUESSING, needs_norm=True, queue_eligible=False),
    Region("single_leg_balance_eyes_closed", "Single-leg balance, eyes closed", "G",
           Capacity.STABILITY, Plane.FRONTAL, "SL stance eyes closed, timed",
           "Age-referenced", Confidence.GUESSING, needs_norm=True, queue_eligible=False),
    Region("loaded_carry_capacity_bw", "Loaded carry capacity vs bodyweight", "G",
           Capacity.ENDURANCE, Plane.FRONTAL, "Carry load relative to bodyweight",
           "Needs normative grounding before queueing", Confidence.GUESSING, per_side=False,
           needs_norm=True, queue_eligible=False),
)

_BY_KEY: dict[str, Region] = {r.key: r for r in _REGIONS}


# --------------------------------------------------------------------------- #
# Accessors                                                                    #
# --------------------------------------------------------------------------- #

def all_regions() -> tuple[Region, ...]:
    return _REGIONS


def by_key(key: str) -> Region | None:
    return _BY_KEY.get(key)


def queue_eligible_regions() -> list[Region]:
    """Regions Probe is allowed to sample — excludes ungrounded §G axes."""
    return [r for r in _REGIONS if r.queue_eligible]


def probe_priority_regions() -> list[Region]:
    return [r for r in _REGIONS if r.probe_priority]


def region_rank(region: Region) -> int:
    """Lower = surfaced earlier in the probe queue."""
    return (0 if region.probe_priority else 1) * 10 + GROUP_PRIORITY.get(region.group, 9)


def as_dict(region: Region) -> dict:
    return {
        "key": region.key,
        "label": region.label,
        "group": region.group,
        "capacity": region.capacity.value,
        "plane": region.plane.value,
        "probing_test": region.probing_test,
        "expectation": region.expectation,
        "confidence": region.confidence.value,
        "per_side": region.per_side,
        "gates": list(region.gates),
        "probe_priority": region.probe_priority,
        "needs_norm": region.needs_norm,
        "queue_eligible": region.queue_eligible,
    }
