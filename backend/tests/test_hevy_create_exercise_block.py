"""The `<hevy_create_exercise>` block — model-facing custom-exercise creation (#164).

`create_and_resolve` (#65) has been dark since it landed: the only action block `chat.py`
parsed was `<hevy_create_routine>`, so a movement genuinely absent from the Hevy account
had no path to exist. This wires the block, its processor, and the contract.

Two things carry the weight here.

**Ordering.** The exercise processor must run before the routine processor. The model
cannot cite a server-minted UUID it has never seen, so a same-turn routine names the new
exercise by TITLE — and `_resolve_missing_ids` finds it only if the create and its sync
already ran. `test_same_turn_create_then_use_resolves_by_title` drives the real call-site
order rather than the processors in isolation, so reversing them fails the test.

**Permanence.** Hevy has no delete/edit-template API, so a wrong create is forever. Two
tests defend that: idempotency (an existing title creates nothing) and the non-goal guard
(`_resolve_missing_ids` still refuses on a miss and never mints).

All Hevy calls are faked — no live POST, and nothing is minted in any real account.
"""
import asyncio
import json
from datetime import datetime, timezone

import pytest

import models
from connectors.hevy import HevyBadRequestError, HevyCustomExerciseLimitError
from context_builder import _section_exercise_creation
from hevy_templates import HevyCreateUnresolvedError, HevyKeyMissingError
from routers import chat


def _run(coro):
    return asyncio.run(coro)


def _key(db, user_id=1):
    """A stored Hevy key, so the processor's not-connected pre-check passes.

    Stamped FRESH: these tests are orthogonal to the #212 catalogue-freshness gate, so the
    user sits in the common recently-synced state and the real gate skips (no Hevy call). The
    gate's own behaviour is covered by `test_hevy_create_freshness_gate.py`.
    """
    from encryption import encrypt
    db.add(models.UserIntegration(
        user_id=user_id, provider="hevy", api_key_encrypted=encrypt("hk_test"),
        templates_synced_at=datetime.now(timezone.utc)))
    db.commit()


def _template(db, tid, title, *, is_custom=False, owner=None):
    db.add(models.HevyExerciseTemplate(
        id=tid, title=title, is_custom=is_custom, owner_user_id=owner))
    db.commit()


def _block(**fields) -> str:
    body = {
        "title": "Copenhagen Plank",
        "exercise_type": "duration",
        "equipment_category": "none",
        "muscle_group": "adductors",
        "other_muscles": ["abdominals"],
    }
    body.update(fields)
    return f"<hevy_create_exercise>\n{json.dumps(body)}\n</hevy_create_exercise>"


def _install_create(monkeypatch, *, returns="NEW-UUID", raises=None, on_call=None):
    """Fake `create_and_resolve` and record the kwargs it receives."""
    calls: list[dict] = []

    async def fake(db, user_id, title, exercise_type, equipment_category,
                   muscle_group, other_muscles=None):
        calls.append({
            "user_id": user_id, "title": title, "exercise_type": exercise_type,
            "equipment_category": equipment_category, "muscle_group": muscle_group,
            "other_muscles": other_muscles,
        })
        if raises is not None:
            raise raises
        if on_call is not None:
            on_call(db, user_id, title)
        return returns

    monkeypatch.setattr(chat, "create_and_resolve", fake)
    return calls


# --------------------------------------------------------------------------- #
# G1 — the block is parsed and dispatched with the fields as written.          #
# --------------------------------------------------------------------------- #

def test_block_calls_create_and_resolve_with_parsed_fields(db_session, monkeypatch):
    _key(db_session)
    calls = _install_create(monkeypatch)

    cleaned, actions = _run(chat._process_exercise_actions(
        "Here you go.\n" + _block(), 1, db_session))

    assert calls == [{
        "user_id": 1, "title": "Copenhagen Plank", "exercise_type": "duration",
        "equipment_category": "none", "muscle_group": "adductors",
        "other_muscles": ["abdominals"],
    }]
    assert actions == ["✓ Custom exercise 'Copenhagen Plank' created in Hevy"]
    assert "<hevy_create_exercise>" not in cleaned      # raw block stripped
    assert cleaned == "Here you go."


def test_no_block_is_a_no_op(db_session, monkeypatch):
    calls = _install_create(monkeypatch)
    cleaned, actions = _run(chat._process_exercise_actions("just talking", 1, db_session))
    assert (cleaned, actions, calls) == ("just talking", [], [])


def test_not_connected_strips_block_and_warns_once(db_session, monkeypatch):
    """No stored key: one warning for the whole reply, as routines do — not one per block."""
    calls = _install_create(monkeypatch)

    cleaned, actions = _run(chat._process_exercise_actions(
        _block() + "\n" + _block(title="Jefferson Curl"), 1, db_session))

    assert actions == ["⚠️ Custom exercise not created — Hevy is not connected."]
    assert calls == []                                  # nothing attempted
    assert "<hevy_create_exercise>" not in cleaned


# --------------------------------------------------------------------------- #
# G2 — THE ordering gate: same-turn create, then use by title in a routine.    #
# --------------------------------------------------------------------------- #

def test_same_turn_create_then_use_resolves_by_title(db_session, monkeypatch):
    """Drives the real call-site order, so a reversal fails here.

    The reply mints a custom and references it by title in the same turn's routine. The
    routine resolves only if the create ran AND its sync landed the row first — which is
    exactly what the call-site ordering guarantees.
    """
    _key(db_session)

    def lands_the_row(db, user_id, title):
        # Stand in for create_and_resolve's create -> sync -> list-back.
        _template(db, "CUSTOM-1", title, is_custom=True, owner=user_id)

    _install_create(monkeypatch, returns="CUSTOM-1", on_call=lands_the_row)

    created_routines: list[dict] = []

    class FakeHevyClient:
        async def create_routine(self, title, exercises, folder_id=None):
            created_routines.append({"title": title, "exercises": exercises})
            return {"id": 1}

    reply = (
        _block(title="Copenhagen Plank")
        + "\n<hevy_create_routine>\n"
        + json.dumps({"title": "Adductor Day", "exercises": [
            {"title": "Copenhagen Plank", "sets": [{"type": "normal", "duration_seconds": 45}]}
        ]})
        + "\n</hevy_create_routine>"
    )

    # The call-site order, verbatim from chat.py: exercises, then routines.
    reply, ex_actions = _run(chat._process_exercise_actions(reply, 1, db_session))
    reply, rt_actions = _run(chat._process_routine_actions(
        reply, FakeHevyClient(), 1, db_session))

    assert ex_actions == ["✓ Custom exercise 'Copenhagen Plank' created in Hevy"]
    assert rt_actions == ["✓ Routine 'Adductor Day' created in Hevy"]
    # Resolved by title to the id minted moments earlier, and the title key consumed.
    assert created_routines[0]["exercises"][0]["exercise_template_id"] == "CUSTOM-1"
    assert "title" not in created_routines[0]["exercises"][0]


def test_reversed_order_would_fail_to_resolve(db_session, monkeypatch):
    """The control for the gate above: routines FIRST cannot see the not-yet-created row.

    This pins WHY the order matters. If someone reorders the call site, the test above
    goes red; this one documents the failure they would be causing.
    """
    _key(db_session)

    def lands_the_row(db, user_id, title):
        _template(db, "CUSTOM-1", title, is_custom=True, owner=user_id)

    _install_create(monkeypatch, returns="CUSTOM-1", on_call=lands_the_row)

    class FakeHevyClient:
        async def create_routine(self, title, exercises, folder_id=None):
            raise AssertionError("must not be reached — the title cannot resolve yet")

    reply = (
        _block(title="Copenhagen Plank")
        + "\n<hevy_create_routine>\n"
        + json.dumps({"title": "Adductor Day", "exercises": [{"title": "Copenhagen Plank",
                                                              "sets": []}]})
        + "\n</hevy_create_routine>"
    )

    reply, rt_actions = _run(chat._process_routine_actions(
        reply, FakeHevyClient(), 1, db_session))

    assert len(rt_actions) == 1
    assert "not created — could not resolve exercise(s)" in rt_actions[0]
    assert "Copenhagen Plank" in rt_actions[0]


# --------------------------------------------------------------------------- #
# G3 — each typed error maps to its own message; the 400 is correctable.       #
# --------------------------------------------------------------------------- #

def test_custom_exercise_limit_maps_to_its_own_message(db_session, monkeypatch):
    _key(db_session)
    _install_create(monkeypatch, raises=HevyCustomExerciseLimitError("limit: 403"))

    _, actions = _run(chat._process_exercise_actions(_block(), 1, db_session))

    assert actions == [
        "⚠️ Custom exercise not created — Hevy's custom-exercise limit reached."
    ]


def test_bad_request_names_the_rejected_field_and_its_valid_values(db_session, monkeypatch):
    """A 400 must leave the next turn able to self-correct (#83's pattern)."""
    _key(db_session)
    _install_create(monkeypatch, raises=HevyBadRequestError(
        "Hevy rejected the exercise-template body: invalid exercise_type"))

    _, actions = _run(chat._process_exercise_actions(_block(), 1, db_session))

    msg = actions[0]
    assert "exercise_type must be one of:" in msg
    assert "bodyweight_assisted_reps" in msg            # the real enum is echoed back
    # Only the named field is echoed — not a wall of every enum.
    assert "equipment_category must be one of:" not in msg
    assert "muscle_group must be one of:" not in msg


def test_bad_request_with_unparseable_detail_lists_every_enum(db_session, monkeypatch):
    """Degrade to all three rather than guess which field was at fault."""
    _key(db_session)
    _install_create(monkeypatch, raises=HevyBadRequestError("400: something went wrong"))

    _, actions = _run(chat._process_exercise_actions(_block(), 1, db_session))

    msg = actions[0]
    for field in ("exercise_type", "equipment_category", "muscle_group"):
        assert f"{field} must be one of:" in msg


def test_unresolved_create_is_an_honest_failure_that_forbids_retry(db_session, monkeypatch):
    """The POST may have succeeded — never report success, and never invite a duplicate."""
    _key(db_session)
    _install_create(monkeypatch, raises=HevyCreateUnresolvedError(
        "Created 'Copenhagen Plank' for user 1 but it never surfaced after 3 sync attempts"))

    _, actions = _run(chat._process_exercise_actions(_block(), 1, db_session))

    msg = actions[0]
    assert msg.startswith("⚠️")                          # never a ✓
    assert "did not surface" in msg
    assert "Do NOT create it again" in msg              # permanence guard


def test_key_missing_mid_turn_surfaces_rather_than_raising(db_session, monkeypatch):
    """Defensive twin of the pre-check: key deleted between the check and the create."""
    _key(db_session)
    _install_create(monkeypatch, raises=HevyKeyMissingError("No Hevy key for user 1"))

    _, actions = _run(chat._process_exercise_actions(_block(), 1, db_session))

    assert actions == ["⚠️ Custom exercise not created — Hevy is not connected."]


def test_unparseable_json_reports_and_strips(db_session, monkeypatch):
    _key(db_session)
    calls = _install_create(monkeypatch)

    cleaned, actions = _run(chat._process_exercise_actions(
        "<hevy_create_exercise>\n{not json\n</hevy_create_exercise>", 1, db_session))

    assert calls == []
    assert actions[0].startswith("⚠️ Could not parse custom-exercise JSON")
    assert "<hevy_create_exercise>" not in cleaned


# --------------------------------------------------------------------------- #
# G4 — idempotency: an existing title mints nothing and says so honestly.      #
# --------------------------------------------------------------------------- #

def test_existing_default_title_creates_nothing(db_session, monkeypatch):
    """Default-wins short-circuit. Reporting "created" here would be a false claim
    about an irreversible act."""
    _key(db_session)
    _template(db_session, "DEFAULT1", "Bench Press")
    calls = _install_create(monkeypatch)

    _, actions = _run(chat._process_exercise_actions(
        _block(title="Bench Press"), 1, db_session))

    assert calls == []                                  # nothing attempted
    assert actions == ["✓ 'Bench Press' is already in the exercise catalogue — nothing created"]
    assert "created in Hevy" not in actions[0]


def test_users_own_existing_custom_creates_nothing(db_session, monkeypatch):
    _key(db_session)
    _template(db_session, "MINE-1", "Copenhagen Plank", is_custom=True, owner=1)
    calls = _install_create(monkeypatch)

    _, actions = _run(chat._process_exercise_actions(_block(), 1, db_session))

    assert calls == []
    assert "already in the exercise catalogue" in actions[0]


def test_another_users_custom_does_not_short_circuit(db_session, monkeypatch):
    """Scope check: someone else's custom is invisible, so the create must still run."""
    _key(db_session)
    _template(db_session, "THEIRS-1", "Copenhagen Plank", is_custom=True, owner=999)
    calls = _install_create(monkeypatch)

    _, actions = _run(chat._process_exercise_actions(_block(), 1, db_session))

    assert len(calls) == 1
    assert actions == ["✓ Custom exercise 'Copenhagen Plank' created in Hevy"]


def test_missing_title_creates_nothing(db_session, monkeypatch):
    _key(db_session)
    calls = _install_create(monkeypatch)

    _, actions = _run(chat._process_exercise_actions(
        _block(title="   "), 1, db_session))

    assert calls == []
    assert actions == ["⚠️ Custom exercise not created — no title given."]


# --------------------------------------------------------------------------- #
# G5 — NON-GOAL GUARD: a routine resolve-miss must never mint.                 #
# --------------------------------------------------------------------------- #

def test_resolve_miss_refuses_and_creates_nothing(db_session, monkeypatch):
    """The deliberate non-goal. Auto-creating on a miss turns every typo into a
    permanent Hevy record, so `_resolve_missing_ids` must still only refuse."""
    _key(db_session)
    calls = _install_create(monkeypatch)

    exercises, unresolved = chat._resolve_missing_ids(
        [{"title": "Zercher Moonwalk Press", "sets": []}], 1, db_session)

    assert calls == []                                              # nothing minted
    assert [t for t, _ in unresolved] == ["Zercher Moonwalk Press"]
    assert exercises[0].get("exercise_template_id") is None
    assert db_session.query(models.HevyExerciseTemplate).count() == 0


def test_routine_with_unresolved_title_creates_no_exercise_and_no_routine(db_session, monkeypatch):
    """End-to-end shape of the non-goal: the miss is reported, nothing is written."""
    _key(db_session)
    calls = _install_create(monkeypatch)

    class FakeHevyClient:
        async def create_routine(self, title, exercises, folder_id=None):
            raise AssertionError("routine must not be created on an unresolved title")

    reply = ("<hevy_create_routine>\n"
             + json.dumps({"title": "Leg Day", "exercises": [{"title": "Nonexistent Lift",
                                                              "sets": []}]})
             + "\n</hevy_create_routine>")

    _, actions = _run(chat._process_routine_actions(reply, FakeHevyClient(), 1, db_session))

    assert calls == []
    assert "could not resolve exercise(s)" in actions[0]
    assert db_session.query(models.HevyExerciseTemplate).count() == 0


# --------------------------------------------------------------------------- #
# G6 — the contract: gated, permanent-warning, and enum-accurate.              #
# --------------------------------------------------------------------------- #

def test_contract_absent_when_hevy_not_connected():
    assert _section_exercise_creation([]) == ""
    assert _section_exercise_creation(["polar"]) == ""


def test_contract_present_and_states_permanence_hard():
    s = _section_exercise_creation(["hevy"])
    assert "<hevy_create_exercise>" in s
    assert "PERMANENT AND CANNOT BE UNDONE" in s
    assert "no API to delete or edit" in s
    assert "NEVER emit this block unless the user has explicitly asked" in s


@pytest.mark.parametrize("value", [
    "weight_reps", "reps_only", "bodyweight_reps", "bodyweight_assisted_reps",
    "duration", "weight_duration", "distance_duration", "short_distance_weight",
])
def test_contract_carries_every_create_exercise_type(value):
    """Quoted from the live spec's CustomExerciseType — all eight, not a sample."""
    assert value in _section_exercise_creation(["hevy"])


@pytest.mark.parametrize("value", [
    "none", "barbell", "dumbbell", "kettlebell", "machine", "plate",
    "resistance_band", "suspension", "other",
])
def test_contract_carries_every_equipment_category(value):
    assert value in _section_exercise_creation(["hevy"])


@pytest.mark.parametrize("value", [
    "abdominals", "shoulders", "biceps", "triceps", "forearms", "quadriceps",
    "hamstrings", "calves", "glutes", "abductors", "adductors", "lats",
    "upper_back", "traps", "lower_back", "chest", "cardio", "neck", "full_body",
    "other",
])
def test_contract_carries_every_muscle_group(value):
    assert value in _section_exercise_creation(["hevy"])


@pytest.mark.parametrize("get_only", [
    "bodyweight_assisted", "bodyweight_weighted", "floors_duration", "steps_duration",
])
def test_contract_warns_about_the_get_only_type_values(get_only):
    """The cross-check finding, pinned. These four occur in the live catalogue's `type`
    but are INVALID for creation — `bodyweight_assisted` vs `bodyweight_assisted_reps`
    being the near-miss that would otherwise cost a 400 per attempt."""
    s = _section_exercise_creation(["hevy"])
    assert get_only in s
    assert "are NOT the type values you see on exercises in" in s


def test_processor_enum_table_matches_the_contract_text():
    """One source of truth: the table the 400-handler echoes and the text the model
    reads must not drift apart."""
    s = _section_exercise_creation(["hevy"])
    for value in chat._CREATE_EXERCISE_TYPES + chat._CREATE_EQUIPMENT + chat._CREATE_MUSCLE_GROUPS:
        assert value in s
