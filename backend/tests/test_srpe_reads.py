"""`reads.srpe_reads` -- the one read door for per-session RPE: `{counted session -> (rpe_cr10, source, rung)}`.

G2 (series invariance): a result changes only because a new observation is read, never because of the order
adapters wrote in or a capture-time UI. The day shapes the brief names are each a test: a Garmin-only day, a
day-only day, a mixed (partial) day, a Hevy + Garmin-mirror day, a twin-lost day, two sources rating one bout
(the hierarchy), and an unknown scale refused (at the writer, `test_srpe_store`, repeated here as the contract
the door relies on).
"""
from datetime import date, datetime, timedelta, timezone

import pytest

import models
import srpe_hierarchy
import srpe_store as ss
from reads import srpe_reads as sr
from reads.aerobic_reads import arbitrated_sessions

GARMIN_PKG = "com.garmin.android.apps.connectmobile"
D = date(2026, 10, 3)
NOW = datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc)


def _t(hh, mm=0, day=3):
    return datetime(2026, 10, day, hh, mm, tzinfo=timezone.utc)      # UTC 01:00-13:59 is the same AEST day 11:00-23:59


def _user(db, uid=1):
    if db.get(models.User, uid) is None:
        db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
        db.commit()
    return uid


def _aero(db, start, minutes=45, *, source="polar_v4", pkg=None, sport="Strength", uid=1, ssid=None):
    _user(db, uid)
    stop = start + timedelta(minutes=minutes)
    row = models.AerobicSession(
        user_id=uid, source=source, source_session_id=ssid or f"{source}|{start.isoformat()}",
        session_date=(start + timedelta(hours=10)).date(), start_time=start, stop_time=stop, sport_name=sport,
        duration_minutes=float(minutes), source_package=pkg, z2_seconds=600)
    db.add(row)
    db.commit()
    return row


def _hevy(db, start, minutes=60, hid="h1", uid=1):
    _user(db, uid)
    db.add(models.HevyWorkout(hevy_id=hid, user_id=uid, start_time=start, end_time=start + timedelta(minutes=minutes),
                              title="Gym", raw={}))
    db.commit()
    return db.query(models.HevyWorkout).filter_by(hevy_id=hid).one()


def _garmin(db, ref, start, minutes=45, rpe_raw=70, now=NOW, uid=1):
    _user(db, uid)
    return ss.record_observation(db, uid, source="garmin", source_activity_ref=ref, start=start,
                                 stop=start + timedelta(minutes=minutes), rpe_raw=rpe_raw,
                                 raw_scale="garmin_0_100", feel=50, now=now)


def _raw_obs(db, source, ref, start, minutes, cr10, captured=NOW, uid=1):
    """A row for a source the writer would refuse (in_app has no writer yet): inserted directly, test-only."""
    _user(db, uid)
    db.add(models.SessionRpeObservation(
        user_id=uid, source=source, source_activity_ref=ref, start_time=start,
        stop_time=start + timedelta(minutes=minutes), rpe_raw=cr10, raw_scale="cr10", rpe_cr10=cr10,
        captured_at=captured, provenance={}))
    db.commit()


def _day_rpe(db, rpe, d=D, uid=1):
    _user(db, uid)
    db.add(models.DailyRecord(user_id=uid, date=d, session_rpe=rpe))
    db.commit()


def _ratings(db, d=D, uid=1):
    return [(r.bout.key[0], None if r.rating is None else (r.rating.rpe_cr10, r.rating.source, r.rating.rung))
            for r in sr.session_ratings(db, uid, since=d, until=d)]


# -- the day shapes ------------------------------------------------------------------------------------------

def test_a_garmin_only_day_carries_the_garmin_value_on_the_garmin_rung(db_session):
    _aero(db_session, _t(2), source="health_connect", pkg=GARMIN_PKG)
    _garmin(db_session, "11", _t(2))
    assert _ratings(db_session) == [("aerobic", (7.0, "garmin", 1))]
    assert sr.srpe_needed(db_session, 1, D) is False


def test_a_day_only_day_is_filled_from_the_whole_day_rating_on_the_last_rung(db_session):
    _aero(db_session, _t(2))
    _day_rpe(db_session, 6.5)
    assert _ratings(db_session) == [("aerobic", (6.5, "day_fill", 2))]
    assert sr.srpe_needed(db_session, 1, D) is True                      # a day value is not a per-session rating


def test_a_mixed_day_rates_one_session_per_session_and_fills_the_other(db_session):
    _aero(db_session, _t(2), source="health_connect", pkg=GARMIN_PKG)
    _aero(db_session, _t(8))
    _garmin(db_session, "11", _t(2))
    _day_rpe(db_session, 5.0)
    assert _ratings(db_session) == [("aerobic", (7.0, "garmin", 1)), ("aerobic", (5.0, "day_fill", 2))]
    assert sr.srpe_needed(db_session, 1, D) is True                      # the second session still wants a rating


def test_a_session_with_neither_has_no_rating(db_session):
    _aero(db_session, _t(2))
    assert _ratings(db_session) == [("aerobic", None)]


def test_a_hevy_workout_with_its_garmin_mirror_takes_the_garmin_rating_once(db_session):
    """hevy2garmin pushes the Hevy workout to Garmin -> Health Connect. The mirror row is the Hevy bout again
    (not counted); the Garmin rating of that activity lands on the counted Hevy workout."""
    w = _hevy(db_session, _t(2), 60)
    _aero(db_session, _t(2), 60, source="health_connect", pkg=GARMIN_PKG, sport="Weightlifting")
    _garmin(db_session, "21", _t(2), 60, rpe_raw=80)
    got = sr.session_ratings(db_session, 1, since=D, until=D)
    assert [(r.bout.key, r.rating.rpe_cr10, r.rating.source) for r in got] == [(("hevy", w.hevy_id), 8.0, "garmin")]


def test_a_garmin_activity_inside_a_long_hevy_workout_needs_half_of_its_own_length_inside(db_session):
    _hevy(db_session, _t(2), 60)
    _garmin(db_session, "22", _t(2, 40), 40)                              # 20 of its own 40 min inside: the Hevy rule, 0.5
    assert _ratings(db_session) == [("hevy", (7.0, "garmin", 1))]
    _garmin(db_session, "23", _t(2, 45), 60, rpe_raw=90)                  # 15 of its own 60 min: not the same bout
    assert _ratings(db_session) == [("hevy", (7.0, "garmin", 1))]


def test_a_twin_lost_day_rates_the_canonical_winner(db_session):
    """The Garmin Health Connect row lost arbitration to a same-bout Polar row: the rating is about the bout,
    so it lands on the counted Polar session with no carry-over code."""
    hc = _aero(db_session, _t(2), source="health_connect", pkg=GARMIN_PKG)
    polar = _aero(db_session, _t(2), source="polar_v4", ssid="polar-1")
    canon = [s for s in arbitrated_sessions(1, db_session) if s.canonical]
    assert [s.id for s in canon] == [polar.id] and hc.id != polar.id
    _garmin(db_session, "11", _t(2))
    got = sr.session_ratings(db_session, 1, since=D, until=D)
    assert [(r.bout.key, r.rating.source) for r in got] == [(("aerobic", polar.id), "garmin")]


def test_two_sources_rating_one_bout_take_the_higher_rung_and_never_average(db_session):
    _aero(db_session, _t(2), source="health_connect", pkg=GARMIN_PKG)
    _garmin(db_session, "11", _t(2), rpe_raw=70)
    _raw_obs(db_session, "in_app", "a1", _t(2), 45, 3.0)
    assert _ratings(db_session) == [("aerobic", (3.0, "in_app", 0))]


def test_the_hierarchy_is_the_declared_config_and_re_ranking_it_changes_the_winner(db_session, monkeypatch):
    _aero(db_session, _t(2), source="health_connect", pkg=GARMIN_PKG)
    _garmin(db_session, "11", _t(2), rpe_raw=70)
    _raw_obs(db_session, "in_app", "a1", _t(2), 45, 3.0)
    monkeypatch.setattr(srpe_hierarchy, "SOURCE_HIERARCHY", ("garmin", "in_app"))
    assert _ratings(db_session) == [("aerobic", (7.0, "garmin", 0))]


def test_a_stored_source_that_is_not_in_the_hierarchy_is_ignored_and_the_session_stays_unrated(db_session):
    _aero(db_session, _t(2))
    _raw_obs(db_session, "strava", "s1", _t(2), 45, 9.0)
    assert _ratings(db_session) == [("aerobic", None)]
    assert sr.srpe_needed(db_session, 1, D) is True


def test_within_one_source_the_latest_capture_wins(db_session):
    _aero(db_session, _t(2), source="health_connect", pkg=GARMIN_PKG)
    _garmin(db_session, "11", _t(2), rpe_raw=40, now=NOW)
    _garmin(db_session, "11", _t(2), rpe_raw=60, now=NOW + timedelta(days=1))          # re-rated: the later row is current
    assert _ratings(db_session) == [("aerobic", (6.0, "garmin", 1))]
    _garmin(db_session, "12", _t(2, 5), 40, rpe_raw=90, now=NOW + timedelta(days=2))   # a second Garmin activity, same bout
    assert _ratings(db_session) == [("aerobic", (9.0, "garmin", 1))]


def test_an_unrated_latest_row_is_no_rating_and_the_day_fill_shows_through(db_session):
    _aero(db_session, _t(2), source="health_connect", pkg=GARMIN_PKG)
    _garmin(db_session, "11", _t(2), rpe_raw=70, now=NOW)
    _garmin(db_session, "11", _t(2), rpe_raw=None, now=NOW + timedelta(days=1))
    _day_rpe(db_session, 4.0)
    assert _ratings(db_session) == [("aerobic", (4.0, "day_fill", 2))]


def test_a_rating_with_no_stop_time_cannot_be_placed_so_its_session_is_unrated(db_session):
    _aero(db_session, _t(2), source="health_connect", pkg=GARMIN_PKG)
    ss.record_observation(db_session, 1, source="garmin", source_activity_ref="11", start=_t(2), stop=None,
                          rpe_raw=70, raw_scale="garmin_0_100", now=NOW)
    assert _ratings(db_session) == [("aerobic", None)]


def test_an_observation_lands_on_the_one_session_it_overlaps_most(db_session):
    a = _aero(db_session, _t(2), 45, ssid="a")
    b = _aero(db_session, _t(2, 40), 45, ssid="b")                        # 5 min vs a, 45 vs b once the activity is 50 long
    _garmin(db_session, "11", _t(2, 40), 50)
    got = {r.bout.key: r.rating for r in sr.session_ratings(db_session, 1, since=D, until=D)}
    assert got[("aerobic", a.id)] is None and got[("aerobic", b.id)].source == "garmin"


# -- what counts ---------------------------------------------------------------------------------------------

def test_a_non_training_sport_is_not_a_counted_session(db_session):
    _aero(db_session, _t(2), sport="Yoga")
    assert sr.counted_sessions(db_session, 1) == []
    assert sr.srpe_needed(db_session, 1, D) is True                      # nothing counted: fail open


def test_pilates_is_a_counted_session(db_session):
    """Pilates left NON_TRAINING_SPORTS by operator ruling: it is counted, so it is asked and it is felt load."""
    pil = _aero(db_session, _t(2), source="health_connect", pkg=GARMIN_PKG, sport="Pilates", minutes=52)
    assert [(b.key, b.minutes) for b in sr.counted_sessions(db_session, 1)] == [(("aerobic", pil.id), 52.0)]


def test_a_rating_can_still_be_resolved_for_a_session_the_count_leaves_out(db_session):
    """The MCP session lines show a Garmin rating on a non-training session though it is not counted."""
    pil = _aero(db_session, _t(2), source="health_connect", pkg=GARMIN_PKG, sport="Yoga")
    _garmin(db_session, "11", _t(2), rpe_raw=30)
    got = sr.observed_ratings(db_session, 1, [sr.aerobic_bout(pil)])
    assert got[("aerobic", pil.id)].rpe_cr10 == 3.0


def test_an_untimed_session_can_only_be_day_filled(db_session):
    _user(db_session)
    db_session.add(models.AerobicSession(user_id=1, source="polar_flow_export", source_session_id="u", session_date=D,
                                         duration_minutes=40.0))
    db_session.commit()
    _garmin(db_session, "11", _t(2))
    assert _ratings(db_session) == [("aerobic", None)]
    _day_rpe(db_session, 6.0)
    assert _ratings(db_session) == [("aerobic", (6.0, "day_fill", 2))]


# -- G1: fail open to asking, and a later value overrides per session --------------------------------------------

def test_a_source_that_has_not_synced_yet_leaves_the_question_open_and_a_later_value_closes_it(db_session):
    _aero(db_session, _t(2), source="health_connect", pkg=GARMIN_PKG)
    _day_rpe(db_session, 6.0)                                            # the close-out was answered tonight
    assert sr.srpe_needed(db_session, 1, D) is True
    assert _ratings(db_session) == [("aerobic", (6.0, "day_fill", 2))]
    _garmin(db_session, "11", _t(2), rpe_raw=80)                        # 02:00 sweep: Garmin's value arrives
    assert _ratings(db_session) == [("aerobic", (8.0, "garmin", 1))]     # overrides this session; nothing re-prompts
    assert sr.srpe_needed(db_session, 1, D) is False


def test_a_day_with_no_counted_session_still_asks(db_session):
    """An unrecorded session leaves nothing to count; only the athlete can rate it."""
    assert sr.srpe_needed(db_session, 1, D) is True


# -- G2: the answer depends on what was observed, not on the order or the window -----------------------------------

def test_write_order_does_not_change_the_answer(db_session):
    def build(db, order):
        _aero(db, _t(2), source="health_connect", pkg=GARMIN_PKG, ssid="x")
        _aero(db, _t(8), ssid="y")
        steps = {
            "garmin": lambda: _garmin(db, "11", _t(2), rpe_raw=70, now=NOW),
            "in_app": lambda: _raw_obs(db, "in_app", "a1", _t(8), 45, 4.0, captured=NOW + timedelta(hours=1)),
            "day": lambda: _day_rpe(db, 5.0),
        }
        for k in order:
            steps[k]()
        return _ratings(db)

    first = build(db_session, ["garmin", "in_app", "day"])
    db_session.query(models.SessionRpeObservation).delete()
    db_session.query(models.DailyRecord).delete()
    db_session.query(models.AerobicSession).delete()
    db_session.commit()
    assert build(db_session, ["day", "in_app", "garmin"]) == first == [
        ("aerobic", (7.0, "garmin", 1)), ("aerobic", (4.0, "in_app", 0))]


def test_cutting_the_window_does_not_move_a_rating_to_another_session(db_session):
    near = _aero(db_session, _t(13, 30), 60, ssid="late")                # 13:30-14:30 UTC: 23:30 AEST on D, so day D
    far = _aero(db_session, _t(14, 15), 60, ssid="after")                # 14:15-15:15 UTC: 00:15 AEST on D+1
    _garmin(db_session, "11", _t(14, 0), 60)                             # 30 min of `near` (enough on its own), 45 of `far`
    full = {r.bout.key: r.rating for r in sr.session_ratings(db_session, 1)}
    cut = {r.bout.key: r.rating for r in sr.session_ratings(db_session, 1, since=D, until=D)}
    assert full[("aerobic", far.id)] is not None and full[("aerobic", near.id)] is None
    assert cut == {("aerobic", near.id): None}                           # D only: the rating is not pulled onto `near`


def test_other_users_ratings_never_cross(db_session):
    _aero(db_session, _t(2), source="health_connect", pkg=GARMIN_PKG)
    _garmin(db_session, "11", _t(2), uid=2)
    assert _ratings(db_session) == [("aerobic", None)]


def test_nothing_outside_the_store_queries_the_observation_table():
    """Q231 imports the door and must not build its own lookup: the table is read through `latest_by_activity`
    (the store) and resolved through `session_ratings` / `observed_ratings` (the door), nowhere else."""
    import re
    from pathlib import Path
    backend = Path(__file__).resolve().parent.parent
    readers = []
    for path in backend.rglob("*.py"):
        rel = path.relative_to(backend).as_posix()
        if rel.startswith(("tests/", "migrations/", ".venv/")) or "/site-packages/" in rel:
            continue
        if re.search(r"(query|select)\(\s*models\.SessionRpeObservation", path.read_text(encoding="utf-8")):
            readers.append(rel)
    assert readers == ["srpe_store.py"]
