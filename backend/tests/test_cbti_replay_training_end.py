"""`load_nights` training_end — deterministic, HC-excluded (#311, Q162).

Post-#309 a session_date can hold DIFFERENT bouts. The old `_TRAINING_SQL` had no ORDER BY
and `load_nights` folded rows `{date: stop_time}` last-row-wins, so a morning walk could
overwrite the evening session (or vice versa) and flip a night's `training_constrained`
exclusion — the ingest changing the sleep engine's inputs as a side effect. The fix:
`MAX(stop_time)` per session_date (deterministic), and `source='health_connect'` EXCLUDED
until Q162 rules which activities constrain a night (interim, mirrors Q160).
"""
from datetime import date, datetime, timedelta, timezone

import pytest

import models
from cbti.replay import load_nights

GARMIN = "com.garmin.android.apps.connectmobile"
NIGHT = date(2026, 7, 25)
SESS = NIGHT - timedelta(days=1)   # a session on the day before constrains the night


def _user(db, email="cbti-te@x.io"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _rec(db, uid, d, *, tst=400):
    db.add(models.DailyRecord(
        user_id=uid, date=d, diary_tst_min=tst, diary_se_pct=90.0,
        lights_out="22:30", out_of_bed="05:00", final_wake="05:00", naps_min=0, alcohol_units=0,
    ))
    db.commit()


def _aero(db, uid, d, *, source, stop_h, sid, pkg=None):
    db.add(models.AerobicSession(
        user_id=uid, source=source, source_session_id=sid, source_package=pkg, session_date=d,
        start_time=datetime(d.year, d.month, d.day, max(stop_h - 1, 0), 0, tzinfo=timezone.utc),
        stop_time=datetime(d.year, d.month, d.day, stop_h, 0, tzinfo=timezone.utc),
        duration_minutes=60.0,
    ))
    db.commit()


def _training_end(db, uid):
    nights = {n.date: n for n in load_nights(db, uid, NIGHT, NIGHT)}
    return nights[NIGHT].training_end


@pytest.mark.parametrize("hc_first", [False, True])
def test_hc_walk_ignored_evening_polar_constrains(db_session, hc_first):
    """{evening Polar 18:00, morning HC walk 08:00} on the day before → training_end is the
    evening Polar stop, in BOTH insert orders. The HC walk is excluded (interim), so it never
    sets — or clears — the constraint."""
    u = _user(db_session)
    _rec(db_session, u.id, NIGHT)
    seed = [
        lambda: _aero(db_session, u.id, SESS, source="health_connect", stop_h=8, sid="walk", pkg=GARMIN),
        lambda: _aero(db_session, u.id, SESS, source="polar_flow_export", stop_h=18, sid="run"),
    ]
    (seed if hc_first else seed[::-1])[0]()
    (seed if hc_first else seed[::-1])[1]()
    te = str(_training_end(db_session, u.id))
    assert "18:00" in te and "08:00" not in te


@pytest.mark.parametrize("evening_first", [False, True])
def test_two_polar_sessions_take_the_latest_stop(db_session, evening_first):
    """§18: MAX(stop_time) per session_date, never iteration order. Two DIFFERENT Polar bouts
    on one day (09:00, 18:00) → training_end is the latest (18:00) in BOTH insert orders.
    Drop the MAX (revert to the order-dependent fold) and one order returns 09:00 → this fails."""
    u = _user(db_session)
    _rec(db_session, u.id, NIGHT)
    seed = [
        lambda: _aero(db_session, u.id, SESS, source="polar_flow_export", stop_h=18, sid="pm"),
        lambda: _aero(db_session, u.id, SESS, source="polar_v4", stop_h=9, sid="am"),
    ]
    (seed if evening_first else seed[::-1])[0]()
    (seed if evening_first else seed[::-1])[1]()
    te = str(_training_end(db_session, u.id))
    assert "18:00" in te and "09:00" not in te


def test_hc_only_session_does_not_constrain_the_night(db_session):
    """A day whose only session is an HC-recorded one → training_end None (interim HC
    exclusion), so an HC evening walk cannot newly constrain a night as an ingest side effect."""
    u = _user(db_session)
    _rec(db_session, u.id, NIGHT)
    _aero(db_session, u.id, SESS, source="health_connect", stop_h=19, sid="walk", pkg=GARMIN)
    assert _training_end(db_session, u.id) is None
