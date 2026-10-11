"""The `concurrent_strength` marker on the MCP readers (Q206 / #367 loop-close).

`get_training_sessions` suffixes a session that is a gym workout's HR trace, and the readiness
snapshot leaves it out of the aerobic count and minutes and reports it on its own line. Both apply
the resolver's own test: `overlaps_workout(session, counted_workouts)` (>= HEVY_MIRROR_OVERLAP_FRACTION
of the session's OWN duration inside one workout). Display and counting only: no load value moves.

  G1  a session at >= 0.5 overlap is marked, with the workout title, and excluded from the count.
  G2  one below 0.5 is not marked and still counts.
  G3  an untimed session is never marked.
  G4  the workout set is the resolver's: an excluded workout, or an unadjudicated duplicate pair,
      marks nothing; an adjudicated pair's survivor does.
  G5  the readers agree with the resolver on the same rows (the drift this closes).
"""
from datetime import date, datetime, timedelta, timezone

import pytest

import mcp_server
import models
from context_builder import CONCURRENT_STRENGTH_PHRASE, _uncounted_phrase
from reads.aerobic_reads import HEVY_MIRROR_OVERLAP_FRACTION

NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)
DAY = (NOW - timedelta(days=2)).replace(hour=0, minute=0)       # 2 days ago, 00:00 UTC
at = lambda h, m=0: DAY + timedelta(hours=h, minutes=m)          # noqa: E731


def _user(db):
    u = models.User(email="gym@example.com", hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _aero(db, uid, sid, *, start, stop, sport="Cross-trainer", source="polar_flow_export", day=None):
    s = models.AerobicSession(
        user_id=uid, source=source, source_session_id=sid,
        session_date=day or (start.date() if start else DAY.date()),
        start_time=start, stop_time=stop, sport_name=sport,
        duration_minutes=(stop - start).total_seconds() / 60 if start and stop else 40.0,
        hr_avg=120, hr_max=150, z1_seconds=0, z2_seconds=600, z3_seconds=1800, z4_seconds=0, z5_seconds=0)
    db.add(s); db.commit(); db.refresh(s)
    return s


def _hevy(db, uid, hid, start, stop, title, **kw):
    db.add(models.HevyWorkout(hevy_id=hid, user_id=uid, start_time=start, end_time=stop, title=title,
                              raw={"id": hid, "title": title, "exercises": []}, **kw))
    db.commit()


@pytest.fixture
def world(db_session, monkeypatch):
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_db_rows", lambda sql, params: [])
    monkeypatch.setattr(mcp_server, "_aest_wake_day", lambda *a, **k: DAY.date())
    u = _user(db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: u.id)
    return u


def test_sanity_the_threshold_under_test_is_half():
    assert HEVY_MIRROR_OVERLAP_FRACTION == 0.50


# --------------------------------------------------------------------------- #
# get_training_sessions                                                        #
# --------------------------------------------------------------------------- #

def test_g1_a_session_at_half_overlap_or_more_is_marked_with_the_workout_title(db_session, world):
    # 60-minute trace, workout covers 30 minutes of it: exactly 0.50, the boundary is inclusive.
    _aero(db_session, world.id, "edge", start=at(9), stop=at(10), sport="Cross-trainer")
    _hevy(db_session, world.id, "h1", at(9, 30), at(11), "Push A")
    out = mcp_server.get_training_sessions(days=14)
    line = next(l for l in out.split("\n") if "Cross-trainer" in l)
    assert line.endswith(f" — {CONCURRENT_STRENGTH_PHRASE} (Push A)")


def test_g1_the_suffix_changes_nothing_else_on_the_line(db_session, world):
    from aerobic_format import format_aerobic_session
    s = _aero(db_session, world.id, "full", start=at(9), stop=at(10))
    _hevy(db_session, world.id, "h1", at(8, 55), at(10, 5), "Legs")
    out = mcp_server.get_training_sessions(days=14)
    assert format_aerobic_session(s) + f" — {CONCURRENT_STRENGTH_PHRASE} (Legs)" in out.split("\n")


def test_g1_the_wording_is_the_one_context_builder_renders(db_session):
    assert _uncounted_phrase({"reason": "concurrent_strength", "sport_name": "Row"}) \
        == f"{CONCURRENT_STRENGTH_PHRASE} (Row)"


def test_g2_a_session_below_half_overlap_is_not_marked(db_session, world):
    # 60-minute session, workout covers 29 of its minutes: 0.483 < 0.5.
    _aero(db_session, world.id, "brush", start=at(9), stop=at(10))
    _hevy(db_session, world.id, "h1", at(9, 31), at(11), "Push A")
    out = mcp_server.get_training_sessions(days=14)
    assert CONCURRENT_STRENGTH_PHRASE not in out


def test_g3_an_untimed_session_is_not_marked(db_session, world):
    _aero(db_session, world.id, "untimed", start=None, stop=None, day=DAY.date())
    _hevy(db_session, world.id, "h1", at(0), at(23), "All day")
    out = mcp_server.get_training_sessions(days=14)
    assert "Cross-trainer" in out and CONCURRENT_STRENGTH_PHRASE not in out


def test_g4_an_excluded_workout_marks_nothing(db_session, world):
    _aero(db_session, world.id, "x", start=at(9), stop=at(10))
    _hevy(db_session, world.id, "gone", at(8, 50), at(10, 10), "Deleted",
          excluded_at=NOW, exclusion_reason="deleted_in_hevy_never_performed")
    assert CONCURRENT_STRENGTH_PHRASE not in mcp_server.get_training_sessions(days=14)


def test_g4_an_unadjudicated_duplicate_pair_marks_nothing_and_an_adjudicated_survivor_marks(db_session, world):
    _aero(db_session, world.id, "x", start=at(9), stop=at(10))
    _hevy(db_session, world.id, "dupA", at(8, 50), at(10, 10), "Pair", dedup_flag=True, dedup_partner_ids=["dupB"])
    _hevy(db_session, world.id, "dupB", at(8, 55), at(10, 5), "Pair", dedup_flag=True, dedup_partner_ids=["dupA"])
    assert CONCURRENT_STRENGTH_PHRASE not in mcp_server.get_training_sessions(days=14)
    # The operator adjudicates: dupB is the artifact. dupA is the retained log and now counts.
    db_session.query(models.HevyWorkout).filter_by(hevy_id="dupB").update(
        {"excluded_at": NOW, "exclusion_reason": "duplicate"})
    db_session.commit()
    out = mcp_server.get_training_sessions(days=14)
    assert f"({'Pair'})" in out and CONCURRENT_STRENGTH_PHRASE in out


def test_g4_a_second_trace_over_the_same_workout_is_marked_too(db_session, world):
    # The resolver tests each session against the whole set; a one-to-one link would lose the second.
    a = _aero(db_session, world.id, "a", start=at(9), stop=at(10), source="polar_flow_export")
    b = _aero(db_session, world.id, "b", start=at(9, 5), stop=at(9, 55), source="polar_v4", sport="Strength training")
    _hevy(db_session, world.id, "h1", at(8, 50), at(10, 10), "Push A")
    counted = db_session.query(models.HevyWorkout).all()
    marks = mcp_server._concurrent_strength_sessions([a, b], counted)
    assert set(marks) == {a.id, b.id}


# --------------------------------------------------------------------------- #
# get_readiness_snapshot                                                       #
# --------------------------------------------------------------------------- #

def test_g1_the_snapshot_excludes_a_gym_trace_from_the_count_and_reports_it(db_session, world):
    _aero(db_session, world.id, "trace", start=at(9), stop=at(10))                  # 60 min, inside the workout
    _aero(db_session, world.id, "real", start=at(14), stop=at(14, 45), sport="Ride")  # 45 min, no workout
    _hevy(db_session, world.id, "h1", at(8, 55), at(10, 5), "Push A")
    out = mcp_server.get_readiness_snapshot()
    assert "Aerobic sessions (last 7 days): 1 sessions, 45 total minutes" in out
    assert "Gym HR traces (last 7 days): 1 sessions, 60 min, not counted as aerobic" in out


def test_g1_with_only_gym_traces_the_aerobic_line_is_absent_and_the_trace_line_present(db_session, world):
    _aero(db_session, world.id, "trace", start=at(9), stop=at(10))
    _hevy(db_session, world.id, "h1", at(9), at(10), "Push A")
    out = mcp_server.get_readiness_snapshot()
    assert "Aerobic sessions (last 7 days)" not in out
    assert "Gym HR traces (last 7 days): 1 sessions, 60 min, not counted as aerobic" in out


def test_g2_below_half_overlap_still_counts_and_no_trace_line_prints(db_session, world):
    _aero(db_session, world.id, "brush", start=at(9), stop=at(10))
    _hevy(db_session, world.id, "h1", at(9, 31), at(11), "Push A")
    out = mcp_server.get_readiness_snapshot()
    assert "Aerobic sessions (last 7 days): 1 sessions, 60 total minutes" in out
    assert "Gym HR traces" not in out


def test_g3_an_untimed_session_counts_and_is_not_a_trace(db_session, world):
    _aero(db_session, world.id, "untimed", start=None, stop=None, day=DAY.date())
    _hevy(db_session, world.id, "h1", at(0), at(23), "All day")
    out = mcp_server.get_readiness_snapshot()
    assert "Aerobic sessions (last 7 days): 1 sessions, 40 total minutes" in out
    assert "Gym HR traces" not in out


def test_g4_the_snapshot_follows_the_resolvers_workout_set(db_session, world):
    _aero(db_session, world.id, "x", start=at(9), stop=at(10))
    _hevy(db_session, world.id, "gone", at(8, 50), at(10, 10), "Deleted",
          excluded_at=NOW, exclusion_reason="deleted_in_hevy_never_performed")
    out = mcp_server.get_readiness_snapshot()
    assert "Aerobic sessions (last 7 days): 1 sessions, 60 total minutes" in out
    assert "Gym HR traces" not in out


def test_the_snapshot_is_unchanged_when_nothing_overlaps(db_session, world):
    _aero(db_session, world.id, "real", start=at(14), stop=at(14, 45), sport="Ride")
    out = mcp_server.get_readiness_snapshot()
    assert "Aerobic sessions (last 7 days): 1 sessions, 45 total minutes\n\n" in out
    assert "Gym HR traces" not in out


# --------------------------------------------------------------------------- #
# G5 — the readers and the resolver call a session the same thing              #
# --------------------------------------------------------------------------- #

def test_g5_the_marker_agrees_with_the_resolvers_concurrent_strength_guard(db_session, world):
    """The resolver's guard is `overlaps_workout(sess, counted_workouts)`; the readers' marker is the
    same call over the same door. Pin them on one fixture so a drift in either fails here."""
    from reads.aerobic_reads import arbitrated_sessions, overlaps_workout
    from reads.hevy_reads import counted_workouts
    rows = [
        _aero(db_session, world.id, "in", start=at(9), stop=at(10)),
        _aero(db_session, world.id, "brush", start=at(12), stop=at(13)),
        _aero(db_session, world.id, "none", start=at(16), stop=at(17)),
    ]
    _hevy(db_session, world.id, "h1", at(8, 55), at(10, 5), "Push A")
    _hevy(db_session, world.id, "h2", at(12, 40), at(14), "Pull")                       # 20/60 = 0.33
    canon = [s for s in arbitrated_sessions(world.id, db_session) if s.canonical]
    counted, _ = counted_workouts(db_session, world.id, db_session.query(models.HevyWorkout).all())
    expected = {s.id for s in canon if overlaps_workout(s, counted)}
    assert expected == {rows[0].id}
    assert set(mcp_server._gym_trace_marks(db_session, world.id, canon)) == expected
