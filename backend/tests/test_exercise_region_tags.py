"""Exercise catalogue taxonomy tagging (DECISIONS_LOG #74).

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
    db.flush()   # parent template before any ExerciseRegionTag references it (FK-enforced, #239)


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
    # Seed a template for every entry in all three lists so all resolve: id-keyed and
    # sided-variant entries under their own id, title-keyed ones under a synthetic id —
    # except the two sided-variant PARENTS, which carry the ids the reference names
    # (fixture assumption mirroring the proposal; prod proves it via --dry-run).
    parent_ids = {"Single Arm Lat Pulldown": "2EE45F81", "Hip Thrust (Machine)": "68CE0B9B"}
    entries = proposal["tags"] + proposal["no_pattern"] + proposal["sided_variants"]
    for i, e in enumerate(entries):
        tid = e.get("template_id") or parent_ids.get(e["title"]) or f"T{i:03d}"
        db_session.add(models.HevyExerciseTemplate(
            id=tid, title=e["title"], is_custom=False, owner_user_id=None,
        ))
    db_session.commit()
    all_titles = entries

    # A plain (non-confirm) run writes llm-proposed tags but stamps NO
    # adjudication — coverage is not claimed until human confirmation.
    r1 = seeder.seed_tags(db_session, user_id=1, proposal=proposal)
    n1 = db_session.query(models.ExerciseRegionTag).count()
    r2 = seeder.seed_tags(db_session, user_id=1, proposal=proposal)  # idempotent
    n2 = db_session.query(models.ExerciseRegionTag).count()
    assert r1["titles_unresolved"] == 0
    assert n1 == n2 == r1["tags_written"], "re-seed duplicated rows"
    assert r1["no_pattern_adjudicated"] == 0, "no_pattern must not persist without --confirm"
    assert r1["inherited_variants"] == len(proposal["sided_variants"])
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


# --------------------------------------------------------------------------- #
# v0.1 (#337): id-keyed entries, sided-variant inheritance, --dry-run.         #
# --------------------------------------------------------------------------- #

def _tmpl(db, tid, title, *, custom=False, owner=None, adjudicated=False):
    if owner is not None and db.get(models.User, owner) is None:
        db.add(models.User(id=owner, email=f"u{owner}@test", hashed_password="x"))
        db.flush()
    db.add(models.HevyExerciseTemplate(
        id=tid, title=title, is_custom=custom, owner_user_id=owner,
        adjudicated_at=datetime.now(timezone.utc) if adjudicated else None,
    ))
    db.flush()


def _rows(db, tid):
    return {(r.region_key, r.role) for r in
            db.query(models.ExerciseRegionTag).filter_by(hevy_exercise_template_id=tid)}


def test_id_keyed_entry_resolves_by_id_not_title(db_session):
    """The title on an id-keyed entry is a LABEL: a same-titled default must not win."""
    _tmpl(db_session, "DEF1", "Plank Pull Through")                       # decoy default
    _tmpl(db_session, "c-uuid", "Plank Pull Through", custom=True, owner=1)
    db_session.commit()
    prop = {"tags": [{"template_id": "c-uuid", "title": "Plank Pull Through",
                      "regions": [{"key": "anti_rotation", "role": "primary"}]}]}
    r = seeder.seed_tags(db_session, 1, proposal=prop)
    assert r["titles_unresolved"] == 0
    assert _rows(db_session, "c-uuid") == {("anti_rotation", "primary")}
    assert _rows(db_session, "DEF1") == set()


def test_id_keyed_entry_refuses_another_users_custom(db_session):
    _tmpl(db_session, "other", "Bird Dog", custom=True, owner=2)
    db_session.commit()
    prop = {"tags": [{"template_id": "other", "title": "Bird Dog",
                      "regions": [{"key": "rotary_stability", "role": "primary"}]}]}
    r = seeder.seed_tags(db_session, 1, proposal=prop)
    assert r["unresolved_titles"] == ["Bird Dog"]
    assert _rows(db_session, "other") == set()


def test_sided_variant_mirrors_parent_planned_in_same_run(db_session):
    """Parent retagged in this run -> the variant copies the NEW tags and loses rows the
    parent no longer carries (it mirrors, it does not accumulate)."""
    _tmpl(db_session, "P1", "Shoulder Internal Rotation", custom=True, owner=1)
    _tmpl(db_session, "V1", "Shoulder Internal Rotation L", custom=True, owner=1)
    db_session.add(models.ExerciseRegionTag(hevy_exercise_template_id="V1",
                                            region_key="rotation", role="primary"))
    db_session.commit()
    prop = {"tags": [{"title": "Shoulder Internal Rotation",
                      "regions": [{"key": "shoulder_er_ir", "role": "primary"}]}],
            "sided_variants": [{"template_id": "V1", "title": "Shoulder IR L",
                                "parent_template_id": "P1"}]}
    r = seeder.seed_tags(db_session, 1, proposal=prop, confirm=True)
    assert r["inherited_variants"] == 1
    assert _rows(db_session, "V1") == {("shoulder_er_ir", "primary")}
    assert r["plan"]["V1"]["via"] == "P1"


def test_sided_variant_inherits_from_adjudicated_db_parent(db_session):
    _tmpl(db_session, "68CE0B9B", "Hip Thrust (Machine)", adjudicated=True)
    db_session.add(models.ExerciseRegionTag(hevy_exercise_template_id="68CE0B9B",
                                            region_key="hinge", role="primary"))
    _tmpl(db_session, "slht-l", "Single Leg Hip Thrust L", custom=True, owner=1)
    db_session.commit()
    prop = {"sided_variants": [{"template_id": "slht-l", "title": "SL Hip Thrust L",
                                "parent_template_id": "68CE0B9B"}]}
    seeder.seed_tags(db_session, 1, proposal=prop)
    assert _rows(db_session, "slht-l") == {("hinge", "primary")}


def test_sided_variant_refuses_unadjudicated_parent(db_session):
    """An unconfirmed parent is not a source: fail soft into `unresolved`, write nothing."""
    _tmpl(db_session, "P2", "Parent")                      # never adjudicated
    db_session.add(models.ExerciseRegionTag(hevy_exercise_template_id="P2",
                                            region_key="hinge", role="primary"))
    _tmpl(db_session, "V2", "Parent L", custom=True, owner=1)
    db_session.commit()
    prop = {"sided_variants": [{"template_id": "V2", "title": "Parent L",
                                "parent_template_id": "P2"}]}
    r = seeder.seed_tags(db_session, 1, proposal=prop)
    assert r["titles_unresolved"] == 1 and "not adjudicated" in r["unresolved_titles"][0]
    assert _rows(db_session, "V2") == set()


def test_sided_variant_of_no_pattern_parent_is_no_pattern(db_session):
    _tmpl(db_session, "LE", "Leg Extension (Machine)")
    _tmpl(db_session, "LE-L", "Leg Extension L", custom=True, owner=1)
    db_session.commit()
    prop = {"no_pattern": [{"title": "Leg Extension (Machine)"}],
            "sided_variants": [{"template_id": "LE-L", "title": "LE L",
                                "parent_template_id": "LE"}]}
    r = seeder.seed_tags(db_session, 1, proposal=prop, confirm=True)
    assert r["no_pattern_adjudicated"] == 2
    assert db_session.get(models.HevyExerciseTemplate, "LE-L").adjudicated_at is not None
    assert _rows(db_session, "LE-L") == set()


@pytest.mark.parametrize("bad", [
    {"sided_variants": [{"template_id": "V", "parent_template_id": "P",
                         "regions": [{"key": "hinge", "role": "primary"}]}]},
    {"sided_variants": [{"template_id": "V"}]},
    {"sided_variants": [{"template_id": "V", "parent_template_id": "W"},
                        {"template_id": "W", "parent_template_id": "P"}]},
    {"tags": [{"template_id": "X", "regions": [{"key": "hinge", "role": "primary"}]}],
     "no_pattern": [{"template_id": "X"}]},
])
def test_malformed_proposal_fails_closed(db_session, bad):
    with pytest.raises(seeder.MalformedProposalError):
        seeder._validate_fail_closed(bad)


def test_dry_run_writes_nothing_but_reports_the_plan(db_session):
    """A plain run is NOT a dry run (it writes llm_proposed rows Rule 1 counts);
    --dry-run resolves the same plan and leaves tags, laterality and adjudication alone."""
    _tmpl(db_session, "A1", "Plank")
    _tmpl(db_session, "A2", "Suitcase Carry L", custom=True, owner=1)
    db_session.commit()
    prop = {"tags": [{"title": "Plank", "laterality": "bilateral",
                      "regions": [{"key": "trunk_stability_sagittal", "role": "primary"}]}],
            "sided_variants": [{"template_id": "A2", "title": "Suitcase L",
                                "parent_template_id": "A1"}]}
    r = seeder.seed_tags(db_session, 1, proposal=prop, dry_run=True)
    assert r["dry_run"] and r["tags_written"] == 0 and r["tags_planned"] == 2
    assert r["plan"]["A2"]["regions"] == [{"key": "trunk_stability_sagittal", "role": "primary"}]
    assert db_session.query(models.ExerciseRegionTag).count() == 0
    assert db_session.get(models.HevyExerciseTemplate, "A1").laterality is None


def test_v01_regions_are_inert_for_probing(db_session):
    """The five tag-coverage axes (#334) never enter the probe queue or observations until
    deliberately admitted; shoulder_er_ir gates dip (gates lists what THIS region gates)."""
    new = ("shoulder_er_ir", "trunk_lateral_flexion", "knee_flexion", "hip_adduction", "dip")
    eligible = {r.key for r in taxonomy.queue_eligible_regions()}
    for key in new:
        region = taxonomy.by_key(key)
        assert region is not None and region.capacity is taxonomy.Capacity.STRENGTH
        assert key not in eligible and not region.probe_priority and region.measures == ()
    assert taxonomy.by_key("shoulder_er_ir").gates == ("dip",)
    for region in taxonomy.all_regions():
        for gated in region.gates:
            assert taxonomy.by_key(gated) is not None, (region.key, gated)


def test_shipped_reference_capacity_split(db_session):
    """Pins what the v0.1 additions credit under Rule 1: IR/ER is STRENGTH (Q27's read),
    so the new STABILITY credit is exactly the 8 trunk/anti-movement exercises."""
    proposal = seeder.load_proposal()
    new_ids = [e for e in proposal["tags"] if e.get("template_id")]
    caps = {}
    for e in new_ids:
        primary = [r["key"] for r in e["regions"] if r["role"] == "primary"]
        caps.setdefault(taxonomy.by_key(primary[0]).capacity.value, []).append(e["title"])
    assert len(caps["stability"]) == 8
    assert len(caps["strength"]) == 15      # 14 (#334) - Deficit KB RDL + Shoulder IR/ER parents (#338)
    assert caps["mobility"] == ["Deficit KB RDL"]


# --------------------------------------------------------------------------- #
# #338: IR/ER parents by id, Deficit KB RDL mobility, preflight, prune, votes.  #
# --------------------------------------------------------------------------- #

IR_PARENT = "b4bab549-a143-4186-9615-249165e5a4a2"
ER_PARENT = "f5f7ecfb-68b8-44d6-99c4-f2dc7b183072"


def test_shipped_reference_ir_er_variants_bind_to_id_keyed_parents(db_session):
    """The four IR/ER sided variants name the parents by id, and the parent entries are
    themselves id-keyed - so a wrong id is UNRESOLVED, never a silent fallback to the
    parent's old no-pattern DB state."""
    proposal = seeder.load_proposal()
    parents = {e["template_id"]: e for e in proposal["tags"] if e.get("template_id")}
    assert parents[IR_PARENT]["title"] == "Shoulder Internal Rotation"
    assert parents[ER_PARENT]["title"] == "Shoulder External Rotation"
    by_parent = {}
    for v in proposal["sided_variants"]:
        by_parent.setdefault(v["parent_template_id"], []).append(v["template_id"])
    assert sorted(by_parent[IR_PARENT]) == sorted([
        "934c52a0-8c5a-4a05-a149-4752bcdb6e61", "6ba537fa-d7dd-41e6-bc54-e5c13f8cb4f9"])
    assert sorted(by_parent[ER_PARENT]) == sorted([
        "c06b41ae-4ebf-4675-9c27-d4a367e101ed", "1af7297b-ba1f-429e-aef2-e78250e403b2"])
    rdl = next(e for e in proposal["tags"]
               if e.get("template_id") == "d724248e-29a8-41b0-8463-e3d8f8fff8c1")
    assert rdl["regions"] == [{"key": "hip_flexion_pc_length", "role": "primary"},
                              {"key": "hinge", "role": "secondary"}]


def test_ir_variant_unresolved_parent_is_loud_not_no_pattern(db_session):
    """Parent id absent from the catalogue (the typo'd twin is live instead): the parent
    entry is UNRESOLVED and the variant does not inherit the old no-pattern verdict."""
    twin = "b4bab549-a143-4166-9615-249185e5a4a2"
    _tmpl(db_session, twin, "Shoulder Internal Rotation", custom=True, owner=1, adjudicated=True)
    _tmpl(db_session, "934c", "Shoulder Internal Rotation L", custom=True, owner=1)
    db_session.commit()
    prop = {"tags": [{"template_id": IR_PARENT, "title": "Shoulder Internal Rotation",
                      "regions": [{"key": "shoulder_er_ir", "role": "primary"}]}],
            "sided_variants": [{"template_id": "934c", "title": "IR L",
                                "parent_template_id": IR_PARENT}]}
    r = seeder.seed_tags(db_session, 1, proposal=prop, dry_run=True)
    assert "Shoulder Internal Rotation" in r["unresolved_titles"]
    assert any("not adjudicated" in t for t in r["unresolved_titles"])
    assert r["near_twins"] == [{"referenced": IR_PARENT, "twin": twin,
                                "twin_title": "Shoulder Internal Rotation"}]
    assert "934c" not in r["plan"]


def test_unconfirmed_rows_reported_and_pruned_only_on_opt_in(db_session):
    _tmpl(db_session, "K1", "Kept")
    _tmpl(db_session, "S1", "Stale")
    db_session.add(models.ExerciseRegionTag(hevy_exercise_template_id="K1", region_key="hinge",
                                            role="primary", source="llm_proposed"))
    db_session.add(models.ExerciseRegionTag(hevy_exercise_template_id="S1", region_key="squat",
                                            role="primary", source="llm_proposed"))
    db_session.commit()
    prop = {"tags": [{"title": "Kept", "regions": [{"key": "hinge", "role": "primary"}]}]}

    dry = seeder.seed_tags(db_session, 1, proposal=prop, dry_run=True, prune_unconfirmed=True)
    assert {u["template_id"] for u in dry["unconfirmed_existing"]} == {"K1", "S1"}
    assert [u["template_id"] for u in dry["prune"]] == ["S1"]
    assert db_session.query(models.ExerciseRegionTag).count() == 2, "dry run deleted rows"

    with pytest.raises(ValueError):
        seeder.seed_tags(db_session, 1, proposal=prop, prune_unconfirmed=True)

    kept = seeder.seed_tags(db_session, 1, proposal=prop, confirm=True)       # no prune
    assert kept["pruned"] == 0 and _rows(db_session, "S1") == {("squat", "primary")}

    r = seeder.seed_tags(db_session, 1, proposal=prop, confirm=True, prune_unconfirmed=True)
    assert r["pruned"] == 1 and _rows(db_session, "S1") == set()
    left = db_session.query(models.ExerciseRegionTag).all()
    assert [(t.hevy_exercise_template_id, t.source) for t in left] == [("K1", "human_confirmed")]


def test_explain_quota_votes_matches_rule_1(db_session):
    """The read-only explainer reports the per-capacity primary votes Rule 1 used."""
    import explain_quota_votes
    _tmpl(db_session, "LLR", "Lying Leg Raise", owner=1)
    _tmpl(db_session, "BD", "Bird Dog")
    _tmpl(db_session, "KLC", "Kneeling Leg Curl L")
    for tid, key in (("LLR", "trunk_stability_sagittal"), ("BD", "rotary_stability"),
                     ("KLC", "knee_flexion")):
        db_session.add(models.ExerciseRegionTag(hevy_exercise_template_id=tid, region_key=key,
                                                role="primary", source="human_confirmed"))
    db_session.add(models.HevyWorkout(
        hevy_id="w1", user_id=1, title="Mixed/Movement Quality",
        start_time=datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc),
        raw={"exercises": [{"exercise_template_id": t, "title": t}
                           for t in ("LLR", "BD", "KLC", "NOPE")]}))
    db_session.commit()
    from datetime import date
    [r] = explain_quota_votes.explain(db_session, 1, [date(2026, 9, 21)])
    assert r["votes"] == {"stability": 2, "strength": 1}
    assert r["dominant"] == "stability" and r["untagged"] == 1
