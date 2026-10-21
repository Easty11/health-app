"""A schedule item links to its quota slot on the folded key (21 Oct 2026, the Tue Pilates item).

The slot was `Pilates`, the Tuesday item was stored `activity:pilates`, and `consistency_rows` compared the
two with `==`: the plan read `scheduled 1 / quota 2 / unplaced 1` for a week with both classes placed. The
resolver counted both sessions (it matches on `device_sports`), so only the schedule-to-quota link broke.
Everything else in the system already treats the key as case-insensitive; `consistency_rows` was the
outlier. These pin the read-side fold (`norm_slot_key`), the write-side spelling
(`canonical_satisfies`, reached through `_stage_upsert_entry`) and the prompt wording.
"""
from __future__ import annotations

from datetime import timedelta

import models
from context_builder import _section_user_profile
from engine import week_plan
from engine.training_phase import _local_day
from routers.knowledge import KnowledgeEntryIn, _stage_upsert_entry
from tests.phase_fixtures import open_phase

TODAY = _local_day()
ENTERED = (TODAY - timedelta(days=3)).isoformat()


def _user(db, email="fold@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _open(db, uid, *slot_lists):
    """Open a phase whose sub-cycles carry the given slot lists (one list per sub-cycle)."""
    subs = [{"label": "ABCD"[i], "slots": slots} for i, slots in enumerate(slot_lists)]
    return open_phase(db, uid, {
        "label": "base", "probe_posture": "held", "vehicle_ranking": "standard",
        "microcycle": {"sub_cycle_days": 7, "sub_cycles": subs},
        "entered_on": ENTERED, "asserted_by": "user", "asserted_on": ENTERED, "source": "api",
    })


def _pilates(name="Pilates", q=2):
    return {"activity": name, "device_sports": ["Pilates"], "sessions_per_cycle": q, "minutes": 50}


def _item(**over):
    base = {"activity": "class", "days": ["tuesday"], "hard": False, "expected_load": "light",
            "time_of_day": "evening", "same_day_training": False, "duration_weeks": None,
            "season_end": None}
    base.update(over)
    return base


# ---- read side: consistency_rows compares the folded key ------------------------------------------

def test_activity_link_in_another_case_counts_as_scheduled():
    """The 21 Oct case, verbatim: slot `Pilates`, items `Pilates` and `pilates`, one session a week each."""
    slots = [{"kind": "activity", "activity": "Pilates", "quota": 2, "done": 2}]
    items = [{"satisfies": {"activity": "Pilates"}, "sessions_per_week": 1},
             {"satisfies": {"activity": "pilates"}, "sessions_per_week": 1}]
    row = week_plan.consistency_rows(slots, items)[0]
    assert (row["scheduled"], row["unplaced"], row["excess"]) == (2, 0, 0)


def test_capacity_link_in_the_validators_uppercase_spelling_counts():
    """`resolve_capacity` accepts `STRENGTH` (the error message advertises uppercase names), the resolver
    emits `strength`; an uppercase link must still reach its slot."""
    slots = [{"kind": "capacity", "capacity": "strength", "quota": 3, "done": 1}]
    items = [{"satisfies": {"capacity": "STRENGTH"}, "sessions_per_week": 3}]
    assert week_plan.consistency_rows(slots, items)[0]["scheduled"] == 3


def test_stray_whitespace_does_not_orphan_a_link():
    slots = [{"kind": "activity", "activity": "Pilates", "quota": 1, "done": 0}]
    items = [{"satisfies": {"activity": "  pilates "}, "sessions_per_week": 1}]
    assert week_plan.consistency_rows(slots, items)[0]["scheduled"] == 1


def test_a_different_key_still_does_not_match():
    """The fold is case and padding only: `swim` is not `Pilates`, and a kind mismatch is not a match."""
    slots = [{"kind": "activity", "activity": "Pilates", "quota": 1, "done": 0}]
    items = [{"satisfies": {"activity": "swim"}, "sessions_per_week": 1},
             {"satisfies": {"capacity": "pilates"}, "sessions_per_week": 1}]
    assert week_plan.consistency_rows(slots, items)[0]["scheduled"] == 0


def test_plan_week_states_no_unplaced_for_the_21_oct_week(db_session):
    """Through `plan_week`, as the UI and `get_training_plan` read it: both Pilates items placed → unplaced 0."""
    u = _user(db_session)
    _open(db_session, u.id, [_pilates(q=2)])
    for key, days, spelled in (("pilates_sat", ["saturday"], "Pilates"), ("pilates_tue", ["tuesday"], "pilates")):
        db_session.add(models.UserKnowledgeEntry(
            user_id=u.id, type="schedule_item", key=key, active=True, source="api",
            value=_item(activity="Pilates - General Class", days=days, satisfies={"activity": spelled})))
    db_session.commit()
    plan = week_plan.plan_week(db_session, u.id, TODAY)
    row = next(r for r in plan["keys"] if r["kind"] == "activity")
    assert (row["scheduled"], row["quota"], row["unplaced"]) == (2, 2, 0)
    assert plan["needs_planning"] is False


# ---- write side: store the slot's own spelling -------------------------------------------------------

def _write(db, uid, key, **over):
    row = _stage_upsert_entry(uid, KnowledgeEntryIn(
        type="schedule_item", key=key, source="api", value=_item(**over)), db)
    db.commit()
    return row.value["satisfies"]


def test_activity_link_is_stored_in_the_declared_slots_spelling(db_session):
    u = _user(db_session)
    _open(db_session, u.id, [_pilates("Pilates")])
    assert _write(db_session, u.id, "tue", satisfies={"activity": "pilates"}) == {"activity": "Pilates"}


def test_the_slots_own_spelling_is_kept_when_it_is_lowercase(db_session):
    """Canonical means the slot's spelling, not lowercase: a slot declared `pilates` stores `pilates`."""
    u = _user(db_session)
    _open(db_session, u.id, [_pilates("pilates")])
    assert _write(db_session, u.id, "tue", satisfies={"activity": "PILATES"}) == {"activity": "pilates"}


def test_a_slot_in_a_later_sub_cycle_is_matched(db_session):
    u = _user(db_session)
    _open(db_session, u.id, [{"capacity": "stability", "sessions_per_cycle": 1, "minutes": 30}],
          [_pilates("Pilates")])
    assert _write(db_session, u.id, "tue", satisfies={"activity": "pilates"}) == {"activity": "Pilates"}


def test_capacity_link_is_stored_as_the_tokens_value(db_session):
    u = _user(db_session)
    assert _write(db_session, u.id, "gym", activity="gym", satisfies={"capacity": "STRENGTH"}) == {"capacity": "strength"}


def test_a_link_matching_no_slot_is_stored_as_written_and_not_refused(db_session):
    """No match keeps today's behaviour: the link may be written before its phase exists."""
    u = _user(db_session)
    _open(db_session, u.id, [_pilates("Pilates")])
    assert _write(db_session, u.id, "swim", activity="swim", satisfies={"activity": "Swim"}) == {"activity": "Swim"}


def test_a_write_with_no_open_phase_and_no_template_is_unchanged(db_session):
    u = _user(db_session)
    assert _write(db_session, u.id, "tue", satisfies={"activity": "pilates"}) == {"activity": "pilates"}


def test_an_unlinked_item_still_writes_without_a_satisfies_key(db_session):
    u = _user(db_session)
    row = _stage_upsert_entry(u.id, KnowledgeEntryIn(
        type="schedule_item", key="walk", source="api", value=_item(activity="walk")), db_session)
    assert "satisfies" not in row.value or row.value["satisfies"] is None


# ---- the prompt no longer teaches a lowercase key ---------------------------------------------------

def test_the_coach_prompt_says_to_copy_the_slot_key_verbatim():
    text = _section_user_profile(None)
    assert "Copy the slot key" in text and "verbatim" in text
    assert '"activity": "pilates"' not in text
