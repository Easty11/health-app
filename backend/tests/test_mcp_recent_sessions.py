"""The `get_recent_sessions` MCP tool — a read-only formatter over `arbitrated_sessions`,
`counted_workouts`, the shared `overlaps_workout` predicate and the #359 freshness read.

GATES (from the brief):
  G1  a Polar strength session plus its matching Hevy workout is ONE line with the sets attached
      under it, not two lines.
  G2  a Hevy workout with no session is marked `Hevy only`; a strength-named session with no
      workout is marked `HR only`.
  G3  the 0-minute junk row: what `arbitrated_sessions` does with it today is pinned here (it is
      canonical and passes through as a line); NO filter is added.
  G4  newest first; the freshness footer reads the #359 pipes.
  G5  the linkage is the shared predicate, not a rule of the tool's own: a session that merely
      brushes a workout (below HEVY_MIRROR_OVERLAP_FRACTION of its own duration) is not linked.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest

import mcp_server
import models
from reads.aerobic_reads import arbitrated_sessions
from sport_classes import is_strength_sport

TODAY = date(2026, 10, 9)                      # Friday
D = lambda day, hh, mm=0: datetime(2026, 10, day, hh, mm, tzinfo=timezone.utc)   # noqa: E731
# 2 Oct 00:00 UTC = 10:00 Brisbane, the day the operator saw the doubled gym session.
GYM_START, GYM_STOP = D(2, 0), D(2, 1, 35)     # 95 minutes


def _user(db):
    u = models.User(email="rs@example.com", hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _aero(db, uid, sid, *, start, stop, sport, source="polar_v4", dur=None, hr=(120, 150), z=(0, 600, 1800, 600, 0)):
    s = models.AerobicSession(
        user_id=uid, source=source, source_session_id=sid, session_date=start.date() if start else TODAY,
        start_time=start, stop_time=stop, sport_name=sport,
        duration_minutes=dur if dur is not None else ((stop - start).total_seconds() / 60 if start and stop else None),
        hr_avg=hr[0], hr_max=hr[1], z1_seconds=z[0], z2_seconds=z[1], z3_seconds=z[2], z4_seconds=z[3], z5_seconds=z[4])
    db.add(s); db.commit(); db.refresh(s)
    return s


def _hevy(db, uid, hid, start, stop, title, exercises, **kw):
    db.add(models.HevyWorkout(hevy_id=hid, user_id=uid, start_time=start, end_time=stop, title=title,
                              raw={"id": hid, "title": title, "exercises": exercises}, **kw))
    db.commit()


def _ex(name, *sets):
    return {"title": name, "sets": [{"weight_kg": w, "reps": r, "type": "normal"} for w, r in sets]}


@pytest.fixture
def call(db_session, monkeypatch):
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_local_day", lambda *a, **k: TODAY)
    u = _user(db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: u.id)
    return lambda **kw: (u, mcp_server.get_recent_sessions(**kw))


def _body(out):
    return out.split("\n\n", 1)[1].split("\n")


# --------------------------------------------------------------------------- #
# G1 — one line, sets attached                                                 #
# --------------------------------------------------------------------------- #

def test_g1_a_polar_strength_session_and_its_hevy_workout_are_one_line_with_sets(db_session, call):
    u, _ = call()
    _aero(db_session, u.id, "p1", start=GYM_START, stop=GYM_STOP, sport="Strength training")
    _hevy(db_session, u.id, "h1", D(2, 0, 2), D(2, 1, 33), "Session C",
          [_ex("Back Squat", (60, 5), (100, 5)), _ex("Row", (50, 8))])
    _, out = call(days=14)
    lines = _body(out)
    heads = [l for l in lines if l and not l.startswith(("  ", "Recent", "Health Connect"))]
    assert len(heads) == 1 and heads[0].startswith("2026-10-02 [polar_v4] Strength training: 95 min")
    assert "HR only" not in out and "Hevy only" not in out
    detail = lines[lines.index(heads[0]) + 1]
    assert detail.startswith("  ↳ 2 exercises · ") and "[hevy] Session C: " in detail
    assert "Back Squat ×2 (top 100kg × 5)" in detail and "Row ×1 (top 50kg × 8)" in detail


# --------------------------------------------------------------------------- #
# G2 — Hevy only, HR only                                                      #
# --------------------------------------------------------------------------- #

def test_g2_hevy_only_and_hr_only_are_marked(db_session, call):
    u, _ = call()
    _hevy(db_session, u.id, "h2", D(6, 0), D(6, 1), "Upper", [_ex("Bench", (80, 5))])
    _aero(db_session, u.id, "p2", start=D(7, 0), stop=D(7, 1), sport="Strength training")
    _aero(db_session, u.id, "p3", start=D(8, 0), stop=D(8, 1), sport="Running")          # not strength: no mark
    _, out = call(days=14)
    assert "2026-10-06 [hevy] Upper: 60 min — Hevy only" in out
    assert any(l.startswith("2026-10-07 [polar_v4] Strength training:") and l.endswith("— HR only (no Hevy workout matches)")
               for l in _body(out))
    running = next(l for l in _body(out) if "Running" in l)
    assert "HR only" not in running and "Hevy only" not in running


def test_g2_an_excluded_workout_is_absent_and_an_unadjudicated_pair_is_listed_not_counted(db_session, call):
    u, _ = call()
    from datetime import datetime as _dt
    _hevy(db_session, u.id, "gone", D(5, 0), D(5, 1), "Deleted", [_ex("X", (1, 1))],
          excluded_at=_dt(2026, 10, 6, tzinfo=timezone.utc), exclusion_reason="deleted_in_hevy_never_performed")
    _hevy(db_session, u.id, "dupA", D(6, 0), D(6, 1), "Pair", [_ex("Y", (2, 2))], dedup_flag=True, dedup_partner_ids=["dupB"])
    _hevy(db_session, u.id, "dupB", D(6, 2), D(6, 3), "Pair", [_ex("Y", (2, 2))], dedup_flag=True, dedup_partner_ids=["dupA"])
    _, out = call(days=14)
    assert "Deleted" not in out
    assert out.count("Hevy only, unadjudicated duplicate (not counted)") == 2


# --------------------------------------------------------------------------- #
# G3 — the 0-minute junk row: pinned, not filtered                             #
# --------------------------------------------------------------------------- #

def test_g3_a_zero_minute_row_is_canonical_in_the_door_and_passes_through(db_session, call):
    u, _ = call()
    junk = _aero(db_session, u.id, "junk", start=D(8, 3), stop=D(8, 3), sport="Other Workout",
                 dur=0, hr=(None, None), z=(None,) * 5)
    rows = arbitrated_sessions(u.id, db_session, since=date(2026, 10, 1))
    assert [(r.id, r.canonical) for r in rows if r.id == junk.id] == [(junk.id, True)]   # today's door behaviour
    _, out = call(days=14)
    assert any(l.startswith("2026-10-08 [polar_v4] Other Workout: — HR=—/—") for l in _body(out))


# --------------------------------------------------------------------------- #
# G4 — order and footer                                                        #
# --------------------------------------------------------------------------- #

def test_g4_newest_first_across_both_kinds(db_session, call):
    u, _ = call()
    _aero(db_session, u.id, "old", start=D(4, 1), stop=D(4, 2), sport="Running")
    _hevy(db_session, u.id, "mid", D(6, 1), D(6, 2), "Mid", [_ex("Z", (1, 1))])
    _aero(db_session, u.id, "new", start=D(8, 1), stop=D(8, 2), sport="Cycling")
    _, out = call(days=14)
    dated = [l[:10] for l in _body(out) if l[:2] == "20"]
    assert dated == ["2026-10-08", "2026-10-06", "2026-10-04"]


def test_g4_the_footer_reads_the_359_pipes(db_session, call):
    u, _ = call()
    db_session.add(models.HealthConnectSyncEvent(user_id=u.id, synced_at=datetime.now(timezone.utc) - timedelta(hours=5)))
    db_session.commit()
    _, out = call()
    assert out.rstrip().endswith("Health Connect delivered 5 h ago · Polar never")


def test_g4_a_late_health_connect_delivery_is_flagged_amber(db_session, call):
    u, _ = call()
    db_session.add(models.HealthConnectSyncEvent(user_id=u.id, synced_at=datetime.now(timezone.utc) - timedelta(hours=20)))
    db_session.commit()
    _, out = call()
    assert "Health Connect delivered 20 h ago (AMBER, older than 13 h)" in out


def test_an_empty_window_still_says_so_and_carries_the_footer(call):
    _, out = call()
    assert "No sessions or Hevy workouts in the last 7 days." in out and "Health Connect delivered never" in out


# --------------------------------------------------------------------------- #
# G5 — the linkage is the shared predicate                                     #
# --------------------------------------------------------------------------- #

def test_g5_a_brush_of_a_workout_is_not_a_link(db_session, call):
    u, _ = call()
    # a 60-minute erg session of which only 10 minutes lie inside the Hevy bout: 0.17 of its own duration
    _aero(db_session, u.id, "erg", start=D(6, 0), stop=D(6, 1), sport="Rowing")
    _hevy(db_session, u.id, "late", D(6, 0, 50), D(6, 2), "Late", [_ex("W", (10, 10))])
    _, out = call(days=14)
    lines = _body(out)
    erg = lines.index(next(l for l in lines if "[polar_v4] Rowing" in l))
    assert not lines[erg + 1].startswith("  ↳")                                  # nothing attached to the erg session
    assert any(l.startswith("2026-10-06 [hevy] Late:") and l.endswith("Hevy only") for l in lines)


def test_two_segments_inside_one_workout_are_both_linked_in_start_order(db_session, call):
    """A gym day recorded as a warm-up segment and a work segment, both inside one Hevy workout (Q206).
    Both are part of the workout, listed in start-time order with the workout's detail once beneath
    them; neither is left "HR only". The later segment is inserted first, so row order is not start order."""
    u, _ = call()
    _aero(db_session, u.id, "work", start=D(2, 0, 50), stop=D(2, 1, 35), sport="Circuit training")
    _aero(db_session, u.id, "warm", start=D(2, 0), stop=D(2, 0, 45), sport="Cross-trainer")
    _hevy(db_session, u.id, "h", D(2, 0), D(2, 1, 35), "S", [_ex("Q", (1, 1))])
    _, out = call(days=14)
    lines = _body(out)
    warm = next(i for i, l in enumerate(lines) if "Cross-trainer" in l)
    work = next(i for i, l in enumerate(lines) if "Circuit training" in l)
    assert (warm, work) == (work - 1, warm + 1)                                     # adjacent, warm-up first
    assert lines[work + 1].startswith("  ↳ 1 exercise · ") and "[hevy] S: " in lines[work + 1]
    assert out.count("  ↳") == 1 and "Hevy only" not in out and "HR only" not in out


def test_two_strength_named_segments_in_one_workout_are_not_hr_only(db_session, call):
    u, _ = call()
    _aero(db_session, u.id, "a", start=D(2, 0), stop=D(2, 0, 45), sport="Strength training")
    _aero(db_session, u.id, "b", start=D(2, 0, 50), stop=D(2, 1, 35), sport="Strength training")
    _hevy(db_session, u.id, "h", D(2, 0), D(2, 1, 35), "S", [_ex("Q", (1, 1))])
    _, out = call(days=14)
    assert out.count("  ↳") == 1 and "Hevy only" not in out and "HR only" not in out


def test_a_segment_below_the_overlap_threshold_stays_hr_only(db_session, call):
    u, _ = call()
    _aero(db_session, u.id, "in", start=D(2, 0), stop=D(2, 0, 45), sport="Cross-trainer")
    # 60 minutes of which 15 lie inside the workout: 0.25 of its own duration, below HEVY_MIRROR_OVERLAP_FRACTION
    _aero(db_session, u.id, "out", start=D(2, 1, 20), stop=D(2, 2, 20), sport="Strength training")
    _hevy(db_session, u.id, "h", D(2, 0), D(2, 1, 35), "S", [_ex("Q", (1, 1))])
    _, out = call(days=14)
    lines = _body(out)
    late = next(l for l in lines if "Strength training" in l)
    assert late.endswith("— HR only (no Hevy workout matches)")
    early = lines.index(next(l for l in lines if "Cross-trainer" in l))
    assert lines[early + 1].startswith("  ↳") and out.count("  ↳") == 1             # the workout stays with the segment inside it


def test_a_session_overlapping_only_an_excluded_workout_is_unlinked_as_in_414(db_session, call):
    u, _ = call()
    _aero(db_session, u.id, "x", start=D(2, 0), stop=D(2, 1), sport="Strength training")
    _hevy(db_session, u.id, "gone", D(2, 0), D(2, 1), "Deleted", [_ex("Q", (1, 1))],
          excluded_at=datetime(2026, 10, 3, tzinfo=timezone.utc), exclusion_reason="deleted_in_hevy_never_performed")
    u_, out = call(days=14)
    assert "HR only (no Hevy workout matches)" in out and "  ↳" not in out and "Deleted" not in out
    sessions = [s for s in arbitrated_sessions(u.id, db_session, since=date(2026, 10, 1)) if s.canonical]
    assert mcp_server._gym_trace_marks(db_session, u.id, sessions) == {}            # the #414 marker agrees


def test_the_links_are_the_414_marks_session_for_session(db_session, call):
    u, _ = call()
    _aero(db_session, u.id, "a", start=D(2, 0), stop=D(2, 0, 45), sport="Cross-trainer")
    _aero(db_session, u.id, "b", start=D(2, 0, 50), stop=D(2, 1, 35), sport="Circuit training")
    _aero(db_session, u.id, "c", start=D(4, 0), stop=D(4, 1), sport="Running")
    _hevy(db_session, u.id, "h", D(2, 0), D(2, 1, 35), "S", [_ex("Q", (1, 1))])
    _, out = call(days=14)
    sessions = [s for s in arbitrated_sessions(u.id, db_session, since=date(2026, 10, 1)) if s.canonical]
    marked = {s.sport_name for s in sessions if s.id in mcp_server._gym_trace_marks(db_session, u.id, sessions)}
    detailed = {l.split("] ", 1)[1].split(":")[0] for l in _body(out) if l.startswith("2026-10-02 [polar_v4] ")}
    assert marked == detailed == {"Cross-trainer", "Circuit training"} and "Running" not in marked
    assert out.count("  ↳") == 1


def test_a_single_segment_day_renders_as_before(db_session, call):
    """One segment, one workout: the session line, then the workout detail, exactly the #408 shape."""
    from aerobic_format import format_aerobic_session
    u, _ = call()
    s = _aero(db_session, u.id, "only", start=GYM_START, stop=GYM_STOP, sport="Strength training")
    _hevy(db_session, u.id, "h1", D(2, 0, 2), D(2, 1, 33), "Session C", [_ex("Row", (50, 8))])
    _, out = call(days=14)
    w = db_session.query(models.HevyWorkout).filter_by(hevy_id="h1").one()
    lines = out.split("\n")
    i = lines.index(format_aerobic_session(s))
    assert lines[i:i + 2] == [format_aerobic_session(s), mcp_server._hevy_detail(w)]
    assert lines[i - 1].startswith("Recent sessions") and lines[i + 2] == ""            # nothing else between header and footer


def test_strength_names_are_the_exact_device_strings():
    for s in ("Strength training", "Strength Training", "WEIGHTLIFTING", "Weightlifting"):
        assert is_strength_sport(s)
    for s in (None, "", "Strength", "Circuit training", "Other Workout"):
        assert not is_strength_sport(s)


def test_pilates_is_deliberately_not_strength_and_carries_no_hr_only_mark(db_session, call):
    """Ruled 10 Oct 2026: the operator logs Pilates as strength work but never logs sets, so "HR only"
    would read as missing data. A Pilates session with no Hevy workout is a plain line."""
    for name in ("Pilates", "pilates", "PILATES"):
        assert not is_strength_sport(name)
    u, _ = call()
    _aero(db_session, u.id, "pil", start=D(8, 0), stop=D(8, 1), sport="Pilates", source="health_connect")
    _, out = call(days=14)
    line = next(l for l in _body(out) if "Pilates" in l)
    assert line.startswith("2026-10-08 [health_connect] Pilates: 60 min")
    assert "HR only" not in out and "Hevy only" not in out


# --------------------------------------------------------------------------- #
# The other two tools are unchanged apart from a docstring pointer             #
# --------------------------------------------------------------------------- #

def test_the_older_tools_point_to_the_combined_view_and_the_new_one_takes_days():
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert "get_recent_sessions" in tools["get_training_sessions"].description
    assert "get_recent_sessions" in tools["get_hevy_workouts"].description
    assert set(tools["get_recent_sessions"].inputSchema["properties"]) == {"days"}
    assert tools["get_recent_sessions"].inputSchema["properties"]["days"]["default"] == 7
