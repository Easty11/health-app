"""Free-text am_notes / pm_notes on the daily record — round-trip, null, no clobber."""
from datetime import date

import models
from routers.checkin_v2 import (
    AMCheckInIn,
    NightlyCloseOutIn,
    TodayOut,
    submit_am,
    submit_pm,
)


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _am(**kw):
    base = dict(morning_readiness=3, sleep_quality=3, fatigue=5, motivation=5, life_load=3)
    base.update(kw)
    return AMCheckInIn(**base)


def test_am_notes_round_trip(db_session):
    u = _user(db_session, "amn@x.io")
    submit_am(body=_am(am_notes="carnival alarm went off at 3am"), current_user=u, db=db_session)
    rec = db_session.query(models.DailyRecord).filter_by(user_id=u.id).first()
    assert rec.am_notes == "carnival alarm went off at 3am"
    assert TodayOut.model_validate(rec).am_notes == "carnival alarm went off at 3am"


def test_pm_notes_round_trip(db_session):
    u = _user(db_session, "pmn@x.io")
    submit_pm(body=NightlyCloseOutIn(today_rating=3, pm_notes="off night, restless"),
              current_user=u, db=db_session)
    rec = db_session.query(models.DailyRecord).filter_by(user_id=u.id).first()
    assert rec.pm_notes == "off night, restless"
    assert TodayOut.model_validate(rec).pm_notes == "off night, restless"


def test_null_notes_accepted(db_session):
    u = _user(db_session, "nulln@x.io")
    ra = submit_am(body=_am(am_notes=None), current_user=u, db=db_session)
    assert ra.am_notes is None
    rp = submit_pm(body=NightlyCloseOutIn(today_rating=3, pm_notes=None),
                   current_user=u, db=db_session)
    assert rp.pm_notes is None


def test_pm_submit_does_not_clobber_am_notes(db_session):
    """The reason there are two columns: AM and PM submit independently, so the PM
    write must not overwrite the morning's note (a shared column would)."""
    u = _user(db_session, "noclobber@x.io")
    submit_am(body=_am(am_notes="morning note"), current_user=u, db=db_session)
    submit_pm(body=NightlyCloseOutIn(today_rating=4, pm_notes="evening note"),
              current_user=u, db=db_session)
    rec = db_session.query(models.DailyRecord).filter_by(user_id=u.id).first()
    assert rec.am_notes == "morning note"        # survived the PM write
    assert rec.pm_notes == "evening note"
    out = TodayOut.model_validate(rec)
    assert out.am_notes == "morning note" and out.pm_notes == "evening note"


def test_notes_are_input_and_output_fields():
    assert "am_notes" in AMCheckInIn.model_fields
    assert "pm_notes" in NightlyCloseOutIn.model_fields
    for f in ("am_notes", "pm_notes"):
        assert f in TodayOut.model_fields
