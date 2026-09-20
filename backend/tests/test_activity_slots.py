"""Activity slots (device-evidenced, zero-load) + zero-load schedule items (#315).

A THIRD microcycle slot kind, `activity`: a session of a DECLARED sport, recorded by a device,
evidences the slot and deposits NO load by virtue of the slot. Two more moves ride with it:
`load_window` slots become SPORT-SCOPED (S2 — a recorded WALK can never satisfy a conditioning
quota), and `schedule_item.satisfies` / `expected_load` gain the `activity` / `none` values.

GATES (from the brief):
  G1  the validator: a slot carries EXACTLY ONE of capacity | load_window | activity; a
      load_window OR activity slot REQUIRES `device_sports`; a capacity slot refuses it; the
      per-sub-cycle duplicate check covers activity (case-insensitive). §18 mutation: collapse
      "exactly one" to "at least one" → the two-kind slot stops being refused.
  G1b a load_window slot WITHOUT device_sports is refused (S2 required — the walk-never-counts
      guarantee is a declaration, not a floor).
  G2  claim order (S3): (1) exclusions first (untimed, concurrent_strength); (2) activity slots
      claim by sport in declared order; (3) the rest → sport-scoped load_window. ONE session ≤
      ONE slot. A pilates session lands on the activity slot, NOT the metabolic window; a walk
      no slot's sport names is `unclaimed_session` ("other activity"); a ride lands on the
      sport-scoped metabolic window. §18 mutation: a session matching BOTH an activity slot and
      a load_window slot must claim the ACTIVITY slot (declared claim order) — flip the order and
      the count moves.
  G2b a canonical session with NULL sport is `unclaimed_session` with detail `no_sport`.
  G3  local-day bucketing + non-canonical twin arbitration still hold for an activity slot
      (one session, counted once).
  G4  `expected_load: "none"` round-trips on a schedule_item; `satisfies: {activity: ...}` lands.

Negative controls: G1's §18 mutation proves "exactly one" is load-bearing; G2's order-flip proves
the activity-before-load_window claim order is read, not incidental; G2b pairs a no-sport session
with a sported walk so "unclaimed" is not merely "any aerobic session".
"""
from datetime import date, datetime, timezone

import pytest

import models
from engine import resolver
from engine.training_phase import validate_microcycle
from routers.knowledge import validate_schedule_item


# --------------------------------------------------------------------------- #
# Fixtures (mirror test_resolver.py)                                           #
# --------------------------------------------------------------------------- #

def _user(db, email="act@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _phase(db, uid, microcycle, entered_on):
    ph = models.TrainingPhase(
        user_id=uid, label="p", probe_posture="held", microcycle=microcycle,
        entered_on=entered_on, asserted_by="user", asserted_on=entered_on, source="api",
    )
    db.add(ph)
    db.commit()
    db.refresh(ph)
    return ph


def _aerobic(db, uid, sid, session_date, *, start=None, stop=None, sport="Ride",
             duration=45.0, zones=(0, 600, 600, 0, 0), source="polar_flow_export"):
    z1, z2, z3, z4, z5 = zones
    obj = models.AerobicSession(
        user_id=uid, source=source, source_session_id=sid, session_date=session_date,
        start_time=start, stop_time=stop, sport_name=sport, duration_minutes=duration,
        z1_seconds=z1, z2_seconds=z2, z3_seconds=z3, z4_seconds=z4, z5_seconds=z5,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj.id


def _gym_workout(db, uid, hevy_id, start, end, tids):
    db.add(models.HevyWorkout(
        hevy_id=hevy_id, user_id=uid, start_time=start, end_time=end, title="W",
        raw={"id": hevy_id, "exercises": [{"exercise_template_id": t} for t in tids]},
        dedup_flag=False, excluded_at=None,
    ))
    db.commit()


def _tpl(db, tid, region_key="hinge", role="primary"):
    db.add(models.HevyExerciseTemplate(id=tid, title=tid, is_custom=True, owner_user_id=None))
    db.flush()
    db.add(models.ExerciseRegionTag(
        hevy_exercise_template_id=tid, region_key=region_key, role=role, source="human_confirmed"))
    db.flush()


MONDAY = date(2026, 9, 7)   # a Monday; leg A anchor
TODAY = date(2026, 9, 9)    # Wednesday inside leg A [09-07, 09-13]


def _one_cycle(*slots):
    return {"sub_cycle_days": 7, "sub_cycles": [{"label": "A", "slots": list(slots)}]}


def _act_slot(name, sports, q=1):
    return {"activity": name, "device_sports": sports, "sessions_per_cycle": q, "minutes": 50}


def _lw_slot(sports, q=2):
    return {"load_window": "metabolic", "device_sports": sports, "sessions_per_cycle": q, "minutes": 40}


def _cap_slot(cap, q=2):
    return {"capacity": cap, "sessions_per_cycle": q, "minutes": 30}


# --------------------------------------------------------------------------- #
# G1 — validator: one-of-three, device_sports discipline, dup check           #
# --------------------------------------------------------------------------- #

def test_g1_three_kind_microcycle_is_valid():
    validate_microcycle(_one_cycle(
        _cap_slot("stability"),
        _lw_slot(["Road cycling", "Indoor cycling"]),
        _act_slot("pilates", ["Pilates"]),
    ))


def test_g1_exactly_one_kind_key_two_is_refused():
    with pytest.raises(ValueError, match="exactly one of"):
        validate_microcycle(_one_cycle(
            {"capacity": "stability", "activity": "pilates", "device_sports": ["Pilates"],
             "sessions_per_cycle": 1, "minutes": 30}))


def test_g1_no_kind_key_is_refused():
    with pytest.raises(ValueError, match="exactly one of"):
        validate_microcycle(_one_cycle({"sessions_per_cycle": 1, "minutes": 30}))


def test_g1_capacity_slot_refuses_device_sports():
    with pytest.raises(ValueError, match="capacity slot does not take device_sports"):
        validate_microcycle(_one_cycle(
            {"capacity": "stability", "device_sports": ["x"], "sessions_per_cycle": 2, "minutes": 30}))


def test_g1_activity_requires_a_name():
    with pytest.raises(ValueError, match=r"activity must be a non-empty name"):
        validate_microcycle(_one_cycle(
            {"activity": "  ", "device_sports": ["Pilates"], "sessions_per_cycle": 1, "minutes": 50}))


def test_g1_duplicate_activity_within_sub_cycle_refused_case_insensitive():
    with pytest.raises(ValueError, match="duplicate activity"):
        validate_microcycle(_one_cycle(
            _act_slot("Pilates", ["Pilates"]),
            _act_slot("pilates", ["Pilates"]),   # same name, different case → refused
        ))


def test_g1_same_activity_across_sub_cycles_is_allowed():
    validate_microcycle({
        "sub_cycle_days": 7,
        "sub_cycles": [
            {"label": "A", "slots": [_act_slot("pilates", ["Pilates"])]},
            {"label": "B", "slots": [_act_slot("pilates", ["Pilates"])]},   # cross-sub-cycle OK
        ],
    })


def test_g1_section18_mutation_exactly_one_is_the_load_bearing_check():
    """§18: the guarantee is EXACTLY one kind key. A two-kind slot has `len(kinds) == 2`, which
    the real `!= 1` check refuses; the weakened rule a mutation would introduce (`>= 1`, "at least
    one") is TRUE for that same slot and would let it through. The pairing of these two facts is
    what makes the mutation detectable — the refusal below is not incidental."""
    slot = {"capacity": "stability", "activity": "pilates", "device_sports": ["Pilates"],
            "sessions_per_cycle": 1, "minutes": 30}
    kinds = [k for k in ("capacity", "load_window", "activity") if k in slot]
    assert len(kinds) == 2
    assert (len(kinds) != 1) is True and (len(kinds) >= 1) is True   # real refuses; mutant passes
    with pytest.raises(ValueError, match="exactly one of"):
        validate_microcycle(_one_cycle(slot))


# --------------------------------------------------------------------------- #
# G1b — a load_window slot WITHOUT device_sports is refused (S2)              #
# --------------------------------------------------------------------------- #

def test_g1b_load_window_without_device_sports_is_refused():
    with pytest.raises(ValueError, match="device_sports must be a non-empty list"):
        validate_microcycle(_one_cycle(
            {"load_window": "metabolic", "sessions_per_cycle": 2, "minutes": 40}))


def test_g1b_load_window_empty_device_sports_is_refused():
    with pytest.raises(ValueError, match="device_sports must be a non-empty list"):
        validate_microcycle(_one_cycle(_lw_slot([])))


def test_g1b_device_sports_must_be_non_empty_strings():
    with pytest.raises(ValueError, match=r"device_sports\[0\] must be a non-empty string"):
        validate_microcycle(_one_cycle(_act_slot("pilates", ["  "])))


# --------------------------------------------------------------------------- #
# G2 — resolver claim order (activity → sport-scoped load_window)             #
# --------------------------------------------------------------------------- #

def test_g2_pilates_claims_the_activity_slot_not_the_metabolic_window(db_session):
    """The operator ruling: a Pilates session lands on its `activity: pilates` slot (zero-load),
    never the conditioning window — even with a metabolic slot present."""
    u = _user(db_session)
    _phase(db_session, u.id, _one_cycle(
        _act_slot("pilates", ["Pilates"]),
        _lw_slot(["Road cycling"]),
    ), MONDAY)
    _aerobic(db_session, u.id, "s_pil", date(2026, 9, 8),
             start=datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc),
             stop=datetime(2026, 9, 8, 6, 50, tzinfo=timezone.utc),
             sport="Pilates", duration=50.0, zones=(0, 0, 0, 0, 0), source="health_connect")
    res = resolver.resolve(db_session, u.id, today=TODAY)
    by = {s["kind"]: s for s in res["slots"]}
    assert by["activity"]["done"] == 1 and by["activity"]["activity"] == "pilates"
    assert by["load_window"]["done"] == 0
    # An activity slot's counted session carries NO trimp key (zero-load).
    counted = by["activity"]["sessions_counted"]
    assert len(counted) == 1 and "trimp" not in counted[0]
    assert res["uncounted"] == []


def test_g2_walk_matching_no_slot_is_unclaimed_other_activity(db_session):
    """A recorded WALK matches no slot's sport → `unclaimed_session` (never a load_window, S2)."""
    u = _user(db_session)
    _phase(db_session, u.id, _one_cycle(_lw_slot(["Road cycling"])), MONDAY)
    aid = _aerobic(db_session, u.id, "s_walk", date(2026, 9, 8),
                   start=datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc),
                   stop=datetime(2026, 9, 8, 6, 30, tzinfo=timezone.utc),
                   sport="Walking", duration=30.0, zones=(0, 0, 0, 0, 0), source="health_connect")
    res = resolver.resolve(db_session, u.id, today=TODAY)
    assert res["slots"][0]["done"] == 0
    assert res["uncounted"] == [
        {"session": aid, "reason": "unclaimed_session",
         "sport_name": "Walking", "duration_minutes": 30.0}]


def test_g2_ride_claims_the_sport_scoped_metabolic_window(db_session):
    """A ride whose sport is in the load_window's device_sports counts, with its trimp."""
    u = _user(db_session)
    _phase(db_session, u.id, _one_cycle(_lw_slot(["Road cycling", "Indoor cycling"])), MONDAY)
    _aerobic(db_session, u.id, "s_ride", date(2026, 9, 8),
             start=datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc),
             stop=datetime(2026, 9, 8, 6, 45, tzinfo=timezone.utc),
             sport="Road cycling", duration=45.0, zones=(0, 600, 1200, 0, 0))
    res = resolver.resolve(db_session, u.id, today=TODAY)
    slot = res["slots"][0]
    assert slot["done"] == 1
    assert slot["sessions_counted"][0]["trimp"] > 0
    assert res["uncounted"] == []


def test_g2_matching_sport_is_case_insensitive(db_session):
    """Ruling 4c: matching is exact but case-insensitive. Declared "Pilates", recorded "PILATES"."""
    u = _user(db_session)
    _phase(db_session, u.id, _one_cycle(_act_slot("pilates", ["Pilates"])), MONDAY)
    _aerobic(db_session, u.id, "s_pil", date(2026, 9, 8),
             start=datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc),
             stop=datetime(2026, 9, 8, 6, 50, tzinfo=timezone.utc),
             sport="PILATES", duration=50.0, zones=(0, 0, 0, 0, 0), source="health_connect")
    res = resolver.resolve(db_session, u.id, today=TODAY)
    assert res["slots"][0]["done"] == 1


def test_g2_section18_activity_claims_before_load_window_when_a_sport_matches_both(db_session):
    """§18 mutation: claim order is activity-BEFORE-load_window. When one sport is in BOTH an
    activity slot's device_sports AND a load_window slot's, the session must land on the ACTIVITY
    slot. Flip the resolver's two `next(...)` lookups and this count moves to the load_window —
    the assertion is what pins the order."""
    u = _user(db_session)
    _phase(db_session, u.id, _one_cycle(
        _lw_slot(["Spin"]),                     # load_window declared FIRST in slot order...
        _act_slot("spin_class", ["Spin"]),      # ...but claim order puts activity first
    ), MONDAY)
    _aerobic(db_session, u.id, "s_spin", date(2026, 9, 8),
             start=datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc),
             stop=datetime(2026, 9, 8, 6, 45, tzinfo=timezone.utc),
             sport="Spin", duration=45.0, zones=(0, 600, 600, 0, 0))
    res = resolver.resolve(db_session, u.id, today=TODAY)
    by = {s["kind"]: s for s in res["slots"]}
    assert by["activity"]["done"] == 1, "a sport matching both kinds claims the activity slot"
    assert by["load_window"]["done"] == 0
    # And exactly one slot claimed it — no double count.
    assert by["activity"]["done"] + by["load_window"]["done"] == 1


def test_g2_one_session_claims_at_most_one_of_two_activity_slots(db_session):
    """Declared order among activity slots: a session matching two activity slots' sports lands on
    the FIRST-declared one only."""
    u = _user(db_session)
    _phase(db_session, u.id, _one_cycle(
        _act_slot("first", ["Yoga"]),
        _act_slot("second", ["Yoga"]),
    ), MONDAY)
    _aerobic(db_session, u.id, "s_yoga", date(2026, 9, 8),
             start=datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc),
             stop=datetime(2026, 9, 8, 6, 40, tzinfo=timezone.utc),
             sport="Yoga", duration=40.0, zones=(0, 0, 0, 0, 0), source="health_connect")
    res = resolver.resolve(db_session, u.id, today=TODAY)
    by = {s["activity"]: s for s in res["slots"]}
    assert by["first"]["done"] == 1 and by["second"]["done"] == 0


# --------------------------------------------------------------------------- #
# G2b — NULL sport → unclaimed_session detail no_sport                         #
# --------------------------------------------------------------------------- #

def test_g2b_null_sport_is_unclaimed_with_no_sport_detail(db_session):
    """Ruling 4b: a canonical session with NO recorded sport can match no sport-scoped slot →
    `unclaimed_session` with detail `no_sport`. Paired with a sported walk so the reason is not
    merely 'any aerobic session is unclaimed' — the walk (Walking, not declared) is unclaimed too
    but WITHOUT the no_sport detail."""
    u = _user(db_session)
    _phase(db_session, u.id, _one_cycle(_act_slot("pilates", ["Pilates"])), MONDAY)
    a_null = _aerobic(db_session, u.id, "s_null", date(2026, 9, 8),
                      start=datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc),
                      stop=datetime(2026, 9, 8, 6, 30, tzinfo=timezone.utc),
                      sport=None, duration=30.0, zones=(0, 0, 0, 0, 0), source="health_connect")
    a_walk = _aerobic(db_session, u.id, "s_walk", date(2026, 9, 9),
                      start=datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc),
                      stop=datetime(2026, 9, 9, 6, 30, tzinfo=timezone.utc),
                      sport="Walking", duration=30.0, zones=(0, 0, 0, 0, 0), source="health_connect")
    res = resolver.resolve(db_session, u.id, today=TODAY)
    assert res["slots"][0]["done"] == 0
    reasons = {u_["session"]: u_ for u_ in res["uncounted"]}
    assert reasons[a_null]["reason"] == "unclaimed_session" and reasons[a_null]["detail"] == "no_sport"
    assert reasons[a_walk]["reason"] == "unclaimed_session" and "detail" not in reasons[a_walk]


# --------------------------------------------------------------------------- #
# G3 — exclusions + arbitration still hold for the aerobic lane               #
# --------------------------------------------------------------------------- #

def test_g3_activity_untimed_fails_closed(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _one_cycle(_act_slot("pilates", ["Pilates"])), MONDAY)
    aid = _aerobic(db_session, u.id, "s_pil", date(2026, 9, 8),
                   start=None, stop=None, sport="Pilates", duration=50.0,
                   zones=(0, 0, 0, 0, 0), source="health_connect")
    res = resolver.resolve(db_session, u.id, today=TODAY)
    assert res["slots"][0]["done"] == 0
    assert res["uncounted"] == [
        {"session": aid, "reason": "untimed", "sport_name": "Pilates", "duration_minutes": 50.0}]


def test_g3_activity_concurrent_strength_excluded_before_sport_match(db_session):
    """Exclusions run FIRST (S3 step 1): a pilates session overlapping a gym workout is
    concurrent_strength, never the activity slot — even though its sport matches."""
    u = _user(db_session)
    _phase(db_session, u.id, _one_cycle(_act_slot("pilates", ["Pilates"])), MONDAY)
    _tpl(db_session, "t_str")
    _gym_workout(db_session, u.id, "w_gym",
                 datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc),
                 datetime(2026, 9, 8, 7, 0, tzinfo=timezone.utc), ["t_str"])
    aid = _aerobic(db_session, u.id, "s_pil", date(2026, 9, 8),
                   start=datetime(2026, 9, 8, 6, 15, tzinfo=timezone.utc),
                   stop=datetime(2026, 9, 8, 7, 5, tzinfo=timezone.utc),
                   sport="Pilates", duration=50.0, zones=(0, 0, 0, 0, 0), source="health_connect")
    res = resolver.resolve(db_session, u.id, today=TODAY)
    assert res["slots"][0]["done"] == 0
    assert {"session": aid, "reason": "concurrent_strength",
            "sport_name": "Pilates", "duration_minutes": 50.0} in res["uncounted"]


def test_g3_activity_counts_only_canonical_of_same_bout(db_session):
    """Read-time arbitration (#260): a same-bout pair (flow_export + health_connect) is one
    canonical session → one count on the activity slot, not two."""
    u = _user(db_session)
    _phase(db_session, u.id, _one_cycle(_act_slot("ride", ["Ride"])), MONDAY)
    start = datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc)
    stop = datetime(2026, 9, 8, 6, 45, tzinfo=timezone.utc)
    _aerobic(db_session, u.id, "flow", date(2026, 9, 8), start=start, stop=stop,
             sport="Ride", zones=(0, 600, 600, 0, 0), source="polar_flow_export")
    _aerobic(db_session, u.id, "hc", date(2026, 9, 8), start=start, stop=stop,
             sport="Ride", zones=(0, 0, 0, 0, 0), source="health_connect")
    res = resolver.resolve(db_session, u.id, today=TODAY)
    assert res["slots"][0]["done"] == 1
    assert res["uncounted"] == []


def test_g3_activity_local_day_trap(db_session):
    """The 23:30-UTC → next-Brisbane-day trap holds for an activity slot too."""
    u = _user(db_session)
    _phase(db_session, u.id, {"sub_cycle_days": 7, "sub_cycles": [
        {"label": "A", "slots": [_act_slot("pilates", ["Pilates"], q=5)]}]}, MONDAY)
    _aerobic(db_session, u.id, "s_late", date(2026, 9, 14),
             start=datetime(2026, 9, 13, 23, 30, tzinfo=timezone.utc),
             stop=datetime(2026, 9, 14, 0, 15, tzinfo=timezone.utc),
             sport="Pilates", zones=(0, 0, 0, 0, 0), source="health_connect")
    a = resolver.resolve(db_session, u.id, today=date(2026, 9, 10))
    assert a["window"]["end_date"] == "2026-09-13" and a["slots"][0]["done"] == 0
    b = resolver.resolve(db_session, u.id, today=date(2026, 9, 14))
    assert b["window"]["start_date"] == "2026-09-14" and b["slots"][0]["done"] == 1


def test_g3_due_slot_lands_on_activity_kind(db_session):
    """Rule 4 across all three kinds: an unmet activity slot first in declared order is due,
    and due_capacity skips it (never reaches /engine/next)."""
    u = _user(db_session)
    _phase(db_session, u.id, _one_cycle(
        _act_slot("pilates", ["Pilates"]),
        _cap_slot("strength", q=1),
    ), MONDAY)
    res = resolver.resolve(db_session, u.id, today=TODAY)
    assert res["due_slot"] == {"kind": "activity", "key": "pilates"}
    assert res["due_capacity"] == "strength"


# --------------------------------------------------------------------------- #
# G4 — schedule_item: expected_load "none" + satisfies {activity}             #
# --------------------------------------------------------------------------- #

def _sched_value(**overrides) -> dict:
    """A conforming schedule_item value (mirrors test_schedule_item_schema._value). Each G4 test
    overrides one field so the mutation is the test."""
    base = {
        "activity": "Pilates class",
        "days": ["monday"],
        "hard": False,
        "expected_load": "none",
        "time_of_day": "evening",
        "same_day_training": False,
        "duration_weeks": None,
        "season_end": None,
    }
    base.update(overrides)
    return base


def test_g4_expected_load_none_round_trips():
    v = validate_schedule_item(_sched_value(expected_load="none"))
    assert v["expected_load"] == "none"


def test_g4_satisfies_activity_is_accepted():
    v = validate_schedule_item(_sched_value(satisfies={"activity": "pilates"}))
    assert v["satisfies"] == {"activity": "pilates"}


def test_g4_satisfies_activity_rejects_empty_name():
    with pytest.raises(ValueError, match="activity must be a non-empty"):
        validate_schedule_item(_sched_value(satisfies={"activity": "  "}))
