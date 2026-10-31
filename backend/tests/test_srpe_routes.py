"""`/checkin-v2/srpe/*` -- the card's read (each counted session with its current rating) and write (one CR-10 per
counted session, source `in_app`).

The starting state is the 31 Oct 2026 shape, built from rows (a 55-min Hevy-only workout and a 52-min Garmin
Pilates that arrived through Health Connect, both unrated), not from an author-typed response: every assertion
reads what the real routes return for those rows.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
import routers.checkin_v2 as c2
from auth import get_current_user
from database import get_db
from routers import srpe_ratings
import srpe_store

TODAY = date(2026, 10, 31)
GARMIN_PKG = "com.garmin.android.apps.connectmobile"


@pytest.fixture(autouse=True)
def _pin_today(monkeypatch):
    monkeypatch.setattr(c2, "_today_aest", lambda: TODAY)


def _user(db, uid=1):
    if db.get(models.User, uid) is None:
        db.add(models.User(id=uid, email=f"u{uid}@x.io", hashed_password="x"))
        db.commit()
    return db.get(models.User, uid)


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(srpe_ratings.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _utc(hh, day=31, mm=0):
    return datetime(2026, 10, day, hh, mm, tzinfo=timezone.utc)      # +10h: UTC 02:00 is 12:00 on the same AEST day


def _hevy(db, start, minutes=55, hid="hevy-1", uid=1, title="Upper body"):
    db.add(models.HevyWorkout(hevy_id=hid, user_id=uid, start_time=start, end_time=start + timedelta(minutes=minutes),
                              title=title, raw={}))
    db.commit()


def _pilates(db, start, minutes=52, uid=1):
    row = models.AerobicSession(
        user_id=uid, source="health_connect", source_session_id=f"hc|{start.isoformat()}",
        session_date=(start + timedelta(hours=10)).date(), start_time=start,
        stop_time=start + timedelta(minutes=minutes), sport_name="Pilates", duration_minutes=float(minutes),
        source_package=GARMIN_PKG, z2_seconds=600)
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def day31(db_session):
    """The 31 Oct shape: a Hevy-only workout and a Pilates, both unrated."""
    u = _user(db_session)
    _hevy(db_session, _utc(2))
    pil = _pilates(db_session, _utc(8))
    return u, pil


def _get(c, since="2026-10-31", until="2026-10-31"):
    return c.get("/checkin-v2/srpe/sessions", params={"since": since, "until": until})


def _by_kind(body):
    return {s["kind"]: s for s in body["sessions"]}


def test_the_31_oct_shape_yields_two_asks_each_with_its_label_minutes_and_local_start(db_session, day31):
    u, pil = day31
    r = _get(_client(db_session, u))
    assert r.status_code == 200
    got = r.json()["sessions"]
    assert [(s["kind"], s["label"], s["minutes"], s["start_local"], s["rpe"], s["source"]) for s in got] == [
        ("hevy", "Upper body", 55.0, "12:00", None, None),
        ("aerobic", "Pilates", 52.0, "18:00", None, None)]
    assert got[1]["id"] == str(pil.id) and all(s["rateable"] for s in got)


def test_rating_through_the_route_lands_on_each_session_and_the_card_reads_it_back(db_session, day31):
    u, pil = day31
    c = _client(db_session, u)
    r = c.post("/checkin-v2/srpe/ratings", json={"ratings": [
        {"kind": "hevy", "id": "hevy-1", "rpe": 8}, {"kind": "aerobic", "id": str(pil.id), "rpe": 3}]})
    assert r.status_code == 200 and r.json()["written"] == 2
    got = _by_kind(_get(c).json())
    assert (got["hevy"]["rpe"], got["hevy"]["source"]) == (8.0, "in_app")
    assert (got["aerobic"]["rpe"], got["aerobic"]["source"]) == (3.0, "in_app")
    assert {(s["kind"], s["rpe"]) for s in r.json()["sessions"]} == {("hevy", 8.0), ("aerobic", 3.0)}


def test_a_day_value_on_the_record_rates_neither_session_on_the_card(db_session, day31):
    u, _pil = day31
    db_session.add(models.DailyRecord(user_id=1, date=TODAY, session_rpe=6.0))
    db_session.commit()
    assert [(s["rpe"], s["source"]) for s in _get(_client(db_session, u)).json()["sessions"]] == [(None, None)] * 2


def test_a_device_rated_session_shows_its_rating_and_an_in_app_override_outranks_it(db_session, day31):
    u, pil = day31
    srpe_store.record_observation(
        db_session, 1, source="garmin", source_activity_ref="g1", start=_utc(8), stop=_utc(8) + timedelta(minutes=52),
        rpe_raw=40, raw_scale="garmin_0_100", now=_utc(11))
    c = _client(db_session, u)
    assert (_by_kind(_get(c).json())["aerobic"]["rpe"], _by_kind(_get(c).json())["aerobic"]["source"]) == (4.0, "garmin")
    c.post("/checkin-v2/srpe/ratings", json={"ratings": [{"kind": "aerobic", "id": str(pil.id), "rpe": 6}]})
    assert (_by_kind(_get(c).json())["aerobic"]["rpe"], _by_kind(_get(c).json())["aerobic"]["source"]) == (6.0, "in_app")


def test_a_re_rate_through_the_route_is_a_new_row_and_the_latest_wins(db_session, day31):
    u, _ = day31
    c = _client(db_session, u)
    for rpe in (5, 9):
        assert c.post("/checkin-v2/srpe/ratings", json={"ratings": [{"kind": "hevy", "id": "hevy-1", "rpe": rpe}]}).status_code == 200
    assert db_session.query(models.SessionRpeObservation).count() == 2
    assert _by_kind(_get(c).json())["hevy"]["rpe"] == 9.0


def test_the_client_cannot_name_a_window_only_a_session(db_session, day31):
    u, _ = day31
    r = _client(db_session, u).post("/checkin-v2/srpe/ratings", json={"ratings": [
        {"kind": "hevy", "id": "hevy-1", "rpe": 7, "start": "2026-01-01T00:00:00Z", "stop": "2026-01-01T01:00:00Z"}]})
    assert r.status_code == 200
    row = db_session.query(models.SessionRpeObservation).one()
    assert row.start_time.replace(tzinfo=timezone.utc) == _utc(2) and row.stop_time.replace(tzinfo=timezone.utc) == _utc(2) + timedelta(minutes=55)


@pytest.mark.parametrize("body", [
    {"ratings": [{"kind": "hevy", "id": "nope", "rpe": 5}]},                      # not a session
    {"ratings": [{"kind": "hevy", "id": "hevy-1", "rpe": 5}, {"kind": "aerobic", "id": "9999", "rpe": 5}]},   # one bad key
    {"ratings": [{"kind": "hevy", "id": "hevy-1", "rpe": 11}]},                   # off the scale
    {"ratings": [{"kind": "hevy", "id": "hevy-1", "rpe": -1}]},
    {"ratings": [{"kind": "swim", "id": "hevy-1", "rpe": 5}]},                    # not a kind
    {"ratings": []},
])
def test_a_bad_write_is_a_422_and_inserts_nothing(db_session, day31, body):
    u, _ = day31
    assert _client(db_session, u).post("/checkin-v2/srpe/ratings", json=body).status_code == 422
    assert db_session.query(models.SessionRpeObservation).count() == 0


def test_another_users_session_can_be_neither_read_nor_rated(db_session, day31):
    _, _pil = day31
    other = _user(db_session, 2)
    _hevy(db_session, _utc(3), hid="theirs", uid=2)
    c = _client(db_session, _user(db_session, 1))
    assert [s["id"] for s in _get(c).json()["sessions"] if s["kind"] == "hevy"] == ["hevy-1"]
    assert c.post("/checkin-v2/srpe/ratings", json={"ratings": [{"kind": "hevy", "id": "theirs", "rpe": 5}]}).status_code == 422
    assert other is not None and db_session.query(models.SessionRpeObservation).count() == 0


def test_the_read_is_bounded_to_the_rateable_window(db_session, day31):
    u, _ = day31
    c = _client(db_session, u)
    assert _get(c, since="2026-10-17", until="2026-10-31").status_code == 422     # before the store's release
    assert _get(c, since="2026-10-31", until="2026-11-01").status_code == 422     # the future
    assert _get(c, since="2026-10-31", until="2026-10-30").status_code == 422     # reversed
    assert _get(c, since="2026-10-18", until="2026-10-31").status_code == 200


def test_an_earlier_unrated_session_is_offered_by_the_backfill_range_and_leaves_it_once_rated(db_session, day31):
    u, _ = day31
    _hevy(db_session, _utc(2, day=25), hid="old", title="Lower body")
    c = _client(db_session, u)
    earlier = _get(c, since="2026-10-18", until="2026-10-30").json()["sessions"]
    assert [(s["id"], s["rpe"]) for s in earlier] == [("old", None)]
    c.post("/checkin-v2/srpe/ratings", json={"ratings": [{"kind": "hevy", "id": "old", "rpe": 6}]})
    assert [(s["id"], s["rpe"], s["source"]) for s in _get(c, since="2026-10-18", until="2026-10-30").json()["sessions"]] == [("old", 6.0, "in_app")]


def test_a_session_with_no_usable_window_is_listed_unrateable(db_session):
    u = _user(db_session)
    db_session.add(models.AerobicSession(user_id=1, source="polar_flow_export", source_session_id="u",
                                         session_date=TODAY, duration_minutes=None, sport_name="Rowing"))
    db_session.commit()
    [s] = _get(_client(db_session, u)).json()["sessions"]
    assert s["rateable"] is False and s["label"] == "Rowing"
    assert _client(db_session, u).post("/checkin-v2/srpe/ratings",
                                       json={"ratings": [{"kind": "aerobic", "id": s["id"], "rpe": 5}]}).status_code == 422
