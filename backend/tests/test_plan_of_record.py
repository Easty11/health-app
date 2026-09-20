"""Plan of record + schedule↔quota link (#312, Q-none).

Gates G1–G6 for the plan-of-record brief:
  G1  `training_plan` validator + write (bound with MEASURED length, exactly-one-current via
      the fixed key, same-key supersede + retained predecessor, expires_at null, belt-and-braces
      rejection of a second active row under any other key; §18 mutation on the key guarantee).
  G2  `satisfies` validator (exactly one key; unknown capacity / load_window refused; an item
      without it validates byte-identically).
  G3  consistency line, DERIVED on read (scheduled vs quota vs done; MISMATCH/UNPLACED only on a
      7-day leg; a K≠7-day leg renders units and no mismatch claim; `done` from resolve(), never
      recounted; §18: computing `scheduled` from `done` collapses the MISMATCH → this fails).
  G4  render — plan section directly ABOVE the phase section; STALE line when due; the macro
      appears exactly ONCE in the whole context.
  G5  regression on the 18-Sep evidence — a carnival load_context + a Mon/Wed/Fri schedule +
      quota-met surfaces the carnival AND the MISMATCH, and the position asserts no phantom
      session (prompt BEHAVIOUR is not unit-testable; this asserts the INPUTS the coach sees).
  G6  S0(b) readers unchanged — `_section_schedule` is byte-identical when an item gains
      `satisfies` and when a `training_plan` row is present.
"""
from datetime import date

import pytest

import context_builder
import models
from current_state import CurrentState
from routers.knowledge import (
    KnowledgeEntryIn,
    TRAINING_PLAN_KEY,
    MACRO_MAX_CHARS,
    upsert_knowledge_entry,
    validate_schedule_item,
    validate_training_plan,
)


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #

def _user(db, email="por@example.com"):
    u = models.User(email=email, hashed_password="x", full_name="Plan Tester")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _plan_value(macro="Phase 1 base; buffer rule: sacrifice conditioning first; knee gate: fall back to bike.",
                revised_on="2026-09-01", revised_by="operator"):
    return {"macro": macro, "revised_on": revised_on, "revised_by": revised_by}


def _valid_item(**over):
    v = {
        "activity": "gym", "hard": False, "expected_load": "moderate",
        "time_of_day": "morning", "same_day_training": False,
        "duration_weeks": None, "season_end": None, "days": ["monday"],
    }
    v.update(over)
    return v


def _sched_entry(**over):
    """A schedule_item knowledge entry as a plain dict (the render sections read via
    getattr-or-.get, so a dict is faithful)."""
    return {"type": "schedule_item", "value": _valid_item(**over)}


_PHASE_STUB = {"label": "base", "probe_posture": "held", "capacities": None,
               "review_on": None, "review_due": False, "microcycle": None}


def _position(*, leg=("2026-09-07", "2026-09-13"), slots, source="phase"):
    return {
        "window": {"label": "A", "start_date": leg[0], "end_date": leg[1], "source": source},
        "slots": slots, "due_capacity": None, "due_slot": None, "uncounted": [],
    }


# --------------------------------------------------------------------------- #
# G1 — training_plan validator + write                                         #
# --------------------------------------------------------------------------- #

def test_training_plan_validator_shape():
    assert validate_training_plan(_plan_value()) == _plan_value()
    with pytest.raises(ValueError, match="unknown field"):
        validate_training_plan({**_plan_value(), "week": "x"})
    with pytest.raises(ValueError, match="missing required field"):
        validate_training_plan({"macro": "x", "revised_on": "2026-09-01"})
    with pytest.raises(ValueError, match="non-empty string"):
        validate_training_plan(_plan_value(macro="   "))
    with pytest.raises(ValueError, match="ISO date"):
        validate_training_plan(_plan_value(revised_on="01-09-2026"))
    with pytest.raises(ValueError, match="revised_by"):
        validate_training_plan(_plan_value(revised_by="system"))


def test_training_plan_macro_bound_names_the_measured_length():
    over = "x" * (MACRO_MAX_CHARS + 7)
    with pytest.raises(ValueError) as exc:
        validate_training_plan(_plan_value(macro=over))
    # G0 ruling 1: the error states the MEASURED length so the caller knows how far over it is.
    assert str(MACRO_MAX_CHARS + 7) in str(exc.value)
    assert str(MACRO_MAX_CHARS) in str(exc.value)
    # exactly the bound is accepted.
    validate_training_plan(_plan_value(macro="y" * MACRO_MAX_CHARS))


def test_training_plan_single_current_supersede_by_key(db_session):
    u = _user(db_session)
    first = upsert_knowledge_entry(
        u.id, KnowledgeEntryIn(type="training_plan", key=TRAINING_PLAN_KEY,
                               value=_plan_value(macro="first"), source="api"), db_session)
    second = upsert_knowledge_entry(
        u.id, KnowledgeEntryIn(type="training_plan", key=TRAINING_PLAN_KEY,
                               value=_plan_value(macro="second"), source="api"), db_session)
    rows = (db_session.query(models.UserKnowledgeEntry)
            .filter_by(user_id=u.id, type="training_plan").all())
    active = [r for r in rows if r.active]
    # exactly one current; the predecessor is retained (superseded_by names its successor).
    assert len(active) == 1 and active[0].id == second.id
    old = db_session.get(models.UserKnowledgeEntry, first.id)
    assert old.active is False and old.superseded_by == second.id
    assert old.value["macro"] == "first"     # history retrievable


def test_training_plan_rejects_wrong_key_and_nonnull_expiry(db_session):
    u = _user(db_session)
    # §18 (key guarantee): a plan under any OTHER key is refused — drop this check and a
    # second-key write would create a SECOND active plan.
    with pytest.raises(ValueError, match="key must be"):
        upsert_knowledge_entry(
            u.id, KnowledgeEntryIn(type="training_plan", key="macro_plan",
                                   value=_plan_value(), source="api"), db_session)
    with pytest.raises(ValueError, match="expires_at must be null"):
        upsert_knowledge_entry(
            u.id, KnowledgeEntryIn(type="training_plan", key=TRAINING_PLAN_KEY,
                                   value=_plan_value(), source="api",
                                   expires_at=date(2027, 1, 1)), db_session)


def test_training_plan_belt_and_braces_rejects_second_active_under_other_key(db_session):
    u = _user(db_session)
    # A stray active plan under a non-canonical key (as a backfill/direct-ORM write could leave).
    stray = models.UserKnowledgeEntry(
        user_id=u.id, type="training_plan", key="legacy_plan",
        value=_plan_value(macro="stray"), source="api", active=True)
    db_session.add(stray)
    db_session.commit()
    with pytest.raises(ValueError, match="already exists under key 'legacy_plan'"):
        upsert_knowledge_entry(
            u.id, KnowledgeEntryIn(type="training_plan", key=TRAINING_PLAN_KEY,
                                   value=_plan_value(), source="api"), db_session)


# --------------------------------------------------------------------------- #
# G2 — satisfies validator                                                     #
# --------------------------------------------------------------------------- #

def test_satisfies_capacity_and_load_window_accepted():
    validate_schedule_item(_valid_item(satisfies={"capacity": "stability"}))
    validate_schedule_item(_valid_item(satisfies={"load_window": "metabolic"}))
    validate_schedule_item(_valid_item(satisfies={"activity": "pilates"}))   # #315 — the third kind


def test_satisfies_unknown_values_and_shapes_refused():
    with pytest.raises(ValueError, match="unknown capacity"):
        validate_schedule_item(_valid_item(satisfies={"capacity": "cardio"}))
    with pytest.raises(ValueError, match="unknown load_window"):
        validate_schedule_item(_valid_item(satisfies={"load_window": "anaerobic"}))
    with pytest.raises(ValueError, match="exactly one key"):
        validate_schedule_item(_valid_item(satisfies={"capacity": "stability", "load_window": "metabolic"}))
    with pytest.raises(ValueError, match="exactly one key"):
        validate_schedule_item(_valid_item(satisfies={}))
    with pytest.raises(ValueError, match="unknown key"):
        validate_schedule_item(_valid_item(satisfies={"tempo": "z2"}))        # not a slot kind


def test_item_without_satisfies_validates_byte_identically():
    item = _valid_item()
    assert "satisfies" not in item
    assert validate_schedule_item(item) == item          # returned unchanged
    # a null satisfies is treated as unlinked (absent), also unchanged.
    item_null = _valid_item(satisfies=None)
    assert validate_schedule_item(item_null) == item_null


# --------------------------------------------------------------------------- #
# G3 — consistency line (derived on read)                                      #
# --------------------------------------------------------------------------- #

def test_consistency_mismatch_on_seven_day_leg():
    """Operator's live state: soft gym Mon/Wed/Fri LINKED to stability, quota 2 →
    scheduled 3 · quota 2 · done 2 · MISMATCH +1. §18: were `scheduled` computed from `done`
    (=2), there would be no MISMATCH and this fails."""
    pos = _position(slots=[{"kind": "capacity", "capacity": "stability", "quota": 2, "done": 2,
                            "remaining": 0, "workouts_counted": ["w1", "w2"]}])
    entries = [
        _sched_entry(activity="gym", days=["monday", "wednesday", "friday"],
                     satisfies={"capacity": "stability"}),
        _sched_entry(activity="mobility flow", days=["sunday"]),   # unlinked soft
    ]
    out = context_builder._section_training_phase(_PHASE_STUB, pos, entries)
    assert "Stability — scheduled 3/wk · quota 2 · done 2" in out
    assert "MISMATCH: scheduled exceeds quota by 1" in out
    assert "unlinked (soft, counted to no slot): mobility flow" in out


def test_consistency_days_are_candidates_not_a_count():
    """G0 ruling a: `sessions_per_week` when present wins over `len(days)` — {days=3, spw=2} → 2."""
    pos = _position(slots=[{"kind": "capacity", "capacity": "stability", "quota": 2, "done": 0,
                            "remaining": 2, "workouts_counted": []}])
    entries = [_sched_entry(days=["monday", "wednesday", "friday"], sessions_per_week=2,
                            satisfies={"capacity": "stability"})]
    out = context_builder._section_training_phase(_PHASE_STUB, pos, entries)
    assert "scheduled 2/wk · quota 2" in out
    assert "MISMATCH" not in out and "UNPLACED" not in out    # aligned


def test_consistency_unplaced_when_quota_exceeds_scheduled():
    pos = _position(slots=[{"kind": "capacity", "capacity": "strength", "quota": 3, "done": 0,
                            "remaining": 3, "workouts_counted": []}])
    entries = [_sched_entry(days=["tuesday"], satisfies={"capacity": "strength"})]   # scheduled 1
    out = context_builder._section_training_phase(_PHASE_STUB, pos, entries)
    assert "UNPLACED: 2 quota sessions has no scheduled slot" in out


def test_consistency_non_seven_day_leg_renders_units_no_mismatch():
    """G0 ruling c: a 10-day leg — scheduled is per-week, quota per-leg, so the two are shown
    with their units and NO mismatch is claimed."""
    pos = _position(leg=("2026-09-07", "2026-09-16"),   # 10 inclusive days
                    slots=[{"kind": "capacity", "capacity": "stability", "quota": 2, "done": 1,
                            "remaining": 1, "workouts_counted": ["w1"]}])
    entries = [_sched_entry(days=["monday", "wednesday", "friday"],
                            satisfies={"capacity": "stability"})]
    out = context_builder._section_training_phase(_PHASE_STUB, pos, entries)
    assert "scheduled 3/wk · quota 2 per 10-day leg · done 1" in out
    assert "MISMATCH" not in out and "UNPLACED" not in out


def test_consistency_absent_without_schedule_items_or_window():
    # No schedule items → no consistency block (keeps the golden byte-identical).
    pos = _position(slots=[{"kind": "capacity", "capacity": "stability", "quota": 2, "done": 0,
                            "remaining": 2, "workouts_counted": []}])
    assert "Schedule vs quota" not in context_builder._section_training_phase(_PHASE_STUB, pos, [])
    # Null window → no line even with schedule items.
    baseline = {"window": None, "slots": [], "due_capacity": None, "due_slot": None, "uncounted": []}
    out = context_builder._section_training_phase(
        _PHASE_STUB, baseline, [_sched_entry(satisfies={"capacity": "stability"})])
    assert "Schedule vs quota" not in out


def test_consistency_done_is_from_resolve_not_recounted(db_session):
    """`done` parity with resolve(): seed an OPEN phase with a 7-day metabolic-free stability
    microcycle and NO workouts → resolve() yields done 0; feed that real position to the section
    with a Mon/Wed/Fri link → scheduled 3 · quota 2 · done 0 · MISMATCH +1. The section reports
    resolve()'s `done` verbatim — it never touches the workout tables."""
    from engine import resolver as resolver_mod
    u = _user(db_session, email="g3resolve@example.com")
    db_session.add(models.TrainingPhase(
        user_id=u.id, label="base", probe_posture="held",
        entered_on=date(2026, 9, 7), asserted_by="user", asserted_on=date(2026, 9, 7), source="api",
        microcycle={"sub_cycle_days": 7, "sub_cycles": [
            {"label": "A", "slots": [{"capacity": "stability", "sessions_per_cycle": 2, "minutes": 30}]}]},
    ))
    db_session.commit()
    pos = resolver_mod.resolve(db_session, u.id, today=date(2026, 9, 9))
    assert pos["window"] is not None and pos["slots"][0]["done"] == 0
    entries = [_sched_entry(days=["monday", "wednesday", "friday"],
                            satisfies={"capacity": "stability"})]
    out = context_builder._section_training_phase(_PHASE_STUB, pos, entries)
    assert "Stability — scheduled 3/wk · quota 2 · done 0" in out
    assert "MISMATCH: scheduled exceeds quota by 1" in out


# --------------------------------------------------------------------------- #
# G4 — render placement, STALE, single occurrence                              #
# --------------------------------------------------------------------------- #

def _state(**over):
    base = dict(knowledge_entries=[], training_plan=None, training_phase=None,
                resolver_position=None)
    base.update(over)
    return CurrentState(**base)


class _U:
    full_name = "Plan Tester"
    email = "por@example.com"


def test_plan_section_renders_above_phase_and_once():
    macro = "UNIQUE-MACRO-TOKEN Phase 1 base, buffer rule, knee gate fallback."
    phase = {**_PHASE_STUB, "entered_on": "2026-09-07"}
    state = _state(knowledge_entries=[_sched_entry()],
                   training_plan=_plan_value(macro=macro), training_phase=phase,
                   resolver_position={"window": None, "slots": [], "due_capacity": None,
                                      "due_slot": None, "uncounted": []})
    out = context_builder.build_system_prompt(_U(), [], state)
    assert out.index("## Plan of Record") < out.index("## Training Phase")   # above
    assert out.count(macro) == 1                                             # rendered ONCE


def test_plan_stale_line_when_revised_before_a_passed_review():
    phase = {**_PHASE_STUB, "entered_on": "2026-08-01",
             "review_on": "2026-09-01", "review_due": True}
    fresh = context_builder._section_training_plan(_plan_value(revised_on="2026-09-15"), phase)
    stale = context_builder._section_training_plan(_plan_value(revised_on="2026-08-15"), phase)
    assert "STALE" not in fresh                 # revised AFTER the review date
    assert "STALE — plan not revised since before the last phase review" in stale
    # review not yet due → never stale, whatever the revised_on.
    not_due = {**phase, "review_due": False}
    assert "STALE" not in context_builder._section_training_plan(
        _plan_value(revised_on="2026-08-15"), not_due)


def test_no_plan_renders_no_section():
    assert context_builder._section_training_plan(None, _PHASE_STUB) == ""
    assert context_builder._section_training_plan({"macro": "  "}, _PHASE_STUB) == ""


# --------------------------------------------------------------------------- #
# G5 — regression on the 18-Sep evidence                                       #
# --------------------------------------------------------------------------- #

def test_evidence_regression_carnival_and_mismatch_surface_no_phantom_session():
    """The 18-Sep failure: the coach invented Tue/Thu swim sessions from `intent` prose and a
    routine title, and missed a carnival it was never told about. Prompt BEHAVIOUR is not
    unit-testable — this asserts the INPUTS the coach now sees: the carnival load_context is
    surfaced, the schedule↔quota MISMATCH is stated, the counted position names no swim, and the
    standing instruction tells the coach titles/intent are not a count."""
    phase = {**_PHASE_STUB, "entered_on": "2026-09-07",
             "intent": "aerobic base; Tue/Thu swim rehab"}
    pos = _position(slots=[{"kind": "capacity", "capacity": "stability", "quota": 2, "done": 2,
                            "remaining": 0, "workouts_counted": ["w1", "w2"]}])
    entries = [
        _sched_entry(activity="gym", days=["monday", "wednesday", "friday"],
                     satisfies={"capacity": "stability"}),
        {"type": "load_context", "value": {"description": "masters carnival Sat–Sun"}},
    ]
    state = _state(knowledge_entries=entries, training_phase=phase, resolver_position=pos)
    out = context_builder.build_system_prompt(_U(), [], state)
    assert "masters carnival" in out                                  # the carnival is surfaced
    assert "MISMATCH: scheduled exceeds quota by 1" in out            # the discrepancy is stated
    assert "never derive what is \"due\" or what was \"done\" from a Hevy routine title" in out
    # "swim" appears EXACTLY ONCE — on the Intent line, framed as intent, never as a counted
    # session: the authoritative position (stability 2/2) names no swim, so nothing in the
    # context reads as "swims happened". A fabricated swim session line would push this above 1.
    assert "Intent: aerobic base; Tue/Thu swim rehab" in out
    assert out.lower().count("swim") == 1


# --------------------------------------------------------------------------- #
# G6 — S0(b) readers unchanged by a satisfies key / a training_plan row        #
# --------------------------------------------------------------------------- #

def test_section_schedule_byte_identical_with_satisfies_and_training_plan():
    from datetime import datetime
    import pytz
    now = pytz.timezone("Australia/Brisbane").localize(datetime(2026, 9, 9, 9, 0))
    base = [{"type": "schedule_item", "source": "chat", "notes": "",
             "value": _valid_item(activity="gym", days=["monday"])}]
    with_sat = [{"type": "schedule_item", "source": "chat", "notes": "",
                 "value": _valid_item(activity="gym", days=["monday"],
                                      satisfies={"capacity": "stability"})}]
    # adding `satisfies` to an item is invisible to _section_schedule.
    assert context_builder._section_schedule(base, now) == context_builder._section_schedule(with_sat, now)
    # a training_plan row in the entries list is ignored by _section_schedule (type-filtered).
    with_plan = base + [{"type": "training_plan", "value": _plan_value()}]
    assert context_builder._section_schedule(base, now) == context_builder._section_schedule(with_plan, now)
