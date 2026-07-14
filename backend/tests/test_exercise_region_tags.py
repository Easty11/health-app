"""Exercise catalogue taxonomy tagging (DECISIONS_LOG #NEXT).

Pins the four documented `_LOADED_KEYWORDS` failures (plus the empirically
strongest live case — Shoulder Rotation falsely loading a radicular-blocked
region), proves the keyword path survives as an instrumented fallback, and
proves the S1 table split holds across a Hevy resync (the G5 clobber test).
"""
import logging
from datetime import datetime, timezone

import pytest

import models
from engine import selection, taxonomy
import hevy_templates


def _seed_template(db, tid, title, laterality=None, is_custom=True, adjudicated=False):
    db.add(models.HevyExerciseTemplate(
        id=tid, title=title, is_custom=is_custom,
        owner_user_id=None, laterality=laterality,
        adjudicated_at=datetime.now(timezone.utc) if adjudicated else None,
    ))


def _tag(db, tid, region_key, role="primary", source="human_confirmed"):
    db.add(models.ExerciseRegionTag(
        hevy_exercise_template_id=tid, region_key=region_key, role=role, source=source,
    ))


def _workout(*exercises):
    return [{"exercises": [
        {"exercise_template_id": tid, "title": title} for tid, title in exercises
    ]}]


# --------------------------------------------------------------------------- #
# The four documented failures + the live Shoulder-Rotation false positive.   #
# --------------------------------------------------------------------------- #

def test_copenhagen_plank_no_pattern_not_sagittal(db_session):
    """Copenhagen Plank matched 'plank' -> trunk_stability_sagittal (a sagittal
    region) when it is frontal-plane adductor STRENGTH — a region v0 has no axis
    for (Q27). Adjudicated no-pattern (interim): contributes nothing, and
    critically is NOT the sagittal region the keyword map falsely produced."""
    _seed_template(db_session, "cop1", "Copenhagen Plank (Short Lever)", adjudicated=True)
    db_session.commit()

    got = selection.infer_loaded_regions(
        _workout(("cop1", "Copenhagen Plank (Short Lever)")), db=db_session
    )
    assert "trunk_stability_sagittal" not in got
    assert got == set(), "no-pattern adjudication contributes no region"


def test_pallof_is_anti_rotation_only(db_session):
    """Pallof press must load anti_rotation ONLY — never `rotation` (which sits
    in _RADICULAR_BLOCKS and would falsely mark it demonstrably loaded)."""
    _seed_template(db_session, "pal1", "Cable Core Pallof Press")
    _tag(db_session, "pal1", "anti_rotation")
    db_session.commit()

    got = selection.infer_loaded_regions(
        _workout(("pal1", "Cable Core Pallof Press")), db=db_session
    )
    assert got == {"anti_rotation"}
    assert "rotation" not in got


def test_cable_twist_is_rotation(db_session):
    """Cable Twist matched NOTHING under the keyword map ('twist' is not a
    needle) — genuine loaded rotation went entirely unseen. Tagged -> rotation."""
    _seed_template(db_session, "tw1", "Cable Twist (Down to up)")
    _tag(db_session, "tw1", "rotation")
    db_session.commit()

    got = selection.infer_loaded_regions(
        _workout(("tw1", "Cable Twist (Down to up)")), db=db_session
    )
    assert "rotation" in got


def test_single_leg_rdl_is_hinge_and_unilateral(db_session):
    """Single Leg RDL -> hinge, and the template carries laterality='unilateral'
    (the whole right-side-deficit story the keyword map dropped entirely)."""
    _seed_template(db_session, "slrdl1", "Single Leg Romanian Deadlift (Dumbbell)",
                   laterality="unilateral")
    _tag(db_session, "slrdl1", "hinge")
    db_session.commit()

    got = selection.infer_loaded_regions(
        _workout(("slrdl1", "Single Leg Romanian Deadlift (Dumbbell)")), db=db_session
    )
    assert "hinge" in got
    tmpl = db_session.get(models.HevyExerciseTemplate, "slrdl1")
    assert tmpl.laterality == "unilateral"


def test_shoulder_rotation_does_not_load_trunk_rotation(db_session):
    """The empirically strongest live false positive: 'Shoulder External/Internal
    Rotation' (×22, the highest-frequency titles) contains the substring
    'rotation' and the keyword map tagged them as loaded `rotation` (a
    _RADICULAR_BLOCKS region) — rotator-cuff STRENGTH masquerading as trunk
    rotation. shoulder_mobility was REJECTED (wrong capacity). Adjudicated
    no-pattern (interim, blocked on the ER:IR ratio axis, Q27) bypasses the
    keyword path and kills the false positive — wrong→empty is a strict
    improvement."""
    _seed_template(db_session, "ser1", "Shoulder External Rotation", adjudicated=True)
    _seed_template(db_session, "sir1", "Shoulder Internal Rotation", adjudicated=True)
    db_session.commit()

    got = selection.infer_loaded_regions(
        _workout(("ser1", "Shoulder External Rotation"),
                 ("sir1", "Shoulder Internal Rotation")),
        db=db_session,
    )
    assert "rotation" not in got
    assert got == set()


# --------------------------------------------------------------------------- #
# Both roles count; fallback is instrumented; orphans fail closed on read.     #
# --------------------------------------------------------------------------- #

def test_both_roles_count_as_loaded(db_session):
    """Suitcase Carry legitimately loads two regions — primary + secondary both
    count as loaded (role governs review, not presence)."""
    _seed_template(db_session, "sc1", "Suitcase Carry")
    _tag(db_session, "sc1", "carry", role="primary")
    _tag(db_session, "sc1", "anti_lateral_flexion", role="secondary")
    db_session.commit()

    got = selection.infer_loaded_regions(_workout(("sc1", "Suitcase Carry")), db=db_session)
    assert got == {"carry", "anti_lateral_flexion"}


def test_untagged_template_hits_instrumented_fallback(db_session, caplog):
    """An untagged template falls back to the keyword matcher AND is logged —
    the fallback hit-rate is the coverage metric."""
    _seed_template(db_session, "bench1", "Barbell Bench Press")  # no tags
    db_session.commit()

    with caplog.at_level(logging.INFO, logger="engine.selection"):
        got = selection.infer_loaded_regions(
            _workout(("bench1", "Barbell Bench Press")), db=db_session
        )
    assert got == {"horizontal_push"}  # legacy keyword still fires for untagged
    assert any("keyword fallback" in r.getMessage() for r in caplog.records)


def test_adjudicated_no_pattern_is_covered_not_a_fallback_hit(db_session, caplog):
    """The three-state distinction (DECISIONS_LOG #76): an ADJUDICATED no-pattern
    template (adjudicated_at set, zero tags) contributes nothing AND is silent —
    it is NOT a coverage gap. An UNTAGGED template (adjudicated_at NULL) still
    hits the counted, logged fallback. 'We looked and it maps to nothing' and 'we
    never looked' stay epistemically distinct."""
    _seed_template(db_session, "hipadd1", "Hip Adduction (Machine)", adjudicated=True)  # no-pattern
    _seed_template(db_session, "legext1", "Leg Extension (Machine)")  # untagged, never adjudicated
    db_session.commit()

    with caplog.at_level(logging.INFO, logger="engine.selection"):
        got = selection.infer_loaded_regions(
            _workout(("hipadd1", "Hip Adduction (Machine)"),
                     ("legext1", "Leg Extension (Machine)")),
            db=db_session,
        )
    assert got == set()  # neither contributes a region
    gap_logs = " ".join(r.getMessage() for r in caplog.records if "coverage gap" in r.getMessage())
    assert "Leg Extension (Machine)" in gap_logs      # untagged → counted
    assert "Hip Adduction (Machine)" not in gap_logs  # adjudicated → silent


def test_orphan_region_key_skipped_on_read(db_session):
    """Defence in depth: a region_key with no matching taxonomy Region is skipped
    and warned, never returned (fail-closed)."""
    _seed_template(db_session, "orphan1", "Mystery Move")
    _tag(db_session, "orphan1", "not_a_real_region")
    _tag(db_session, "orphan1", "squat")
    db_session.commit()

    got = selection.infer_loaded_regions(_workout(("orphan1", "Mystery Move")), db=db_session)
    assert got == {"squat"}


def test_db_none_is_pure_keyword_backcompat(db_session):
    """With no db, the function degrades to the original keyword path — the four
    documented misfires reproduce exactly (the correction comes from tagging,
    not from a behaviour change to the fallback)."""
    got = selection.infer_loaded_regions(
        _workout(("cop1", "Copenhagen Plank (Short Lever)")), db=None
    )
    assert got == {"trunk_stability_sagittal"}  # legacy misfire, unchanged
    got2 = selection.infer_loaded_regions(
        _workout(("ser1", "Shoulder External Rotation")), db=None
    )
    assert got2 == {"rotation"}  # legacy false positive, unchanged


# --------------------------------------------------------------------------- #
# G5 — clobber test: tags + laterality survive a full Hevy resync.            #
# --------------------------------------------------------------------------- #

def test_resync_preserves_tags_and_laterality(db_session):
    """The entire reason for the S1 table split + not assigning laterality in
    `_upsert_template`: a full resync must not lose a single tag or laterality
    value."""
    _seed_template(db_session, "slrdl1", "Single Leg Romanian Deadlift (Dumbbell)",
                   laterality="unilateral", adjudicated=True)
    _tag(db_session, "slrdl1", "hinge")
    db_session.commit()

    # A fresh Hevy payload for the SAME template id — exactly what a resync feeds
    # `_upsert_template`. Note it carries no laterality, no adjudicated_at and no
    # tags (Hevy-owned data only).
    payload = {
        "id": "slrdl1",
        "title": "Single Leg Romanian Deadlift (Dumbbell)",
        "type": "weight_reps",
        "is_custom": True,
        "primary_muscle_group": "hamstrings",
        "secondary_muscle_groups": ["glutes"],
    }
    hevy_templates._upsert_template(db_session, payload, owner_user_id=None,
                                    now=datetime.now(timezone.utc))
    db_session.commit()

    tmpl = db_session.get(models.HevyExerciseTemplate, "slrdl1")
    assert tmpl.laterality == "unilateral", "resync clobbered laterality"
    assert tmpl.adjudicated_at is not None, "resync clobbered adjudicated_at"
    assert tmpl.primary_muscle_group == "hamstrings"  # Hevy field did update
    tags = db_session.query(models.ExerciseRegionTag).filter_by(
        hevy_exercise_template_id="slrdl1"
    ).all()
    assert {t.region_key for t in tags} == {"hinge"}, "resync clobbered tags"


# --------------------------------------------------------------------------- #
# Seeder (seed_exercise_region_tags.py) — fail-closed, idempotent, confirm.    #
# --------------------------------------------------------------------------- #

import seed_exercise_region_tags as seeder  # noqa: E402


def test_proposal_reference_validates_fail_closed(db_session):
    """The shipped proposal reference resolves every region_key to a taxonomy
    Region (G1) — a drifted proposal must fail closed, not seed orphans."""
    proposal = seeder.load_proposal()
    seeder._validate_fail_closed(proposal)  # must not raise

    bad = {"_meta": {"source": "llm_proposed"},
           "tags": [{"title": "X", "regions": [{"key": "not_a_region", "role": "primary"}]}]}
    with pytest.raises(seeder.OrphanRegionKeyError):
        seeder._validate_fail_closed(bad)


def test_seed_is_idempotent_and_confirm_stamps_provenance(db_session):
    proposal = seeder.load_proposal()
    # Seed a template for every title in BOTH lists so all resolve.
    all_titles = ([e["title"] for e in proposal["tags"]]
                  + [e["title"] for e in proposal["no_pattern"]])
    for i, title in enumerate(all_titles):
        db_session.add(models.HevyExerciseTemplate(
            id=f"T{i:03d}", title=title, is_custom=False, owner_user_id=None,
        ))
    db_session.commit()

    # A plain (non-confirm) run writes llm-proposed tags but stamps NO
    # adjudication — coverage is not claimed until human confirmation.
    r1 = seeder.seed_tags(db_session, user_id=1, proposal=proposal)
    n1 = db_session.query(models.ExerciseRegionTag).count()
    r2 = seeder.seed_tags(db_session, user_id=1, proposal=proposal)  # idempotent
    n2 = db_session.query(models.ExerciseRegionTag).count()
    assert r1["titles_unresolved"] == 0
    assert n1 == n2 == r1["tags_written"], "re-seed duplicated rows"
    assert r1["no_pattern_adjudicated"] == 0, "no_pattern must not persist without --confirm"
    assert db_session.query(models.HevyExerciseTemplate).filter(
        models.HevyExerciseTemplate.adjudicated_at.isnot(None)).count() == 0

    # laterality landed on the templates (not clobber-exposed)
    slrdl = next(e for e in proposal["tags"] if "Single Leg Romanian" in e["title"])
    tid = next(t.id for t in db_session.query(models.HevyExerciseTemplate)
               if t.title == slrdl["title"])
    assert db_session.get(models.HevyExerciseTemplate, tid).laterality == "unilateral"

    # --confirm: tag rows become human_confirmed AND every processed template
    # (tagged + no_pattern) is stamped adjudicated_at; no_pattern carries zero tags.
    r3 = seeder.seed_tags(db_session, user_id=1, proposal=proposal, confirm=True)
    row = db_session.query(models.ExerciseRegionTag).first()
    assert row.source == "human_confirmed" and row.confirmed_at is not None
    assert row.taxonomy_version == taxonomy.TAXONOMY_VERSION
    assert r3["no_pattern_adjudicated"] == len(proposal["no_pattern"])

    adjudicated = db_session.query(models.HevyExerciseTemplate).filter(
        models.HevyExerciseTemplate.adjudicated_at.isnot(None)).count()
    assert adjudicated == len(all_titles), "every processed template adjudicated on --confirm"

    # A no_pattern template: adjudicated, zero tag rows.
    calf_title = "Calf Extension (Machine)"
    calf_tid = next(t.id for t in db_session.query(models.HevyExerciseTemplate)
                    if t.title == calf_title)
    assert db_session.get(models.HevyExerciseTemplate, calf_tid).adjudicated_at is not None
    assert db_session.query(models.ExerciseRegionTag).filter_by(
        hevy_exercise_template_id=calf_tid).count() == 0
