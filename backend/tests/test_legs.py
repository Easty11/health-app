"""Know (d) — the leg wrap: `resolver.past_legs`, `GET /engine/legs`, the injected-window `resolve`,
and the widened `week-plan` day items.

GATES (operator rulings R1-R7, the leg-strip / leg-wrap brief):
  R2  a past leg compares QUOTA vs DONE per slot key — and the quota is the one ITS phase declared.
      Mutation control: swapping `phase_at` for `current_training_phase` in the walk must change the
      answer (`test_mutation_current_phase_for_phase_at_changes_the_answer`), so the test above it
      discriminates rather than passing on a ledger with one phase.
  R3  only legs of a phase with a microcycle; weekly-template periods are excluded and the payload
      says so.
  R4  a leg cut short by a phase change is `partial` with its actual dates, never stretched; a
      zero-length row (#379) never produces a leg (paired with a one-day row that DOES).
  R5  derived and stateless: the walk reads, nothing is written.
  `resolve(window=None)` is byte-identical to the current behaviour (golden literal + equality with the
  same window injected); `resolve(today=<past>)` alone still counts against TODAY's phase, which is
  why the wrap injects a window instead.

The ledgers use fixed dates with an explicit `today`, so none of them depends on the clock.
"""
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from engine import profile as profile_mod
from engine import resolver as resolver_mod
from engine import training_phase as phase_mod
from engine import week_plan as week_plan_mod
from load_metrics import _local_day
from routers import engine as engine_router
from tests.phase_fixtures import open_phase

STABILITY_RK = "anti_rotation"   # capacity: stability
STRENGTH_RK = "hinge"            # capacity: strength


def _user(db, email="legs@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _micro(*slots, days=7, label="A"):
    return {"sub_cycle_days": days, "sub_cycles": [{"label": label, "slots": [
        {"capacity": cap, "sessions_per_cycle": q, "minutes": 30} for cap, q in slots]}]}


def _open(db, uid, label, entered_on, microcycle=None):
    payload = {
        "label": label, "probe_posture": "held", "entered_on": str(entered_on),
        "asserted_by": "user", "asserted_on": str(entered_on), "source": "api",
    }
    if microcycle is not None:
        payload["microcycle"] = microcycle
    return open_phase(db, uid, payload)


def _tpl(db, tid, region_key):
    db.add(models.HevyExerciseTemplate(id=tid, title=tid, is_custom=True, owner_user_id=None))
    db.flush()
    db.add(models.ExerciseRegionTag(
        hevy_exercise_template_id=tid, region_key=region_key, role="primary", source="human_confirmed",
    ))
    db.flush()


def _workout(db, uid, hevy_id, day, tid):
    """A counted workout at 09:00 Brisbane on `day` (23:00Z the day before)."""
    start = datetime.combine(day - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=23)
    db.add(models.HevyWorkout(
        hevy_id=hevy_id, user_id=uid, start_time=start, title="W",
        raw={"id": hevy_id, "exercises": [{"exercise_template_id": tid, "title": tid}]},
    ))
    db.commit()


def _two_phase_ledger(db, uid):
    """P1 (stability x2) 3 Aug -> closed Fri 4 Sep; P2 (strength x3) from 4 Sep, open. Weekly legs."""
    _tpl(db, "t_stab", STABILITY_RK)
    _tpl(db, "t_str", STRENGTH_RK)
    p1 = _open(db, uid, "block-1", date(2026, 8, 3), _micro(("stability", 2)))
    p2 = _open(db, uid, "block-2", date(2026, 9, 4), _micro(("strength", 3)))
    return p1, p2


TODAY = date(2026, 9, 20)   # P2 leg 2 is current: 09-18..09-24 (P2 entered Fri 4 Sep)


# ── R2: a past leg counts against ITS phase's quota ──────────────────────────

def test_a_leg_in_a_prior_phase_counts_against_that_phases_quota(db_session):
    u = _user(db_session)
    _two_phase_ledger(db_session, u.id)
    # Two stability sessions in P1's leg 08-24..08-30, one in the leg before (08-17..08-23).
    _workout(db_session, u.id, "s1", date(2026, 8, 25), "t_stab")
    _workout(db_session, u.id, "s2", date(2026, 8, 27), "t_stab")
    _workout(db_session, u.id, "s3", date(2026, 8, 18), "t_stab")
    # A strength session in P2's first leg 09-04..09-10.
    _workout(db_session, u.id, "g1", date(2026, 9, 5), "t_str")

    out = resolver_mod.past_legs(db_session, u.id, n=6, today=TODAY)
    legs = {leg["start_date"]: leg for leg in out["legs"]}

    p1_leg = legs["2026-08-24"]
    assert p1_leg["phase"]["label"] == "block-1"
    assert [(k["kind"], k["key"], k["quota"], k["done"]) for k in p1_leg["keys"]] == [
        ("capacity", "stability", 2, 2)]          # P1's quota (2), not P2's strength x3

    p2_leg = legs["2026-09-04"]
    assert p2_leg["phase"]["label"] == "block-2"
    assert [(k["kind"], k["key"], k["quota"], k["done"]) for k in p2_leg["keys"]] == [
        ("capacity", "strength", 3, 1)]


def test_mutation_current_phase_for_phase_at_changes_the_answer(db_session, monkeypatch):
    """The control for the test above: with `phase_at` replaced by `current_training_phase` (every
    past leg counted against TODAY's phase) the P1 leg is wrong. If this stops differing, the test
    above no longer discriminates."""
    u = _user(db_session)
    _two_phase_ledger(db_session, u.id)
    _workout(db_session, u.id, "s1", date(2026, 8, 25), "t_stab")

    right = resolver_mod.past_legs(db_session, u.id, n=4, today=TODAY)
    monkeypatch.setattr(
        resolver_mod, "phase_at",
        lambda db, uid, d: phase_mod.current_training_phase(db, uid),
    )
    wrong = resolver_mod.past_legs(db_session, u.id, n=4, today=TODAY)

    assert wrong != right
    assert "block-1" in {leg["phase"]["label"] for leg in right["legs"]}
    assert "block-1" not in {leg["phase"]["label"] for leg in wrong["legs"]}


def test_resolve_with_a_past_today_alone_counts_against_todays_phase(db_session):
    """(d) pinned: `resolve(today=<past>)` reads the OPEN phase, so it is the wrong tool for a past
    leg — the wrap injects a window instead."""
    u = _user(db_session)
    _two_phase_ledger(db_session, u.id)
    res = resolver_mod.resolve(db_session, u.id, today=date(2026, 8, 25))   # a P1 day
    assert [s["capacity"] for s in res["slots"]] == ["strength"]            # P2's slot, not P1's


# ── delta_done ───────────────────────────────────────────────────────────────

def test_delta_done_is_against_the_chronologically_previous_leg_for_shared_keys(db_session):
    u = _user(db_session)
    _two_phase_ledger(db_session, u.id)
    _workout(db_session, u.id, "s1", date(2026, 8, 18), "t_stab")                 # leg 08-17: 1
    _workout(db_session, u.id, "s2", date(2026, 8, 25), "t_stab")                 # leg 08-24: 2
    _workout(db_session, u.id, "s3", date(2026, 8, 26), "t_stab")

    legs = {l["start_date"]: l for l in resolver_mod.past_legs(db_session, u.id, n=6, today=TODAY)["legs"]}
    delta = lambda start: legs[start]["keys"][0]["delta_done"]
    assert delta("2026-08-24") == 2 - 1                  # vs 08-17 (1)
    assert delta("2026-08-17") == 1 - 0                  # vs 08-10 (0)
    # A partial leg is compared as it stands (0 done in 4 days vs 2): the row carries `partial`, the
    # delta is not adjusted for it.
    assert legs["2026-08-31"]["partial"] is True and delta("2026-08-31") == 0 - 2
    # Across the phase change the keys differ (strength vs stability): nothing to compare.
    assert delta("2026-09-04") is None
    # Within P2 the same key is shared: leg 09-11 vs leg 09-04 (1 strength session on 5 Sep).
    _workout(db_session, u.id, "g1", date(2026, 9, 5), "t_str")
    again = {l["start_date"]: l for l in resolver_mod.past_legs(db_session, u.id, n=6, today=TODAY)["legs"]}
    assert again["2026-09-11"]["keys"][0]["delta_done"] == 0 - 1


def test_oldest_returned_leg_carries_a_delta_from_the_leg_beyond_n(db_session):
    u = _user(db_session)
    _two_phase_ledger(db_session, u.id)
    _workout(db_session, u.id, "a", date(2026, 8, 18), "t_stab")
    _workout(db_session, u.id, "b", date(2026, 8, 25), "t_stab")
    _workout(db_session, u.id, "c", date(2026, 8, 26), "t_stab")
    out = resolver_mod.past_legs(db_session, u.id, n=4, today=TODAY)
    assert [leg["start_date"] for leg in out["legs"]][-1] == "2026-08-24"
    assert out["legs"][-1]["keys"][0]["delta_done"] == 1                          # 2 vs 08-17's 1


def test_previous_partial_names_whether_the_predecessor_was_cut_short(db_session):
    """R8's input: the page withholds a delta against a partial leg, including for the oldest returned
    row, whose predecessor is the leg beyond `n`."""
    u = _user(db_session)
    _two_phase_ledger(db_session, u.id)
    flags = lambda n: {l["start_date"]: l["previous_partial"]
                       for l in resolver_mod.past_legs(db_session, u.id, n=n, today=TODAY)["legs"]}
    wide = flags(6)
    assert wide["2026-09-04"] is True          # predecessor 08-31..09-03 was cut by the phase change
    assert wide["2026-09-11"] is False         # predecessor 09-04..09-10 is a full leg
    assert wide["2026-08-31"] is False         # predecessor 08-24..08-30 is full
    # The oldest RETURNED row still knows: its predecessor is counted though not returned.
    assert flags(2) == {"2026-09-11": False, "2026-09-04": True}
    assert flags(3)["2026-08-31"] is False
    # Start of the ledger: no predecessor at all.
    only = _user(db_session, "ledger-start@example.com")
    _open(db_session, only.id, "only", date(2026, 9, 7), _micro(("stability", 2)))
    got = resolver_mod.past_legs(db_session, only.id, n=26, today=date(2026, 9, 25))["legs"]
    assert got[-1]["previous_partial"] is None


# ── R4: partial, never stretched; zero-length never a leg ────────────────────

def test_a_leg_cut_short_by_a_phase_change_is_partial_with_its_actual_dates(db_session):
    u = _user(db_session)
    _two_phase_ledger(db_session, u.id)        # P1 closes Fri 4 Sep; its leg 08-31..09-06 is cut
    legs = resolver_mod.past_legs(db_session, u.id, n=6, today=TODAY)["legs"]
    by_start = {leg["start_date"]: leg for leg in legs}

    cut = by_start["2026-08-31"]
    assert cut["partial"] is True
    assert cut["end_date"] == "2026-09-03"     # the day before closed_on; not 09-06
    assert cut["phase"]["label"] == "block-1"
    assert by_start["2026-08-24"]["partial"] is False
    assert by_start["2026-09-04"]["partial"] is False
    # P2's first leg starts on its own entered_on; the two never overlap or merge.
    assert by_start["2026-09-04"]["end_date"] == "2026-09-10"
    assert [leg["start_date"] for leg in legs] == [
        "2026-09-11", "2026-09-04", "2026-08-31", "2026-08-24", "2026-08-17", "2026-08-10"]


def test_a_workout_after_the_close_is_not_counted_in_the_partial_leg(db_session):
    u = _user(db_session)
    _two_phase_ledger(db_session, u.id)
    _workout(db_session, u.id, "in", date(2026, 9, 3), "t_stab")     # last day of the cut leg
    _workout(db_session, u.id, "out", date(2026, 9, 5), "t_stab")    # P2's day: off-plan there
    legs = {l["start_date"]: l for l in resolver_mod.past_legs(db_session, u.id, n=6, today=TODAY)["legs"]}
    assert legs["2026-08-31"]["keys"][0]["done"] == 1


def test_a_zero_length_row_yields_no_leg_but_a_one_day_row_does(db_session):
    # Zero-length: P1 -> z opened and replaced on the SAME day (z closes 4 Sep, entered 4 Sep) -> P2.
    zero = _user(db_session, "zero@example.com")
    _open(db_session, zero.id, "block-1", date(2026, 8, 3), _micro(("stability", 2)))
    _open(db_session, zero.id, "z-oops", date(2026, 9, 4), _micro(("power", 9)))
    _open(db_session, zero.id, "block-2", date(2026, 9, 4), _micro(("strength", 3)))
    z = db_session.query(models.TrainingPhase).filter_by(user_id=zero.id, label="z-oops").one()
    assert z.entered_on == z.closed_on == date(2026, 9, 4)          # the fixture really holds one

    got = resolver_mod.past_legs(db_session, zero.id, n=8, today=TODAY)["legs"]
    assert "z-oops" not in {l["phase"]["label"] for l in got}
    assert "power" not in {k["key"] for l in got for k in l["keys"]}

    # Control: the same ledger with z one day long DOES surface, as a one-day partial leg.
    one = _user(db_session, "one@example.com")
    _open(db_session, one.id, "block-1", date(2026, 8, 3), _micro(("stability", 2)))
    _open(db_session, one.id, "z-oops", date(2026, 9, 4), _micro(("power", 9)))
    _open(db_session, one.id, "block-2", date(2026, 9, 5), _micro(("strength", 3)))
    got1 = resolver_mod.past_legs(db_session, one.id, n=8, today=TODAY)["legs"]
    z_leg = next(l for l in got1 if l["phase"]["label"] == "z-oops")
    assert (z_leg["start_date"], z_leg["end_date"], z_leg["partial"]) == ("2026-09-04", "2026-09-04", True)


# ── R3: phases with a microcycle only; the weekly template is excluded ───────

def test_template_only_history_yields_no_legs_and_says_why(db_session):
    u = _user(db_session)
    profile_mod.upsert_profile(db_session, u.id, {"weekly_template": {"slots": [
        {"capacity": "STRENGTH", "sessions_per_week": 2, "minutes": 45}]}})
    out = resolver_mod.past_legs(db_session, u.id, n=8, today=TODAY)
    assert out["legs"] == []
    assert "weekly-template" in out["excluded"] and "not versioned" in out["excluded"]


def test_a_phase_without_a_microcycle_is_stepped_over_and_a_baseline_gap_is_jumped(db_session):
    u = _user(db_session)
    _tpl(db_session, "t_stab", STABILITY_RK)
    _open(db_session, u.id, "block-1", date(2026, 8, 3), _micro(("stability", 2)))
    _open(db_session, u.id, "plain", date(2026, 8, 24))                          # no microcycle
    phase_mod.close_phase(db_session, u.id, "to baseline")                        # closes today (real clock)
    plain = db_session.query(models.TrainingPhase).filter_by(user_id=u.id, label="plain").one()
    plain.closed_on = date(2026, 9, 1)                                            # then a baseline gap
    db_session.commit()
    _workout(db_session, u.id, "s1", date(2026, 8, 18), "t_stab")

    legs = resolver_mod.past_legs(db_session, u.id, n=8, today=TODAY)["legs"]
    # block-1 closed 24 Aug (entered 3 Aug): legs 3, 10, 17 Aug, the last (17-23) full; "plain" absent.
    assert [l["start_date"] for l in legs] == ["2026-08-17", "2026-08-10", "2026-08-03"]
    assert {l["phase"]["label"] for l in legs} == {"block-1"}
    assert legs[0]["keys"][0]["done"] == 1


def test_stops_at_the_start_of_the_ledger(db_session):
    u = _user(db_session)
    _open(db_session, u.id, "only", date(2026, 9, 7), _micro(("stability", 2)))
    out = resolver_mod.past_legs(db_session, u.id, n=26, today=date(2026, 9, 25))
    assert [l["start_date"] for l in out["legs"]] == ["2026-09-14", "2026-09-07"]
    assert out["legs"][-1]["keys"][0]["delta_done"] is None
    empty = _user(db_session, "empty@example.com")
    assert resolver_mod.past_legs(db_session, empty.id, n=8, today=TODAY)["legs"] == []


def test_a_weekly_template_current_window_does_not_hide_the_phase_legs_behind_it(db_session):
    """Baseline now (template running) but a microcycle phase ended earlier: its legs still come back."""
    u = _user(db_session)
    _open(db_session, u.id, "block-1", date(2026, 8, 3), _micro(("stability", 2)))
    phase_mod.close_phase(db_session, u.id, "to baseline")
    row = db_session.query(models.TrainingPhase).filter_by(user_id=u.id).one()
    row.closed_on = date(2026, 8, 17)
    db_session.commit()
    profile_mod.upsert_profile(db_session, u.id, {"weekly_template": {"slots": [
        {"capacity": "STRENGTH", "sessions_per_week": 2, "minutes": 45}]}})
    legs = resolver_mod.past_legs(db_session, u.id, n=8, today=TODAY)["legs"]
    assert [l["start_date"] for l in legs] == ["2026-08-10", "2026-08-03"]


# ── R5: stateless ────────────────────────────────────────────────────────────

def test_past_legs_writes_nothing(db_session):
    u = _user(db_session)
    _two_phase_ledger(db_session, u.id)
    _workout(db_session, u.id, "s1", date(2026, 8, 25), "t_stab")
    before = {m.__tablename__: db_session.query(m).count() for m in (
        models.TrainingPhase, models.HevyWorkout, models.UserKnowledgeEntry, models.AerobicSession)}
    db_session.expire_all()
    resolver_mod.past_legs(db_session, u.id, n=8, today=TODAY)
    assert not db_session.new and not db_session.dirty and not db_session.deleted
    after = {m.__tablename__: db_session.query(m).count() for m in (
        models.TrainingPhase, models.HevyWorkout, models.UserKnowledgeEntry, models.AerobicSession)}
    assert before == after


# ── resolve(window=None) is byte-identical ───────────────────────────────────

def test_resolve_current_path_is_byte_identical(db_session):
    u = _user(db_session)
    _tpl(db_session, "t_str", STRENGTH_RK)
    _open(db_session, u.id, "block-2", date(2026, 9, 7), _micro(("strength", 3), ("stability", 1)))
    _workout(db_session, u.id, "g1", date(2026, 9, 9), "t_str")

    got = resolver_mod.resolve(db_session, u.id, today=date(2026, 9, 10))
    assert got == {
        "window": {"start_date": "2026-09-07", "end_date": "2026-09-13", "label": "A", "source": "phase"},
        "slots": [
            {"kind": "capacity", "quota": 3, "done": 1, "remaining": 2,
             "capacity": "strength", "workouts_counted": ["g1"]},
            {"kind": "capacity", "quota": 1, "done": 0, "remaining": 1,
             "capacity": "stability", "workouts_counted": []},
        ],
        "due_capacity": "strength",
        "due_slot": {"kind": "capacity", "key": "strength"},
        "uncounted": [],
    }
    # And injecting the very window the producer would have built changes nothing.
    window = resolver_mod.resolve_window(db_session, u.id, date(2026, 9, 10))
    assert resolver_mod.resolve(db_session, u.id, today=date(2026, 9, 10), window=window) == got


# ── the widened week-plan keys ───────────────────────────────────────────────

def _sched(db, uid, key, value):
    db.add(models.UserKnowledgeEntry(
        user_id=uid, type="schedule_item", key=key, value=value, source="chat", active=True))
    db.commit()


def test_week_plan_widens_hard_and_flexible_items_additively(db_session):
    u = _user(db_session)
    _open(db_session, u.id, "block-2", date(2026, 9, 7), _micro(("strength", 2)))
    base = {"expected_load": "moderate", "time_of_day": "evening", "same_day_training": False,
            "duration_weeks": None, "season_end": None}
    _sched(db_session, u.id, "rugby", {
        **base, "activity": "rugby", "days": ["tuesday"], "hard": True, "expected_load": "heavy",
        "time_range": "18:00-20:00", "satisfies": {"activity": "rugby"}})
    _sched(db_session, u.id, "work", {**base, "activity": "work", "days": ["monday"], "hard": True,
                                      "expected_load": "none", "time_of_day": "morning"})
    _sched(db_session, u.id, "gym", {
        **base, "activity": "gym", "days": ["monday", "wednesday", "friday"], "hard": False,
        "sessions_per_week": 2, "satisfies": {"capacity": "strength"}, "time_range": "06:00-07:00"})
    _sched(db_session, u.id, "walk", {**base, "activity": "walk", "days": ["saturday", "sunday"],
                                      "hard": False})

    plan = week_plan_mod.plan_week(db_session, u.id, date(2026, 9, 9))
    days = {d["weekday"]: d for d in plan["days"]}

    rugby = days["tuesday"]["hard"][0]
    assert rugby == {
        "activity": "rugby", "expected_load": "heavy", "same_day_training": False,
        "satisfies": {"activity": "rugby"}, "time_of_day": "evening", "time_range": "18:00-20:00"}

    # No satisfies / no time_range on the item -> those keys are absent; the three old keys unchanged.
    work = days["monday"]["hard"][0]
    assert work == {"activity": "work", "expected_load": "none", "same_day_training": False,
                    "time_of_day": "morning"}

    # A flexible item carries its weekly count, repeats per candidate day, and keeps its old keys.
    for wd in ("monday", "wednesday", "friday"):
        gym = days[wd]["flexible"][0]
        assert gym["activity"] == "gym" and gym["satisfies"] == {"capacity": "strength"}
        assert gym["pool"] == 2                                   # sessions_per_week wins over len(days)
        assert gym["time_range"] == "06:00-07:00" and gym["time_of_day"] == "evening"
    walk = days["saturday"]["flexible"][0]
    assert walk["pool"] == 2 and walk["satisfies"] is None and "time_range" not in walk
    # The #316 top-level keys are untouched.
    assert set(plan) == {"window", "days", "keys", "unlinked_soft", "one_off_notes",
                         "needs_planning", "freshness"}
    assert set(days["monday"]) == {"date", "weekday", "hard", "flexible", "actual", "available", "caution"}


# ── the route ────────────────────────────────────────────────────────────────

def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(engine_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_legs_route_serves_past_legs_and_clamps_n(db_session):
    u = _user(db_session)
    # A long-running phase anchored relative to the clock, so the route's own `_local_day()` has
    # past legs to return whatever day it runs.
    start = _local_day() - timedelta(days=7 * 40)
    _open(db_session, u.id, "block-1", start, _micro(("stability", 2)))
    client = _client(db_session, u)

    r = client.get("/engine/legs")
    assert r.status_code == 200
    body = r.json()
    assert len(body["legs"]) == 8                                   # the default
    assert body["legs"][0]["start_date"] > body["legs"][1]["start_date"]   # newest first
    assert body["legs"][0]["keys"][0].keys() >= {"kind", "key", "quota", "done", "delta_done"}

    assert len(client.get("/engine/legs?n=500").json()["legs"]) == resolver_mod.LEGS_MAX == 26
    assert len(client.get("/engine/legs?n=0").json()["legs"]) == 1
