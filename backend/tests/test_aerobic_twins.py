"""Q201(b) — a canonical aerobic row names the twins it suppressed (`also_recorded_by`), on the MCP coach reads only.

GATES (operator ruling 11 Oct 2026):
  * the 1 Oct shape: 95 polar_v4 canonical; 93 Garmin HC, 96 Polar Flow HC, 118 Strava HC suppressed
    -> ONE line carrying three {source, source_package} entries, nothing else about the twins
  * a row with no twin carries no field (omitted, never empty-listed)
  * a row with no usable start/stop is canonical by default and carries no field
  * the winner is derived with arbitrate's OWN pair predicate (`_outranks`) — no second definition of "twin"
  * suppression itself is unchanged: non-canonical rows stay filtered, and the shared renderer
    (`format_aerobic_session`, also the in-app chat's pinned block) is byte-identical.
Fixtures are synthetic placeholders.
"""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

import mcp_server
import models
from aerobic_format import format_aerobic_session, format_also_recorded_by
from reads.aerobic_reads import arbitrate, arbitrated_sessions, twins_by_canonical

GARMIN, POLAR_FLOW, STRAVA = "com.garmin.android.apps.connectmobile", "fi.polar.polarflow", "com.strava"
T0 = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
ZONED = (0, 600, 1800, 300, 0)
TODAY = date(2026, 10, 9)


def _row(sid, source, *, start_min=0, minutes=60, hr=None, zones=None, package=None, untimed=False):
    start = T0 + timedelta(minutes=start_min)
    z = zones or (None,) * 5
    return models.AerobicSession(
        id=sid, user_id=1, source=source, session_date=start.date(),
        start_time=None if untimed else start, stop_time=None if untimed else start + timedelta(minutes=minutes),
        duration_minutes=minutes, sport_name="Running", hr_avg=hr, hr_max=hr and hr + 20,
        z1_seconds=z[0], z2_seconds=z[1], z3_seconds=z[2], z4_seconds=z[3], z5_seconds=z[4],
        source_package=package,
    )


def _oct1():
    return [
        _row(93, "health_connect", hr=130, package=GARMIN),
        _row(95, "polar_v4", hr=140, zones=ZONED),
        _row(96, "health_connect", start_min=1, hr=128, package=POLAR_FLOW),
        _row(118, "health_connect", start_min=2, hr=127, package=STRAVA),
    ]


def _entries(line):
    marker = " also_recorded_by="
    assert marker in line, line
    return json.loads(line.split(marker, 1)[1])


# ── the derivation ───────────────────────────────────────────────────────────

def test_oct1_shape_three_twins_on_the_one_canonical():
    rows = arbitrate(_oct1())
    assert [r.id for r in rows if r.canonical] == [95]
    twins = twins_by_canonical(rows)
    assert list(twins) == [95]
    assert [t.id for t in twins[95]] == [93, 96, 118]


def test_no_twin_row_is_absent_from_the_map():
    rows = arbitrate([_row(1, "polar_v4", hr=140, zones=ZONED), _row(2, "polar_v4", start_min=300, hr=140, zones=ZONED)])
    assert twins_by_canonical(rows) == {}


def test_untimed_row_is_canonical_and_has_no_twins():
    rows = arbitrate(_oct1() + [_row(200, "polar_v4", untimed=True)])
    assert next(r for r in rows if r.id == 200).canonical is True
    assert 200 not in twins_by_canonical(rows)


def test_loser_that_lost_only_to_another_loser_attaches_to_the_chain_end():
    # A (0-60) vs C (50-110): overlap 10 min < 50% of 60 -> not a bout. B (25-85) overlaps both >= 50%.
    # B outranks C and A outranks B (richer tier), so C is beaten only by B (a loser): C -> A via B.
    a = _row(1, "polar_v4", start_min=0, hr=140, zones=ZONED)
    b = _row(2, "health_connect", start_min=25, hr=130, package=GARMIN)
    c = _row(3, "health_connect", start_min=50, minutes=60, package=STRAVA)          # tier 0
    rows = arbitrate([a, b, c])
    assert [r.id for r in rows if r.canonical] == [1]
    assert [t.id for t in twins_by_canonical(rows)[1]] == [2, 3]


def test_hevy_mirror_is_never_a_twin():
    rows = _oct1()
    for r in rows:                                   # as arbitrated_sessions marks every row
        r.hevy_mirror = r.id == 93
    arbitrate([r for r in rows if not r.hevy_mirror])
    rows[0].canonical = False
    twins = twins_by_canonical(rows)
    assert [t.id for t in twins[95]] == [96, 118]       # 93 (a mirror) is not listed


def test_twin_pass_agrees_with_arbitrate_on_who_won():
    rows = arbitrate(_oct1())
    for winner_id, losers in twins_by_canonical(rows).items():
        assert next(r for r in rows if r.id == winner_id).canonical
        assert all(not l.canonical for l in losers)


# ── the renderer ─────────────────────────────────────────────────────────────

def test_format_is_identity_only():
    twins = twins_by_canonical(arbitrate(_oct1()))[95]
    out = format_also_recorded_by(twins)
    assert _entries("x" + out) == [
        {"source": "health_connect", "source_package": GARMIN},
        {"source": "health_connect", "source_package": POLAR_FLOW},
        {"source": "health_connect", "source_package": STRAVA},
    ]
    assert all(set(e) == {"source", "source_package"} for e in _entries("x" + out))


@pytest.mark.parametrize("empty", [None, [], ()])
def test_no_twins_renders_nothing(empty):
    assert format_also_recorded_by(empty) == ""


def test_shared_renderer_does_not_carry_the_field():
    rows = arbitrate(_oct1())
    assert "also_recorded_by" not in format_aerobic_session(next(r for r in rows if r.id == 95))


# ── the coach reads ──────────────────────────────────────────────────────────

@pytest.fixture
def coach(db_session, monkeypatch):
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_local_day", lambda *a, **k: TODAY)
    monkeypatch.setattr(mcp_server, "_aest_wake_day", lambda *a, **k: TODAY)   # get_training_sessions anchors its window here, not on _local_day
    u = models.User(email="tw@example.com", hashed_password="x")
    db_session.add(u); db_session.commit(); db_session.refresh(u)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: u.id)
    for r in _oct1() + [_row(300, "polar_v4", start_min=24 * 60, hr=120, zones=ZONED),
                        _row(301, "polar_v4", untimed=True, start_min=48 * 60)]:
        r.id = None
        r.user_id = u.id
        r.source_session_id = f"s{len(db_session.new)}-{r.start_time}-{r.source}-{r.source_package}"
        db_session.add(r)
    db_session.commit()
    return u


@pytest.mark.parametrize("read", [lambda: mcp_server.get_training_sessions(days=30),
                                  lambda: mcp_server.get_recent_sessions(days=30)])
def test_both_coach_reads_carry_the_field_on_the_canonical_line_only(coach, read):
    out = read()
    twin_lines = [l for l in out.split("\n") if "also_recorded_by=" in l]
    assert len(twin_lines) == 1                                   # the 1 Oct canonical, no other row
    assert "[polar_v4]" in twin_lines[0] and "[health_connect]" not in twin_lines[0]
    assert {e["source_package"] for e in _entries(twin_lines[0])} == {GARMIN, POLAR_FLOW, STRAVA}
    assert "[health_connect]" not in out                          # suppression itself unchanged: twins stay filtered
    for l in out.split("\n"):
        if l.startswith("2026-10-02") or "dist=—" in l and "also_recorded_by" not in l:
            assert "also_recorded_by" not in l                    # no-twin and untimed rows: field absent
