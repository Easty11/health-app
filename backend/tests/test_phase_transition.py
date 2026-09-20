"""Phase transition — the single atomic write behind the phase-change form (#317, PR1).

GATES:
  G1  atomicity — a failing schedule item rolls back the phase open (row counts unchanged);
      a re-submit identical to the open phase opens ONE phase and writes nothing (natural-state
      idempotency, cross-worker).
  G2  the operator's 5 Oct Continue-with-revise case: decompression → decompression, stability
      2→3, activity pilates ×2 [Pilates], gym Mon/Wed/Fri + pilates Sat/Tue linked → consistency
      shows NO MISMATCH afterwards.
  G3  dated one-off (event_date): a carnival blocks its days, cautions the day after a heavy one,
      and drops off the planner once past.
  G4  draft replay is BOUNDED — `resolve()` is never asked about a day before `entered_on`
      (§18 mutation: probing earlier would call resolve() with an earlier day → the spy fails).
  Same-day correction (ruling 3): transition → corrected transition on one local day yields one
  open phase, the interim closed same-day.

Direct service calls (`_apply_phase_transition`, `_matching_open_phase`, `_outgoing_review`) carry
the atomicity/idempotency/replay gates; the route is exercised for the folder + orphan path.
"""
from datetime import date, timedelta

import pytest

import models
from engine import resolver as resolver_mod
from engine import training_phase as phase_mod
from engine import week_plan as week_plan_mod
from routers import training_phase as tp


# Anchored to the real operator-local day (the phase validator refuses a future `entered_on`),
# so the fixtures stay valid whatever day the suite runs. The operator's real case is 5 Oct; the
# shape is what these assert, not the calendar.
TODAY = phase_mod._local_day()
PRIOR = TODAY - timedelta(days=28)


def _user(db, email="tr@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _phase_payload(label="decompression", *, entered_on, stability=2, pilates=None,
                   close_prior_reason=None):
    slots = [{"capacity": "stability", "sessions_per_cycle": stability, "minutes": 30}]
    if pilates is not None:
        slots.append({"activity": "pilates", "device_sports": ["Pilates"],
                      "sessions_per_cycle": pilates, "minutes": 50})
    payload = {
        "label": label, "probe_posture": "held",
        "microcycle": {"sub_cycle_days": 7, "sub_cycles": [{"label": "A", "slots": slots}]},
        "entered_on": entered_on, "asserted_by": "user", "asserted_on": entered_on, "source": "api",
    }
    if close_prior_reason is not None:
        payload["close_prior_reason"] = close_prior_reason
    return payload


def _sched_op(key, activity, days, satisfies, *, expected_load="moderate"):
    return tp.ScheduleOpIn(action="upsert", key=key, value={
        "activity": activity, "days": days, "hard": False, "expected_load": expected_load,
        "time_of_day": "evening", "same_day_training": False,
        "duration_weeks": None, "season_end": None, "satisfies": satisfies,
    })


def _count_phases(db, uid):
    return db.query(models.TrainingPhase).filter_by(user_id=uid).count()


def _active_schedule(db, uid):
    return (db.query(models.UserKnowledgeEntry)
            .filter_by(user_id=uid, type="schedule_item", active=True).count())


# --------------------------------------------------------------------------- #
# G1 — atomicity + idempotency                                                 #
# --------------------------------------------------------------------------- #

def test_g1_failing_schedule_item_rolls_back_the_phase_open(db_session):
    u = _user(db_session)
    phase_mod.open_phase(db_session, u.id, _phase_payload(entered_on="2026-09-01"))
    phases_before = _count_phases(db_session, u.id)
    sched_before = _active_schedule(db_session, u.id)

    # A valid new phase, but a schedule op whose value is invalid (bad expected_load).
    bad_op = tp.ScheduleOpIn(action="upsert", key="gym", value={
        "activity": "gym", "days": ["monday"], "hard": False, "expected_load": "SUPER-HEAVY",
        "time_of_day": "evening", "same_day_training": False,
        "duration_weeks": None, "season_end": None})
    with pytest.raises(ValueError):
        tp._apply_phase_transition(
            db_session, u.id, phase_payload=_phase_payload(entered_on="2026-09-08", stability=3),
            schedule_ops=[bad_op], folder_id=None)
    db_session.rollback()

    assert _count_phases(db_session, u.id) == phases_before   # no new phase opened
    assert _active_schedule(db_session, u.id) == sched_before  # no schedule row written
    # the outgoing phase is still open (its close was rolled back too)
    cur = phase_mod.current_training_phase(db_session, u.id)
    assert cur is not None and cur.entered_on == date(2026, 9, 1)


def test_g1_identical_resubmit_is_a_noop(db_session):
    u = _user(db_session)
    payload = _phase_payload(entered_on="2026-09-01", stability=2)
    tp._apply_phase_transition(db_session, u.id, phase_payload=payload, schedule_ops=[], folder_id=None)
    n = _count_phases(db_session, u.id)
    # A re-submit deep-equal on label + entered_on + microcycle → matches → route writes nothing.
    match = tp._matching_open_phase(db_session, u.id, payload)
    assert match is not None and match.label == "decompression"
    assert _count_phases(db_session, u.id) == n   # matching does not write


def test_g1_different_submit_is_not_matched(db_session):
    u = _user(db_session)
    tp._apply_phase_transition(db_session, u.id,
                               phase_payload=_phase_payload(entered_on="2026-09-01", stability=2),
                               schedule_ops=[], folder_id=None)
    # Same label + entered_on but a DIFFERENT microcycle (stability 3) → not a match → proceeds.
    assert tp._matching_open_phase(
        db_session, u.id, _phase_payload(entered_on="2026-09-01", stability=3)) is None


# --------------------------------------------------------------------------- #
# G2 — the 5 Oct Continue-with-revise case                                     #
# --------------------------------------------------------------------------- #

def test_g2_five_oct_continue_with_revise_leaves_no_mismatch(db_session):
    u = _user(db_session)
    # Outgoing: decompression, stability ×2, gym Mon/Wed/Fri linked (the deliberate 3-vs-2).
    phase_mod.open_phase(db_session, u.id, _phase_payload(label="decompression", entered_on=PRIOR.isoformat(), stability=2))
    from routers.knowledge import upsert_knowledge_entry, KnowledgeEntryIn
    upsert_knowledge_entry(u.id, KnowledgeEntryIn(type="schedule_item", key="gym", source="api", value={
        "activity": "gym", "days": ["monday", "wednesday", "friday"], "hard": False,
        "expected_load": "moderate", "time_of_day": "evening", "same_day_training": False,
        "duration_weeks": None, "season_end": None, "satisfies": {"capacity": "stability"}}), db_session)

    # The transition: continue decompression, stability 2→3, add activity pilates ×2, link pilates Sat+Tue.
    payload = _phase_payload(label="decompression", entered_on=TODAY.isoformat(), stability=3, pilates=2,
                             close_prior_reason="continue — revise stability + add pilates")
    ops = [
        _sched_op("pilates_sat", "pilates", ["saturday"], {"activity": "pilates"}),
        _sched_op("pilates_tue", "pilates", ["tuesday"], {"activity": "pilates"}),
    ]
    tp._apply_phase_transition(db_session, u.id, phase_payload=payload, schedule_ops=ops, folder_id=None)

    # Afterwards: the plan shows no MISMATCH — stability scheduled 3 == quota 3; pilates 2 == 2.
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    by = {r["key"]: r for r in plan["keys"]}
    assert by["stability"]["scheduled"] == 3 and by["stability"]["quota"] == 3 and by["stability"]["excess"] == 0
    assert by["pilates"]["scheduled"] == 2 and by["pilates"]["quota"] == 2 and by["pilates"]["excess"] == 0
    # one open phase, decompression, entered today; the prior decompression closed today
    cur = phase_mod.current_training_phase(db_session, u.id)
    assert cur.label == "decompression" and cur.entered_on == TODAY
    closed = (db_session.query(models.TrainingPhase)
              .filter_by(user_id=u.id).filter(models.TrainingPhase.closed_on.isnot(None)).all())
    assert len(closed) == 1 and closed[0].closed_on == TODAY


# --------------------------------------------------------------------------- #
# Same-day correction (ruling 3)                                               #
# --------------------------------------------------------------------------- #

def test_same_day_correction_yields_one_open_phase(db_session):
    u = _user(db_session)
    tp._apply_phase_transition(db_session, u.id,
                               phase_payload=_phase_payload(label="build", entered_on=TODAY.isoformat(), stability=2),
                               schedule_ops=[], folder_id=None)
    # A corrected transition the SAME day (stability 3) — monotonic rule permits entered_on == today.
    tp._apply_phase_transition(db_session, u.id,
                               phase_payload=_phase_payload(label="build", entered_on=TODAY.isoformat(), stability=3),
                               schedule_ops=[], folder_id=None)
    cur = phase_mod.current_training_phase(db_session, u.id)
    assert cur.microcycle["sub_cycles"][0]["slots"][0]["sessions_per_cycle"] == 3   # the correction won
    # exactly one open; the interim closed same-day
    open_rows = db_session.query(models.TrainingPhase).filter_by(user_id=u.id, closed_on=None).count()
    assert open_rows == 1


# --------------------------------------------------------------------------- #
# G3 — dated one-off (event_date)                                              #
# --------------------------------------------------------------------------- #

def _event_item(db, uid, key, activity, event_date, event_end=None, expected_load="heavy"):
    from routers.knowledge import upsert_knowledge_entry, KnowledgeEntryIn
    upsert_knowledge_entry(uid, KnowledgeEntryIn(type="schedule_item", key=key, source="api", value={
        "activity": activity, "hard": True, "expected_load": expected_load, "time_of_day": "unknown",
        "same_day_training": False, "duration_weeks": None, "season_end": None,
        "event_date": event_date, "event_end": event_end}), db)


def test_g3_dated_item_blocks_days_and_cautions_after(db_session):
    u = _user(db_session)
    # 14-day leg so the window spans the carnival and the day after.
    phase_mod.open_phase(db_session, u.id, {
        "label": "base", "probe_posture": "held",
        "microcycle": {"sub_cycle_days": 14, "sub_cycles": [{"label": "A", "slots": [
            {"capacity": "stability", "sessions_per_cycle": 2, "minutes": 30}]}]},
        "entered_on": "2026-09-15", "asserted_by": "user", "asserted_on": "2026-09-15", "source": "api"})
    _event_item(db_session, u.id, "carnival", "athletics carnival", "2026-09-19", "2026-09-20")

    plan = week_plan_mod.plan_week(db_session, u.id, date(2026, 9, 16))
    by_date = {d["date"]: d for d in plan["days"]}
    assert by_date["2026-09-19"]["available"] is False and by_date["2026-09-20"]["available"] is False
    assert by_date["2026-09-21"]["available"] is True and by_date["2026-09-21"]["caution"] == "day after heavy"
    assert by_date["2026-09-22"]["caution"] is None


def test_g3_dated_item_drops_off_after_it_passes(db_session):
    u = _user(db_session)
    entered = TODAY - timedelta(days=1)          # a fresh leg starting yesterday (not future)
    carnival_start = (entered - timedelta(days=6)).isoformat()
    carnival_end = (entered - timedelta(days=5)).isoformat()
    phase_mod.open_phase(db_session, u.id, {
        "label": "base", "probe_posture": "held",
        "microcycle": {"sub_cycle_days": 7, "sub_cycles": [{"label": "A", "slots": [
            {"capacity": "stability", "sessions_per_cycle": 2, "minutes": 30}]}]},
        "entered_on": entered.isoformat(), "asserted_by": "user",
        "asserted_on": entered.isoformat(), "source": "api"})
    _event_item(db_session, u.id, "carnival", "athletics carnival", carnival_start, carnival_end)
    # The window starts AFTER the carnival → its days are all past the event → nothing blocked.
    plan = week_plan_mod.plan_week(db_session, u.id, TODAY)
    assert all(d["available"] for d in plan["days"])


def test_g3_section_schedule_renders_dated_line_only_while_live(db_session):
    import context_builder
    from datetime import datetime as _dt
    import pytz
    now = pytz.timezone("Australia/Brisbane").localize(_dt(2026, 9, 18, 9, 0))  # before the carnival
    live = [type("E", (), {"type": "schedule_item", "source": "api", "notes": "", "value": {
        "activity": "carnival", "hard": True, "expected_load": "heavy",
        "event_date": "2026-09-19", "event_end": "2026-09-20"}})()]
    out = context_builder._section_schedule(live, now)
    assert "DATED ONE-OFFS" in out and "carnival" in out and "hard, heavy" in out
    # After it passes → the dated line drops off (byte-identical to no-dated output).
    now_after = pytz.timezone("Australia/Brisbane").localize(_dt(2026, 9, 25, 9, 0))
    assert "DATED ONE-OFFS" not in context_builder._section_schedule(live, now_after)


# --------------------------------------------------------------------------- #
# G4 — draft replay is bounded to windows >= entered_on                        #
# --------------------------------------------------------------------------- #

def test_g4_draft_replay_never_resolves_before_entered_on(db_session, monkeypatch):
    u = _user(db_session)
    phase = phase_mod.open_phase(db_session, u.id, {
        "label": "base", "probe_posture": "held",
        "microcycle": {"sub_cycle_days": 7, "sub_cycles": [{"label": "A", "slots": [
            {"capacity": "stability", "sessions_per_cycle": 2, "minutes": 30}]}]},
        "entered_on": "2026-09-07", "asserted_by": "user", "asserted_on": "2026-09-07", "source": "api"})

    seen_days: list[date] = []
    real = resolver_mod.resolve

    def _spy(db, uid, *, today):
        seen_days.append(today)
        return real(db, uid, today=today)

    monkeypatch.setattr(tp.resolver_mod, "resolve", _spy)
    tp._outgoing_review(db_session, u.id, phase, date(2026, 9, 28))
    assert seen_days, "the replay must probe at least one window"
    # §18: the bound — resolve() is NEVER asked about a day before entered_on. Removing the bound
    # (probing an earlier day) would put a date < 2026-09-07 in this list and fail the assertion.
    assert min(seen_days) >= date(2026, 9, 7)
    # and windows only report legs at/after entry
    review = tp._outgoing_review(db_session, u.id, phase, date(2026, 9, 28))
    assert all(w["window"]["start_date"] >= "2026-09-07" for w in review)


# --------------------------------------------------------------------------- #
# recorded_via (metadata, closed set)                                          #
# --------------------------------------------------------------------------- #

def test_recorded_via_accepted_and_closed(db_session):
    from engine.training_phase import validate_microcycle
    for rv in ("hevy", "polar_h10", "garmin", "samsung_health", "manual"):
        validate_microcycle({"sub_cycle_days": 7, "sub_cycles": [{"label": "A", "slots": [
            {"capacity": "stability", "sessions_per_cycle": 2, "minutes": 30, "recorded_via": rv}]}]})
    with pytest.raises(ValueError, match="recorded_via"):
        validate_microcycle({"sub_cycle_days": 7, "sub_cycles": [{"label": "A", "slots": [
            {"capacity": "stability", "sessions_per_cycle": 2, "minutes": 30, "recorded_via": "fitbit"}]}]})
