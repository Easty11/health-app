"""`correct_cbti_block3_anchor.py` — the operator correction restoring block id 2's wake
anchor to 05:45 (#331). Runs the script's own `correct()` against the create_all SQLite
schema: append + supersede only, the identity guard, and a rationale that states which
rows understate their window, resolved from the ledger rather than the brief.
"""
from datetime import date

import pytest

import models
from correct_cbti_block3_anchor import correct

EF = date(2026, 9, 27)

# (effective_from, effective_to, lights_out, anchor, window, decision) — block id 2's ledger
LEDGER = [
    (date(2026, 7, 24), date(2026, 7, 26), "23:45", "05:45", 360, "adopt"),    # rx 10
    (date(2026, 7, 27), date(2026, 8, 12), "22:30", "05:00", 390, "adopt"),    # rx 11
    (date(2026, 8, 13), date(2026, 8, 19), "22:30", "05:00", 390, "hold"),
    (date(2026, 8, 20), date(2026, 8, 26), "22:15", "05:00", 405, "extend"),
    (date(2026, 8, 27), date(2026, 9, 3), "22:00", "05:00", 420, "extend"),
    (date(2026, 9, 4), date(2026, 9, 11), "22:15", "05:00", 405, "compress"),
    (date(2026, 9, 12), date(2026, 9, 19), "22:03", "05:00", 417, "extend"),
    (date(2026, 9, 20), None, "21:48", "05:00", 432, "extend"),                # rx 17, live
]


@pytest.fixture()
def db(db_session):
    db_session.add(models.User(id=1, email="op@x.io", hashed_password="x"))
    db_session.commit()
    db_session.add(models.CBTIBlock(id=2, user_id=1, opened_on=date(2026, 7, 24), wake_anchor="05:45"))
    db_session.commit()
    for i, (ef, et, lo, anchor, win, dec) in enumerate(LEDGER, start=10):
        db_session.add(models.CBTIPrescription(
            id=i, block_id=2, effective_from=ef, effective_to=et, prescribed_lights_out=lo,
            wake_anchor=anchor, window_minutes=win, decision=dec))
    db_session.commit()
    return db_session


def _rows(db):
    db.expire_all()
    return {r.id: r for r in db.query(models.CBTIPrescription).all()}


def test_dry_run_writes_nothing_and_resolves_rx_11_to_17(db):
    plan = correct(db.connection(), EF, apply=False)
    assert plan["old_id"] == 17 and plan["affected_ids"] == [11, 12, 13, 14, 15, 16, 17]
    assert plan["old_effective_to"] == date(2026, 9, 26)
    assert "rx 11 390->435" in plan["rationale"] and "rx 17 432->477" in plan["rationale"]
    assert "UNDERSTATE the window actually run by 45 min" in plan["rationale"]
    assert len(_rows(db)) == 8


def test_apply_appends_one_adopt_row_and_supersedes_the_live_row_only(db):
    before = {i: (r.prescribed_lights_out, r.wake_anchor, r.window_minutes, r.decision)
              for i, r in _rows(db).items()}
    plan = correct(db.connection(), EF, apply=True)
    rows = _rows(db)
    new = rows[plan["new_id"]]
    assert (new.effective_from, new.effective_to, new.prescribed_lights_out, new.wake_anchor,
            new.window_minutes, new.decision) == (EF, None, "21:48", "05:45", 477, "adopt")
    assert new.basis_tst_min is None and new.basis_nights_n is None
    assert rows[17].effective_to == date(2026, 9, 26) and rows[17].superseded_by == new.id
    # nothing else moved: rx 11-17 keep their recorded (wrong) values — append-only
    for i, v in before.items():
        r = rows[i]
        assert (r.prescribed_lights_out, r.wake_anchor, r.window_minutes, r.decision) == v
    assert db.get(models.CBTIBlock, 2).wake_anchor == "05:45"


def test_identity_guard_aborts_if_an_evaluation_moved_the_live_row(db):
    db.get(models.CBTIPrescription, 17).effective_to = date(2026, 9, 26)
    db.add(models.CBTIPrescription(id=18, block_id=2, effective_from=date(2026, 9, 27),
                                   prescribed_lights_out="22:03", wake_anchor="05:00",
                                   window_minutes=417, decision="compress"))
    db.commit()
    with pytest.raises(SystemExit, match="not the row this correction was written against"):
        correct(db.connection(), date(2026, 9, 28), apply=True)
    assert len(_rows(db)) == 9


def test_second_apply_is_refused(db):
    correct(db.connection(), EF, apply=True)
    db.commit()
    with pytest.raises(SystemExit):
        correct(db.connection(), EF, apply=True)


def test_correction_must_postdate_the_live_row(db):
    with pytest.raises(SystemExit, match="is not after"):
        correct(db.connection(), date(2026, 9, 20), apply=False)
