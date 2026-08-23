"""`schedule_item` is a closed, validated shape at write (#233).

Every fault these tests pin was read out of live data, not imagined: constraint prose
sitting in a documented-boolean field, quota values smuggled into `days[]`
(`"flexible"`, `"flexible_third_day"`), a `minimum_days` key invented to work around a
field that did not exist, and duplicate rows for one commitment because the writer
minted a new key instead of reusing the old one.

The overlap tests carry the most weight. The trigger is DAY OVERLAP ALONE — an earlier
draft of this rule also required a matching `activity`, which would have shipped the
exact regression `test_overlap_is_refused_even_when_activity_differs` pins: matching on
free text fails OPEN, so a near-miss string reproduces the silent duplicate the rule
exists to close.
"""
from datetime import date

import pytest
from fastapi import HTTPException

import models
from routers.knowledge import (
    EXPECTED_LOAD_VALUES,
    SCHEDULE_ITEM_FIELDS,
    TIME_OF_DAY_VALUES,
    WEEKDAYS,
    KnowledgeEntryIn,
    ScheduleItemOverlap,
    upsert_knowledge_entry,
    validate_schedule_item,
)

# `db_session` comes from conftest.py, collected by pytest.


# ---------- fixtures ----------

def _user(db, email="schedule@example.com") -> models.User:
    u = models.User(email=email, hashed_password="x", full_name="Schedule Tester")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _value(**overrides) -> dict:
    """A conforming value. Overrides mutate one field at a time so each test states
    exactly what it is making wrong — the mutation IS the test."""
    base = {
        "activity": "Rugby Training — Seniors",
        "days": ["tuesday"],
        "hard": True,
        "expected_load": "moderate",
        "time_of_day": "evening",
        "same_day_training": False,
        "duration_weeks": None,
        "season_end": None,
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not ...}


def _write(db, user_id: int, key: str, **overrides) -> models.UserKnowledgeEntry:
    return upsert_knowledge_entry(
        user_id,
        KnowledgeEntryIn(type="schedule_item", key=key, value=_value(**overrides),
                         source="chat"),
        db,
    )


# ---------- the closed set ----------

def test_a_conforming_value_is_accepted_and_stored_verbatim(db_session):
    """Positive control. Without it, every refusal below could be a validator that
    refuses everything — which passes the negatives and is useless (`FEEDBACK` §17)."""
    u = _user(db_session)
    row = _write(db_session, u.id, "rugby_2026_08")
    assert row.value == _value()
    assert row.active is True


def test_an_unknown_key_is_refused(db_session):
    """`minimum_days` is the live instance: a key invented to express a fact the shape
    had no field for. The fix is a field or a refusal, never a silent extra key."""
    with pytest.raises(ValueError, match="unknown field"):
        validate_schedule_item(_value(minimum_days=2))


def test_a_weekday_typo_is_refused(db_session):
    with pytest.raises(ValueError, match="unknown weekday"):
        validate_schedule_item(_value(days=["tuseday"]))


def test_a_frequency_in_days_is_refused_and_told_where_it_belongs(db_session):
    """`["flexible"]` and `["monday", "wednesday", "flexible_third_day"]` are both live.
    A frequency is not a day; the refusal names the field that does hold it."""
    with pytest.raises(ValueError, match="sessions_per_week"):
        validate_schedule_item(_value(days=["flexible"]))


def test_a_truthy_string_boolean_is_refused(db_session):
    """Live: ids 1 and 2 held constraint PROSE in `same_day_training`, a field the
    prompt documented as a boolean. Truthy strings are why the field read as `true`
    everywhere and meant nothing."""
    with pytest.raises(ValueError, match="strict boolean"):
        validate_schedule_item(_value(same_day_training="only if upper body"))
    with pytest.raises(ValueError, match="strict boolean"):
        validate_schedule_item(_value(hard="yes"))


def test_an_integer_is_not_a_boolean(db_session):
    """`isinstance(True, int)` is True in Python, so a bool check that uses `int` lets
    `1` through. This pins the direction that mistake would break."""
    with pytest.raises(ValueError, match="strict boolean"):
        validate_schedule_item(_value(hard=1))


def test_both_days_and_sessions_per_week_absent_is_refused(db_session):
    v = _value()
    del v["days"]
    with pytest.raises(ValueError, match="at least one of"):
        validate_schedule_item(v)


def test_sessions_per_week_alone_is_accepted(db_session):
    """The quota conversion's target shape: a commitment that happens N times a week on
    no fixed day (live ids 66, 74)."""
    v = _value(sessions_per_week=1)
    del v["days"]
    assert validate_schedule_item(v) is v


def test_sessions_per_week_out_of_range_is_refused(db_session):
    with pytest.raises(ValueError, match="between 1 and 14"):
        validate_schedule_item(_value(sessions_per_week=15))
    with pytest.raises(ValueError, match="between 1 and 14"):
        validate_schedule_item(_value(sessions_per_week=0))


def test_a_missing_required_field_is_refused(db_session):
    v = _value()
    del v["time_of_day"]
    with pytest.raises(ValueError, match="missing required field"):
        validate_schedule_item(v)


def test_expected_load_is_required_and_non_null_on_write(db_session):
    """Required ON WRITE, nullable IN STORE. A caller that does not know the load must
    ask; a fabricated load entering a load model is worse than a visible gap. The ten
    live rows carrying null predate this and are reached by backfill, not by write."""
    with pytest.raises(ValueError, match="required on write"):
        validate_schedule_item(_value(expected_load=None))
    with pytest.raises(ValueError, match="not one of"):
        validate_schedule_item(_value(expected_load="very heavy"))


def test_time_of_day_is_closed(db_session):
    with pytest.raises(ValueError, match="not one of"):
        validate_schedule_item(_value(time_of_day="lunchtime"))


def test_season_end_must_be_an_iso_date_or_null(db_session):
    assert validate_schedule_item(_value(season_end="2026-09-05"))
    assert validate_schedule_item(_value(season_end=None))
    with pytest.raises(ValueError, match="ISO date"):
        validate_schedule_item(_value(season_end="September"))


def test_duplicate_weekdays_are_refused(db_session):
    with pytest.raises(ValueError, match="duplicate weekday"):
        validate_schedule_item(_value(days=["tuesday", "tuesday"]))


# ---------- the overlap rule (A1) ----------

def test_an_overlapping_write_with_no_acknowledgement_is_refused(db_session):
    u = _user(db_session)
    first = _write(db_session, u.id, "rugby_2026_08")

    with pytest.raises(ScheduleItemOverlap) as exc:
        _write(db_session, u.id, "conditioning_2026_08", activity="Conditioning")

    assert [o["id"] for o in exc.value.overlapping] == [first.id]
    assert exc.value.overlapping[0]["days"] == ["tuesday"]
    assert exc.value.overlapping[0]["activity"] == "Rugby Training — Seniors"


def test_overlap_is_refused_even_when_activity_differs(db_session):
    """THE REGRESSION THE v1 RULE WOULD HAVE SHIPPED.

    v1 triggered on `days` overlap AND an identical `activity`. The duplicate pairs in
    live data exist precisely because the writer used a DIFFERENT string for the same
    commitment — so an activity-matching rule fails open on the only case it was
    written for. Day overlap alone is the trigger; this test is what says so.
    """
    u = _user(db_session)
    _write(db_session, u.id, "rugby_2026_08", activity="Rugby Training — Seniors")

    with pytest.raises(ScheduleItemOverlap):
        _write(db_session, u.id, "rugby_seniors_aug", activity="Seniors rugby session")


def test_an_overlapping_write_with_distinct_from_is_accepted(db_session):
    u = _user(db_session)
    first = _write(db_session, u.id, "rugby_2026_08")

    row = _write(db_session, u.id, "gym_2026_08", activity="Gym — upper",
                 distinct_from=[first.id])

    # Accepted, and the acknowledgement token is NOT persisted: it satisfied the
    # validator for this write, it is not a relationship the store models.
    assert "distinct_from" not in row.value
    assert row.active is True
    db_session.refresh(first)
    assert first.active is True, "distinct_from must not retire the row it acknowledges"


def test_an_overlapping_write_with_supersedes_retires_the_named_row(db_session):
    u = _user(db_session)
    first = _write(db_session, u.id, "rugby_2026_08")

    row = _write(db_session, u.id, "rugby_seniors_aug", activity="Seniors rugby",
                 supersedes=first.id)

    db_session.refresh(first)
    assert first.active is False
    assert first.superseded_by == row.id
    # Stored, unlike `distinct_from` — `supersedes` is a real relationship.
    assert row.value["supersedes"] == first.id


def test_every_overlapping_row_must_be_acknowledged_not_just_one(db_session):
    """Acknowledging one row out of two would leave the other to duplicate silently —
    the same hole the rule closes, one row further along."""
    u = _user(db_session)
    a = _write(db_session, u.id, "rugby_2026_08")
    _write(db_session, u.id, "gym_2026_08", activity="Gym", distinct_from=[a.id])

    with pytest.raises(ScheduleItemOverlap) as exc:
        _write(db_session, u.id, "physio_2026_08", activity="Physio",
               distinct_from=[a.id])

    assert [o["activity"] for o in exc.value.overlapping] == ["Gym"]


def test_a_same_key_rewrite_does_not_overlap_itself(db_session):
    """Supersede-by-key already handles this; making a row acknowledge its own
    predecessor would refuse every ordinary edit."""
    u = _user(db_session)
    _write(db_session, u.id, "rugby_2026_08")
    row = _write(db_session, u.id, "rugby_2026_08", expected_load="heavy")
    assert row.value["expected_load"] == "heavy"


def test_no_day_overlap_is_not_refused(db_session):
    """Negative control paired with the positives above (`FEEDBACK` §17): if this
    refused too, the overlap check would be refusing on presence, not on overlap."""
    u = _user(db_session)
    _write(db_session, u.id, "rugby_2026_08", days=["tuesday"])
    row = _write(db_session, u.id, "gym_2026_08", activity="Gym", days=["wednesday"])
    assert row.active is True


def test_overlap_is_scoped_to_the_writing_user(db_session):
    u1 = _user(db_session, "one@example.com")
    u2 = _user(db_session, "two@example.com")
    _write(db_session, u1.id, "rugby_2026_08")
    row = _write(db_session, u2.id, "rugby_2026_08", activity="Someone else's Tuesday")
    assert row.active is True


# ---------- the HTTP surface ----------

def test_the_route_returns_422_for_shape_and_409_for_overlap(db_session):
    """A refusal must be structured and legible, never a 500 and never a silent store."""
    from routers.knowledge import create_entry

    u = _user(db_session)
    _write(db_session, u.id, "rugby_2026_08")

    with pytest.raises(HTTPException) as shape:
        create_entry(
            KnowledgeEntryIn(type="schedule_item", key="bad", source="chat",
                             value=_value(days=["tuseday"])),
            u, db_session,
        )
    assert shape.value.status_code == 422

    with pytest.raises(HTTPException) as overlap:
        create_entry(
            KnowledgeEntryIn(type="schedule_item", key="other", source="chat",
                             value=_value(activity="Other")),
            u, db_session,
        )
    assert overlap.value.status_code == 409
    detail = overlap.value.detail
    assert detail["error"] == "schedule_item_overlap"
    assert detail["resolve_with"] == ["supersedes", "distinct_from"]
    # Names the row, so the retry needs no second lookup.
    assert detail["overlapping"][0]["activity"] == "Rugby Training — Seniors"


def test_a_refused_write_leaves_no_row_behind(db_session):
    """#221's ordering: validate BEFORE touching the session, or a refused write
    strands a pending INSERT for whoever shares the session."""
    u = _user(db_session)
    with pytest.raises(ValueError):
        _write(db_session, u.id, "bad_row", days=["tuseday"])
    db_session.rollback()
    assert db_session.query(models.UserKnowledgeEntry).filter_by(
        user_id=u.id, key="bad_row").count() == 0


def test_other_entry_types_are_untouched_by_this_validator(db_session):
    """The validator is keyed on `type == 'schedule_item'`. An injury row with none of
    these fields must still write — otherwise this change is a store-wide break."""
    u = _user(db_session)
    row = upsert_knowledge_entry(
        u.id,
        KnowledgeEntryIn(type="injury", key="left_hamstring", source="chat",
                         value={"body_part": "left hamstring"}),
        db_session,
    )
    assert row.active is True


# ---------- the declared vocabulary ----------

def test_the_declared_sets_are_what_the_schema_documents(db_session):
    """Pins the vocabularies themselves. A silent widening here would let a value
    through that `SCHEMA.md` says is refused, and nothing else would notice."""
    assert WEEKDAYS == ("monday", "tuesday", "wednesday", "thursday", "friday",
                        "saturday", "sunday")
    assert EXPECTED_LOAD_VALUES == ("light", "moderate", "heavy")
    assert TIME_OF_DAY_VALUES == ("morning", "afternoon", "evening", "unknown")
    assert set(SCHEDULE_ITEM_FIELDS) == {
        "activity", "days", "sessions_per_week", "hard", "expected_load",
        "time_of_day", "time_range", "same_day_training", "same_day_note",
        "duration_weeks", "season_end", "supersedes",
    }
