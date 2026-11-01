"""`srpe_in_app` -- the app's own per-session capture, written as source `in_app` through the store's one writer.

The contract half (scale declared, window never from the client) and the placement half (the rating lands on the
exact bout it was made for, outranks the device's, a re-rate wins) are tests; so is the refusal of anything that is
not a counted session of this user. The 31 Oct shape (a Hevy-only workout and a Health Connect Pilates, both
unrated) is the real starting state the card was built for.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

import models
import srpe_in_app as ia
import srpe_store as ss
from reads import srpe_reads as sr
from srpe_in_app import RatingIn

GARMIN_PKG = "com.garmin.android.apps.connectmobile"
TODAY = date(2026, 10, 31)
NOW = datetime(2026, 10, 31, 11, 0, tzinfo=timezone.utc)


def _t(hh, mm=0, day=31):
    return datetime(2026, 10, day, hh, mm, tzinfo=timezone.utc)      # UTC 01:00-13:59 is the same AEST day


def _user(db, uid=1):
    if db.get(models.User, uid) is None:
        db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
        db.commit()
    return uid


def _aero(db, start, minutes=52, *, sport="Pilates", source="health_connect", pkg=GARMIN_PKG, uid=1, stop="auto"):
    _user(db, uid)
    row = models.AerobicSession(
        user_id=uid, source=source, source_session_id=f"{source}|{start.isoformat()}",
        session_date=(start + timedelta(hours=10)).date(), start_time=start,
        stop_time=start + timedelta(minutes=minutes) if stop == "auto" else stop, sport_name=sport,
        duration_minutes=float(minutes), source_package=pkg, z2_seconds=600)
    db.add(row)
    db.commit()
    return row


def _hevy(db, start, minutes=55, hid="hevy-1", uid=1, title="Upper body"):
    _user(db, uid)
    db.add(models.HevyWorkout(hevy_id=hid, user_id=uid, start_time=start, end_time=start + timedelta(minutes=minutes),
                              title=title, raw={}))
    db.commit()
    return db.query(models.HevyWorkout).filter_by(hevy_id=hid).one()


def _rows(db):
    return db.query(models.SessionRpeObservation).order_by(models.SessionRpeObservation.id).all()


def _rated(db, d=TODAY):
    return {r.bout.key: (r.rating.rpe_cr10, r.rating.source) if r.rating else None
            for r in sr.session_ratings(db, 1, since=d, until=d)}


# -- the contract -------------------------------------------------------------------------------------------

def test_in_app_declares_a_cr10_scale_and_nothing_else():
    assert set(ss.SOURCE_SCALES["in_app"]) == {"cr10"}
    assert (ss.CR10.lo, ss.CR10.hi, ss.CR10.divisor) == (0.0, 10.0, 1.0)


def test_the_contract_refuses_an_undeclared_scale_for_in_app(db_session):
    w = _hevy(db_session, _t(2))
    b = sr.counted_sessions(db_session, 1)[0]
    for scale in ("garmin_0_100", "borg_6_20", ""):
        with pytest.raises(ss.UnknownScale):
            ss.record_observation(db_session, 1, source="in_app", source_activity_ref="x", bout=b, rpe_raw=5,
                                  raw_scale=scale, now=NOW)
    assert _rows(db_session) == [] and w is not None


def test_an_in_app_write_without_a_bout_or_with_a_client_window_is_refused(db_session):
    _user(db_session)
    _hevy(db_session, _t(2))
    b = sr.counted_sessions(db_session, 1)[0]
    with pytest.raises(ss.SRPEContractError):       # no bout: nothing to take the window from
        ss.record_observation(db_session, 1, source="in_app", source_activity_ref="x", rpe_raw=5, raw_scale="cr10",
                              now=NOW)
    with pytest.raises(ss.SRPEContractError):       # a client window alongside the bout
        ss.record_observation(db_session, 1, source="in_app", source_activity_ref="x", bout=b, rpe_raw=5,
                              raw_scale="cr10", start=_t(0), stop=_t(1), now=NOW)
    assert _rows(db_session) == []


def test_a_bout_is_refused_for_every_other_source(db_session):
    _user(db_session)
    _hevy(db_session, _t(2))
    b = sr.counted_sessions(db_session, 1)[0]
    with pytest.raises(ss.SRPEContractError):
        ss.record_observation(db_session, 1, source="garmin", source_activity_ref="x", bout=b, start=_t(2),
                              stop=_t(3), rpe_raw=50, raw_scale="garmin_0_100", now=NOW)
    assert _rows(db_session) == []


def test_out_of_range_in_app_values_are_refused(db_session):
    _hevy(db_session, _t(2))
    for bad in (-1, 10.5, 11, True, float("nan")):
        with pytest.raises(ss.SRPEContractError):
            ia.rate_sessions(db_session, 1, [RatingIn("hevy", "hevy-1", bad)], today=TODAY, now=NOW)
    assert _rows(db_session) == []


# -- placement: the rating lands exactly on the bout it was made for ----------------------------------------

def test_an_in_app_rating_lands_on_the_hevy_bout_exactly_with_the_servers_window(db_session):
    w = _hevy(db_session, _t(2), minutes=55)
    [row] = ia.rate_sessions(db_session, 1, [RatingIn("hevy", "hevy-1", 7)], today=TODAY, now=NOW)
    assert (row.source, row.source_activity_ref, row.rpe_cr10, row.raw_scale) == ("in_app", "hevy:hevy-1", 7.0, "cr10")
    assert row.start_time.replace(tzinfo=timezone.utc) == w.start_time.astimezone(timezone.utc)
    assert row.stop_time.replace(tzinfo=timezone.utc) - row.start_time.replace(tzinfo=timezone.utc) == timedelta(minutes=55)
    assert _rated(db_session) == {("hevy", "hevy-1"): (7.0, "in_app")}


def test_the_31_oct_shape_two_unrated_sessions_take_one_rating_each_and_neither_borrows_the_other(db_session):
    """A 55-min Hevy-only workout and a 52-min Health Connect Pilates, both unrated. Each takes its own value."""
    _hevy(db_session, _t(2), minutes=55)
    pil = _aero(db_session, _t(8), minutes=52)
    assert _rated(db_session) == {("hevy", "hevy-1"): None, ("aerobic", pil.id): None}
    ia.rate_sessions(db_session, 1, [RatingIn("hevy", "hevy-1", 8), RatingIn("aerobic", str(pil.id), 3)],
                     today=TODAY, now=NOW)
    assert _rated(db_session) == {("hevy", "hevy-1"): (8.0, "in_app"), ("aerobic", pil.id): (3.0, "in_app")}


def test_in_app_outranks_garmin_on_the_same_session(db_session):
    s = _aero(db_session, _t(2), minutes=45, sport="Strength")
    ss.record_observation(db_session, 1, source="garmin", source_activity_ref="g1", start=_t(2),
                          stop=_t(2) + timedelta(minutes=45), rpe_raw=70, raw_scale="garmin_0_100", now=NOW)
    assert _rated(db_session) == {("aerobic", s.id): (7.0, "garmin")}
    ia.rate_sessions(db_session, 1, [RatingIn("aerobic", str(s.id), 4)], today=TODAY, now=NOW - timedelta(hours=1))
    assert _rated(db_session) == {("aerobic", s.id): (4.0, "in_app")}      # the app's own, though captured earlier


def test_a_re_rate_is_a_new_row_and_the_latest_wins(db_session):
    _hevy(db_session, _t(2))
    ia.rate_sessions(db_session, 1, [RatingIn("hevy", "hevy-1", 5)], today=TODAY, now=NOW)
    ia.rate_sessions(db_session, 1, [RatingIn("hevy", "hevy-1", 8)], today=TODAY, now=NOW)       # same instant
    assert [r.rpe_cr10 for r in _rows(db_session)] == [5.0, 8.0]
    assert _rated(db_session) == {("hevy", "hevy-1"): (8.0, "in_app")}


# -- refusals: only a counted session of this user, in the window --------------------------------------------

def test_a_key_that_is_not_a_counted_session_of_the_user_is_refused_and_inserts_nothing(db_session):
    _hevy(db_session, _t(2))
    _hevy(db_session, _t(2), hid="theirs", uid=2)
    for kind, ref in (("hevy", "theirs"), ("hevy", "nope"), ("aerobic", "999"), ("swim", "hevy-1")):
        with pytest.raises(ia.NotARateableSession):
            ia.rate_sessions(db_session, 1, [RatingIn(kind, ref, 5)], today=TODAY, now=NOW)
    assert _rows(db_session) == []


def test_one_bad_key_in_a_batch_refuses_the_whole_batch(db_session):
    _hevy(db_session, _t(2))
    with pytest.raises(ia.NotARateableSession):
        ia.rate_sessions(db_session, 1, [RatingIn("hevy", "hevy-1", 5), RatingIn("hevy", "nope", 5)],
                         today=TODAY, now=NOW)
    assert _rows(db_session) == []


def test_a_session_outside_the_rateable_window_is_refused(db_session):
    _hevy(db_session, _t(2, day=17), hid="before-release")           # 17 Oct: the day before the store's release
    _hevy(db_session, _t(2, day=20), hid="too-old")
    for hid in ("before-release", "too-old"):
        with pytest.raises(ia.NotARateableSession):
            ia.rate_sessions(db_session, 1, [RatingIn("hevy", hid, 5)], today=date(2026, 11, 20), now=NOW)
    assert _rows(db_session) == []
    assert ia.rating_window(date(2026, 11, 20)) == (date(2026, 11, 5), date(2026, 11, 20))
    assert ia.rating_window(date(2026, 10, 31)) == (date(2026, 10, 18), date(2026, 10, 31))


def test_a_counted_session_with_no_usable_window_is_refused(db_session):
    s = _aero(db_session, _t(2), minutes=45, sport="Strength", stop=None)
    s.duration_minutes = None
    db_session.commit()
    with pytest.raises(ss.UnplaceableBout):
        ia.rate_sessions(db_session, 1, [RatingIn("aerobic", str(s.id), 5)], today=TODAY, now=NOW)
    assert _rows(db_session) == []


def test_a_session_with_a_duration_but_no_stop_is_rated_over_start_plus_duration(db_session):
    s = _aero(db_session, _t(2), minutes=45, sport="Strength", stop=None)
    [row] = ia.rate_sessions(db_session, 1, [RatingIn("aerobic", str(s.id), 6)], today=TODAY, now=NOW)
    assert row.stop_time.replace(tzinfo=timezone.utc) - row.start_time.replace(tzinfo=timezone.utc) == timedelta(minutes=45)
