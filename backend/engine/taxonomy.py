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
from typing import Any, Literal

# Matches the companion doc (Capability_Taxonomy v1). Bump when the axis list
# changes so capability_state rows can record which version scored them.
# v0.1: +5 tag-coverage axes (#334).
# v1:   Q27 — joint-action strength group H, the Ratio type and Measure/Ratio
#       `reference_kind`; `shoulder_er_ir` is split into `shoulder_er` + `shoulder_ir`.
TAXONOMY_VERSION = "v1"


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


# What a reference band is anchored to (Q27 v1). The rule that governs both
# `Measure.reference_kind` and `Ratio.reference_kind`:
#
#   A "literature" band applies as a THRESHOLD only when the observation's
#   instrument and protocol match the norm's. Otherwise the internal
#   baseline / trend governs, and the literature gives DIRECTION only.
#
# FAILS CLOSED: an observation with no administered_by / protocol provenance is
# evaluated as "internal", whatever the declaration says. Today no observation
# carries that provenance, so nothing evaluates as "literature".
#
# A measure or ratio flips to "literature" only when a norm matching its
# instrument AND protocol is CITED. "internal" means the user's own baseline and
# trend are the only reference.
ReferenceKind = Literal["internal", "literature"]
REFERENCE_KINDS: tuple[str, ...] = ("internal", "literature")


def _check_reference_kind(owner: str, kind: Any) -> None:
    # A Literal is not enforced at runtime; a typo here would silently read as
    # "not literature" everywhere it is compared.
    if kind not in REFERENCE_KINDS:
        raise ValueError(f"{owner}: reference_kind {kind!r} is not one of {list(REFERENCE_KINDS)}")


@dataclass(frozen=True)
class Measure:
    """A declared, unit-bearing quantity a region can be MEASURED on.

    Distinct from `capability_state.status`, which is the response-to-load verdict
    written from the adaptation loop's education idiom. A measure is a quantity
    someone recorded — different signal, different provenance, both real
    (DECISIONS_LOG #161). Declaring the set here rather than accepting free text
    is what stops `measure_key` drifting into a synonym pile within weeks.

    `per_side` is a property of the INSTRUMENT, not of the region. A region can be
    readable per-side (`Region.per_side`, the §F symmetry layer) while a particular
    measure of it is not: a trunk-mounted GPS unit records one deceleration count
    for the athlete and cannot attribute it to a leg, even though
    `deceleration_landing` is a per-side region. Sidedness is therefore validated
    per-measure, and a region's `sides()` remains the ceiling.

    A region with no declared measure is observation-ineligible. That is the
    correct default for an axis nobody has chosen an instrument for, not a gap.

    `reference_kind` (Q27 v1) says what a reference band for THIS measure is
    anchored to. The rule: a "literature" band applies as a threshold ONLY when
    the observation's instrument and protocol match the norm's; otherwise the
    internal baseline / trend governs and the literature gives direction only.
    The gate FAILS CLOSED: an observation with no administered_by / protocol
    provenance is evaluated as "internal" even where the measure is declared
    "literature". `capability_observations` carries no such provenance yet, so
    today every observation evaluates as "internal".
    A measure flips to "literature" only when a norm matching its protocol is
    cited. The default is "internal"; every v1 measure is "internal" because no
    matching norm is cited (the ER:IR band is isokinetic torque, not HHD force;
    the Copenhagen squeeze is validated as a pain score, not as mmHg). No consumer
    reads this field yet. No numeric norm lives on the declaration either, by
    design: bands are expectation text.
    """
    key: str                    # stable id, e.g. "knee_to_wall_cm"
    unit: str                   # "cm", "deg", "s", "m/s", "m/s^2", "N", "mmHg", "count"
    higher_is_better: bool
    per_side: bool = True
    reference_kind: ReferenceKind = "internal"

    def __post_init__(self) -> None:
        _check_reference_kind(f"Measure {self.key!r}", self.reference_kind)

    def sides(self) -> list[str]:
        """Sides this measure can legally carry, before the region's own ceiling."""
        return [SIDE_LEFT, SIDE_RIGHT] if self.per_side else [SIDE_BILATERAL]


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
    gates: tuple[str, ...] = () # region keys THIS region gates (mobility reserves, §B;
                                # ankle_df -> squat) — never the regions that gate it
    probe_priority: bool = False  # §E + the seed comfort-gap — Probe targets first
    needs_norm: bool = False    # normative grounding still missing ("populate")
    # §G longevity-end axes are flagged but "need normative grounding before they
    # enter the queue" — excluded from the probe queue until grounded, non-blocking.
    queue_eligible: bool = True
    # Quantities this region may be OBSERVED on (capability_observations). Empty
    # = observation-ineligible. Versioned with TAXONOMY_VERSION like the rest of
    # the axis list; seeded narrow on purpose (DECISIONS_LOG #161).
    measures: tuple[Measure, ...] = ()

    def sides(self) -> list[str]:
        return [SIDE_LEFT, SIDE_RIGHT] if self.per_side else [SIDE_BILATERAL]

    def measure(self, measure_key: str) -> Measure | None:
        for m in self.measures:
            if m.key == measure_key:
                return m
        return None


@dataclass(frozen=True)
class Ratio:
    """A DERIVED read across two observations (Q27 v1) — it generalises the §F
    limb-symmetry index. A Region is something you can load or test; a Measure is
    a quantity recorded on a region; a Ratio is neither: it is `numerator /
    denominator` computed at READ time from two measures already declared on
    regions. It is never stored as an observation (no key here is a region key or
    a measure key — asserted in the tests), so there is no ratio row to drift from
    the two observations it came from.

    `numerator` / `denominator` are `(region_key, measure_key)` pairs and must
    resolve on the taxonomy and share a unit. `same_side=True` pairs the left
    numerator with the left denominator (never across limbs), which needs both
    measures to be per-side. `same_protocol=True` records that the two readings
    must come from the same protocol; it is declarative only until observations
    carry protocol provenance (OPEN_QUESTIONS Q27), so nothing enforces it yet.

    `reference_kind` follows the Measure rule: a "literature" band applies as a
    threshold ONLY when the observation's instrument and protocol match the
    norm's; otherwise the internal baseline / trend governs and the literature
    gives direction only. It FAILS CLOSED: an observation with no administered_by
    / protocol provenance is evaluated as "internal". A ratio flips to
    "literature" only when a norm matching its protocol is cited.
    `expectation` is a FLAG, not a verdict, like
    `Region.expectation`: any band sits in that text marked "to populate" and
    there is NO numeric threshold on this class, so no automatic deficit flag
    can fire from it.

    The log-derived computation (route i) is not built; this is the declaration.
    """
    key: str                              # stable id, e.g. "er_ir"
    label: str
    numerator: tuple[str, str]            # (region_key, measure_key)
    denominator: tuple[str, str]
    reference_kind: ReferenceKind
    expectation: str
    confidence: Confidence
    same_side: bool = True
    same_protocol: bool = True

    def __post_init__(self) -> None:
        _check_reference_kind(f"Ratio {self.key!r}", self.reference_kind)

    def pairs(self) -> tuple[tuple[str, str], tuple[str, str]]:
        return (self.numerator, self.denominator)


# Ordering used when ranking the probe queue: the comfort-cluster blind spot (E)
# and the under-trained transverse/frontal patterns come first. H (joint-action
# strength, v1) ranks last on purpose: every H region is queue-ineligible, so the
# slot is inert today, and admitting one to the queue must set its rank deliberately.
GROUP_PRIORITY = {"E": 0, "A": 1, "C": 2, "B": 3, "D": 4, "F": 5, "G": 6, "H": 7}


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

    # ---- A (v0.1). Tag-coverage axes (#334). Admitted under the region-admission (#335)
    # guardrail: each names a quality the program deliberately trains, tests or protects.
    # Every probe/observation field is EXPLICIT and inert — no measure, not queue-eligible,
    # not probe-priority — so none becomes a probe candidate until deliberately admitted.
    # They exist so tagged exercises stop falling to the keyword fallback / Rule 1 `untagged`.
    # v1 (Q27): the three joint-action regions of this batch (shoulder_er_ir, knee_flexion,
    # hip_adduction) moved to group H below; only trunk_lateral_flexion and dip remain here.
    Region("trunk_lateral_flexion", "Trunk lateral flexion (loaded, through range)", "A",
           Capacity.STRENGTH, Plane.FRONTAL, "Weighted side bend / lateral flexion-extension",
           "Loaded lateral flexion THROUGH range - distinct from anti_lateral_flexion "
           "(resisting it); symmetry L/R", Confidence.LIKELY, per_side=True,
           probe_priority=False, queue_eligible=False, measures=()),
    Region("dip", "Dip", "A", Capacity.STRENGTH, Plane.SAGITTAL,
           "Dip / dip machine",
           "Depth without anterior-shoulder compensation; distinct from vertical_push",
           Confidence.LIKELY, per_side=False, probe_priority=False, queue_eligible=False,
           measures=()),

    # ---- B. Mobility reserves (ROM gates — these gate the patterns above) ----
    Region("ankle_df", "Ankle dorsiflexion", "B", Capacity.MOBILITY, Plane.SAGITTAL,
           "Weight-bearing lunge / knee-to-wall (cm, heel down)",
           "Functional target ~9-10 cm; L/R difference is the more reliable signal",
           Confidence.LIKELY, gates=("squat",),
           measures=(Measure("knee_to_wall_cm", "cm", higher_is_better=True),)),
    Region("hip_flexion_pc_length", "Hip flexion / posterior-chain length", "B",
           Capacity.MOBILITY, Plane.SAGITTAL, "Active straight-leg raise (FMS)",
           "Symmetry L/R; gates hinge depth", Confidence.LIKELY, gates=("hinge",),
           measures=(Measure("aslr_deg", "deg", higher_is_better=True),)),
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
           gates=("vertical_push",),
           measures=(Measure("er_rom_deg", "deg", higher_is_better=True),)),

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
           "Age-referenced balance norms", Confidence.GUESSING, needs_norm=True,
           measures=(Measure("stance_seconds", "s", higher_is_better=True),)),
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
           probe_priority=True,
           measures=(Measure("hop_distance_cm", "cm", higher_is_better=True),)),
    Region("deceleration_landing", "Deceleration / landing control", "E", Capacity.POWER,
           Plane.MULTI, "Drop-landing, controlled decel",
           "Quality of absorption; asymmetry", Confidence.LIKELY, probe_priority=True,
           # Trunk-mounted GPS: one figure for the athlete, not attributable to a
           # leg — hence per_side=False on a per-side region (see Measure).
           measures=(Measure("peak_decel_ms2", "m/s^2", higher_is_better=True,
                             per_side=False),)),
    Region("change_of_direction", "Change of direction", "E", Capacity.POWER, Plane.MULTI,
           "COD drills (controlled)",
           "Explicitly absent from FMS; the under-probed region", Confidence.CERTAIN,
           probe_priority=True,
           measures=(Measure("cod_count", "count", higher_is_better=True,
                             per_side=False),)),

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

    # ---- H. Joint-action strength (v1, Q27) ----
    # One region per joint action, so a strength RATIO can be declared across two of them
    # (see _RATIOS). Group H rather than A: A is loaded movement PATTERNS; these are joint
    # actions, and the group is what keeps them from being read as patterns.
    # Admitted under #335 (tested as a ratio denominator, or trained and tested). Every
    # probe field is EXPLICIT and inert: not probe-priority, not queue-eligible, norms
    # still to populate, confidence GUESSING on the bands. Bands live in `expectation`
    # text only, marked "to populate" — there is no numeric norm in code (G3).
    # shoulder_er_ir was split in two (R1). Neither half gates anything: the old
    # `gates=("dip",)` was dropped by the operator's ruling, so dip is ungated (inert either way).
    # HHD force (N) is a clinic dynamometry reading, EP-administered (R4), not a gym lift.
    # Every measure here keeps the "internal" reference_kind: a measure flips to "literature"
    # only when a norm matching its instrument and protocol is CITED, and none is yet.
    Region("shoulder_er", "Shoulder external rotation (rotator cuff)", "H", Capacity.STRENGTH,
           Plane.TRANSVERSE, "Clinic HHD ER force (EP-administered); cable / band ER at load",
           "Numerator of the ER:IR ratio (er_ir); symmetry L/R. Band to populate (Q27 "
           "cites ~0.66-0.75, an isokinetic-torque reference, not HHD force; unverified)",
           Confidence.GUESSING, per_side=True, probe_priority=False,
           needs_norm=True, queue_eligible=False,
           measures=(Measure("hhd_force_n", "N", higher_is_better=True),)),
    Region("shoulder_ir", "Shoulder internal rotation (rotator cuff)", "H", Capacity.STRENGTH,
           Plane.TRANSVERSE, "Clinic HHD IR force (EP-administered); cable / band IR at load",
           "Denominator of the ER:IR ratio (er_ir); symmetry L/R. Band to populate",
           Confidence.GUESSING, per_side=True, probe_priority=False,
           needs_norm=True, queue_eligible=False,
           measures=(Measure("hhd_force_n", "N", higher_is_better=True),)),
    Region("hip_adduction", "Hip adduction (adductor)", "H", Capacity.STRENGTH,
           Plane.FRONTAL, "Clinic HHD adduction force (EP-administered); adductor squeeze "
           "(BP cuff, optional); Copenhagen plank (exposure)",
           "Numerator of the adductor:abductor ratio (add_abd); groin protection; symmetry "
           "L/R. Copenhagen is exposure only and does not feed add_abd. Band to populate",
           Confidence.GUESSING, per_side=True, probe_priority=False, needs_norm=True,
           queue_eligible=False,
           measures=(Measure("hhd_force_n", "N", higher_is_better=True),
                     # One cuff reading squeezed between the knees: not attributable to a leg.
                     Measure("squeeze_mmhg", "mmHg", higher_is_better=True, per_side=False))),
    Region("hip_abduction", "Hip abduction (abductor)", "H", Capacity.STRENGTH,
           Plane.FRONTAL, "Clinic HHD abduction force (EP-administered); hip abduction machine "
           "at load (exposure)",
           "Denominator of the adductor:abductor ratio (add_abd); symmetry L/R. Band to populate",
           Confidence.GUESSING, per_side=True, probe_priority=False, needs_norm=True,
           queue_eligible=False,
           measures=(Measure("hhd_force_n", "N", higher_is_better=True),)),
    Region("ankle_plantarflexion", "Ankle plantarflexion (calf)", "H", Capacity.STRENGTH,
           Plane.SAGITTAL, "Single-leg heel raise, reps to fatigue; calf raise at load",
           "Reps against the internal baseline and L/R; band to populate. "
           "Plantarflexion STRENGTH, not ankle_df (dorsiflexion MOBILITY)",
           Confidence.GUESSING, per_side=True, probe_priority=False, needs_norm=True,
           queue_eligible=False,
           measures=(Measure("sl_heel_raise_reps", "count", higher_is_better=True),)),
    # R3: an ABSOLUTE + LSI read. No H:Q ratio is declared and knee_extension is NOT admitted.
    # No Measure is declared (R3 names no instrument), so this stays observation-ineligible.
    Region("knee_flexion", "Knee flexion (hamstring)", "H", Capacity.STRENGTH,
           Plane.SAGITTAL, "Nordic curl / leg curl",
           "Absolute eccentric + LSI (L/R); no H:Q ratio. Band to populate",
           Confidence.GUESSING, per_side=True, probe_priority=False, needs_norm=True,
           queue_eligible=False, measures=()),
)

_BY_KEY: dict[str, Region] = {r.key: r for r in _REGIONS}


# --------------------------------------------------------------------------- #
# Ratios (Q27 v1) — derived reads across two declared measures                #
# --------------------------------------------------------------------------- #

_RATIOS: tuple[Ratio, ...] = (
    Ratio("er_ir", "Shoulder ER:IR (rotator cuff)",
          numerator=("shoulder_er", "hhd_force_n"), denominator=("shoulder_ir", "hhd_force_n"),
          reference_kind="internal",
          expectation="External:internal rotation force, same side, same protocol. Band to "
                      "populate (Q27 cites ~0.66-0.75, an isokinetic-torque reference, not HHD "
                      "force; unverified). Internal baseline and trend govern until a norm "
                      "matching the protocol is cited",
          confidence=Confidence.GUESSING),
    Ratio("add_abd", "Hip adductor:abductor",
          numerator=("hip_adduction", "hhd_force_n"), denominator=("hip_abduction", "hhd_force_n"),
          reference_kind="internal",
          expectation="Adductor:abductor force, same side, same protocol (groin-strain "
                      "literature). Band to populate. Internal baseline and trend govern until "
                      "a norm matching the protocol is cited",
          confidence=Confidence.GUESSING),
)


def validate_ratio(ratio: Ratio, regions: dict[str, Region] | None = None) -> None:
    """Raise ValueError unless `ratio` is a coherent declaration against `regions`
    (default: the live taxonomy). Run over every declared ratio at import, so a bad
    declaration fails loudly instead of producing a ratio nothing can compute."""
    regions = _BY_KEY if regions is None else regions
    if not ratio.key:
        raise ValueError("Ratio: key is empty")
    ends: list[Measure] = []
    for role, (region_key, measure_key) in (("numerator", ratio.numerator),
                                            ("denominator", ratio.denominator)):
        region = regions.get(region_key)
        if region is None:
            raise ValueError(f"Ratio {ratio.key!r}: {role} region {region_key!r} is not in the taxonomy")
        measure = region.measure(measure_key)
        if measure is None:
            raise ValueError(
                f"Ratio {ratio.key!r}: {role} measure {measure_key!r} is not declared on "
                f"region {region_key!r} (declared: {[m.key for m in region.measures]})"
            )
        ends.append(measure)
    if ratio.numerator == ratio.denominator:
        raise ValueError(f"Ratio {ratio.key!r}: numerator and denominator are the same reading")
    num, den = ends
    if num.unit != den.unit:
        raise ValueError(
            f"Ratio {ratio.key!r}: units differ ({num.unit!r} / {den.unit!r}) — a ratio of "
            f"unlike quantities is not a ratio"
        )
    if ratio.same_side and not (num.per_side and den.per_side):
        raise ValueError(
            f"Ratio {ratio.key!r}: same_side=True needs both measures per-side, "
            f"got {num.key!r} per_side={num.per_side} / {den.key!r} per_side={den.per_side}"
        )
    _check_reference_kind(f"Ratio {ratio.key!r}", ratio.reference_kind)
    if not isinstance(ratio.confidence, Confidence):
        raise ValueError(f"Ratio {ratio.key!r}: confidence must be a Confidence")


def _validate_declared_ratios() -> dict[str, Ratio]:
    seen: dict[str, Ratio] = {}
    for ratio in _RATIOS:
        if ratio.key in seen:
            raise ValueError(f"Ratio {ratio.key!r} is declared twice")
        validate_ratio(ratio)
        seen[ratio.key] = ratio
    return seen


_RATIO_BY_KEY: dict[str, Ratio] = _validate_declared_ratios()


# --------------------------------------------------------------------------- #
# Accessors                                                                    #
# --------------------------------------------------------------------------- #

def all_regions() -> tuple[Region, ...]:
    return _REGIONS


def by_key(key: str) -> Region | None:
    return _BY_KEY.get(key)


def capacity_tokens() -> list[str]:
    """The accepted spellings, for error messages. Uppercase because that is the
    form the weekly-template and the `?capacity=` query parameter are written in."""
    return [c.name for c in Capacity]


def resolve_capacity(token: Any) -> "Capacity | None":
    """Resolve a caller-supplied capacity token, or None if it is not one.

    Accepts either the enum NAME ("STABILITY", the form templates and query
    parameters are written in) or its VALUE ("stability", the form
    `Region.capacity.value` and the probe-queue entries carry), case-insensitively.
    Both spellings collapse because `name.lower() == value` holds for every member
    — asserted in `tests/test_weekly_template.py` so a later member that breaks the
    identity cannot land silently.

    Returns None rather than raising: callers turn it into their own refusal
    (422 at the router, ValueError inside the engine).
    """
    if not isinstance(token, str):
        return None
    try:
        return Capacity(token.strip().lower())
    except ValueError:
        return None


def measures_for(region_key: str) -> tuple[Measure, ...]:
    """Declared measures for a region. Empty for an unknown key AND for a known
    region with no instrument chosen — callers that must tell those apart check
    `by_key()` first, which is why this does not raise."""
    region = _BY_KEY.get(region_key)
    return region.measures if region else ()


def measure_for(region_key: str, measure_key: str) -> Measure | None:
    region = _BY_KEY.get(region_key)
    return region.measure(measure_key) if region else None


def all_ratios() -> tuple[Ratio, ...]:
    return _RATIOS


def ratio_by_key(key: str) -> Ratio | None:
    return _RATIO_BY_KEY.get(key)


def ratios_for_region(region_key: str) -> tuple[Ratio, ...]:
    """Ratios a region takes part in, as numerator or denominator."""
    return tuple(r for r in _RATIOS if region_key in (r.numerator[0], r.denominator[0]))


def observable_regions() -> list[Region]:
    """Regions carrying at least one declared measure — the observation-eligible set."""
    return [r for r in _REGIONS if r.measures]


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
        "measures": [
            {
                "key": m.key,
                "unit": m.unit,
                "higher_is_better": m.higher_is_better,
                "per_side": m.per_side,
                "sides": m.sides(),
                "reference_kind": m.reference_kind,
            }
            for m in region.measures
        ],
    }


def ratio_as_dict(ratio: Ratio) -> dict:
    return {
        "key": ratio.key,
        "label": ratio.label,
        "numerator": {"region": ratio.numerator[0], "measure": ratio.numerator[1]},
        "denominator": {"region": ratio.denominator[0], "measure": ratio.denominator[1]},
        "same_side": ratio.same_side,
        "same_protocol": ratio.same_protocol,
        "reference_kind": ratio.reference_kind,
        "expectation": ratio.expectation,
        "confidence": ratio.confidence.value,
    }
