"""PM nap capture (Step A-C) — naps_min stored at PM, default 0 not null, the engine's
nap exclusion live for an open block, and the Q45 -> #219 attribution.

Two load-bearing properties, both silent when broken:

  * A blank submits 0, never null. `engine.classify_night` guards on `is not None`, so a
    null silently disables the exclusion — every night would look clean rather than
    unknown. Without PM capture the exclusion is structurally dead.
  * A nap is attributed to the night it PRECEDES. `replay.load_nights` reads Night(W)'s
    nap from row W-1. Get this backwards and the engine excludes a night the nap could
    not have affected while keeping the one it did — a wrong answer that looks like a
    right one, since both nights are real and both verdicts are well-formed.

This file pins both, plus the 30-minute floor in both directions.
"""
from datetime import date, timedelta

import models
from cbti.engine import NAP_EXCLUDE_MIN, Night, classify_night
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


def test_a_nap_over_the_threshold_excludes_the_night(db_session=None):
    v = classify_night(_night(45), "23:45")
    assert v.valid is False and v.reason == "nap"


def test_the_threshold_floor_is_inclusive_and_sub_threshold_naps_are_kept():
    """The floor is a chosen boundary, so pin it on both sides. A nap AT the threshold
    is kept (the guard is `>`), and a sub-threshold nap is recorded-but-not-excluded —
    which is what lets the data accumulate to test the floor later."""
    assert classify_night(_night(NAP_EXCLUDE_MIN), "23:45").valid is True
    assert classify_night(_night(NAP_EXCLUDE_MIN - 1), "23:45").valid is True
    assert classify_night(_night(NAP_EXCLUDE_MIN + 1), "23:45").valid is False


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


# ── Q45 -> #219 attribution: Night(W) reads the nap recorded on W-1 ───────────────

def _rec(db, uid, d, *, naps_min, tst=380):
    db.add(models.DailyRecord(
        user_id=uid, date=d, diary_tst_min=tst, diary_se_pct=90.0,
        lights_out="22:30", out_of_bed="05:00", final_wake="05:00",
        naps_min=naps_min, alcohol_units=0,
    ))
    db.commit()


def test_load_nights_attributes_a_nap_to_the_night_it_precedes(db_session):
    """A nap recorded on day D discharged the sleep pressure for the night ending the
    NEXT morning, so it lands on Night(D+1) — not on Night(D), which had already ended
    that morning. Asserts the positive AND the negative: the old same-row read would
    still satisfy a test that only checked some night carried the nap."""
    u = _user(db_session, "loadnights@x.io")
    d0 = date(2026, 7, 24)
    _rec(db_session, u.id, d0, naps_min=0)
    _rec(db_session, u.id, d0 + timedelta(days=1), naps_min=60)   # the nap day
    _rec(db_session, u.id, d0 + timedelta(days=2), naps_min=0)

    nights = {n.date: n for n in load_nights(db_session, u.id, d0, d0 + timedelta(days=2))}
    assert nights[d0 + timedelta(days=2)].naps_min == 60   # the night the nap preceded
    assert nights[d0 + timedelta(days=1)].naps_min == 0    # NOT the nap's own night
    # the first night has no W-1 row in range, so its nap is unknown, not a spurious 0
    assert nights[d0].naps_min is None


def test_the_attribution_reads_one_day_before_the_window_not_just_inside_it(db_session):
    """The W-1 read must reach OUTSIDE the requested range. If the nap query shared the
    night query's window, the first night of every cycle would silently carry no nap —
    an off-by-one that reads as clean data on exactly the night a cycle starts."""
    u = _user(db_session, "napwindow@x.io")
    d0 = date(2026, 7, 24)
    _rec(db_session, u.id, d0 - timedelta(days=1), naps_min=90)   # OUTSIDE the range below
    _rec(db_session, u.id, d0, naps_min=0)

    nights = {n.date: n for n in load_nights(db_session, u.id, d0, d0)}
    assert nights[d0].naps_min == 90


def test_a_nap_on_a_day_with_no_diary_row_still_attributes_forward(db_session):
    """Naps are captured at PM and the diary at AM, so a day can legitimately carry a nap
    and no `diary_tst_min`. The night query drops such rows; the nap read must not, or a
    real contaminant vanishes because the napper skipped one morning's diary."""
    u = _user(db_session, "napnodiary@x.io")
    d0 = date(2026, 7, 24)
    _rec(db_session, u.id, d0, naps_min=75, tst=None)      # no diary -> not itself a Night
    _rec(db_session, u.id, d0 + timedelta(days=1), naps_min=0)

    nights = {n.date: n for n in load_nights(db_session, u.id, d0, d0 + timedelta(days=1))}
    assert d0 not in nights                                # dropped as a Night, as before
    assert nights[d0 + timedelta(days=1)].naps_min == 75   # but its nap still attributed


def test_attribution_and_threshold_compose_into_the_verdict(db_session):
    """End-to-end through both halves: the nap crosses a day boundary AND clears the
    floor before a night is excluded. Pins that neither half alone produces the verdict."""
    u = _user(db_session, "napcompose@x.io")
    d0 = date(2026, 7, 24)
    _rec(db_session, u.id, d0, naps_min=NAP_EXCLUDE_MIN + 15)   # over the floor
    _rec(db_session, u.id, d0 + timedelta(days=1), naps_min=NAP_EXCLUDE_MIN - 15)  # under
    _rec(db_session, u.id, d0 + timedelta(days=2), naps_min=0)

    nights = {n.date: n for n in load_nights(db_session, u.id, d0, d0 + timedelta(days=2))}
    # day d0's over-floor nap excludes the night it precedes
    assert classify_night(nights[d0 + timedelta(days=1)], "22:30").reason == "nap"
    # day d0+1's under-floor nap does not exclude the night it precedes
    assert classify_night(nights[d0 + timedelta(days=2)], "22:30").valid is True
