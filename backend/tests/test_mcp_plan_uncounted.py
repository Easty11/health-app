"""`get_training_plan` states what the leg did NOT count, with the date and the resolver's reason.

21 Oct 2026: three Polar "Indoor cycling" sessions never counted toward the metabolic slot because that
sport was not in its `device_sports`. The resolver listed each in `uncounted[]` (`unclaimed_session`), the
chat context printed "other activity (Indoor cycling)", but the plan tool printed nothing, so the miss was
invisible from the one read the operator uses to check the week. These pin the section: present with date,
sport, duration and reason when something is uncounted; absent (the plan byte-identical) when nothing is.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

import mcp_server
import models
from load_metrics import _local_day as _real_local_day

MONDAY = date(2026, 9, 7)
TODAY = date(2026, 9, 9)          # Wednesday, inside leg A [09-07, 09-13]
LIVE_SPORTS = ["Biking Stationary", "Biking", "Jogging", "Running", "Elliptical", "Cross-trainer",
               "Treadmill running", "Rowing", "Indoor rowing", "Cycling", "Hiking"]
HEADER = "== Not counted toward any slot this leg =="


def _user(db, email="unc@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _phase(db, uid, sports):
    micro = {"sub_cycle_days": 7, "sub_cycles": [{"label": "A", "slots": [
        {"load_window": "metabolic", "device_sports": sports, "sessions_per_cycle": 7, "minutes": 30}]}]}
    db.add(models.TrainingPhase(
        user_id=uid, label="aerobic base", probe_posture="suppressed", vehicle_ranking="standard",
        microcycle=micro, entered_on=MONDAY, asserted_by="user", asserted_on=MONDAY, source="api"))
    db.commit()


def _session(db, uid, sid, sport, *, timed=True, minutes=35.0, source="polar_v4", day=date(2026, 9, 8)):
    start = datetime(day.year, day.month, day.day, 6, 0, tzinfo=timezone.utc) if timed else None
    stop = datetime(day.year, day.month, day.day, 6, int(minutes), tzinfo=timezone.utc) if timed else None
    db.add(models.AerobicSession(
        user_id=uid, source=source, source_session_id=sid, session_date=day, start_time=start,
        stop_time=stop, sport_name=sport, duration_minutes=minutes,
        z1_seconds=60, z2_seconds=180, z3_seconds=300, z4_seconds=540, z5_seconds=960))
    db.commit()


@pytest.fixture
def tool(db_session, monkeypatch):
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    # "today" is pinned; a call WITH a timestamp still buckets it (the plan tool buckets each uncounted item).
    monkeypatch.setattr(mcp_server, "_local_day", lambda *a, **k: _real_local_day(*a, **k) if a else TODAY)

    def call(user):
        monkeypatch.setattr(mcp_server, "_current_user_id", lambda: user.id)
        return mcp_server.get_training_plan()
    return call


def _section(out: str) -> str:
    assert HEADER in out, out
    return out.split(HEADER, 1)[1].split("\n\n", 1)[0]


def test_an_unclaimed_sport_is_listed_with_its_date_duration_and_reason(db_session, tool):
    u = _user(db_session)
    _phase(db_session, u.id, LIVE_SPORTS)
    _session(db_session, u.id, "p1", "Indoor cycling")
    sec = _section(tool(u))
    assert "2026-09-08" in sec and "Indoor cycling" in sec and "35 min" in sec
    assert "unclaimed_session" in sec
    assert 'no slot\'s sports list names "Indoor cycling"' in sec


def test_listing_the_sport_removes_the_section_entirely(db_session, tool):
    """Control: the same session under a list that names it counts, and nothing is printed."""
    u = _user(db_session)
    _phase(db_session, u.id, LIVE_SPORTS + ["Indoor cycling"])
    _session(db_session, u.id, "p1", "Indoor cycling")
    out = tool(u)
    assert HEADER not in out
    assert "load_window:metabolic" in out and "done 1" in out


def test_a_counted_session_is_not_listed_and_an_uncounted_one_beside_it_is(db_session, tool):
    u = _user(db_session)
    _phase(db_session, u.id, LIVE_SPORTS)
    _session(db_session, u.id, "p1", "Biking", day=date(2026, 9, 7))
    _session(db_session, u.id, "p2", "Indoor cycling", day=date(2026, 9, 8))
    sec = _section(tool(u))
    assert "Indoor cycling" in sec and "Biking" not in sec


def test_a_session_with_no_sport_says_so(db_session, tool):
    u = _user(db_session)
    _phase(db_session, u.id, LIVE_SPORTS)
    _session(db_session, u.id, "p1", None)
    sec = _section(tool(u))
    assert "unclaimed_session" in sec and "no sport recorded" in sec


def test_an_untimed_session_is_listed_on_its_session_date(db_session, tool):
    u = _user(db_session)
    _phase(db_session, u.id, LIVE_SPORTS)
    _session(db_session, u.id, "p1", "Running", timed=False, day=date(2026, 9, 8))
    sec = _section(tool(u))
    assert "2026-09-08" in sec and "untimed" in sec and "no start or stop time" in sec


def test_an_untagged_hevy_workout_is_listed_with_its_title(db_session, tool):
    u = _user(db_session)
    _phase(db_session, u.id, LIVE_SPORTS)
    db_session.add(models.HevyWorkout(
        hevy_id="w1", user_id=u.id, title="Session C",
        start_time=datetime(2026, 9, 8, 7, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 8, 8, 0, tzinfo=timezone.utc),
        raw={"id": "w1", "exercises": []}, dedup_flag=False, excluded_at=None))
    db_session.commit()
    sec = _section(tool(u))
    assert 'Hevy "Session C"' in sec and "2026-09-08" in sec and "untagged" in sec


def test_nothing_uncounted_leaves_the_plan_without_the_section(db_session, tool):
    u = _user(db_session)
    _phase(db_session, u.id, LIVE_SPORTS)
    assert HEADER not in tool(u)


def test_no_window_leaves_the_plan_without_the_section(db_session, tool):
    u = _user(db_session)
    _session(db_session, u.id, "p1", "Indoor cycling")
    assert HEADER not in tool(u)


def test_the_section_states_facts_and_no_verdicts(db_session, tool):
    u = _user(db_session)
    _phase(db_session, u.id, LIVE_SPORTS)
    _session(db_session, u.id, "p1", "Indoor cycling")
    _session(db_session, u.id, "p2", None, day=date(2026, 9, 7))
    _session(db_session, u.id, "p3", "Running", timed=False, day=date(2026, 9, 9))
    sec = _section(tool(u)).lower()
    for word in ("on track", "behind", "ahead of", "should", "recommend", "good", "bad", "fix", "wrong"):
        assert word not in sec


# ---- durations read in whole minutes (the 22 Oct Rugby line printed "58.9167 min") ------------------------

def test_a_fractional_duration_is_rounded_to_whole_minutes(db_session, tool):
    u = _user(db_session)
    _phase(db_session, u.id, LIVE_SPORTS)
    _session(db_session, u.id, "p1", "Rugby", minutes=58.9167)
    sec = _section(tool(u))
    assert "59 min" in sec and "58.9167" not in sec


def test_the_rounding_is_to_the_nearest_minute_not_a_floor_or_a_ceiling(db_session, tool):
    u = _user(db_session)
    _phase(db_session, u.id, LIVE_SPORTS)
    _session(db_session, u.id, "p1", "Rugby", minutes=40.4, day=date(2026, 9, 7))
    _session(db_session, u.id, "p2", "Squash", minutes=40.6, day=date(2026, 9, 8))
    sec = _section(tool(u))
    assert "Rugby) · 40 min" in sec and "Squash) · 41 min" in sec


def test_a_session_under_a_minute_is_not_shown_as_zero(db_session, tool):
    u = _user(db_session)
    _phase(db_session, u.id, LIVE_SPORTS)
    _session(db_session, u.id, "p1", "Rugby", minutes=0.5)
    sec = _section(tool(u))
    assert "<1 min" in sec and "0 min" not in sec.replace("<1 min", "")
