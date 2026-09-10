"""Due-slot resolver (Q106 week-to-date half, #221-deferred / #270-scoped).

Covers the brief's GATES: leg boundary (day before/after), the local-day trap (a late-UTC
workout bucketed to the next Brisbane day), the dominant-capacity tie (Rule 1 → first in slot
order), an untagged workout surfaced not swallowed (secondary tags ignored for dominance), an
off-plan workout surfaced distinctly, dedup/excluded not counted, the weekly fallback at
baseline, Rule 4 due-slot selection, and `/engine/next` default-to-due vs explicit over HTTP.

Negative controls are built in: the tie test flips slot order to prove the tie-break reads the
order (not a fixed capacity), and the untagged test pairs a secondary-only exercise with a
zero-tag one to prove secondary tags are ignored rather than the workout simply having no tags.
"""
from datetime import date, datetime, timezone

import models
from engine import profile as profile_mod
from engine import resolver, taxonomy
from load_metrics import _local_day


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #

def _user(db, email="res@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _tpl(db, tid, region_key=None, role="primary"):
    """A template, optionally carrying one region tag. `region_key=None` → a wholly untagged
    template (a zero-derivable exercise)."""
    db.add(models.HevyExerciseTemplate(id=tid, title=tid, is_custom=True, owner_user_id=None))
    db.flush()   # parent before the FK-enforced tag (#239)
    if region_key is not None:
        db.add(models.ExerciseRegionTag(
            hevy_exercise_template_id=tid, region_key=region_key, role=role,
            source="human_confirmed",
        ))
        db.flush()


def _workout(db, uid, hevy_id, start, tids, *, dedup=False, excluded=False, raw_exercises=None):
    exercises = raw_exercises if raw_exercises is not None else [
        {"exercise_template_id": t, "title": t} for t in tids
    ]
    db.add(models.HevyWorkout(
        hevy_id=hevy_id, user_id=uid, start_time=start, title="W",
        raw={"id": hevy_id, "exercises": exercises},
        dedup_flag=dedup,
        excluded_at=datetime(2026, 1, 1, tzinfo=timezone.utc) if excluded else None,
    ))
    db.commit()


def _phase(db, uid, microcycle, entered_on, *, probe_posture="held"):
    ph = models.TrainingPhase(
        user_id=uid, label="p", probe_posture=probe_posture, microcycle=microcycle,
        entered_on=entered_on, asserted_by="user", asserted_on=entered_on, source="api",
    )
    db.add(ph)
    db.commit()
    db.refresh(ph)
    return ph


def _micro(sub_cycle_days, *sub_cycles):
    """`_micro(7, ("A", [("strength", 2), ("stability", 2)]), ("B", [("power", 2)]))`."""
    return {
        "sub_cycle_days": sub_cycle_days,
        "sub_cycles": [
            {"label": label, "slots": [
                {"capacity": cap, "sessions_per_cycle": q, "minutes": 30} for cap, q in slots]}
            for label, slots in sub_cycles
        ],
    }


# Region keys with known capacities (from taxonomy).
STRENGTH_RK = "hinge"
STABILITY_RK = "anti_rotation"
POWER_RK = "single_leg_hop"
MONDAY = date(2026, 9, 7)   # entered_on anchor; 2026-09-07 is a Monday


# --------------------------------------------------------------------------- #
# Window producers — leg boundary                                             #
# --------------------------------------------------------------------------- #

def test_phase_leg_boundary_day_before_and_after(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _micro(7, ("A", [("strength", 2), ("stability", 2)]),
                                       ("B", [("power", 2)])), MONDAY)

    # Day 6 (2026-09-13) is still leg A; day 7 (2026-09-14) flips to leg B.
    a = resolver.resolve(db_session, u.id, today=date(2026, 9, 13))
    assert a["window"]["label"] == "A"
    assert a["window"]["start_date"] == "2026-09-07"
    assert a["window"]["end_date"] == "2026-09-13"
    assert a["window"]["source"] == "phase"
    assert [s["capacity"] for s in a["slots"]] == ["strength", "stability"]

    b = resolver.resolve(db_session, u.id, today=date(2026, 9, 14))
    assert b["window"]["label"] == "B"
    assert b["window"]["start_date"] == "2026-09-14"
    assert b["window"]["end_date"] == "2026-09-20"
    assert [s["capacity"] for s in b["slots"]] == ["power"]

    # Day 14 (2026-09-21) wraps back to leg A, a fresh window.
    a2 = resolver.resolve(db_session, u.id, today=date(2026, 9, 21))
    assert a2["window"]["label"] == "A"
    assert a2["window"]["start_date"] == "2026-09-21"


# --------------------------------------------------------------------------- #
# The local-day trap                                                          #
# --------------------------------------------------------------------------- #

def test_local_day_trap_late_utc_lands_next_brisbane_day(db_session):
    # A 23:30 UTC instant on 09-13 is 09:30 on 09-14 in Brisbane (+10) — the trap.
    assert _local_day(datetime(2026, 9, 13, 23, 30, tzinfo=timezone.utc)) == date(2026, 9, 14)

    u = _user(db_session)
    _phase(db_session, u.id, _micro(7, ("A", [("strength", 3)])), MONDAY)
    _tpl(db_session, "t_str", STRENGTH_RK)
    # Same UTC calendar day, opposite sides of the Brisbane midnight for leg A [09-07, 09-13].
    _workout(db_session, u.id, "w_in", datetime(2026, 9, 13, 9, 0, tzinfo=timezone.utc), ["t_str"])
    _workout(db_session, u.id, "w_out", datetime(2026, 9, 13, 23, 30, tzinfo=timezone.utc), ["t_str"])

    res = resolver.resolve(db_session, u.id, today=date(2026, 9, 10))
    slot = res["slots"][0]
    assert slot["done"] == 1, "only the 09:00Z workout is local-09-13; 23:30Z is local-09-14"
    assert slot["workouts_counted"] == ["w_in"]


# --------------------------------------------------------------------------- #
# Rule 1 — dominant capacity + tie                                            #
# --------------------------------------------------------------------------- #

def test_dominant_tie_breaks_to_first_in_slot_order(db_session):
    _tpl_db = db_session
    u = _user(_tpl_db)
    _tpl(_tpl_db, "t_str", STRENGTH_RK)
    _tpl(_tpl_db, "t_stab", STABILITY_RK)
    # One strength-primary + one stability-primary exercise → a 1–1 tie.
    _workout(_tpl_db, u.id, "w_tie", datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc),
             ["t_str", "t_stab"])

    # Slots strength-first → the tie resolves to strength.
    _phase(_tpl_db, u.id, _micro(7, ("A", [("strength", 2), ("stability", 2)])), MONDAY)
    res = resolver.resolve(_tpl_db, u.id, today=date(2026, 9, 9))
    by_cap = {s["capacity"]: s for s in res["slots"]}
    assert by_cap["strength"]["done"] == 1 and by_cap["stability"]["done"] == 0


def test_dominant_tie_follows_slot_order_when_flipped(db_session):
    u = _user(db_session)
    _tpl(db_session, "t_str", STRENGTH_RK)
    _tpl(db_session, "t_stab", STABILITY_RK)
    _workout(db_session, u.id, "w_tie", datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc),
             ["t_str", "t_stab"])
    # Slots stability-first → the SAME tie now resolves to stability (proves order is read).
    _phase(db_session, u.id, _micro(7, ("A", [("stability", 2), ("strength", 2)])), MONDAY)
    res = resolver.resolve(db_session, u.id, today=date(2026, 9, 9))
    by_cap = {s["capacity"]: s for s in res["slots"]}
    assert by_cap["stability"]["done"] == 1 and by_cap["strength"]["done"] == 0


# --------------------------------------------------------------------------- #
# uncounted[] — untagged (secondary ignored) and off-plan                     #
# --------------------------------------------------------------------------- #

def test_untagged_workout_surfaced_not_swallowed(db_session):
    u = _user(db_session)
    _tpl(db_session, "t_sec", STRENGTH_RK, role="secondary")   # secondary-only → not dominant
    _tpl(db_session, "t_none", None)                            # no tag at all
    _workout(db_session, u.id, "w_untagged",
             datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc), ["t_sec", "t_none"])
    _phase(db_session, u.id, _micro(7, ("A", [("strength", 2)])), MONDAY)

    res = resolver.resolve(db_session, u.id, today=date(2026, 9, 9))
    assert res["slots"][0]["done"] == 0, "a secondary strength tag must not count toward the slot"
    assert res["uncounted"] == [
        {"workout": "w_untagged", "reason": "untagged", "untagged_exercises": 2}]


def test_off_plan_workout_surfaced_distinct_from_untagged(db_session):
    u = _user(db_session)
    _tpl(db_session, "t_pow", POWER_RK)
    _workout(db_session, u.id, "w_off", datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc), ["t_pow"])
    _phase(db_session, u.id, _micro(7, ("A", [("strength", 2), ("stability", 2)])), MONDAY)

    res = resolver.resolve(db_session, u.id, today=date(2026, 9, 9))
    assert all(s["done"] == 0 for s in res["slots"])
    assert res["uncounted"] == [{"workout": "w_off", "reason": "off_plan", "capacity": "power"}]


# --------------------------------------------------------------------------- #
# dedup / excluded not counted                                                #
# --------------------------------------------------------------------------- #

def test_dedup_and_excluded_workouts_are_not_counted(db_session):
    u = _user(db_session)
    _tpl(db_session, "t_str", STRENGTH_RK)
    d = datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc)
    _workout(db_session, u.id, "w_dedup", d, ["t_str"], dedup=True)
    _workout(db_session, u.id, "w_excl", d, ["t_str"], excluded=True)
    _workout(db_session, u.id, "w_ok", d, ["t_str"])
    _phase(db_session, u.id, _micro(7, ("A", [("strength", 3)])), MONDAY)

    res = resolver.resolve(db_session, u.id, today=date(2026, 9, 9))
    assert res["slots"][0]["done"] == 1 and res["slots"][0]["workouts_counted"] == ["w_ok"]
    assert res["uncounted"] == [], "dedup/excluded are filtered out entirely, not surfaced"


# --------------------------------------------------------------------------- #
# Precedence + weekly fallback                                                #
# --------------------------------------------------------------------------- #

def test_weekly_fallback_at_baseline_and_q105_spelling(db_session):
    u = _user(db_session)
    # Uppercase capability tokens — resolver must route through resolve_capacity (Q105).
    profile_mod.upsert_profile(db_session, u.id, {"weekly_template": {"slots": [
        {"capacity": "STRENGTH", "sessions_per_week": 2, "minutes": 45},
        {"capacity": "STABILITY", "sessions_per_week": 2, "minutes": 30}]}})
    _tpl(db_session, "t_str", STRENGTH_RK)
    # Wednesday 2026-09-09 → Mon–Sun week is 09-07..09-13.
    _workout(db_session, u.id, "w1", datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc), ["t_str"])

    res = resolver.resolve(db_session, u.id, today=date(2026, 9, 9))
    assert res["window"]["source"] == "weekly"
    assert res["window"]["start_date"] == "2026-09-07" and res["window"]["end_date"] == "2026-09-13"
    by_cap = {s["capacity"]: s for s in res["slots"]}
    assert by_cap["strength"]["done"] == 1


def test_phase_with_microcycle_wins_over_weekly(db_session):
    u = _user(db_session)
    profile_mod.upsert_profile(db_session, u.id, {"weekly_template": {"slots": [
        {"capacity": "STRENGTH", "sessions_per_week": 2, "minutes": 45}]}})
    _phase(db_session, u.id, _micro(7, ("A", [("power", 2)])), MONDAY)
    res = resolver.resolve(db_session, u.id, today=date(2026, 9, 9))
    assert res["window"]["source"] == "phase"
    assert [s["capacity"] for s in res["slots"]] == ["power"]


def test_open_phase_without_microcycle_falls_back_to_weekly(db_session):
    u = _user(db_session)
    profile_mod.upsert_profile(db_session, u.id, {"weekly_template": {"slots": [
        {"capacity": "STRENGTH", "sessions_per_week": 2, "minutes": 45}]}})
    _phase(db_session, u.id, None, MONDAY)   # open phase, no microcycle
    res = resolver.resolve(db_session, u.id, today=date(2026, 9, 9))
    assert res["window"]["source"] == "weekly"


def test_baseline_no_phase_no_profile_is_null_window(db_session):
    u = _user(db_session)
    res = resolver.resolve(db_session, u.id, today=date(2026, 9, 9))
    assert res == {"window": None, "slots": [], "due_capacity": None, "uncounted": []}


# --------------------------------------------------------------------------- #
# Rule 4 — due slot                                                           #
# --------------------------------------------------------------------------- #

def test_due_capacity_is_first_unmet_in_declared_order(db_session):
    u = _user(db_session)
    _tpl(db_session, "t_str", STRENGTH_RK)
    d = datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc)
    _phase(db_session, u.id, _micro(7, ("A", [("strength", 2), ("stability", 2)])), MONDAY)

    # No work → strength (first) is due.
    assert resolver.resolve(db_session, u.id, today=date(2026, 9, 9))["due_capacity"] == "strength"

    # Meet strength (2 sessions) → stability becomes due.
    _workout(db_session, u.id, "s1", d, ["t_str"])
    _workout(db_session, u.id, "s2", d, ["t_str"])
    res = resolver.resolve(db_session, u.id, today=date(2026, 9, 9))
    assert res["slots"][0]["remaining"] == 0
    assert res["due_capacity"] == "stability"


def test_due_capacity_none_when_every_slot_met(db_session):
    u = _user(db_session)
    _tpl(db_session, "t_str", STRENGTH_RK)
    _tpl(db_session, "t_stab", STABILITY_RK)
    d = datetime(2026, 9, 8, 9, 0, tzinfo=timezone.utc)
    _phase(db_session, u.id, _micro(7, ("A", [("strength", 1), ("stability", 1)])), MONDAY)
    _workout(db_session, u.id, "s1", d, ["t_str"])
    _workout(db_session, u.id, "b1", d, ["t_stab"])
    res = resolver.resolve(db_session, u.id, today=date(2026, 9, 9))
    assert res["due_capacity"] is None
    assert all(s["remaining"] == 0 for s in res["slots"])


# --------------------------------------------------------------------------- #
# HTTP — /engine/next default-to-due vs explicit, and /engine/resolver        #
# --------------------------------------------------------------------------- #

from fastapi import FastAPI                       # noqa: E402
from fastapi.testclient import TestClient         # noqa: E402

from auth import get_current_user                 # noqa: E402
from database import get_db                       # noqa: E402
from routers import engine as engine_router       # noqa: E402


def _client(db, user):
    app = FastAPI()
    app.include_router(engine_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_http_next_defaults_to_due_slot_and_explicit_wins(db_session):
    u = _user(db_session)
    # Anchor the phase to the real Brisbane today so the endpoint's own `_local_day()` window
    # contains it (the endpoint does not take an injected `today`).
    now = datetime.now(timezone.utc)
    today = _local_day(now)
    _phase(db_session, u.id, _micro(7, ("A", [("strength", 2), ("stability", 2)])), today)
    c = _client(db_session, u)

    # No capacity param → the resolver's due slot (strength, nothing done) is applied.
    default = c.get("/engine/next")
    assert default.status_code == 200, default.text
    assert default.json()["slot"]["capacity"] == "strength"

    # Explicit capacity still wins, unchanged.
    explicit = c.get("/engine/next", params={"capacity": "STABILITY"})
    assert explicit.json()["slot"]["capacity"] == "stability"


def test_http_next_unfiltered_when_no_due_slot(db_session):
    u = _user(db_session)
    now = datetime.now(timezone.utc)
    today = _local_day(now)
    _tpl(db_session, "t_str", STRENGTH_RK)
    _tpl(db_session, "t_stab", STABILITY_RK)
    _phase(db_session, u.id, _micro(7, ("A", [("strength", 1), ("stability", 1)])), today)
    _workout(db_session, u.id, "s1", now, ["t_str"])
    _workout(db_session, u.id, "b1", now, ["t_stab"])
    c = _client(db_session, u)

    # Every slot met → due None → default /next is unfiltered (no slot block), today's behaviour.
    r = c.get("/engine/next")
    assert r.status_code == 200, r.text
    assert "slot" not in r.json()


def test_http_resolver_endpoint_and_baseline_null_window(db_session):
    u = _user(db_session)
    now = datetime.now(timezone.utc)
    today = _local_day(now)
    _phase(db_session, u.id, _micro(7, ("A", [("strength", 2)])), today)
    c = _client(db_session, u)
    r = c.get("/engine/resolver")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["window"]["source"] == "phase"
    assert body["due_capacity"] == "strength"

    # A fresh user at baseline → null window, still 200.
    u2 = _user(db_session, email="baseline@example.com")
    c2 = _client(db_session, u2)
    r2 = c2.get("/engine/resolver")
    assert r2.status_code == 200
    assert r2.json() == {"window": None, "slots": [], "due_capacity": None, "uncounted": []}
