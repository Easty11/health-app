"""The `get_training_plan` MCP tool — a read-only text formatter over `current_state`.

GATES (from the brief):
  G1  synthetic data with an open phase, two hard items, one flexible item and a plan of record:
      the output names every section; the flexible item is listed on EVERY candidate day (never
      "placed"); scheduled / quota / done / excess / unplaced match `plan_week()` EXACTLY (the
      same function, asserted by identity of the numbers, not by a copy of the arithmetic).
  G2  baseline: no open phase and no template gives no week section and no error, and says so.
  G3  the STALE flag is `context_builder.plan_of_record_stale`, not a second derivation.
  G4  no verdict words anywhere in the output.

Seeded through the ORM (as `test_week_plan` does) so the tool's reads run over real rows.
"""
import asyncio
import re
from datetime import date

import pytest

import mcp_server
import models
from context_builder import plan_of_record_stale
from engine import week_plan as week_plan_mod

MONDAY = date(2026, 9, 7)
TODAY = date(2026, 9, 9)          # Wednesday, inside leg A [09-07, 09-13]


def _user(db, email="plan@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _phase(db, uid, *, review_on=None, folders=None):
    micro = {"sub_cycle_days": 7, "sub_cycles": [
        {"label": "A", "slots": [{"capacity": "stability", "sessions_per_cycle": 2, "minutes": 30}]},
        {"label": "B", "slots": [{"capacity": "stability", "sessions_per_cycle": 1, "minutes": 30}]},
    ]}
    db.add(models.TrainingPhase(
        user_id=uid, label="base", intent="rebuild the base", probe_posture="held",
        capacities=["stability"], microcycle=micro, entered_on=MONDAY, review_on=review_on,
        asserted_by="user", asserted_on=MONDAY, source="api"))
    if folders is not None:
        db.add(models.UserKnowledgeEntry(user_id=uid, type="preference", key="phase_folders",
                                         value=folders, source="api", active=True))
    db.commit()


def _sched(db, uid, key, activity, days, *, hard, satisfies=None, expected_load="moderate",
           same_day_training=False, sessions_per_week=None, season_end=None, time_range=None):
    value = {"activity": activity, "days": days, "hard": hard, "expected_load": expected_load,
             "time_of_day": "evening", "same_day_training": same_day_training,
             "duration_weeks": None, "season_end": season_end}
    if satisfies is not None:
        value["satisfies"] = satisfies
    if sessions_per_week is not None:
        value["sessions_per_week"] = sessions_per_week
    if time_range is not None:
        value["time_range"] = time_range
    db.add(models.UserKnowledgeEntry(user_id=uid, type="schedule_item", key=key, value=value,
                                     source="chat", active=True))
    db.commit()


def _plan(db, uid, macro="## Offseason\nBase first, then build.", revised_on="2026-09-01"):
    db.add(models.UserKnowledgeEntry(
        user_id=uid, type="training_plan", key="training_plan", active=True, source="api",
        value={"macro": macro, "revised_on": revised_on, "revised_by": "operator"}))
    db.commit()


def _seed_full(db):
    u = _user(db)
    _plan(db, u.id)
    _phase(db, u.id, review_on=date(2026, 12, 1), folders={"base": 42})
    _sched(db, u.id, "work", "Work", ["monday", "tuesday"], hard=True, expected_load="heavy",
           time_range="07:00-15:00", season_end="2026-12-20")
    _sched(db, u.id, "rugby", "Rugby training", ["wednesday"], hard=True, same_day_training=True)
    _sched(db, u.id, "gym", "Gym", ["monday", "wednesday", "friday"], hard=False,
           satisfies={"capacity": "stability"}, sessions_per_week=2)
    return u


@pytest.fixture
def tool(db_session, monkeypatch):
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_local_day", lambda *a, **k: TODAY)

    def call(user):
        monkeypatch.setattr(mcp_server, "_current_user_id", lambda: user.id)
        return mcp_server.get_training_plan()
    return call


# --------------------------------------------------------------------------- #
# G1 — every section, and the numbers are plan_week's                          #
# --------------------------------------------------------------------------- #

def test_g1_names_every_section_and_carries_the_stores(db_session, tool):
    u = _seed_full(db_session)
    out = tool(u)
    assert out.startswith("as_of: ")
    for heading in ("== Plan of record ==", "== Current phase ==", "== This week ==", "== Schedule items =="):
        assert heading in out
    assert "Last revised 2026-09-01, by operator" in out
    assert "## Offseason\nBase first, then build." in out                      # macro verbatim
    assert "base (entered 2026-09-07)" in out and "intent: rebuild the base" in out
    assert "review on: 2026-12-01" in out and "review due" not in out
    assert "probe posture: held" in out and "capacities: stability" in out
    assert "Hevy folder (phase_folders): 42" in out
    assert "microcycle: 7-day sub-cycles, 2 in rotation" in out
    assert "1/2 A <- today" in out and "2/2 B\n" in out and "<- today" not in out.split("2/2 B")[1].split("\n")[0]
    assert "today is in leg A (2026-09-07 -> 2026-09-13)" in out
    assert "- Work · Mon/Tue · hard · evening 07:00-15:00 · expected_load heavy · season end 2026-12-20" in out
    assert "- Gym · Mon/Wed/Fri, 2/wk · flexible · evening · expected_load moderate · satisfies capacity:stability" in out


def _week_days(out):
    """{date: [lines under that day's header]} for the This week section."""
    week = out.split("== This week ==")[1].split("== Schedule items ==")[0].split("\n")
    days, cur = {}, None
    for line in week:
        m = re.match(r"^[A-Z][a-z]+day (\d{4}-\d{2}-\d{2})", line)
        if m:
            cur = m.group(1)
            days[cur] = []
        elif cur and line.startswith("  "):
            days[cur].append(line)
        else:
            cur = None
    return days


def test_g1_the_flexible_item_is_on_every_candidate_day_and_never_placed(db_session, tool):
    u = _seed_full(db_session)
    out = tool(u)
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    days = _week_days(out)
    assert len(days) == 7
    for d in plan["days"]:
        flex = [l for l in days[d["date"]] if l.startswith("  flexible")]
        assert len(flex) == len(d["flexible"])                     # same days, same count, as plan_week
    # Gym is a candidate on Mon, Wed and Fri only, and is listed on all three, not on one "placed" day
    assert {dt for dt, ls in days.items() if any("Gym" in l for l in ls)} == {
        "2026-09-07", "2026-09-09", "2026-09-11"}
    assert "placed" not in out.lower().replace("unplaced", "")


def test_g1_quota_done_and_the_rest_are_plan_weeks_exactly(db_session, tool):
    u = _seed_full(db_session)
    out = tool(u)
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    keys = plan["keys"]
    assert keys, "the fixture must yield at least one slot key"
    for k in keys:
        assert (f"  {k['kind']}:{k['key']} - scheduled {k['scheduled']} / quota {k['quota']} / done {k['done']}"
                f" - excess {k['excess']}, unplaced {k['unplaced']}") in out
    # the fixture is not degenerate: scheduled 2 against quota 2, nothing counted yet
    k = keys[0]
    assert (k["scheduled"], k["quota"], k["done"]) == (2, 2, 0)
    assert "needs_planning: no" in out
    # hard items by day, from plan_week's own days
    wed = next(d for d in plan["days"] if d["weekday"] == "wednesday")
    assert wed["hard"][0]["activity"] == "Rugby training"
    assert "Wednesday 2026-09-09" in out and "hard: Rugby training (moderate, same-day training OK" in out
    # Tue is the day after a heavy hard item (Mon): the caution flag is carried, and Mon/Tue are blocked
    tue = next(d for d in plan["days"] if d["weekday"] == "tuesday")
    assert tue["caution"] == "day after heavy"
    assert "Tuesday 2026-09-08 - UNAVAILABLE" in out and "caution: day after heavy" in out


def test_g1_needs_planning_is_carried_when_plan_week_says_so(db_session, tool):
    u = _user(db_session)
    _phase(db_session, u.id)
    out = tool(u)                                   # a quota, nothing linked to it
    assert week_plan_mod.plan_week(db_session, u.id, TODAY)["needs_planning"] is True
    assert "needs_planning: yes" in out


def test_g1_review_due_is_stated_once_the_review_date_has_passed(db_session, tool):
    u = _user(db_session)
    _phase(db_session, u.id, review_on=date(2026, 9, 8))
    assert "review on: 2026-09-08 - review due" in tool(u)


# --------------------------------------------------------------------------- #
# G2 — baseline                                                                #
# --------------------------------------------------------------------------- #

def test_g2_baseline_no_phase_gives_no_week_and_no_error(db_session, tool):
    u = _user(db_session)
    _plan(db_session, u.id)
    _sched(db_session, u.id, "gym", "Gym", ["monday"], hard=False)
    out = tool(u)
    assert "No open training phase (baseline)." in out
    assert "== This week ==" not in out
    assert "== Plan of record ==" in out and "== Schedule items ==" in out
    assert "- Gym · Mon · flexible" in out


def test_g2_nothing_at_all_is_still_a_plain_answer(db_session, tool):
    out = tool(_user(db_session, "empty@example.com"))
    assert out.endswith("== Current phase ==\nNo open training phase (baseline).")


# --------------------------------------------------------------------------- #
# G3 — STALE is the shared definition                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("revised_on,expect_stale", [("2026-09-01", True), ("2026-09-08", False)])
def test_g3_stale_flag_follows_plan_of_record_stale(db_session, tool, revised_on, expect_stale):
    u = _user(db_session)
    _plan(db_session, u.id, revised_on=revised_on)
    _phase(db_session, u.id, review_on=date(2026, 9, 8))       # passed as of TODAY
    out = tool(u)
    phase = {"review_due": True, "review_on": "2026-09-08"}
    assert plan_of_record_stale({"revised_on": revised_on}, phase) is expect_stale
    assert ("STALE: last revised" in out) is expect_stale


# --------------------------------------------------------------------------- #
# Failure is loud, the tool's shape, and no verdicts                           #
# --------------------------------------------------------------------------- #

def test_a_failed_week_plan_is_named_not_dropped(db_session, tool, monkeypatch):
    u = _seed_full(db_session)
    def boom(*a, **k):
        raise RuntimeError("synthetic")
    monkeypatch.setattr(week_plan_mod, "plan_week", boom)
    out = tool(u)
    assert "The week plan could not be read (see the server log)." in out
    assert "== Plan of record ==" in out and "== Schedule items ==" in out


def test_the_tool_takes_no_horizon_parameter():
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    # plan_week reads the resolver's current window and has no horizon argument, so the brief's
    # optional `days_ahead` is omitted rather than faked by slicing the render.
    assert tools["get_training_plan"].inputSchema["properties"] == {}


def test_no_verdict_words(db_session, tool):
    out = tool(_seed_full(db_session)).lower()
    for word in ("on track", "behind", "ahead of", "should", "recommend", "good", "bad"):
        assert word not in out
