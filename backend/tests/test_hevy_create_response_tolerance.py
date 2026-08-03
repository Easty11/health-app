"""The create-response body is not load-bearing — a 2xx must never orphan the template.

Confirmed prod bug in the `#164` path. `create_exercise_template` ended with
`return self._check(r).json()`. The live create returns a 2xx whose body is NOT the
`{"id": <int>}` the OpenAPI spec promised, so `.json()` raised
`json.JSONDecodeError: Extra data: line 1 column 4 (char 3)`.

Why that was destructive rather than cosmetic: by that line the status is already 2xx
(401/4xx die in `_check`; the 400/403 branches pre-empt it), so **Hevy had already created
the template**. The untyped exception unwound past `create_and_resolve`'s sync + list-back,
leaving the template live in Hevy and absent from `hevy_exercise_templates`, while chat
reported "Failed to create". A user who trusted that message and retried would mint a
permanent duplicate against an API with no delete.

**Why `#164`'s 61 tests did not catch it.** They fake the client or the orchestrator, so
every fake returned clean JSON and the real parse never ran. These tests fake the
*transport* instead and drive the genuine `HevyClient`, so the parse executes. That is the
distinction that matters: a fake one layer above the defect cannot see it.
"""
import asyncio
import json

import httpx
import pytest

import hevy_templates
import models
from connectors.hevy import (
    HevyBadRequestError,
    HevyClient,
    HevyCustomExerciseLimitError,
    HevyForbiddenError,
)
from encryption import encrypt

USER = 11
NEW_UUID = "bbbbbbbb-1111-2222-3333-444444444444"

# The shape that broke prod: a 2xx body that is valid JSON for its first three characters
# and then carries trailing data — exactly what `Extra data: line 1 column 4 (char 3)`
# describes. Used as the canonical bad body throughout.
BAD_BODY = '123{"id":123}'


def _run(coro):
    return asyncio.run(coro)


def _response(status=200, text=BAD_BODY):
    req = httpx.Request("POST", "https://api.hevyapp.com/v1/exercise_templates")
    return httpx.Response(status, request=req, text=text)


def _patch_post(monkeypatch, response):
    """Fake the TRANSPORT, not the client — so the real parse path runs."""
    sent: list[dict] = []

    async def fake_post(self, url, json=None, **kw):
        sent.append({"url": url, "json": json})
        return response

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return sent


def _tmpl(db, id_, title, is_custom, owner=None):
    db.add(models.HevyExerciseTemplate(
        id=id_, title=title, type="duration", is_custom=is_custom, owner_user_id=owner))
    db.commit()


def _seed_key(db, user_id=USER):
    db.add(models.UserIntegration(
        user_id=user_id, provider="hevy", api_key_encrypted=encrypt("fake-key")))
    db.commit()


# --------------------------------------------------------------------------- #
# G1 — the connector tolerates the real bad body on a 2xx.                     #
# --------------------------------------------------------------------------- #

def test_unparseable_2xx_body_does_not_raise(monkeypatch):
    """THE regression. Before the fix this raised JSONDecodeError."""
    _patch_post(monkeypatch, _response())

    out = _run(HevyClient("k").create_exercise_template(
        title="Copenhagen Plank", exercise_type="duration",
        equipment_category="none", muscle_group="adductors"))

    assert out == {}          # body discarded, not propagated as garbage


def test_unparseable_body_is_logged_with_status_and_bytes(monkeypatch, caplog):
    """The capture hook: the live shape must reach the log, or we learn nothing."""
    import logging
    _patch_post(monkeypatch, _response(status=201))

    with caplog.at_level(logging.WARNING, logger="connectors.hevy"):
        _run(HevyClient("k").create_exercise_template(
            title="X", exercise_type="duration",
            equipment_category="none", muscle_group="adductors"))

    msg = " ".join(r.getMessage() for r in caplog.records)
    assert "unparseable body" in msg
    assert "201" in msg
    assert BAD_BODY in msg            # the actual bytes, not a paraphrase
    assert "WAS created" in msg       # says the destructive thing out loud


def test_wellformed_body_still_returned_verbatim(monkeypatch):
    """Positive control: the fix must not swallow a GOOD body."""
    _patch_post(monkeypatch, _response(text='{"id": 4242}'))

    out = _run(HevyClient("k").create_exercise_template(
        title="X", exercise_type="duration",
        equipment_category="none", muscle_group="adductors"))

    assert out == {"id": 4242}


@pytest.mark.parametrize("body", ['', '   ', 'OK', '<html>nope</html>', 'null123'])
def test_any_unparseable_2xx_body_is_tolerated(monkeypatch, body):
    """The fix is not keyed to one byte sequence — the endpoint's shape is unknown."""
    _patch_post(monkeypatch, _response(text=body))
    out = _run(HevyClient("k").create_exercise_template(
        title="X", exercise_type="duration",
        equipment_category="none", muscle_group="adductors"))
    assert isinstance(out, dict)


# --------------------------------------------------------------------------- #
# G2 — the typed-error path is UNTOUCHED. Tolerance must not swallow failures. #
# --------------------------------------------------------------------------- #

def test_403_still_raises_the_limit_error(monkeypatch):
    _patch_post(monkeypatch, _response(status=403, text="exceeds-custom-exercise-limit"))
    with pytest.raises(HevyCustomExerciseLimitError):
        _run(HevyClient("k").create_exercise_template(
            title="X", exercise_type="duration",
            equipment_category="none", muscle_group="adductors"))


def test_400_still_raises_the_bad_request_error(monkeypatch):
    _patch_post(monkeypatch, _response(status=400, text="invalid exercise_type"))
    with pytest.raises(HevyBadRequestError):
        _run(HevyClient("k").create_exercise_template(
            title="X", exercise_type="nope",
            equipment_category="none", muscle_group="adductors"))


def test_500_still_raises_rather_than_returning_empty(monkeypatch):
    """A server error is NOT a create — it must never be tolerated into a {}."""
    _patch_post(monkeypatch, _response(status=500, text="boom"))
    with pytest.raises(httpx.HTTPStatusError):
        _run(HevyClient("k").create_exercise_template(
            title="X", exercise_type="duration",
            equipment_category="none", muscle_group="adductors"))


def test_401_still_raises_auth_error(monkeypatch):
    from connectors.hevy import HevyAuthError
    _patch_post(monkeypatch, _response(status=401, text="bad key"))
    with pytest.raises(HevyAuthError):
        _run(HevyClient("k").create_exercise_template(
            title="X", exercise_type="duration",
            equipment_category="none", muscle_group="adductors"))


# --------------------------------------------------------------------------- #
# G3 — THE ORPHAN GATE: a 2xx create always reaches sync + list-back.          #
# --------------------------------------------------------------------------- #

def test_2xx_with_bad_body_still_resolves_by_list_back(db_session, monkeypatch):
    """The invariant the incident violated, pinned end-to-end.

    Real connector, real parse, bad body — and `create_and_resolve` must still complete
    the create -> sync -> list-back loop and return the canonical UUID. Before the fix
    this raised out of step 3 and never reached step 4.
    """
    _seed_key(db_session)
    _patch_post(monkeypatch, _response())

    # Stand in for the sync that follows the create: Hevy now lists the new custom.
    async def fake_sync_one_user(db, user_id, api_key):
        _tmpl(db, NEW_UUID, "Copenhagen Plank", True, owner=user_id)
        return {"rows_processed": 1, "defaults_seen": 0, "customs_seen": 1}

    monkeypatch.setattr(hevy_templates, "sync_one_user", fake_sync_one_user)

    resolved = _run(hevy_templates.create_and_resolve(
        db_session, USER, "Copenhagen Plank", "duration", "none", "adductors"))

    assert resolved == NEW_UUID                       # canonical id, not the body's int
    # And the template is IN the local catalogue — the definition of not-orphaned.
    assert hevy_templates.resolve_exercise(db_session, "Copenhagen Plank", USER) == NEW_UUID


def test_the_template_is_never_left_orphaned(db_session, monkeypatch):
    """Restates the gate as the failure the user actually saw: created in Hevy, missing
    locally. After the fix there is no 2xx path that ends with the row absent."""
    _seed_key(db_session)
    _patch_post(monkeypatch, _response())

    synced: list[str] = []

    async def fake_sync_one_user(db, user_id, api_key):
        synced.append("ran")
        _tmpl(db, NEW_UUID, "Jefferson Curl", True, owner=user_id)
        return {"rows_processed": 1, "defaults_seen": 0, "customs_seen": 1}

    monkeypatch.setattr(hevy_templates, "sync_one_user", fake_sync_one_user)

    _run(hevy_templates.create_and_resolve(
        db_session, USER, "Jefferson Curl", "duration", "none", "adductors"))

    assert synced == ["ran"]                          # step 4 was REACHED
    assert db_session.query(models.HevyExerciseTemplate).filter_by(
        title="Jefferson Curl").count() == 1


def test_no_duplicate_on_a_retry_after_the_bad_body(db_session, monkeypatch):
    """The latent harm: a second attempt must short-circuit, not mint again.

    Once the first attempt's template is in the catalogue, the idempotency pre-check owns
    the retry — so the POST is never sent a second time.
    """
    _seed_key(db_session)
    sent = _patch_post(monkeypatch, _response())

    async def fake_sync_one_user(db, user_id, api_key):
        _tmpl(db, NEW_UUID, "Copenhagen Plank", True, owner=user_id)
        return {"rows_processed": 1, "defaults_seen": 0, "customs_seen": 1}

    monkeypatch.setattr(hevy_templates, "sync_one_user", fake_sync_one_user)

    first = _run(hevy_templates.create_and_resolve(
        db_session, USER, "Copenhagen Plank", "duration", "none", "adductors"))
    assert len(sent) == 1

    second = _run(hevy_templates.create_and_resolve(
        db_session, USER, "Copenhagen Plank", "duration", "none", "adductors"))

    assert second == first
    assert len(sent) == 1        # NO second POST — nothing minted twice


def test_chat_reports_success_not_failure_after_a_bad_body(db_session, monkeypatch):
    """The user-visible half: the false negative is gone.

    Before the fix this reply carried "⚠️ Failed to create custom exercise" while the
    template sat live in Hevy.
    """
    from routers import chat

    db_session.add(models.UserIntegration(
        user_id=USER, provider="hevy", api_key_encrypted=encrypt("fake-key")))
    db_session.commit()
    _patch_post(monkeypatch, _response())

    async def fake_sync_one_user(db, user_id, api_key):
        _tmpl(db, NEW_UUID, "Copenhagen Plank", True, owner=user_id)
        return {"rows_processed": 1, "defaults_seen": 0, "customs_seen": 1}

    monkeypatch.setattr(hevy_templates, "sync_one_user", fake_sync_one_user)

    block = ('<hevy_create_exercise>\n'
             + json.dumps({"title": "Copenhagen Plank", "exercise_type": "duration",
                           "equipment_category": "none", "muscle_group": "adductors"})
             + '\n</hevy_create_exercise>')

    _, actions = _run(chat._process_exercise_actions(block, USER, db_session))

    assert actions == ["✓ Custom exercise 'Copenhagen Plank' created in Hevy"]
    assert not any("Failed to create" in a for a in actions)
