"""create_and_resolve — app-originated custom exercise, resolved by list-back (#NEXT).

Canonical id is read create -> sync -> resolve within the user's custom subset,
never trusted from the POST body (which returns an int, not the canonical UUID):

(a) pre-existing default short-circuits create (idempotency, default-wins #60)
(b) absent title round-trips create -> sync -> resolve to the new custom's UUID
(c) list-back stays in the custom subset — a same-titled default never masks it
(d) 403 custom-limit and 400 bad-body surface as typed connector errors
(e) bounded retry covers create-visibility latency (first GET miss, then hit)
(f) unresolved-after-retries raises, never returns None silently

The Hevy client is faked (no live API). create_and_resolve and sync_one_user each
construct their own HevyClient, so the fake shares Hevy-side state via a closure.
"""
import asyncio

import pytest

import hevy_templates
import models
from connectors.hevy import HevyBadRequestError, HevyCustomExerciseLimitError
from encryption import encrypt

USER = 7
NEW_UUID = "aaaaaaaa-1111-2222-3333-444444444444"


def _tmpl(db, id_, title, is_custom, owner=None, type_="weight_reps"):
    db.add(models.HevyExerciseTemplate(
        id=id_, title=title, type=type_, is_custom=is_custom, owner_user_id=owner,
    ))
    db.commit()


def _seed_key(db, user_id=USER):
    db.add(models.UserIntegration(
        user_id=user_id, provider="hevy", api_key_encrypted=encrypt("fake-key"),
    ))
    db.commit()


def _install_fake(monkeypatch, *, catalogue=None, new_uuid=NEW_UUID,
                  appear_after=0, raise_on_create=None):
    """Patch hevy_templates.HevyClient with a fake sharing Hevy-side state.

    `catalogue`   — rows GET always returns (defaults / pre-existing customs).
    `appear_after`— the freshly created custom becomes GET-visible only once the
                    GET-call count exceeds this (0 = immediately; 1 = after a miss).
    `raise_on_create` — an exception instance the fake raises from create.
    """
    state = {
        "catalogue": list(catalogue or []),
        "created": None,          # the row minted by create, once POSTed
        "new_uuid": new_uuid,
        "appear_after": appear_after,
        "get_calls": 0,
        "create_calls": 0,
        "raise_on_create": raise_on_create,
    }

    class FakeHevyClient:
        def __init__(self, api_key):
            self.api_key = api_key

        async def create_exercise_template(self, title, exercise_type,
                                           equipment_category, muscle_group,
                                           other_muscles=None):
            state["create_calls"] += 1
            if state["raise_on_create"] is not None:
                raise state["raise_on_create"]
            # The canonical row Hevy would expose via GET (string UUID id) — NOT
            # the {"id": <int>} the POST body actually returns.
            state["created"] = {
                "id": state["new_uuid"],
                "title": title,
                "type": exercise_type,
                "is_custom": True,
                "primary_muscle_group": muscle_group,
                "secondary_muscle_groups": other_muscles,
            }
            return {"id": 123}  # integer id — deliberately not the canonical UUID

        async def get_exercise_templates(self, page=1, page_size=100):
            state["get_calls"] += 1
            rows = list(state["catalogue"])
            if state["created"] is not None and state["get_calls"] > state["appear_after"]:
                rows.append(state["created"])
            return {"exercise_templates": rows, "page_count": 1}

    monkeypatch.setattr(hevy_templates, "HevyClient", FakeHevyClient)
    # Keep the visibility-latency retry fast without touching real timing paths.
    monkeypatch.setattr(hevy_templates, "_BACKOFF_BASE", 0.001)
    return state


# ---------- (a) pre-existing default short-circuits create ----------
def test_existing_default_short_circuits_create(db_session, monkeypatch):
    _tmpl(db_session, "BENCH001", "Bench Press", is_custom=False)
    state = _install_fake(monkeypatch)

    result = asyncio.run(hevy_templates.create_and_resolve(
        db_session, USER, "Bench Press", "weight_reps", "barbell", "chest",
    ))

    assert result == "BENCH001"          # default id, via default-wins pre-check
    assert state["create_calls"] == 0    # never minted


def test_existing_own_custom_short_circuits_create(db_session, monkeypatch):
    _tmpl(db_session, "cccccccc-9999", "Sled Push", is_custom=True, owner=USER)
    state = _install_fake(monkeypatch)

    result = asyncio.run(hevy_templates.create_and_resolve(
        db_session, USER, "Sled Push", "weight_reps", "other", "quadriceps",
    ))

    assert result == "cccccccc-9999"     # the user's own existing custom
    assert state["create_calls"] == 0


# ---------- (b) absent title -> create -> sync -> resolve to new UUID ----------
def test_absent_title_round_trips_to_new_custom(db_session, monkeypatch):
    _seed_key(db_session)
    state = _install_fake(monkeypatch)

    result = asyncio.run(hevy_templates.create_and_resolve(
        db_session, USER, "Zercher Carry", "weight_reps", "barbell", "full_body",
        other_muscles=["forearms", "glutes"],
    ))

    assert result == NEW_UUID
    assert state["create_calls"] == 1
    # The row landed in the store as this user's custom.
    row = db_session.get(models.HevyExerciseTemplate, NEW_UUID)
    assert row.is_custom is True and row.owner_user_id == USER
    assert row.secondary_muscle_groups == ["forearms", "glutes"]


# ---------- (c) list-back stays in the custom subset ----------
def test_list_back_ignores_same_titled_default(db_session, monkeypatch):
    _seed_key(db_session)
    # Hevy's catalogue carries a same-titled DEFAULT not yet in the local store,
    # so the pre-check misses and create proceeds; after sync both rows land.
    default_row = {
        "id": "SLEDDEF1", "title": "Sled Push", "type": "weight_reps",
        "is_custom": False, "primary_muscle_group": "quadriceps",
        "secondary_muscle_groups": None,
    }
    state = _install_fake(monkeypatch, catalogue=[default_row])

    result = asyncio.run(hevy_templates.create_and_resolve(
        db_session, USER, "Sled Push", "weight_reps", "other", "quadriceps",
    ))

    assert result == NEW_UUID            # the custom UUID, NOT "SLEDDEF1"
    assert state["create_calls"] == 1
    # The hazard is real: bare default-wins resolution WOULD return the default.
    assert hevy_templates.resolve_exercise(db_session, "Sled Push", USER) == "SLEDDEF1"


# ---------- (d) 403 / 400 surface as typed errors ----------
def test_403_custom_limit_surfaces(db_session, monkeypatch):
    _seed_key(db_session)
    _install_fake(monkeypatch, raise_on_create=HevyCustomExerciseLimitError("limit"))

    with pytest.raises(HevyCustomExerciseLimitError):
        asyncio.run(hevy_templates.create_and_resolve(
            db_session, USER, "Anything", "weight_reps", "barbell", "chest",
        ))


def test_400_bad_body_surfaces(db_session, monkeypatch):
    _seed_key(db_session)
    _install_fake(monkeypatch, raise_on_create=HevyBadRequestError("bad body"))

    with pytest.raises(HevyBadRequestError):
        asyncio.run(hevy_templates.create_and_resolve(
            db_session, USER, "Anything", "weight_reps", "barbell", "chest",
        ))


# ---------- (e) bounded retry covers create-visibility latency ----------
def test_retry_covers_first_get_miss(db_session, monkeypatch):
    _seed_key(db_session)
    # appear_after=1: the first sync's GET misses the new custom, the second hits.
    state = _install_fake(monkeypatch, appear_after=1)

    result = asyncio.run(hevy_templates.create_and_resolve(
        db_session, USER, "Landmine Press", "weight_reps", "barbell", "shoulders",
    ))

    assert result == NEW_UUID
    assert state["create_calls"] == 1
    assert state["get_calls"] >= 2       # required at least one retry


# ---------- (f) unresolved after all retries -> raises, never None ----------
def test_unresolved_after_retries_raises(db_session, monkeypatch):
    _seed_key(db_session)
    # Never becomes visible within the attempt budget.
    _install_fake(monkeypatch, appear_after=99)

    with pytest.raises(hevy_templates.HevyCreateUnresolvedError):
        asyncio.run(hevy_templates.create_and_resolve(
            db_session, USER, "Ghost Lift", "weight_reps", "barbell", "chest",
        ))


# ---------- key-missing precondition ----------
def test_missing_key_raises(db_session, monkeypatch):
    _install_fake(monkeypatch)  # no _seed_key
    with pytest.raises(hevy_templates.HevyKeyMissingError):
        asyncio.run(hevy_templates.create_and_resolve(
            db_session, USER, "No Key Lift", "weight_reps", "barbell", "chest",
        ))
