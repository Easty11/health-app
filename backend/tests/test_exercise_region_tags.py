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
from engine.taxonomy import Plane
import hevy_templates


def _seed_template(db, tid, title, laterality=None, is_custom=True):
    db.add(models.HevyExerciseTemplate(
        id=tid, title=title, is_custom=is_custom,
        owner_user_id=None, laterality=laterality,
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

def test_copenhagen_plank_is_frontal_not_sagittal(db_session):
    """Copenhagen Plank matched 'plank' -> trunk_stability_sagittal (a sagittal
    region) when it is frontal-plane / adductor work. Tagged, it resolves to a
    frontal region and NOT trunk_stability_sagittal."""
    _seed_template(db_session, "cop1", "Copenhagen Plank (Short Lever)")
    _tag(db_session, "cop1", "frontal_single_leg_stability")
    db_session.commit()

    got = selection.infer_loaded_regions(
        _workout(("cop1", "Copenhagen Plank (Short Lever)")), db=db_session
    )
    assert "trunk_stability_sagittal" not in got
    assert got, "expected a tagged region"
    assert all(taxonomy.by_key(rk).plane == Plane.FRONTAL for rk in got)


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
    Rotation' contains the substring 'rotation' and the keyword map tagged them
    as loaded `rotation` (a radicular-blocked region) — 22 logged sets of
    rotator-cuff isometrics masquerading as trunk rotation. Once tagged, the
    keyword path is bypassed entirely and the false positive is gone."""
    _seed_template(db_session, "ser1", "Shoulder External Rotation")
    _seed_template(db_session, "sir1", "Shoulder Internal Rotation")
    _tag(db_session, "ser1", "shoulder_mobility", role="secondary")
    _tag(db_session, "sir1", "shoulder_mobility", role="secondary")
    db_session.commit()

    got = selection.infer_loaded_regions(
        _workout(("ser1", "Shoulder External Rotation"),
                 ("sir1", "Shoulder Internal Rotation")),
        db=db_session,
    )
    assert "rotation" not in got


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
                   laterality="unilateral")
    _tag(db_session, "slrdl1", "hinge")
    db_session.commit()

    # A fresh Hevy payload for the SAME template id — exactly what a resync feeds
    # `_upsert_template`. Note it carries no laterality and no tags (Hevy-owned
    # data only).
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
    for i, entry in enumerate(proposal["tags"]):
        db_session.add(models.HevyExerciseTemplate(
            id=f"T{i:03d}", title=entry["title"], is_custom=False, owner_user_id=None,
        ))
    db_session.commit()

    r1 = seeder.seed_tags(db_session, user_id=1, proposal=proposal)
    n1 = db_session.query(models.ExerciseRegionTag).count()
    r2 = seeder.seed_tags(db_session, user_id=1, proposal=proposal)  # idempotent
    n2 = db_session.query(models.ExerciseRegionTag).count()
    assert r1["titles_unresolved"] == 0
    assert n1 == n2 == r1["tags_written"], "re-seed duplicated rows"

    # laterality landed on the templates (not clobber-exposed)
    slrdl = next(e for e in proposal["tags"] if "Single Leg Romanian" in e["title"])
    tid = next(t.id for t in db_session.query(models.HevyExerciseTemplate)
               if t.title == slrdl["title"])
    assert db_session.get(models.HevyExerciseTemplate, tid).laterality == "unilateral"

    seeder.seed_tags(db_session, user_id=1, proposal=proposal, confirm=True)
    row = db_session.query(models.ExerciseRegionTag).first()
    assert row.source == "human_confirmed" and row.confirmed_at is not None
    assert row.taxonomy_version == taxonomy.TAXONOMY_VERSION
