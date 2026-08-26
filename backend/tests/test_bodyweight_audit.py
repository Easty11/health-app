"""Bodyweight-template worklist audit (DECISIONS_LOG #245) — the operator's tagging surface.

Confirms the audit surfaces exactly the in-use templates that log a 0/NULL-weight rep-based
set, distinguishes catalogued-untagged from uncatalogued, and never flags a template that
only logs real weight or only non-rep work.
"""
from datetime import datetime, timezone

import models
import audit_bodyweight_templates as abt


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


def _tmpl(db, id_, bw_fraction=None):
    db.add(models.HevyExerciseTemplate(id=id_, title=id_, bw_fraction=bw_fraction))
    db.commit()


def _workout(db, hevy_id, uid, sets, excluded=False):
    db.add(models.HevyWorkout(
        hevy_id=hevy_id, user_id=uid, start_time=datetime(2026, 7, 1, tzinfo=timezone.utc),
        title="W", raw={"id": hevy_id},
        excluded_at=datetime(2026, 8, 25, tzinfo=timezone.utc) if excluded else None,
    ))
    db.flush()
    for i, s in enumerate(sets):
        db.add(models.HevySet(workout_id=hevy_id, block_index=s["b"], set_index=i, **s["d"]))
    db.commit()


def test_audit_surfaces_bodyweight_templates_only(db_session):
    _user(db_session)
    _tmpl(db_session, "PUSHUP", bw_fraction=None)     # catalogued, untagged
    _tmpl(db_session, "BENCH", bw_fraction=None)      # catalogued, but only weighted
    # PULLUP intentionally NOT catalogued → uncatalogued row
    _workout(db_session, "w1", 1, [
        {"b": 0, "d": {"exercise_template_id": "PUSHUP", "weight_kg": None, "reps": 12}},
        {"b": 0, "d": {"exercise_template_id": "PUSHUP", "weight_kg": 0.0, "reps": 10}},
        {"b": 1, "d": {"exercise_template_id": "BENCH", "weight_kg": 100.0, "reps": 5}},      # weighted → excluded
        {"b": 2, "d": {"exercise_template_id": "PULLUP", "weight_kg": 0.0, "reps": 8}},       # uncatalogued bodyweight
        {"b": 3, "d": {"exercise_template_id": "PLANK", "weight_kg": None, "reps": None,       # non-rep → excluded
                        "duration_seconds": 60}},
    ])
    rows = {r.template_id: r for r in abt.audit(db_session, only_user_id=1)}

    assert set(rows) == {"PUSHUP", "PULLUP"}          # BENCH (weighted) and PLANK (non-rep) excluded
    assert rows["PUSHUP"].bodyweight_sets == 2 and rows["PUSHUP"].catalogued and rows["PUSHUP"].needs_tag
    assert rows["PULLUP"].bodyweight_sets == 1 and not rows["PULLUP"].catalogued and rows["PULLUP"].needs_tag


def test_audit_tagged_template_does_not_need_tag(db_session):
    _user(db_session)
    _tmpl(db_session, "DEADBUG", bw_fraction=0.25)
    _workout(db_session, "w1", 1, [
        {"b": 0, "d": {"exercise_template_id": "DEADBUG", "weight_kg": 0.0, "reps": 60}},
    ])
    row = abt.audit(db_session, only_user_id=1)[0]
    assert row.template_id == "DEADBUG" and row.bw_fraction == 0.25 and not row.needs_tag


def test_audit_excludes_adjudicated_out_workouts(db_session):
    _user(db_session)
    _tmpl(db_session, "PUSHUP", bw_fraction=None)
    _workout(db_session, "drop", 1, [
        {"b": 0, "d": {"exercise_template_id": "PUSHUP", "weight_kg": 0.0, "reps": 12}},
    ], excluded=True)
    assert abt.audit(db_session, only_user_id=1) == []
