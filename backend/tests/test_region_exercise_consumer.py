"""Region→exercise consumer — loose mode-router (DECISIONS_LOG #NEXT).

Pins the routing axis (tags-and-measure, NOT queue_eligible), the tiered tag usability
(trusted vs provisional-surfaced), the §E screen-via-measure fix, the §G honest stub, the
laterality-to-side mapping, and rotation/recency-avoidance. Sibling of the routine/exercise
WriteResult folds: a guess is never narrated as settled, and a region handed to the
consumer never falls to silent nothing.
"""
from datetime import datetime, timezone

import models
from engine import region_exercise as rx

USER = 1


def _seed_template(db, tid, title, laterality=None, is_custom=False, owner_user_id=None):
    # Default = a Hevy global default (is_custom=False, owner NULL), visible to every user
    # via `_visible_to`. Pass is_custom=True + owner_user_id=USER for an account custom.
    db.add(models.HevyExerciseTemplate(
        id=tid, title=title, is_custom=is_custom, owner_user_id=owner_user_id, laterality=laterality,
    ))
    db.flush()  # parent before any ExerciseRegionTag (FK-enforced, #239)


def _tag(db, tid, region_key, role="primary", source="human_confirmed"):
    db.add(models.ExerciseRegionTag(
        hevy_exercise_template_id=tid, region_key=region_key, role=role, source=source,
    ))
    db.flush()


# --------------------------------------------------------------------------- #
# TRAIN mode — a region with tags returns a concrete, side-correct exercise.  #
# --------------------------------------------------------------------------- #

def test_train_trusted_returns_concrete_exercise(db_session):
    _seed_template(db_session, "sq1", "Goblet Squat", laterality="bilateral")
    _tag(db_session, "sq1", "squat", source="human_confirmed")
    db_session.commit()

    res = rx.resolve_region(db_session, USER, region_key="squat", side="bilateral")
    assert res.mode == rx.MODE_TRAIN
    assert res.reason_code == rx.RC_TRAIN_SELECTED
    assert res.provisional is False
    assert res.exercise["template_id"] == "sq1"
    assert res.exercise["title"] == "Goblet Squat"


def test_sided_prescription_picks_unilateral_not_bilateral(db_session):
    """A left/right prescription must resolve to a unilateral/alternating exercise — a
    bilateral one cannot isolate a side (V4)."""
    _seed_template(db_session, "bi1", "Leg Press (Machine)", laterality="bilateral")
    _seed_template(db_session, "uni1", "Bulgarian Split Squat", laterality="unilateral")
    _tag(db_session, "bi1", "lunge_single_leg")
    _tag(db_session, "uni1", "lunge_single_leg")
    db_session.commit()

    res = rx.resolve_region(db_session, USER, region_key="lunge_single_leg", side="left")
    assert res.mode == rx.MODE_TRAIN
    assert res.exercise["template_id"] == "uni1"
    assert res.exercise["laterality"] == "unilateral"


def test_sided_prescription_with_only_bilateral_tags_is_honest_no_side_match(db_session):
    """Tags exist but none can express the side → explicit no_side_match, never a silent
    drop and never a bilateral exercise mislabelled as sided."""
    _seed_template(db_session, "bi1", "Leg Press (Machine)", laterality="bilateral")
    _tag(db_session, "bi1", "lunge_single_leg")
    db_session.commit()

    res = rx.resolve_region(db_session, USER, region_key="lunge_single_leg", side="right")
    assert res.mode == rx.MODE_UNRESOLVED
    assert res.reason_code == rx.RC_NO_SIDE_MATCH
    assert res.exercise is None
    assert "unilateral" in res.reason


# --------------------------------------------------------------------------- #
# Tiered tag usability — a provisional guess is surfaced, never narrated settled. #
# --------------------------------------------------------------------------- #

def test_llm_proposed_tag_returns_exercise_flagged_provisional_and_surfaced(db_session):
    """GATE: llm_proposed → exercise IS returned, provisional flag True AND the reason
    SAYS provisional (surfacing tested, not just the field)."""
    _seed_template(db_session, "hz1", "Chest Press (Machine)", laterality="bilateral")
    _tag(db_session, "hz1", "horizontal_push", source="llm_proposed")
    db_session.commit()

    res = rx.resolve_region(db_session, USER, region_key="horizontal_push", side="bilateral")
    assert res.mode == rx.MODE_TRAIN
    assert res.reason_code == rx.RC_TRAIN_PROVISIONAL
    assert res.provisional is True
    assert res.exercise["template_id"] == "hz1"
    # The flag is surfaced in words, not just a boolean a narrator can drop.
    assert "provisional" in res.reason.lower()


def test_trusted_preferred_over_provisional(db_session):
    """When both trust tiers serve a region, the confirmed tag wins and the result is not
    flagged provisional."""
    _seed_template(db_session, "conf", "Confirmed Row", laterality="bilateral")
    _seed_template(db_session, "prov", "Proposed Row", laterality="bilateral")
    _tag(db_session, "conf", "horizontal_pull", source="human_confirmed")
    _tag(db_session, "prov", "horizontal_pull", source="llm_proposed")
    db_session.commit()

    res = rx.resolve_region(db_session, USER, region_key="horizontal_pull", side="bilateral")
    assert res.exercise["template_id"] == "conf"
    assert res.provisional is False


# --------------------------------------------------------------------------- #
# SCREEN mode — the routing-axis correction (REV 2) and the §G hole-closer.    #
# --------------------------------------------------------------------------- #

def test_e_region_measure_no_tags_routes_to_screen_not_train_fallback(db_session):
    """REV 2 regression guard: §E (single_leg_hop) is queue_eligible=True and declares a
    measure but has zero tags. It MUST route to a Measure-layer screen, NOT to a train
    fallback — the exact misroute the corrected tags-and-measure axis fixes."""
    # No templates/tags for single_leg_hop at all.
    res = rx.resolve_region(db_session, USER, region_key="single_leg_hop", side="left")
    assert res.mode == rx.MODE_SCREEN
    assert res.reason_code == rx.RC_SCREEN_MEASURE
    assert res.screen["measure_key"] == "hop_distance_cm"
    assert res.screen["side"] == "left"   # per-side measure admits the sided prescription
    assert res.exercise is None


def test_g_region_no_measure_no_tags_returns_honest_stub_never_silent(db_session):
    """GATE: a §G region (sit_to_rise: queue_eligible=False, no measure, no tags) handed to
    the consumer returns an explicit 'no instrument yet' screen — never a silent nothing."""
    res = rx.resolve_region(db_session, USER, region_key="sit_to_rise", side="bilateral")
    assert res.mode == rx.MODE_SCREEN
    assert res.reason_code == rx.RC_SCREEN_NO_INSTRUMENT
    assert res.screen is None
    assert res.reason  # a real, honest reason string, not empty
    assert "no" in res.reason.lower()


def test_needs_norm_queue_eligible_regions_land_sensibly(db_session):
    """The 3 needs_norm queue-eligible regions under the tags-and-measure axis (report):
      - hip_ir_er:                    no tags, no measure  → screen_no_instrument
      - frontal_single_leg_stability: no tags, has measure → screen_measure
      - aerobic_base (tagged here):   has a tag            → train
    None fall into a fourth surprise state."""
    assert rx.resolve_region(db_session, USER, region_key="hip_ir_er", side="left").reason_code \
        == rx.RC_SCREEN_NO_INSTRUMENT
    assert rx.resolve_region(
        db_session, USER, region_key="frontal_single_leg_stability", side="left"
    ).reason_code == rx.RC_SCREEN_MEASURE

    _seed_template(db_session, "aer", "Assault Bike", laterality="bilateral")
    _tag(db_session, "aer", "aerobic_base", source="llm_proposed")
    db_session.commit()
    aer = rx.resolve_region(db_session, USER, region_key="aerobic_base", side="bilateral")
    assert aer.mode == rx.MODE_TRAIN


# --------------------------------------------------------------------------- #
# Rotation / recency-avoidance.                                               #
# --------------------------------------------------------------------------- #

def test_rotation_avoids_recently_used_when_alternatives_exist(db_session):
    """GATE: repeated prescriptions vary the exercise. With two confirmed candidates, the
    one NOT in recent history is preferred; feeding the first back as recent flips it."""
    _seed_template(db_session, "aaa", "AAA Squat", laterality="bilateral")
    _seed_template(db_session, "bbb", "BBB Squat", laterality="bilateral")
    _tag(db_session, "aaa", "squat")
    _tag(db_session, "bbb", "squat")
    db_session.commit()

    first = rx.resolve_region(db_session, USER, region_key="squat", side="bilateral").exercise["template_id"]
    other = rx.resolve_region(
        db_session, USER, region_key="squat", side="bilateral",
        recent_template_ids=frozenset({first}),
    ).exercise["template_id"]
    assert other != first, "rotation must avoid the recently-used exercise"


def test_recent_template_ids_reads_hevy_sets(db_session):
    """The live recency source is DB-only (hevy_sets), no Hevy call."""
    db_session.add(models.User(id=USER, email="u1@test", hashed_password="x"))
    _seed_template(db_session, "t1", "Some Lift")
    db_session.add(models.HevyWorkout(
        hevy_id="w1", user_id=USER, start_time=datetime(2026, 9, 1, tzinfo=timezone.utc), raw={},
    ))
    db_session.flush()
    db_session.add(models.HevySet(
        workout_id="w1", exercise_template_id="t1", block_index=0, set_index=0,
    ))
    db_session.commit()
    assert rx.recent_template_ids(db_session, USER) == frozenset({"t1"})


# --------------------------------------------------------------------------- #
# Fallback / empty cases + the prescription-level consumer.                   #
# --------------------------------------------------------------------------- #

def test_fortify_target_not_a_region_is_honest(db_session):
    """A fortify primary_target may be a free descriptor, not a Region.key → honest
    unresolved, never a crash or a guess."""
    res = rx.resolve_region(db_session, USER, region_key="get generally robust", side="bilateral")
    assert res.mode == rx.MODE_UNRESOLVED
    assert res.reason_code == rx.RC_TARGET_NOT_A_REGION


def test_resolve_prescription_handles_probe_and_fortify(db_session):
    """The prescription-level consumer resolves the probe (region+side) and the fortify
    target (no side → bilateral default, the V2 seam), unchanged select_next output."""
    _seed_template(db_session, "sq1", "Goblet Squat", laterality="bilateral")
    _tag(db_session, "sq1", "squat")
    db_session.commit()

    engine_out = {
        "probe": {"region_key": "single_leg_hop", "side": "left"},
        "fortify": {"target": "squat"},  # no side
    }
    got = rx.resolve_prescription(db_session, USER, engine_out)
    assert got["probe"]["mode"] == rx.MODE_SCREEN            # §E → screen
    assert got["fortify"]["mode"] == rx.MODE_TRAIN
    assert got["fortify"]["side"] == "bilateral"             # V2 seam default
    assert got["fortify"]["exercise"]["template_id"] == "sq1"


def test_resolve_prescription_tolerates_missing_blocks(db_session):
    """A suppressed probe (None) or absent fortify target resolves to None, never a crash."""
    got = rx.resolve_prescription(db_session, USER, {"probe": None, "fortify": {"target": None}})
    assert got == {"probe": None, "fortify": None}


def test_consumer_does_not_mutate_engine_output(db_session):
    """Pure-downstream (V2): the consumer never changes the prescription it reads."""
    engine_out = {"probe": {"region_key": "sit_to_rise", "side": "bilateral"}, "fortify": {"target": None}}
    before = {"probe": dict(engine_out["probe"]), "fortify": dict(engine_out["fortify"])}
    rx.resolve_prescription(db_session, USER, engine_out)
    assert engine_out["probe"] == before["probe"]
    assert engine_out["fortify"] == before["fortify"]
