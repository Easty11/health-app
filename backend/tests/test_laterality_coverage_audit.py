"""Usage-joined laterality-coverage audit (DECISIONS_LOG #74/#76/#79).

The audit joins to actual `hevy_sets` usage, so it surfaces BOTH failure modes a
catalogue-only scan misses:
  * untagged   — id in the catalogue, laterality NULL (Kneeling Leg Curl);
  * uncatalogued — id used in hevy_sets but absent from the catalogue (the
                   "default-template hole").
A tagged template is never listed. Duplicate custom templates are listed as
separate rows (#76: tag both, never merge). Keyed on id, never title (#79).
"""
import models
from audit_laterality_coverage import audit_laterality_coverage, LateralityGap


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


def _tmpl(db, id_, title, laterality=None, is_custom=False, owner=None):
    db.add(models.HevyExerciseTemplate(
        id=id_, title=title, is_custom=is_custom, owner_user_id=owner, laterality=laterality,
    ))
    db.commit()


def _workout(db, hevy_id, uid, template_ids):
    db.add(models.HevyWorkout(hevy_id=hevy_id, user_id=uid, raw={}))
    db.flush()   # parent before children — the FK-enforced session mirrors prod
    for block, tid in enumerate(template_ids):
        db.add(models.HevySet(
            workout_id=hevy_id, exercise_template_id=tid,
            block_index=block, set_index=0, type="normal", weight_kg=50.0, reps=8,
        ))
    db.commit()


def test_untagged_and_uncatalogued_surfaced_tagged_excluded(db_session):
    _user(db_session)
    _tmpl(db_session, "BENCH", "Bench Press", laterality="bilateral")   # tagged → excluded
    _tmpl(db_session, "KLC", "Kneeling Leg Curl", laterality=None)      # untagged → listed
    # "UNCAT" deliberately NOT inserted into the catalogue.
    _workout(db_session, "w1", 1, ["BENCH", "KLC", "UNCAT"])

    gaps = audit_laterality_coverage(db_session)
    by_id = {g.exercise_template_id: g for g in gaps}
    assert "BENCH" not in by_id                       # tagged, resolved
    assert by_id["KLC"].reason == "untagged"
    assert by_id["KLC"].title == "Kneeling Leg Curl"
    assert by_id["UNCAT"].reason == "uncatalogued"
    assert by_id["UNCAT"].title is None


def test_complete_coverage_returns_empty(db_session):
    _user(db_session)
    _tmpl(db_session, "BENCH", "Bench Press", laterality="bilateral")
    _tmpl(db_session, "SPLIT", "Split Squat", laterality="unilateral")
    _workout(db_session, "w1", 1, ["BENCH", "SPLIT"])
    assert audit_laterality_coverage(db_session) == []


def test_unused_untagged_template_not_listed(db_session):
    """Usage-JOINED: an untagged template nobody logged is NOT a worklist item."""
    _user(db_session)
    _tmpl(db_session, "KLC", "Kneeling Leg Curl", laterality=None)      # untagged but unused
    _tmpl(db_session, "BENCH", "Bench Press", laterality="bilateral")
    _workout(db_session, "w1", 1, ["BENCH"])
    assert audit_laterality_coverage(db_session) == []


def test_duplicate_custom_templates_listed_separately(db_session):
    """Two custom ids sharing a title are two rows — tag both, never merge (#76)."""
    _user(db_session)
    _tmpl(db_session, "cust-1", "My Machine Row", laterality=None, is_custom=True, owner=1)
    _tmpl(db_session, "cust-2", "My Machine Row", laterality=None, is_custom=True, owner=1)
    _workout(db_session, "w1", 1, ["cust-1", "cust-2"])
    gaps = audit_laterality_coverage(db_session)
    ids = {g.exercise_template_id for g in gaps}
    assert ids == {"cust-1", "cust-2"}


def test_usage_counts_and_ordering(db_session):
    """set_count / workout_count reflect real usage; most-logged gap sorts first."""
    _user(db_session)
    _tmpl(db_session, "KLC", "Kneeling Leg Curl", laterality=None)
    _workout(db_session, "w1", 1, ["KLC", "RARE"])
    _workout(db_session, "w2", 1, ["KLC"])
    gaps = audit_laterality_coverage(db_session)
    by_id = {g.exercise_template_id: g for g in gaps}
    assert by_id["KLC"].set_count == 2 and by_id["KLC"].workout_count == 2
    assert by_id["RARE"].set_count == 1 and by_id["RARE"].workout_count == 1
    assert gaps[0].exercise_template_id == "KLC"       # higher usage first


def test_user_scoping(db_session):
    """--user scopes usage to that user's workouts."""
    _user(db_session, 1)
    _user(db_session, 2)
    _tmpl(db_session, "KLC", "Kneeling Leg Curl", laterality=None)
    _workout(db_session, "w-u2", 2, ["KLC"])
    assert audit_laterality_coverage(db_session, user_id=1) == []
    assert len(audit_laterality_coverage(db_session, user_id=2)) == 1
