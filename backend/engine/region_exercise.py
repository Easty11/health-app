"""Region→exercise consumer — the loose mode-router (DECISIONS_LOG #NEXT).

`select_next` prescribes at region×capacity×side but never names a concrete exercise;
the model improvised one per session, the source of exercise-duplication and the
55-routine sprawl. This module sits DOWNSTREAM of `select_next` (it never changes the
prescription) and resolves each prescribed region to either a concrete exercise (TRAIN
mode) or a screen (SCREEN mode).

Routing axis — tags-and-measure, NOT `queue_eligible` (DESIGN CALL 0). `queue_eligible`
governs the upstream probe queue (`compute_probe_queue`), not this consumer. Each region
handed here is classified by two orthogonal facts:

  has exercise_region_tags?   declares a Region.measure?   mode
  ----------------------------------------------------------------
  yes                         (either)                     TRAIN   — return an exercise
  no                          yes                          SCREEN  — via the Measure layer (§E)
  no                          no                           SCREEN  — honest "no instrument" stub (§G)
  yes                         no                           TRAIN

Tiered tag usability (DESIGN CALL 1). `source='human_confirmed'` tags are TRUSTED; the
`llm_proposed` reference is USABLE-BUT-PROVISIONAL — the exercise is still returned, but
the result carries `provisional=True` AND a `reason` that says so in words, so a guess is
narrated as a guess (the WriteResult acknowledgement discipline, #283/#286/#288). Trusted
candidates are preferred; only-provisional falls back to provisional-flagged.

Loose, not lifecycle (DESIGN CALL 3). The router reads current state and picks a mode per
call. No auto-promotion screen→train on a passing screen, no persisted per-region mode
state machine, no progression-tier selection — all DEFERRED (OPEN_QUESTIONS).

Scope honesty (DESIGN CALL 2). This consumer guarantees that any region handed to it
returns honest-not-silent. It does NOT make the engine proactively surface §G: a
`queue_eligible=False` region reaches here only as a `fortify` primary_target, because
`compute_probe_queue` (untouched) never emits one. Proactive §G screening is a separate
upstream change (see OPEN_QUESTIONS).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

import models
from hevy_templates import _visible_to  # ONE visibility rule, never two (#83, FEEDBACK §10)
from reads.hevy_reads import counted_workouts   # the counted-workouts read-door (#Q161)

from . import taxonomy
from .taxonomy import SIDE_BILATERAL, SIDE_LEFT, SIDE_RIGHT

# Modes. UNRESOLVED is not a third routing mode — it is the honest terminal for a
# prescription that names no taxonomy region, or a sided TRAIN prescription no tagged
# exercise can express. Never a silent drop (GATE).
MODE_TRAIN = "train"
MODE_SCREEN = "screen"
MODE_UNRESOLVED = "unresolved"

# Reason codes — the WriteResult-style honest vocabulary for this lane.
RC_TRAIN_SELECTED = "train_selected"            # trusted tag → concrete exercise
RC_TRAIN_PROVISIONAL = "train_provisional"      # llm_proposed tag → exercise, flagged provisional
RC_SCREEN_MEASURE = "screen_measure"            # no tags, declares a measure → screen via Measure layer
RC_SCREEN_NO_INSTRUMENT = "screen_no_instrument"  # no tags, no measure (§G) → honest stub
RC_NO_SIDE_MATCH = "no_side_match"              # tags exist but none express the prescribed side
RC_TARGET_NOT_A_REGION = "target_not_a_region"  # fortify target is a free descriptor, not a Region.key

# A tag is TRUSTED iff human-confirmed; the --confirm seed stamps this alongside
# `hevy_exercise_templates.adjudicated_at` (DECISIONS_LOG #76). Anything else (the
# `llm_proposed` reference) is usable-but-provisional.
_TRUSTED_SOURCE = "human_confirmed"

# Laterality values an exercise can carry (models.HevyExerciseTemplate.laterality).
_UNILATERAL = "unilateral"
_ALTERNATING = "alternating"


@dataclass(frozen=True)
class RegionResolution:
    """One prescribed region resolved to an exercise, a screen, or an honest terminal.

    `exercise` is populated only in TRAIN mode; `screen` only for SCREEN via a measure.
    `provisional` is meaningful only in TRAIN mode and is always surfaced through `reason`
    as well as the flag (DESIGN CALL 1) — never a bare boolean a narrator can drop.
    """
    region_key: str
    side: str
    mode: str
    reason_code: str
    reason: str
    provisional: bool = False
    exercise: dict[str, Any] | None = None
    screen: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "region_key": self.region_key,
            "side": self.side,
            "mode": self.mode,
            "reason_code": self.reason_code,
            "reason": self.reason,
            "provisional": self.provisional,
            "exercise": self.exercise,
            "screen": self.screen,
        }


def _side_ok(laterality: str | None, side: str) -> bool:
    """Can an exercise of this `laterality` express a prescription for this `side` (V4)?

    A bilateral prescription accepts any exercise. A sided prescription (left/right) needs
    a `unilateral`/`alternating` exercise — logged as two sided entries (#287); a bilateral
    or untagged-laterality (NULL) exercise cannot isolate one side, so it is refused for a
    sided prescription rather than silently mis-served.
    """
    if side == SIDE_BILATERAL:
        return True
    if side in (SIDE_LEFT, SIDE_RIGHT):
        return laterality in (_UNILATERAL, _ALTERNATING)
    return False


def _candidate_tags(db: Session, user_id: int, region_key: str) -> list[dict[str, Any]]:
    """Tagged, in-scope templates for a region (the prescribe-direction join, V3).

    Joins `exercise_region_tags` → `hevy_exercise_templates`, scoped by `_visible_to`
    (global defaults OR this user's own customs — the SAME predicate the resolver uses).
    Both `primary` and `secondary` roles count: the region IS served regardless of primacy.
    """
    Tag = models.ExerciseRegionTag
    Tmpl = models.HevyExerciseTemplate
    rows = db.execute(
        select(Tmpl.id, Tmpl.title, Tmpl.laterality, Tag.source)
        .join(Tmpl, Tag.hevy_exercise_template_id == Tmpl.id)
        .where(Tag.region_key == region_key)
        .where(_visible_to(user_id))
    ).all()
    return [
        {"template_id": tid, "title": title, "laterality": lat, "source": source}
        for (tid, title, lat, source) in rows
    ]


def _select(candidates: list[dict[str, Any]], recent_template_ids: frozenset[str]) -> dict[str, Any]:
    """Pick one candidate with rotation / recency-avoidance (DESIGN CALL 4).

    Prefer TRUSTED tags over provisional; within the chosen trust tier, prefer an exercise
    NOT recently prescribed for this region, then a stable title tie-break so output is
    reproducible. Simple and legible — the documented hook the DEFERRED tiering extends.
    """
    trusted = [c for c in candidates if c["source"] == _TRUSTED_SOURCE]
    tier = trusted or candidates
    tier = sorted(
        tier,
        key=lambda c: (c["template_id"] in recent_template_ids, (c["title"] or "").lower(), c["template_id"]),
    )
    return tier[0]


def _screen_for(region: taxonomy.Region, side: str) -> dict[str, Any]:
    """The Measure-layer screen descriptor for a region that declares a measure (§E).

    Names WHAT to log so the caller can record it through `observations.record_observation`
    (self-report is the default source, V1). Picks a measure whose sidedness admits the
    prescribed side; otherwise the first declared measure at its own default side.
    """
    for m in region.measures:
        if side in m.sides():
            chosen, chosen_side = m, side
            break
    else:
        chosen = region.measures[0]
        chosen_side = chosen.sides()[0]
    return {
        "measure_key": chosen.key,
        "unit": chosen.unit,
        "higher_is_better": chosen.higher_is_better,
        "side": chosen_side,
        "probing_test": region.probing_test,
    }


def resolve_region(
    db: Session,
    user_id: int,
    *,
    region_key: str,
    side: str,
    recent_template_ids: frozenset[str] = frozenset(),
) -> RegionResolution:
    """Resolve one prescribed (region, side) to an exercise, a screen, or an honest terminal."""
    region = taxonomy.by_key(region_key)
    if region is None:
        # A `fortify` primary_target may be a free descriptor, not a Region.key (models note).
        return RegionResolution(
            region_key=region_key, side=side, mode=MODE_UNRESOLVED,
            reason_code=RC_TARGET_NOT_A_REGION,
            reason=(
                f"'{region_key}' is not a taxonomy region — no exercise or screen can be "
                "resolved for it (likely a free-text fortify target)."
            ),
        )

    candidates = _candidate_tags(db, user_id, region_key)
    if candidates:  # TRAIN — the region has tags
        compatible = [c for c in candidates if _side_ok(c["laterality"], side)]
        if not compatible:
            return RegionResolution(
                region_key=region_key, side=side, mode=MODE_UNRESOLVED,
                reason_code=RC_NO_SIDE_MATCH,
                reason=(
                    f"{len(candidates)} exercise(s) are tagged for '{region_key}', but none is "
                    f"unilateral/alternating, so none can express a {side}-side prescription."
                ),
            )
        pick = _select(compatible, recent_template_ids)
        provisional = pick["source"] != _TRUSTED_SOURCE
        exercise = {
            "template_id": pick["template_id"],
            "title": pick["title"],
            "laterality": pick["laterality"],
        }
        if provisional:
            return RegionResolution(
                region_key=region_key, side=side, mode=MODE_TRAIN,
                reason_code=RC_TRAIN_PROVISIONAL, provisional=True, exercise=exercise,
                reason=(
                    f"'{pick['title']}' — drawn from an UNCONFIRMED (LLM-proposed) region tag; "
                    "treat as provisional until the tag is human-confirmed."
                ),
            )
        return RegionResolution(
            region_key=region_key, side=side, mode=MODE_TRAIN,
            reason_code=RC_TRAIN_SELECTED, provisional=False, exercise=exercise,
            reason=f"'{pick['title']}' — selected from a confirmed tag for '{region_key}'.",
        )

    # SCREEN — no tags. A declared measure means the Measure layer can screen it (§E);
    # otherwise the honest "no instrument yet" stub (§G), never a silent nothing.
    if region.measures:
        return RegionResolution(
            region_key=region_key, side=side, mode=MODE_SCREEN,
            reason_code=RC_SCREEN_MEASURE, screen=_screen_for(region, side),
            reason=(
                f"No trainable exercise is tagged for '{region_key}' yet — screen it via "
                f"'{region.measures[0].key}' (self-report accepted)."
            ),
        )
    return RegionResolution(
        region_key=region_key, side=side, mode=MODE_SCREEN,
        reason_code=RC_SCREEN_NO_INSTRUMENT, screen=None,
        reason=(
            f"'{region_key}' has no tagged exercise and no declared screen instrument yet — "
            "it cannot be trained or measured until one is added."
        ),
    )


def recent_template_ids(db: Session, user_id: int, *, limit_workouts: int = 20) -> frozenset[str]:
    """Template ids logged in the user's most recent workouts — the recency signal for
    rotation (DESIGN CALL 4). DB-only (`hevy_sets`), sync, no Hevy call. Empty is a valid
    result (nothing logged, or the sets table not backfilled) → rotation is simply inert."""
    Workout = models.HevyWorkout
    Set = models.HevySet
    # Read-door (#Q161): fetch the non-excluded candidates, filter to COUNTED via the door,
    # THEN take the most-recent `limit_workouts`. The limit is applied AFTER the door so an
    # unadjudicated duplicate cannot eat a recency slot and evict a genuinely-distinct workout.
    candidates = db.execute(
        select(Workout)
        .where(Workout.user_id == user_id)
        .where(Workout.excluded_at.is_(None))
        .order_by(Workout.start_time.desc().nullslast())
    ).scalars().all()
    counted, _unadjudicated = counted_workouts(db, user_id, candidates)
    recent_ids = [w.hevy_id for w in counted[:limit_workouts]]
    if not recent_ids:
        return frozenset()
    tmpl_ids = db.execute(
        select(Set.exercise_template_id).where(Set.workout_id.in_(recent_ids)).distinct()
    ).scalars().all()
    return frozenset(t for t in tmpl_ids if t)


def resolve_prescription(
    db: Session,
    user_id: int,
    engine_out: dict[str, Any],
    *,
    recent_template_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Resolve a `select_next` return to concrete exercises/screens (pure-downstream, V2).

    Resolves the Probe candidate (carries region_key+side) and the Fortify target (carries
    NO side — defaults to bilateral, the one V2 seam). Never mutates `engine_out`.
    """
    recent = recent_template_ids if recent_template_ids is not None else frozenset()

    probe = engine_out.get("probe")
    probe_res = None
    if isinstance(probe, dict) and probe.get("region_key"):
        probe_res = resolve_region(
            db, user_id,
            region_key=probe["region_key"], side=probe.get("side", SIDE_BILATERAL),
            recent_template_ids=recent,
        ).to_dict()

    fortify = engine_out.get("fortify") or {}
    target = fortify.get("target")
    fortify_res = None
    if target:
        fortify_res = resolve_region(
            db, user_id,
            region_key=target, side=SIDE_BILATERAL,  # V2 seam: fortify carries no side
            recent_template_ids=recent,
        ).to_dict()

    return {"probe": probe_res, "fortify": fortify_res}
