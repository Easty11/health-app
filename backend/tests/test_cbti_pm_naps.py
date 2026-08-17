"""PM nap capture (Step A-C) — naps_min stored at PM, default 0 not null, the engine's
nap exclusion live for an open block, and the Q45 attribution (naps read from W-1).

The load-bearing property is that a blank submits 0, never null: engine.classify_night
excludes a night whose nap clears NAP_EXCLUDE_MIN (30 min, Q45 closed), guarded on
`is not None`, so a null silently disables the exclusion. Without PM capture every
open-block night is null and the exclusion is structurally dead — this test pins that,
the 30-min threshold, and the day-of-nap -> following-night attribution.
"""
from datetime import date, timedelta

import models
from cbti.engine import Night, classify_night
from cbti.replay import load_nights
from routers.checkin_v2 import AMCheckInIn, NightlyCloseOutIn, TodayOut, submit_pm


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


# ── submit_pm stores naps_min (the client sends 0 for a blank-when-block-open) ────

def test_zero_is_stored_as_zero_not_dropped(db_session):
    """The payload a blank field produces while a block is open. 0 must persist as 0
    (asked, no nap) — not be treated as falsy and lost."""
    u = _user(db_session, "nap0@x.io")
    rec = submit_pm(body=NightlyCloseOutIn(today_rating=3, naps_min=0), current_user=u, db=db_session)
    assert rec.naps_min == 0


def test_a_positive_nap_is_stored(db_session):
    u = _user(db_session, "nap30@x.io")
    rec = submit_pm(body=NightlyCloseOutIn(today_rating=3, naps_min=30), current_user=u, db=db_session)
    assert rec.naps_min == 30


def test_null_means_not_asked_and_persists_as_null(db_session):
    """No block open -> the field is not shown -> the client sends null. Stored null,
    which after this build means 'PM nap capture did not run for this night'."""
    u = _user(db_session, "napnull@x.io")
    rec = submit_pm(body=NightlyCloseOutIn(today_rating=3, naps_min=None), current_user=u, db=db_session)
    assert rec.naps_min is None


def test_today_out_round_trips_naps_min(db_session):
    """/today must carry the stored value back so the PM form can re-show it."""
    u = _user(db_session, "napround@x.io")
    submit_pm(body=NightlyCloseOutIn(today_rating=3, naps_min=45), current_user=u, db=db_session)
    rec = db_session.query(models.DailyRecord).filter_by(user_id=u.id).first()
    assert TodayOut.model_validate(rec).naps_min == 45


def test_derived_pair_naps_is_a_real_input_field():
    assert "naps_min" in NightlyCloseOutIn.model_fields
    assert "naps_min" in TodayOut.model_fields


# ── the engine: why 0-vs-null is load-bearing ─────────────────────────────────────

def _night(naps_min):
    # tst/se present and no alcohol so classification reaches the nap gate
    return Night(date=date(2026, 7, 25), tst_min=380, se_pct=90.0, naps_min=naps_min,
                 lights_out="23:45")


def test_nap_over_threshold_excludes_the_night(db_session=None):
    v = classify_night(_night(45), "23:45")
    assert v.valid is False and v.reason == "nap"


def test_zero_nap_is_not_excluded():
    v = classify_night(_night(0), "23:45")
    assert v.valid is True     # asked, no nap -> the night counts


def test_null_nap_is_silently_kept_which_is_the_bug_this_fixes():
    """An unrecorded nap night (naps_min=None) is NOT excluded — the `is not None`
    guard passes it through. So a real nap night that never went through PM capture
    looks identical to a no-nap night. Capturing 0/N at PM is what makes the
    exclusion able to fire at all."""
    v = classify_night(_night(None), "23:45")
    assert v.valid is True     # kept — not because it's clean, but because it's unknown


# ── Q45 attribution: naps read from W-1 (the day-of-nap -> following-night off-by-one) ──

def _rec(db, uid, d, *, naps_min):
    db.add(models.DailyRecord(
        user_id=uid, date=d, diary_tst_min=380, diary_se_pct=90.0,
        lights_out="22:30", out_of_bed="05:00", final_wake="05:00",
        naps_min=naps_min, alcohol_units=0,
    ))
    db.commit()


def test_load_nights_attributes_a_nap_to_the_following_night(db_session):
    """Q45 off-by-one: a nap recorded on day D discharged Process S for the night ending
    the NEXT morning (Night D+1), not the night that ended on D. load_nights reads
    Night(W).naps_min from row W-1 — the same day-before-the-wake-date shape training uses."""
    u = _user(db_session, "loadnights@x.io")
    d0 = date(2026, 7, 24)
    _rec(db_session, u.id, d0, naps_min=0)
    _rec(db_session, u.id, d0 + timedelta(days=1), naps_min=60)   # nap recorded on the middle day
    _rec(db_session, u.id, d0 + timedelta(days=2), naps_min=0)

    nights = {n.date: n for n in load_nights(db_session, u.id, d0, d0 + timedelta(days=2))}
    # the nap lands on the night AFTER the day it was recorded...
    assert nights[d0 + timedelta(days=2)].naps_min == 60
    # ...and NOT on the night that ended the morning of the nap day (the old off-by-one)
    assert nights[d0 + timedelta(days=1)].naps_min == 0
    # the first night has no W-1 row, so its nap is unknown (None), not a spurious 0
    assert nights[d0].naps_min is None
