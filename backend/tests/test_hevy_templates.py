"""Tests for resolve_exercise (DECISIONS_LOG #60) — default-wins title resolution.

(a) collision (default + user's own custom, same title) -> default id
(b) custom-only title -> that custom id
(c) another user's custom -> no match (never leaks another user's custom)
(d) unknown title -> None
"""
import models
from hevy_templates import resolve_exercise

USER_A = 1
USER_B = 2


def _tmpl(db, id_, title, is_custom, owner=None, type_="weight_reps"):
    row = models.HevyExerciseTemplate(
        id=id_, title=title, type=type_, is_custom=is_custom, owner_user_id=owner,
    )
    db.add(row)
    db.commit()
    return row


# ---------- (a) collision -> default wins ----------
def test_collision_returns_default_id(db_session):
    _tmpl(db_session, "AAAA1111", "Bench Press", is_custom=False)
    _tmpl(db_session, "cccccccc-1111-2222-3333-444444444444", "Bench Press",
          is_custom=True, owner=USER_B)

    # user B has a custom "Bench Press" shadowing the default — default still wins
    assert resolve_exercise(db_session, "Bench Press", USER_B) == "AAAA1111"


# ---------- (b) custom-only title -> custom id ----------
def test_custom_only_returns_custom_id(db_session):
    custom_id = "dddddddd-1111-2222-3333-555555555555"
    _tmpl(db_session, custom_id, "Sled Push", is_custom=True, owner=USER_B)

    assert resolve_exercise(db_session, "Sled Push", USER_B) == custom_id


# ---------- (c) another user's custom -> no match ----------
def test_other_users_custom_no_match(db_session):
    _tmpl(db_session, "eeeeeeee-1111-2222-3333-666666666666", "Secret Lift",
          is_custom=True, owner=USER_A)

    # user B must never resolve user A's private custom
    assert resolve_exercise(db_session, "Secret Lift", USER_B) is None


# ---------- (d) unknown title -> None ----------
def test_unknown_title_returns_none(db_session):
    _tmpl(db_session, "BBBB2222", "Squat", is_custom=False)
    assert resolve_exercise(db_session, "Nonexistent Exercise", USER_B) is None
