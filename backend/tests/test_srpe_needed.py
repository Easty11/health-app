"""`/checkin-v2/today.srpe_needed` and `/prefill.missed_pm.srpe_needed` -- whether the close-out should ask for sRPE.

Needed = at least one counted session that day has no PER-SESSION rating from any source (the whole-day fill is
not one). Fails open to asking (G1): an unsynced source, a day with nothing counted, or a read that errors all
answer "ask"; a later per-session value overrides per session and nothing re-prompts.
"""
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
import routers.checkin_v2 as c2
import srpe_store
from auth import get_current_user
from database import get_db
from routers.checkin_v2 import get_prefill


def _user(db, email="srpe@x.io"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(c2.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _session(db, uid, day, hour_utc=2, minutes=45, ssid="s"):
    """A timed session on local day `day` (UTC 02:00 is 12:00 AEST)."""
    start = datetime(day.year, day.month, day.day, hour_utc, 0, tzinfo=timezone.utc)
    db.add(models.AerobicSession(
        user_id=uid, source="polar_v4", source_session_id=ssid, session_date=day, start_time=start,
        stop_time=start + timedelta(minutes=minutes), duration_minutes=float(minutes), z2_seconds=600))
    db.commit()
    return start


def _rate(db, uid, start, minutes=45, raw=70, ref="1"):
    srpe_store.record_observation(db, uid, source="garmin", source_activity_ref=ref, start=start,
                                  stop=start + timedelta(minutes=minutes), rpe_raw=raw, raw_scale="garmin_0_100",
                                  now=datetime(2031, 1, 1, tzinfo=timezone.utc))


def _today(db, u):
    r = _client(db, u).get("/checkin-v2/today")
    assert r.status_code == 200
    return r.json()["srpe_needed"]


def test_a_session_nobody_rated_means_the_question_is_needed(db_session):
    u = _user(db_session)
    _session(db_session, u.id, c2._today_aest())
    assert _today(db_session, u) is True


def test_every_session_rated_per_session_means_it_is_not_needed(db_session):
    u = _user(db_session)
    start = _session(db_session, u.id, c2._today_aest())
    _rate(db_session, u.id, start)
    assert _today(db_session, u) is False


def test_the_whole_day_value_is_not_a_per_session_rating(db_session):
    u = _user(db_session)
    today = c2._today_aest()
    _session(db_session, u.id, today)
    db_session.add(models.DailyRecord(user_id=u.id, date=today, session_rpe=6.0))
    db_session.commit()
    assert _today(db_session, u) is True


def test_one_rated_and_one_unrated_session_still_needs_the_question(db_session):
    u = _user(db_session)
    today = c2._today_aest()
    a = _session(db_session, u.id, today, hour_utc=2, ssid="a")
    _session(db_session, u.id, today, hour_utc=8, ssid="b")
    _rate(db_session, u.id, a)
    assert _today(db_session, u) is True


def test_a_later_per_session_value_closes_the_question_without_a_re_prompt(db_session):
    """The close-out was answered tonight (day fill); the 02:00 sweep then brings Garmin's value."""
    u = _user(db_session)
    today = c2._today_aest()
    start = _session(db_session, u.id, today)
    db_session.add(models.DailyRecord(user_id=u.id, date=today, session_rpe=6.0))
    db_session.commit()
    assert _today(db_session, u) is True
    _rate(db_session, u.id, start)
    assert _today(db_session, u) is False


def test_a_day_with_nothing_counted_still_asks(db_session):
    """An unrecorded session leaves nothing to count; only the athlete can rate it."""
    u = _user(db_session)
    assert _today(db_session, u) is True


def test_a_read_that_errors_fails_open_to_asking_and_does_not_cost_the_close_out(db_session, monkeypatch):
    u = _user(db_session)

    def boom(*a, **k):
        raise RuntimeError("door down")
    monkeypatch.setattr(c2, "srpe_needed", boom)
    r = _client(db_session, u).get("/checkin-v2/today")
    assert r.status_code == 200 and r.json()["srpe_needed"] is True


def test_the_catch_up_day_carries_its_own_answer(db_session):
    """/prefill.missed_pm is yesterday: rated per session -> not needed; with an unrated session -> needed."""
    u = _user(db_session)
    today = c2._today_aest()
    yday = today - timedelta(days=1)
    db_session.add(models.DailyRecord(user_id=u.id, date=yday - timedelta(days=1)))   # history, so yesterday is offered
    db_session.commit()
    start = _session(db_session, u.id, yday)
    assert get_prefill(current_user=u, db=db_session).missed_pm.srpe_needed is True
    _rate(db_session, u.id, start)
    assert get_prefill(current_user=u, db=db_session).missed_pm.srpe_needed is False


def test_the_answer_for_today_does_not_leak_into_yesterday(db_session):
    u = _user(db_session)
    today = c2._today_aest()
    start = _session(db_session, u.id, today)
    _rate(db_session, u.id, start)
    assert _today(db_session, u) is False
    db_session.add(models.DailyRecord(user_id=u.id, date=today - timedelta(days=2)))
    db_session.commit()
    assert get_prefill(current_user=u, db=db_session).missed_pm.srpe_needed is True      # yesterday has no session at all
