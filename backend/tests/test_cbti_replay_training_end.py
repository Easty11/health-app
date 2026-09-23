"""`load_nights` training_end — deterministic MAX, non-training sports excluded (#311, #322).

Post-#309 a session_date can hold DIFFERENT bouts. The old `_TRAINING_SQL` had no ORDER BY
and `load_nights` folded rows `{date: stop_time}` last-row-wins, so a morning walk could
overwrite the evening session (or vice versa) and flip a night's `training_constrained`
exclusion. #311 fixed it with `MAX(stop_time)` per session_date (the latest session is what
constrains the night). #322 (closing Q162) replaced #311's interim `source='health_connect'`
exclusion with the shared static set `sport_classes.NON_TRAINING_SPORTS`: a Walking / Pilates /
Yoga / Stretching session (case-insensitive, ANY source) never constrains a night; every other
session does, including generic names and a NULL/blank sport_name.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

import models
from cbti.engine import classify_night
from cbti.replay import load_nights

GARMIN = "com.garmin.android.apps.connectmobile"
NIGHT = date(2026, 7, 25)
SESS = NIGHT - timedelta(days=1)   # a session on the day before constrains the night
RX_LIGHTS_OUT = "22:30"


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


def _aero(db, uid, d, *, source, stop_h, sid, pkg=None, sport=None):
    db.add(models.AerobicSession(
        user_id=uid, source=source, source_session_id=sid, source_package=pkg, session_date=d,
        sport_name=sport,
        start_time=datetime(d.year, d.month, d.day, max(stop_h - 1, 0), 0, tzinfo=timezone.utc),
        stop_time=datetime(d.year, d.month, d.day, stop_h, 0, tzinfo=timezone.utc),
        duration_minutes=60.0,
    ))
    db.commit()


def _night(db, uid):
    return {n.date: n for n in load_nights(db, uid, NIGHT, NIGHT)}[NIGHT]


def _classify(n):
    """classify_night on the loaded Night. SQLite returns the `MAX(stop_time)` aggregate as a
    string (Postgres returns a datetime), so coerce it here — test-side only."""
    if isinstance(n.training_end, str):
        n.training_end = datetime.fromisoformat(n.training_end)
    return classify_night(n, RX_LIGHTS_OUT).reason


def _training_end(db, uid):
    return _night(db, uid).training_end


@pytest.mark.parametrize("hc_first", [False, True])
def test_hc_walk_ignored_evening_polar_constrains(db_session, hc_first):
    """{evening Polar 18:00, morning HC Walking 08:00} on the day before → training_end is the
    evening Polar stop, in BOTH insert orders. The walk is non-training (#322 S4), so it never
    sets — or clears — the constraint."""
    u = _user(db_session)
    _rec(db_session, u.id, NIGHT)
    seed = [
        lambda: _aero(db_session, u.id, SESS, source="health_connect", stop_h=8, sid="walk",
                      pkg=GARMIN, sport="Walking"),
        lambda: _aero(db_session, u.id, SESS, source="polar_flow_export", stop_h=18, sid="run",
                      sport="Fitness"),
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


@pytest.mark.parametrize("late_first", [False, True])
def test_two_sessions_mixed_sources_take_the_later_stop(db_session, late_first):
    """#322 D: two training sessions on one day, different sources (Polar Fitness 09:00, HC
    Rugby 20:00) → training_end is the LATER stop, in both insert orders."""
    u = _user(db_session)
    _rec(db_session, u.id, NIGHT)
    seed = [
        lambda: _aero(db_session, u.id, SESS, source="health_connect", stop_h=20, sid="rugby",
                      pkg=GARMIN, sport="Rugby"),
        lambda: _aero(db_session, u.id, SESS, source="polar_flow_export", stop_h=9, sid="fit",
                      sport="Fitness"),
    ]
    (seed if late_first else seed[::-1])[0]()
    (seed if late_first else seed[::-1])[1]()
    te = str(_training_end(db_session, u.id))
    assert "20:00" in te and "09:00" not in te


def test_polar_fitness_day_unchanged(db_session):
    """#322 D: a Polar "Fitness" day is byte-identical to pre-#322 behaviour — training_end is
    exactly that session's stop, and a late one still constrains the night."""
    u = _user(db_session)
    _rec(db_session, u.id, NIGHT)
    _aero(db_session, u.id, SESS, source="polar_flow_export", stop_h=22, sid="fit", sport="Fitness")
    n = _night(db_session, u.id)
    assert "22:00" in str(n.training_end)
    assert _classify(n) == "training_constrained"


@pytest.mark.parametrize("sport", ["Walking", "Pilates", "yoga", "STRETCHING"])
@pytest.mark.parametrize("source", ["health_connect", "polar_flow_export"])
def test_non_training_session_does_not_constrain(db_session, sport, source):
    """#322 S1/S4: a late non-training session (case-insensitive, ANY source) sets no
    training_end, so the night is not training_constrained."""
    u = _user(db_session)
    _rec(db_session, u.id, NIGHT)
    _aero(db_session, u.id, SESS, source=source, stop_h=22, sid="nt", pkg=GARMIN, sport=sport)
    n = _night(db_session, u.id)
    assert n.training_end is None
    assert _classify(n) != "training_constrained"


@pytest.mark.parametrize("sport", ["Other Workout", "Rugby", "Fitness", "", None])
def test_hc_training_session_now_constrains(db_session, sport):
    """#322 S4 lifts the #311 interim: an HC session that is NOT non-training — including a
    generic name, blank, or NULL sport_name — sets training_end, and ending at 22:00 it
    constrains a 22:30 prescription (22:00 + TRAINING_RECOVERY_MIN 90 = 23:30 > 22:30).
    Under the interim this returned None."""
    u = _user(db_session)
    _rec(db_session, u.id, NIGHT)
    _aero(db_session, u.id, SESS, source="health_connect", stop_h=22, sid="hc", pkg=GARMIN, sport=sport)
    n = _night(db_session, u.id)
    assert n.training_end is not None and "22:00" in str(n.training_end)
    assert _classify(n) == "training_constrained"
