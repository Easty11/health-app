"""The injury seed must not resurrect a resolved injury.

`_seed_injuries` once skipped a key only when an ACTIVE row held it, so re-running
`seed_engine.py` after an injury was resolved (active=False) wrote a fresh active copy —
one seed run silently undid the resolution and any clearance sweep behind it.
"""
import models
from seed_engine import _INJURY_SEED, _seed_injuries


def _make_user(db, email):
    user = models.User(email=email, hashed_password="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _injury_rows(db, user_id, key):
    return db.query(models.UserKnowledgeEntry).filter_by(
        user_id=user_id, type="injury", key=key).all()


def test_first_seed_writes_every_injury(db_session):
    user = _make_user(db_session, "inj-seed@example.com")
    assert _seed_injuries(db_session, user.id) == len(_INJURY_SEED)


def test_reseed_is_idempotent(db_session):
    user = _make_user(db_session, "inj-idem@example.com")
    _seed_injuries(db_session, user.id)
    assert _seed_injuries(db_session, user.id) == 0


def test_reseed_does_not_recreate_a_resolved_injury(db_session):
    user = _make_user(db_session, "inj-resolved@example.com")
    _seed_injuries(db_session, user.id)
    key = "injury_hamstring_right"
    row = _injury_rows(db_session, user.id, key)[0]
    row.value = {**row.value, "resolution": {
        "resolved_on": "2026-09-27", "basis": "test", "resolved_by": "user"}}
    row.active = False
    db_session.commit()

    assert _seed_injuries(db_session, user.id) == 0
    rows = _injury_rows(db_session, user.id, key)
    assert len(rows) == 1
    assert rows[0].active is False
