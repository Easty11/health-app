"""A slot CLAIMS a session to count it; load accrues from the device data whichever slot (or none) claimed it.

Q210 ruled option (a) on 4 Oct 2026: per-category counts through `activity` slots, which claim first; one
`metabolic` load_window slot for the remainder; and load deposits for every device session regardless of the
claim -- with no validator or resolver change. That ruling rests on two facts, pinned here so a later change
that breaks either fails a test instead of silently dropping load or inflating a count:

  1. The claim is exclusive and ordered (the resolver): one session counts in at most one slot, activity
     slots first, so an aggregate metabolic slot counts only the REMAINDER.
  2. The load transform reads `aerobic_sessions` directly and never consults a phase or a slot, so the
     same sessions deposit the same load with the slots declared, with different slots, or with no phase.

Fixtures reuse `test_activity_slots` (same sessions, same zones: 600 s in zone 2 and 600 s in zone 3 is an
Edwards TRIMP of 10*2 + 10*3 = 50).
"""
from datetime import date, datetime, timezone

import load_events_metabolic as lem
import models
from engine import resolver
from tests.test_activity_slots import (
    MONDAY, TODAY, _act_slot, _aerobic, _lw_slot, _one_cycle, _phase, _user,
)


def _session(db, uid, sid, day, sport, hour=6):
    return _aerobic(
        db, uid, sid, day,
        start=datetime(day.year, day.month, day.day, hour, 0, tzinfo=timezone.utc),
        stop=datetime(day.year, day.month, day.day, hour, 45, tzinfo=timezone.utc),
        sport=sport, duration=45.0, zones=(0, 600, 600, 0, 0))


def _three_sessions(db, uid):
    return {
        "run": _session(db, uid, "run1", date(2026, 9, 8), "Running"),
        "bike": _session(db, uid, "bike1", date(2026, 9, 9), "Cycling"),
        "row": _session(db, uid, "row1", date(2026, 9, 10), "Rowing"),
    }


def _events(db, uid):
    rows = (db.query(models.LoadEvent)
            .filter_by(user_id=uid, formula_version=lem.FORMULA_VERSION_METABOLIC).all())
    return {int(e.source_ref): e for e in rows}


def _aggregate_plus_activity_slots():
    return _one_cycle(
        _lw_slot(["Running", "Cycling", "Rowing"], q=3),     # the aggregate over every conditioning sport
        _act_slot("run", ["Running"], q=1),                  # per-category counts, which claim first
        _act_slot("bike", ["Cycling"], q=1),
    )


def test_an_activity_slot_claims_its_sessions_so_the_metabolic_slot_counts_only_the_remainder(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _aggregate_plus_activity_slots(), MONDAY)
    _three_sessions(db_session, u.id)
    res = resolver.resolve(db_session, u.id, today=TODAY)
    by = {(s["kind"], s.get("activity") or s.get("load_window")): s for s in res["slots"]}
    assert by[("activity", "run")]["done"] == 1 and by[("activity", "bike")]["done"] == 1
    lw = by[("load_window", "metabolic")]
    assert lw["done"] == 1                                    # the rowing session only: 3 sessions, 2 claimed first
    assert [c["sport_name"] for c in lw["sessions_counted"]] == ["Rowing"]
    # One session, one slot: the three sessions are counted exactly three times across all slots.
    assert sum(s["done"] for s in res["slots"]) == 3
    assert res["uncounted"] == []


def test_load_deposits_for_every_device_session_whichever_slot_claimed_it(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _aggregate_plus_activity_slots(), MONDAY)
    ids = _three_sessions(db_session, u.id)
    lem.compute_all_users_metabolic(db_session, only_user_id=u.id)
    ev = _events(db_session, u.id)
    assert set(ev) == set(ids.values())                       # the activity-claimed run and bike deposit too
    assert {round(e.load, 1) for e in ev.values()} == {50.0}  # same zones, same TRIMP, claim or no claim
    assert {e.unit for e in ev.values()} == {"trimp_edw_au"}


def test_the_load_is_identical_with_other_slots_and_with_no_phase_at_all(db_session):
    """The load transform never reads a slot: declare different slots, or none, and the events are the same."""
    u = _user(db_session)
    ids = _three_sessions(db_session, u.id)
    lem.compute_all_users_metabolic(db_session, only_user_id=u.id)
    no_phase = {k: round(e.load, 1) for k, e in _events(db_session, u.id).items()}       # no phase declared

    _phase(db_session, u.id, _one_cycle(_act_slot("run", ["Running"], q=1)), MONDAY)       # one activity slot only
    lem.compute_all_users_metabolic(db_session, only_user_id=u.id)
    one_slot = {k: round(e.load, 1) for k, e in _events(db_session, u.id).items()}

    assert no_phase == one_slot == {sid: 50.0 for sid in ids.values()}


def test_a_session_no_slot_names_is_uncounted_but_still_deposits_load(db_session):
    u = _user(db_session)
    _phase(db_session, u.id, _one_cycle(_act_slot("run", ["Running"], q=1)), MONDAY)
    run = _session(db_session, u.id, "run1", date(2026, 9, 8), "Running")
    walk = _session(db_session, u.id, "walk1", date(2026, 9, 9), "Walking")        # no slot names Walking
    res = resolver.resolve(db_session, u.id, today=TODAY)
    assert [u_["reason"] for u_ in res["uncounted"]] == ["unclaimed_session"]
    lem.compute_all_users_metabolic(db_session, only_user_id=u.id)
    assert set(_events(db_session, u.id)) == {run, walk}                          # counted or not, both deposit
