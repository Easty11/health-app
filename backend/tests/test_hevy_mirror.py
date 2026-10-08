"""Hevy-mirror suppression at the read-door (A3.2).

hevy2garmin pushes Hevy workouts to Garmin; Garmin Connect / Strava then write them into Health
Connect as their OWN activities (16 `com.strava` Weightlifting rows, Sept-Oct 2026). Admission drops
only `com.hevy`, so the rows are stored. They are the Hevy bout again, so `arbitrated_sessions` marks
a Health Connect row a `hevy_mirror` -- not canonical, and out of the arbitration -- when its overlap
with ONE Hevy bout (any hevy_workouts row, excluded or not) is >= HEVY_MIRROR_OVERLAP_FRACTION (0.5) of the ROW'S OWN duration. And
`overlaps_workout` (the resolver's concurrent_strength guard, the psychological read) is the same
fraction test, not any intersection (D-b).

Gates: G1 the fraction test (boundary, own-duration denominator, one bout at a time) · G2 package-
agnostic, Health Connect only · G3 any Hevy bout makes a mirror, excluded or unadjudicated included · G4 a mirror never
suppresses a live row · G5 every raw reader agrees (metabolic load, CBT-I training_end, psychological
minutes) · G6 the API says so.
"""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import models
from cbti.replay import load_nights
from load_events_metabolic import compute_all_users_metabolic
from reads import psychological_reads
from reads.hevy_reads import counted_workouts
from reads.aerobic_reads import (
    HEVY_MIRROR_OVERLAP_FRACTION,
    arbitrated_sessions,
    hevy_mirror_session_ids,
    overlap_fraction,
    overlaps_workout,
)
from routers.polar import AerobicSessionOut

GARMIN = "com.garmin.android.apps.connectmobile"
STRAVA = "com.strava"
D = date(2026, 9, 8)


def _t(hh, mm=0, day=8):
    return datetime(2026, 9, day, hh, mm, tzinfo=timezone.utc)


def _user(db, email="mirror@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _hevy(db, uid, hid, start, end, *, excluded=False, dedup=False, partners=None):
    db.add(models.HevyWorkout(
        hevy_id=hid, user_id=uid, start_time=start, end_time=end, title="Gym", raw={},
        dedup_flag=dedup, dedup_partner_ids=partners,
        excluded_at=datetime(2026, 9, 9, tzinfo=timezone.utc) if excluded else None))
    db.commit()


def _hc(db, uid, ssid, start, stop, pkg, *, sport="Weightlifting", zones=(0, 0, 0, 0, 0), source="health_connect"):
    row = models.AerobicSession(
        user_id=uid, source=source, source_session_id=ssid, session_date=start.date(),
        start_time=start, stop_time=stop, sport_name=sport, source_package=pkg,
        duration_minutes=(stop - start).total_seconds() / 60.0,
        z1_seconds=zones[0], z2_seconds=zones[1], z3_seconds=zones[2], z4_seconds=zones[3], z5_seconds=zones[4])
    db.add(row)
    db.commit()
    return row.id


def _by_id(db, uid):
    return {s.id: s for s in arbitrated_sessions(uid, db)}


# ── G1: the fraction test ───────────────────────────────────────────────────────────────

def _span(a, b):
    return SimpleNamespace(start_time=_t(*a), stop_time=_t(*b), end_time=_t(*b))


def test_the_constant_is_one_half_of_the_rows_own_duration():
    assert HEVY_MIRROR_OVERLAP_FRACTION == 0.5
    bout = [_span((6, 0), (7, 0))]
    assert overlap_fraction(_span((6, 15), (7, 5)), bout) == 45 / 50          # 90% inside: a copy
    assert overlaps_workout(_span((6, 0), (6, 50)), bout)                      # fully inside


def test_exactly_half_is_a_copy_and_just_under_is_not():
    bout = [_span((6, 0), (7, 0))]
    assert overlaps_workout(_span((6, 30), (7, 30)), bout)                     # 30 of 60 min = 0.5, inclusive
    assert not overlaps_workout(_span((6, 31), (7, 31)), bout)                 # 29 of 60 = 0.483


def test_the_denominator_is_the_rows_own_duration_not_the_shorter_of_the_pair():
    bout = [_span((6, 0), (6, 25))]
    long_row = _span((5, 40), (6, 40))                                          # 60 min around a 25-min bout
    assert overlap_fraction(long_row, bout) == 25 / 60 and not overlaps_workout(long_row, bout)


def test_an_erg_session_that_brushes_a_hevy_timer_is_not_a_copy():
    bout = [_span((6, 0), (7, 0))]
    assert not overlaps_workout(_span((6, 58), (7, 28)), bout)                 # 2 min of 30
    assert overlap_fraction(_span((6, 58), (7, 28)), bout) < 0.1


def test_one_bout_at_a_time_never_the_sum_of_two():
    bouts = [_span((6, 0), (6, 25)), _span((6, 25), (6, 50))]                  # back-to-back
    assert not overlaps_workout(_span((5, 55), (6, 55)), bouts)                # 25/60 each, 50/60 together


def test_an_untimed_or_empty_row_can_never_be_shown_to_overlap():
    bout = [_span((6, 0), (7, 0))]
    assert overlap_fraction(SimpleNamespace(start_time=None, stop_time=_t(7)), bout) == 0.0
    assert overlap_fraction(SimpleNamespace(start_time=_t(6, 30), stop_time=_t(6, 30)), bout) == 0.0
    assert overlap_fraction(_span((6, 0), (7, 0)), [SimpleNamespace(start_time=None, end_time=_t(7))]) == 0.0


def test_naive_and_aware_stamps_do_not_raise():
    naive = SimpleNamespace(start_time=datetime(2026, 9, 8, 6, 0), stop_time=datetime(2026, 9, 8, 7, 0))
    assert overlaps_workout(naive, [_span((6, 0), (7, 0))])


# ── G2: package-agnostic, Health Connect only ───────────────────────────────────────────

def test_a_health_connect_copy_is_a_mirror_whichever_package_wrote_it(db_session):
    u = _user(db_session)
    _hevy(db_session, u.id, "w1", _t(6), _t(7))
    ids = {pkg: _hc(db_session, u.id, f"s_{i}", _t(6, 5), _t(6, 55), pkg)
           for i, pkg in enumerate([STRAVA, GARMIN, "com.example.unknown", None])}
    rows = _by_id(db_session, u.id)
    for pkg, sid in ids.items():
        assert rows[sid].hevy_mirror is True and rows[sid].canonical is False, pkg


def test_a_polar_row_in_the_gym_is_never_a_mirror(db_session):
    u = _user(db_session)
    _hevy(db_session, u.id, "w1", _t(6), _t(7))
    sid = _hc(db_session, u.id, "p1", _t(6, 5), _t(6, 55), None, source="polar_flow_export", sport="Strength")
    row = _by_id(db_session, u.id)[sid]
    assert row.hevy_mirror is False and row.canonical is True                   # a strap in the gym is a real HR trace


def test_a_session_far_from_any_hevy_bout_is_untouched(db_session):
    u = _user(db_session)
    _hevy(db_session, u.id, "w1", _t(6), _t(7))
    sid = _hc(db_session, u.id, "run", _t(17), _t(17, 40), GARMIN, sport="Running")
    row = _by_id(db_session, u.id)[sid]
    assert row.hevy_mirror is False and row.canonical is True


# ── G3: any Hevy bout makes a mirror, counted or not ─────────────────────────────────────────

def test_an_excluded_hevy_bout_still_makes_a_mirror(db_session):
    """INVERTED by the A3.2 amendment (it asserted an excluded bout makes no mirror). Prod row 111
    mirrors hevy_workouts b3ebc404, excluded 18 Sep as `deleted_in_hevy_never_performed`;
    hevy2garmin does not honour Hevy deletions and resurrected it into Garmin on the 7 Oct backfill.
    The mirror test asks where a Health Connect row CAME FROM, not whether Hevy's bout still counts,
    so an excluded bout must suppress its copy. Counting stays on the door, pinned below."""
    u = _user(db_session)
    _hevy(db_session, u.id, "w1", _t(6), _t(7), excluded=True)
    sid = _hc(db_session, u.id, "s1", _t(6, 5), _t(6, 55), STRAVA)
    row = _by_id(db_session, u.id)[sid]
    assert row.hevy_mirror is True and row.canonical is False
    assert sid in hevy_mirror_session_ids(u.id, db_session)


def test_an_excluded_bout_suppresses_its_copy_but_is_still_not_counted(db_session):
    u = _user(db_session)
    _hevy(db_session, u.id, "w1", _t(6), _t(7), excluded=True)
    counted, _ = counted_workouts(db_session, u.id, db_session.query(models.HevyWorkout).all())
    assert counted == []                                                        # the door is unchanged


def test_both_sides_of_an_unadjudicated_duplicate_pair_make_a_mirror_and_so_does_a_survivor(db_session):
    """The pair counts nothing until adjudicated (the door), but a copy of EITHER side is a copy of
    a Hevy workout. Adjudicating the pair changes nothing about the copy."""
    u = _user(db_session)
    _hevy(db_session, u.id, "wA", _t(6), _t(7), dedup=True, partners=["wB"])
    _hevy(db_session, u.id, "wB", _t(6), _t(7), dedup=True, partners=["wA"])
    sid = _hc(db_session, u.id, "s1", _t(6, 5), _t(6, 55), STRAVA)
    assert _by_id(db_session, u.id)[sid].hevy_mirror is True                    # pair unadjudicated
    db_session.get(models.HevyWorkout, "wB").excluded_at = datetime(2026, 9, 9, tzinfo=timezone.utc)
    db_session.commit()
    assert _by_id(db_session, u.id)[sid].hevy_mirror is True                    # survivor wA, loser wB excluded


def test_an_excluded_bout_that_the_row_only_brushes_is_still_not_a_copy(db_session):
    u = _user(db_session)
    _hevy(db_session, u.id, "w1", _t(6), _t(6, 25), excluded=True)
    sid = _hc(db_session, u.id, "s1", _t(6), _t(7), GARMIN)                     # 25 of 60 minutes: 0.42
    assert _by_id(db_session, u.id)[sid].hevy_mirror is False


# ── G4: a mirror never suppresses a live row ────────────────────────────────────────────

def test_a_zoned_mirror_does_not_outrank_the_genuine_watch_row(db_session):
    """A 25-minute Strava copy WITH zones sits inside a 25-minute Hevy bout; a 60-minute Garmin row
    around it (0.42 inside the bout, so kept) has none. Without the mirror rule the zoned copy wins
    the same-bout arbitration (richer data tier) and the genuine row is dropped."""
    u = _user(db_session)
    _hevy(db_session, u.id, "w1", _t(6), _t(6, 25))
    copy = _hc(db_session, u.id, "strava", _t(6), _t(6, 25), STRAVA, zones=(0, 900, 600, 0, 0))
    real = _hc(db_session, u.id, "garmin", _t(5, 40), _t(6, 40), GARMIN, sport="Strength")
    rows = _by_id(db_session, u.id)
    assert (rows[copy].hevy_mirror, rows[copy].canonical) == (True, False)
    assert (rows[real].hevy_mirror, rows[real].canonical) == (False, True)

    # Control: with no Hevy bout the zoned copy IS the richer row and wins -- so it is the rule that moved it.
    other = _user(db_session, "control@example.com")
    c2 = _hc(db_session, other.id, "strava", _t(6), _t(6, 25), STRAVA, zones=(0, 900, 600, 0, 0))
    r2 = _hc(db_session, other.id, "garmin", _t(5, 40), _t(6, 40), GARMIN, sport="Strength")
    ctl = _by_id(db_session, other.id)
    assert (ctl[c2].canonical, ctl[r2].canonical) == (True, False)


def test_mirrors_are_still_returned_for_callers_that_need_every_row(db_session):
    u = _user(db_session)
    _hevy(db_session, u.id, "w1", _t(6), _t(7))
    sid = _hc(db_session, u.id, "s1", _t(6, 5), _t(6, 55), STRAVA)
    assert sid in [s.id for s in arbitrated_sessions(u.id, db_session, limit=5)]      # find_link reads these


# ── G5: every raw reader agrees ─────────────────────────────────────────────────────────

def test_the_metabolic_transform_emits_no_load_for_a_mirror(db_session):
    u = _user(db_session)
    _hevy(db_session, u.id, "w1", _t(6), _t(7))
    copy = _hc(db_session, u.id, "strava", _t(6, 5), _t(6, 55), STRAVA, zones=(0, 900, 600, 0, 0))
    genuine = _hc(db_session, u.id, "run", _t(17), _t(17, 40), GARMIN, sport="Running", zones=(0, 900, 600, 0, 0))
    compute_all_users_metabolic(db_session, only_user_id=u.id)
    refs = {e.source_ref for e in db_session.query(models.LoadEvent).filter_by(user_id=u.id, source="aerobic_sessions")}
    assert refs == {str(genuine)} and str(copy) not in refs


def _night(db, uid, wake_day):
    db.add(models.DailyRecord(user_id=uid, date=wake_day, diary_tst_min=420, diary_se_pct=90.0))
    db.commit()


def test_a_mirror_never_sets_a_cbti_training_end_but_a_genuine_session_does(db_session):
    """cbti/replay.py reads aerobic_sessions with raw SQL (it must run before a migration deploys), so
    it bypasses the door. A Strava copy of a late gym session would otherwise set a night's training_end
    that the Hevy bout itself never did and could flip the night to training_constrained."""
    u = _user(db_session)
    # Day 8: a late gym session whose only Health Connect trace is a Strava copy.
    _hevy(db_session, u.id, "w1", _t(9, 30), _t(10, 30))
    _hc(db_session, u.id, "strava", _t(9, 35), _t(10, 29), STRAVA)
    # Day 10: a genuine Garmin run, no Hevy bout.
    run_stop = _t(10, 0, day=10)
    _hc(db_session, u.id, "run", _t(9, 20, day=10), run_stop, GARMIN, sport="Running")
    _night(db_session, u.id, date(2026, 9, 9))      # follows day 8
    _night(db_session, u.id, date(2026, 9, 11))     # follows day 10
    nights = {n.date: n for n in load_nights(db_session, u.id, date(2026, 9, 9), date(2026, 9, 11))}
    assert nights[date(2026, 9, 9)].training_end is None
    assert nights[date(2026, 9, 11)].training_end is not None


def test_the_latest_genuine_session_of_the_day_still_wins_the_cbti_max(db_session):
    u = _user(db_session)
    _hevy(db_session, u.id, "w1", _t(9, 30), _t(10, 30))
    _hc(db_session, u.id, "strava", _t(9, 35), _t(10, 29), STRAVA)                       # a mirror, ends 10:29
    _hc(db_session, u.id, "walk_run", _t(6, 0), _t(6, 45), GARMIN, sport="Running")       # genuine, ends 06:45
    _night(db_session, u.id, date(2026, 9, 9))
    n = load_nights(db_session, u.id, date(2026, 9, 9), date(2026, 9, 9))[0]
    assert str(n.training_end)[11:16] == "06:45"                                          # not the mirror's 10:29


def test_the_psychological_read_counts_a_brushing_erg_session_but_not_a_copy(db_session):
    u = _user(db_session)
    _hevy(db_session, u.id, "w1", _t(6), _t(7))
    _hc(db_session, u.id, "erg", _t(6, 58), _t(7, 28), GARMIN, sport="Row")                # 2 of 30 min: its own session
    _hc(db_session, u.id, "copy", _t(6, 5), _t(6, 55), STRAVA)                             # 50 of 50 min: the bout again
    minutes, count = psychological_reads._duration_min_by_day(db_session, u.id)[D]
    assert count == 2 and minutes == 60.0 + 30.0                                           # the Hevy hour + the erg's 30


def test_the_mirror_id_helper_agrees_with_the_read_door(db_session):
    u = _user(db_session)
    _hevy(db_session, u.id, "w1", _t(6), _t(7))
    copy = _hc(db_session, u.id, "strava", _t(6, 5), _t(6, 55), STRAVA)
    _hc(db_session, u.id, "run", _t(17), _t(17, 40), GARMIN, sport="Running")
    from_door = {s.id for s in arbitrated_sessions(u.id, db_session) if s.hevy_mirror}
    assert hevy_mirror_session_ids(u.id, db_session) == from_door == {copy}
    assert hevy_mirror_session_ids(u.id, db_session, since=date(2026, 9, 9)) == set()      # session_date window


# ── G6: the API says so ─────────────────────────────────────────────────────────────────

def test_the_session_list_marks_a_mirror(db_session):
    u = _user(db_session)
    _hevy(db_session, u.id, "w1", _t(6), _t(7))
    copy = _hc(db_session, u.id, "strava", _t(6, 5), _t(6, 55), STRAVA)
    out = {s.id: AerobicSessionOut.model_validate(s) for s in arbitrated_sessions(u.id, db_session)}
    assert (out[copy].hevy_mirror, out[copy].canonical) == (True, False)
