"""`load_nights` no longer reads training (#436, retiring #311 / #322 S4 / #323 for CBT-I).

The `training_constrained` predicate is gone: a training session neither constrains nor excuses
a night, whatever its sport, source or finish time. These tests seed `aerobic_sessions` and
check that the loaded Night, and its verdict, are the same as with no session at all.

The first case is the session that motivated the ruling: session 133, Biking (Health Connect,
Garmin), 2026-10-16 20:13 to 20:39 Brisbane (10:13:50Z to 10:39:33Z). Under the retired rule its
end plus 90 min (22:09) sat after the 21:48 prescription, so a night with an ADHERENT lights-out
was excluded as `training_constrained`. The night here is adherent (lights-out 21:55, +7), so it
must be valid. The session is real; the night around it is the adherent counterfactual, not the
operator's actual 23:25.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

import models
from cbti.engine import classify_night
from cbti.replay import load_nights

GARMIN = "com.garmin.android.apps.connectmobile"
NIGHT = date(2026, 10, 17)
SESS_DAY = NIGHT - timedelta(days=1)
RX, ANCHOR = "21:48", "05:45"
_BNE = timezone(timedelta(hours=10))          # Australia/Brisbane: UTC+10, no DST


def _user(db, email="cbti-notrain@x.io"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _rec(db, uid, d, *, lights_out="21:55"):
    db.add(models.DailyRecord(
        user_id=uid, date=d, diary_tst_min=400, diary_se_pct=88.0,
        lights_out=lights_out, out_of_bed="05:30", final_wake="05:20", naps_min=0, alcohol_units=0,
    ))
    db.commit()


def _aero(db, uid, d, *, source, start, stop, sid, pkg=None, sport=None):
    db.add(models.AerobicSession(
        user_id=uid, source=source, source_session_id=sid, source_package=pkg, session_date=d,
        sport_name=sport, start_time=start, stop_time=stop,
        duration_minutes=(stop - start).total_seconds() / 60,
    ))
    db.commit()


def _night(db, uid):
    return {n.date: n for n in load_nights(db, uid, NIGHT, NIGHT)}[NIGHT]


def _verdict(db, uid):
    return classify_night(_night(db, uid), RX, ANCHOR)


def test_session_133_inside_the_old_90_minute_floor_leaves_an_adherent_night_valid(db_session):
    u = _user(db_session)
    _rec(db_session, u.id, NIGHT)
    stop = datetime(2026, 10, 16, 10, 39, 33, tzinfo=timezone.utc)
    assert stop.astimezone(_BNE).strftime("%H:%M") == "20:39"       # the floor was 20:39 + 90 = 22:09 > 21:48
    _aero(db_session, u.id, SESS_DAY, source="health_connect", sid="133", pkg=GARMIN, sport="Biking",
          start=datetime(2026, 10, 16, 10, 13, 50, tzinfo=timezone.utc), stop=stop)
    v = _verdict(db_session, u.id)
    assert v.valid is True and v.reason is None
    assert v.adherent is True and v.adherence_delta_min == 7


def test_a_night_loads_the_same_with_and_without_a_late_session(db_session):
    u = _user(db_session)
    _rec(db_session, u.id, NIGHT)
    before = _night(db_session, u.id)
    _aero(db_session, u.id, SESS_DAY, source="polar_flow_export", sid="late", sport="Fitness",
          start=datetime(2026, 10, 16, 11, 0, tzinfo=timezone.utc),
          stop=datetime(2026, 10, 16, 12, 30, tzinfo=timezone.utc))                 # ends 22:30 Brisbane
    after = _night(db_session, u.id)
    assert after == before
    assert not hasattr(after, "training_end")


@pytest.mark.parametrize("sport", ["Other Workout", "Rugby", "Fitness", "Walking", "Pilates", "", None])
@pytest.mark.parametrize("source", ["health_connect", "polar_flow_export", "polar_v4"])
def test_no_session_of_any_kind_constrains_a_night(db_session, sport, source):
    u = _user(db_session)
    _rec(db_session, u.id, NIGHT)
    _aero(db_session, u.id, SESS_DAY, source=source, sid="s", pkg=GARMIN, sport=sport,
          start=datetime(2026, 10, 16, 11, 0, tzinfo=timezone.utc),
          stop=datetime(2026, 10, 16, 13, 0, tzinfo=timezone.utc))                  # ends 23:00 Brisbane
    assert _verdict(db_session, u.id).valid is True


def test_the_replay_module_has_no_training_read():
    import cbti.replay as replay_mod
    assert not hasattr(replay_mod, "_TRAINING_SQL")
    assert not hasattr(replay_mod, "_NON_TRAINING_PARAMS")
