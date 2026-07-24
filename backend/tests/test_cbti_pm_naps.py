"""PM nap capture (Step A-C) — naps_min stored at PM, default 0 not null, and the
engine's nap exclusion becomes live for block 3.

The load-bearing property is that a blank submits 0, never null: engine.classify_night
excludes any night with naps_min > 0, guarded on `is not None`, so a null silently
disables the exclusion. Without PM capture every block-3 night is null and the
exclusion is structurally dead — this test pins both halves.
"""
from datetime import date

import models
from cbti.engine import Night, classify_night
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


def test_any_nap_excludes_the_night(db_session=None):
    v = classify_night(_night(30), "23:45")
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
