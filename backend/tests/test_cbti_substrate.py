"""CBT-I data substrate (phase 1) — schema smoke + append-only invariants.

Covers the block/prescription ledger and the sleep-diary fields on DailyRecord
(#107 titration-on-TST / #108 block-structured, readiness-isolated). No engine
under test here — this is the substrate the import (Gate 4) and titration engine
(Gate 5) are built on.

Enforcement note: append-only is a model+application invariant, not a DB trigger.
The one DB-enforced constraint is the `decision` domain CHECK, exercised below.
"""
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

import models


def _make_user(db, email="cbti@x.io"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _open_block(db, user_id, **kw):
    b = models.CBTIBlock(
        user_id=user_id, opened_on=date(2026, 3, 19), wake_anchor="05:00",
        open_reason="third block", **kw,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def test_block_and_prescription_roundtrip(db_session):
    u = _make_user(db_session)
    b = _open_block(db_session, u.id)
    rx = models.CBTIPrescription(
        block_id=b.id, effective_from=date(2026, 3, 19),
        prescribed_lights_out="22:36", wake_anchor="05:00",
        window_minutes=384, decision="adopt",
        basis_tst_min=397, basis_se_pct=0.958, basis_nights_n=7,
        excluded_nights={"2026-04-02": "alcohol"},
    )
    db_session.add(rx)
    db_session.commit()
    db_session.refresh(rx)
    assert rx.id is not None
    assert rx.decision == "adopt"
    assert rx.excluded_nights == {"2026-04-02": "alcohol"}
    assert rx.effective_to is None and rx.superseded_by is None


def test_decision_domain_check_rejects_invalid(db_session):
    u = _make_user(db_session)
    b = _open_block(db_session, u.id)
    bad = models.CBTIPrescription(
        block_id=b.id, effective_from=date(2026, 3, 19),
        prescribed_lights_out="22:36", wake_anchor="05:00",
        window_minutes=384, decision="tighten",   # not in the allowed domain
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize("decision", ["adopt", "extend", "hold", "compress", "close"])
def test_all_valid_decisions_accepted(db_session, decision):
    u = _make_user(db_session, email=f"{decision}@x.io")
    b = _open_block(db_session, u.id)
    rx = models.CBTIPrescription(
        block_id=b.id, effective_from=date(2026, 3, 19),
        prescribed_lights_out="22:36", wake_anchor="05:00",
        window_minutes=384, decision=decision,
    )
    db_session.add(rx)
    db_session.commit()
    assert rx.id is not None


def test_prescription_supersession_chain(db_session):
    """The two whitelisted append-only UPDATEs: effective_to on the predecessor,
    superseded_by pointing at the successor. Nothing else is rewritten."""
    u = _make_user(db_session)
    b = _open_block(db_session, u.id)
    rx1 = models.CBTIPrescription(
        block_id=b.id, effective_from=date(2026, 3, 19),
        prescribed_lights_out="22:36", wake_anchor="05:00",
        window_minutes=384, decision="adopt",
    )
    db_session.add(rx1)
    db_session.commit()
    db_session.refresh(rx1)

    rx2 = models.CBTIPrescription(
        block_id=b.id, effective_from=date(2026, 3, 22),
        prescribed_lights_out="22:35", wake_anchor="05:00",
        window_minutes=385, decision="extend",
    )
    db_session.add(rx2)
    db_session.commit()
    db_session.refresh(rx2)

    rx1.effective_to = date(2026, 3, 21)
    rx1.superseded_by = rx2.id
    db_session.commit()
    db_session.refresh(rx1)
    assert rx1.effective_to == date(2026, 3, 21)
    assert rx1.superseded_by == rx2.id


def test_block_close_updates_only_exit_fields(db_session):
    u = _make_user(db_session)
    b = _open_block(db_session, u.id)
    assert b.closed_on is None
    b.closed_on = date(2026, 5, 11)
    b.close_reason = "TST plateau, SE >=85%"
    b.exit_tst_min = 449
    b.exit_se_pct = 0.922
    db_session.commit()
    db_session.refresh(b)
    assert b.closed_on == date(2026, 5, 11)
    assert b.exit_tst_min == 449


def test_diary_fields_persist_on_daily_record(db_session):
    u = _make_user(db_session)
    rec = models.DailyRecord(
        user_id=u.id, date=date(2026, 3, 20),
        lights_out="22:36", sleep_latency_min=12, waso_min=8,
        night_wakings_n=1, final_wake="05:00", out_of_bed="05:08",
        naps_min=0, diary_se_pct=0.958, diary_tst_min=397,
    )
    db_session.add(rec)
    db_session.commit()
    db_session.refresh(rec)
    assert rec.diary_tst_min == 397
    assert rec.diary_se_pct == 0.958
    assert rec.lights_out == "22:36"
    # never-prefilled device-hostile fields still round-trip when user-entered
    assert rec.sleep_latency_min == 12 and rec.waso_min == 8
    # phase-2 column; historical rows carry it NULL by design
    assert rec.got_into_bed is None


def test_got_into_bed_is_distinct_from_lights_out(db_session):
    """The diary separates got-into-bed from tried-to-sleep. SE opens at the
    latter, so they must not be conflated — a 16-minute gap here is typical."""
    u = _make_user(db_session, email="gib@x.io")
    rec = models.DailyRecord(
        user_id=u.id, date=date(2026, 7, 22),
        got_into_bed="22:20", lights_out="22:36", out_of_bed="05:08",
    )
    db_session.add(rec)
    db_session.commit()
    db_session.refresh(rec)
    assert rec.got_into_bed == "22:20"
    assert rec.lights_out == "22:36"
    assert rec.got_into_bed != rec.lights_out
