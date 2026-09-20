"""Week planner — schedule checked against the phase, hard items first (#316).

GATES (from the brief):
  G1  `plan_week` fixtures — the operator's live state: quota stability ×2, soft gym Mon/Wed/Fri
      LINKED to stability → scheduled 3, excess 1; a hard item on Sat → Sat unavailable;
      `same_day_training: true` → available; `expected_load: "none"` never constrains; a new phase
      with no linked items → needs_planning. §18 mutation: `excess` computed from `done` instead of
      `scheduled` — the Mon/Wed/Fri fixture (done 0, scheduled 3, quota 2) would read excess 0.
  G2  parity — `done` in `week_plan.keys[]` equals `resolve()`'s, by assertion.
  G3  render — day-view (hard → availability → caution) precedes the #312 per-key block; the week
      block is gated on `week_plan` (absent → the #312 tests stay byte-identical); a null window
      renders no week block; `_section_schedule` folds its next-7-days hard lines when suppressed.
  G4  failure isolation — `plan_week` raising must not take the chat context down.
  Freshness (ruling 4): synced-today + zero sessions this window → NO incomplete flag; a sync that
      predates the window start → incomplete when a device-evidenced slot exists.

Negative controls: the §18 mutation pins excess to `scheduled`, not `done`; the caution test pairs a
heavy day with a non-heavy day so "day after heavy" is not simply "every day".
"""
from datetime import date, datetime, timezone

import pytest

import models
from engine import resolver as resolver_mod
from engine import week_plan as week_plan_mod


MONDAY = date(2026, 9, 7)     # a Monday; phase entered_on anchor
TODAY = date(2026, 9, 9)      # Wednesday inside leg A [09-07, 09-13]


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #

def _user(db, email="wk@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _phase(db, uid, microcycle, entered_on=MONDAY):
    ph = models.TrainingPhase(
        user_id=uid, label="base", probe_posture="held", microcycle=microcycle,
        entered_on=entered_on, asserted_by="user", asserted_on=entered_on, source="api",
    )
    db.add(ph)
    db.commit()
    db.refresh(ph)
    return ph


def _stability_micro(quota=2):
    return {"sub_cycle_days": 7, "sub_cycles": [
        {"label": "A", "slots": [
            {"capacity": "stability", "sessions_per_cycle": quota, "minutes": 30}]}]}


def _sched(db, uid, key, activity, days, *, hard=False, satisfies=None,
           expected_load="moderate", same_day_training=False, sessions_per_week=None):
    value = {
        "activity": activity, "days": days, "hard": hard,
        "expected_load": expected_load, "time_of_day": "evening",
        "same_day_training": same_day_training, "duration_weeks": None, "season_end": None,
    }
    if satisfies is not None:
        value["satisfies"] = satisfies
    if sessions_per_week is not None:
        value["sessions_per_week"] = sessions_per_week
    db.add(models.UserKnowledgeEntry(
        user_id=uid, type="schedule_item", key=key, value=value, source="chat", active=True))
    db.commit()


def _load_context(db, uid, key, description, expires_at=None):
    db.add(models.UserKnowledgeEntry(
        user_id=uid, type="load_context", key=key,
        value={"description": description, "expires_at": expires_at},
        source="chat", active=True))
    db.commit()


def _hc_sync(db, uid, on_date, synced_at):
    row = models.HealthConnectSync(user_id=uid, date=on_date, steps=1000)
    db.add(row)
    db.flush()
    row.synced_at = synced_at
    db.commit()


def _day(plan, weekday):
    return next(d for d in plan["days"] if d["weekday"] == weekday)


def _key(plan, key):
    return next(k for k in plan["keys"] if k["key"] == key)


# --------------------------------------------------------------------------- #
# G1 — the operator's live state                                               #
# --------------------------------------------------------------------------- #

def test_g1_gym_linked_thrice_reads_scheduled_3_excess_1(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro(quota=2))
    _sched(db_session, u.id, "gym", "gym", ["monday", "wednesday", "friday"],
           satisfies={"capacity": "stability"})
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    row = _key(plan, "stability")
    assert row["scheduled"] == 3 and row["quota"] == 2
    assert row["excess"] == 1 and row["unplaced"] == 0
    # §18: excess is from SCHEDULED, not done. done is 0 here (no workouts) → a done-based excess
    # would be max(0, 0 - 2) = 0. The value 1 can only come from scheduled 3 − quota 2.
    assert row["done"] == 0
    assert row["excess"] != max(0, row["done"] - row["quota"])


def test_g1_hard_item_makes_its_day_unavailable(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro())
    _sched(db_session, u.id, "carnival", "carnival", ["saturday"], hard=True, expected_load="heavy")
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    assert _day(plan, "saturday")["available"] is False
    assert _day(plan, "tuesday")["available"] is True   # no hard item → available


def test_g1_same_day_training_keeps_the_day_available(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro())
    _sched(db_session, u.id, "work", "work", ["monday"], hard=True,
           expected_load="moderate", same_day_training=True)
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    mon = _day(plan, "monday")
    assert mon["available"] is True and mon["hard"][0]["same_day_training"] is True


def test_g1_expected_load_none_never_constrains(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro())
    _sched(db_session, u.id, "recovery", "active recovery", ["sunday"], hard=True,
           expected_load="none")
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    assert _day(plan, "sunday")["available"] is True   # a zero-load hard item does not block


def test_g1_caution_day_after_heavy(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro())
    _sched(db_session, u.id, "carnival", "carnival", ["saturday"], hard=True, expected_load="heavy")
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    assert _day(plan, "sunday")["caution"] == "day after heavy"     # day AFTER heavy
    assert _day(plan, "friday")["caution"] is None                  # day before is not cautioned


def test_g1_new_phase_no_linked_items_needs_planning(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro())
    # only an UNLINKED soft item → no key is placed against
    _sched(db_session, u.id, "walk", "walk", ["tuesday"])
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    assert plan["needs_planning"] is True
    assert plan["unlinked_soft"] == ["walk"]


def test_g1_needs_planning_false_once_a_slot_is_placed(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro())
    _sched(db_session, u.id, "gym", "gym", ["monday"], satisfies={"capacity": "stability"})
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    assert plan["needs_planning"] is False


# --------------------------------------------------------------------------- #
# G2 — done parity with resolve()                                              #
# --------------------------------------------------------------------------- #

def test_g2_done_equals_resolve(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro())
    _sched(db_session, u.id, "gym", "gym", ["monday", "wednesday", "friday"],
           satisfies={"capacity": "stability"})
    pos = resolver_mod.resolve(db_session, u.id, today=TODAY)
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    by_key_pos = {s[s["kind"]]: s["done"] for s in pos["slots"]}
    for row in plan["keys"]:
        assert row["done"] == by_key_pos[row["key"]]


def test_g2_null_window_returns_none(db_session):
    u = _user(db_session)   # no phase, no template
    assert week_plan_mod.plan_week(db_session, u.id, TODAY) is None


# --------------------------------------------------------------------------- #
# G1b — freshness (ruling 4)                                                   #
# --------------------------------------------------------------------------- #

def test_freshness_synced_today_zero_sessions_no_incomplete_flag(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro())
    _hc_sync(db_session, u.id, TODAY, datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc))
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    fr = plan["freshness"]
    assert fr["hc_stale"] is False          # synced today (in window) → not stale
    assert fr["polar_pull_ts_exists"] is False


def test_freshness_sync_before_window_is_stale(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro())
    # last synced 2026-09-01, before the window start 2026-09-07
    _hc_sync(db_session, u.id, date(2026, 9, 1), datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc))
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    assert plan["freshness"]["hc_stale"] is True


def test_freshness_never_synced_is_stale(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro())
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    assert plan["freshness"]["hc_stale"] is True
    assert plan["freshness"]["hc_synced_at"] is None


# --------------------------------------------------------------------------- #
# One-off notes (ruling 3)                                                     #
# --------------------------------------------------------------------------- #

def test_one_off_load_context_surfaced_beside_the_week(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro())
    _load_context(db_session, u.id, "carnival", "Athletics carnival 19–20 Sep", expires_at="2026-09-21")
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    assert plan["one_off_notes"] == [
        {"description": "Athletics carnival 19–20 Sep", "expires_at": "2026-09-21"}]


# --------------------------------------------------------------------------- #
# G3 — render                                                                  #
# --------------------------------------------------------------------------- #

import context_builder                                     # noqa: E402


_PHASE_STUB = {"label": "base", "entered_on": "2026-09-07"}


def _pos(slots, leg=("2026-09-07", "2026-09-13")):
    return {"window": {"label": "A", "start_date": leg[0], "end_date": leg[1], "source": "phase"},
            "slots": slots, "due_capacity": None, "due_slot": None, "uncounted": []}


def test_g3_week_block_renders_hard_before_keys(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro())
    _sched(db_session, u.id, "gym", "gym", ["monday", "wednesday", "friday"],
           satisfies={"capacity": "stability"})
    _sched(db_session, u.id, "carnival", "carnival", ["saturday"], hard=True, expected_load="heavy")
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    pos = _pos([{"kind": "capacity", "capacity": "stability", "quota": 2, "done": 0,
                 "remaining": 2, "workouts_counted": []}])
    entries = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, active=True).all()
    out = context_builder._section_training_phase(_PHASE_STUB, pos, entries, plan)
    # ordering: the per-day week view precedes the #312 per-key consistency block
    assert "Week (hard commitments first" in out
    assert out.index("Week (hard commitments first") < out.index("Schedule vs quota")
    assert "Saturday 2026-09-12: carnival, heavy — UNAVAILABLE" in out
    assert "day after heavy" in out                       # Sunday flagged
    assert "Data freshness:" in out


def test_g3_week_block_gated_on_week_plan(db_session):
    # No week_plan passed → the #312 tests' path — no week block, consistency line intact.
    pos = _pos([{"kind": "capacity", "capacity": "stability", "quota": 2, "done": 2,
                 "remaining": 0, "workouts_counted": ["w1", "w2"]}])
    val = {"activity": "gym", "days": ["monday", "wednesday", "friday"], "hard": False,
           "satisfies": {"capacity": "stability"}}
    ent = [type("E", (), {"type": "schedule_item", "value": val})()]
    out = context_builder._section_training_phase(_PHASE_STUB, pos, ent)
    assert "Week (hard commitments first" not in out
    assert "Stability — scheduled 3/wk · quota 2 · done 2" in out


def test_g3_planning_needed_line_renders(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro())
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)   # no linked items
    pos = _pos([{"kind": "capacity", "capacity": "stability", "quota": 2, "done": 0,
                 "remaining": 2, "workouts_counted": []}])
    out = context_builder._section_training_phase(_PHASE_STUB, pos, [], plan)
    assert "PLANNING NEEDED" in out


def test_g3_section_schedule_folds_hard_flags_when_suppressed(db_session):
    from datetime import datetime as _dt
    import pytz
    now = pytz.timezone("Australia/Brisbane").localize(_dt(2026, 9, 9, 9, 0))
    val = {"activity": "carnival", "days": ["saturday"], "hard": True}
    ent = [type("E", (), {"type": "schedule_item", "value": val, "source": "chat", "notes": ""})()]
    shown = context_builder._section_schedule(ent, now, suppress_hard_flags=False)
    folded = context_builder._section_schedule(ent, now, suppress_hard_flags=True)
    assert "Hard commitment: carnival" in shown
    assert "Hard commitment: carnival" not in folded     # folded into the week block
    # The weekly day-grid itself is unchanged either way.
    assert "Saturday: carnival (hard)" in folded


# --------------------------------------------------------------------------- #
# G4 — failure isolation                                                       #
# --------------------------------------------------------------------------- #

def test_g4_plan_week_failure_leaves_context_building(db_session, monkeypatch):
    import current_state as cs_mod
    u = _user(db_session)
    _phase(db_session, u.id, _stability_micro())

    def _boom(*a, **k):
        raise RuntimeError("week plan exploded")

    monkeypatch.setattr(cs_mod.week_plan_mod, "plan_week", _boom)
    state = cs_mod.current_state(u.id, db_session, today=TODAY)
    assert state.week_plan is None                        # swallowed, logged
    # context still assembles
    out = context_builder.build_system_prompt(u, [], state)
    assert isinstance(out, str) and "Training Phase" in out
