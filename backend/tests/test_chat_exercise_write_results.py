"""The Hevy exercise-action lane folded onto the WriteResult substrate (Q144).

The LAST un-wrapped Hevy write surface. A failed, rejected, unconfirmed, or
already-present custom-exercise create can no longer be narrated as a fresh
success — each yields a `WriteResult` paired 1:1 with its action string, mirroring
the routine fold (#286). Wrap-only: this lane is already idempotent (the
`resolve_exercise` pre-check + `create_and_resolve`'s #65 pre-check + the freshness
gate), so no collision guard is added.

The chat module's helpers are monkeypatched so the orchestration is tested in
isolation from the DB/network — the connector-level create behaviour is covered by
test_hevy_create_response_tolerance.py.
"""
import asyncio

import pytest

from connectors.hevy import HevyBadRequestError, HevyCustomExerciseLimitError
from hevy_templates import HevyCreateUnresolvedError
from routers import chat as chat_mod

USER = 7


def _block(title="Copenhagen Plank") -> str:
    import json
    payload = {"title": title, "exercise_type": "duration",
               "equipment_category": "none", "muscle_group": "adductors"}
    return "Sure!\n<hevy_create_exercise>\n" + json.dumps(payload) + "\n</hevy_create_exercise>"


@pytest.fixture
def isolate(monkeypatch):
    """Key present, catalogue fresh, nothing already resolves — the create path runs."""
    monkeypatch.setattr(chat_mod, "user_hevy_key", lambda db, uid: "fake-key")

    async def _noop_refresh(db, uid):
        return None
    monkeypatch.setattr(chat_mod, "refresh_catalogue_if_stale", _noop_refresh)
    monkeypatch.setattr(chat_mod, "resolve_exercise", lambda db, title, uid: None)
    return monkeypatch


def _set_create(monkeypatch, behaviour):
    async def _fake_create(db, uid, *, title, exercise_type, equipment_category, muscle_group, other_muscles=None):
        return behaviour(title)
    monkeypatch.setattr(chat_mod, "create_and_resolve", _fake_create)


def _run(block, db=None):
    return asyncio.run(chat_mod._process_exercise_actions(block, USER, db))


# --------------------------------------------------------------------------- #
# Success + no-op                                                              #
# --------------------------------------------------------------------------- #

def test_created_is_saved(isolate):
    _set_create(isolate, lambda title: "UUID-1")
    _cleaned, actions, wr = _run(_block())
    assert len(wr) == 1 and wr[0].saved is True and wr[0].reason_code == "created"
    assert wr[0].reason in actions


def test_already_present_is_not_narrated_as_created(isolate):
    """The idempotent no-op: nothing minted, so saved=False corrects a would-be
    'created!' to 'already in your catalogue'."""
    isolate.setattr(chat_mod, "resolve_exercise", lambda db, title, uid: "EXISTING-UUID")
    _cleaned, _actions, wr = _run(_block())
    assert wr[0].saved is False
    assert wr[0].reason_code == "already_present"
    assert wr[0].reason.startswith("ℹ️")


# --------------------------------------------------------------------------- #
# Distinct failure outcomes                                                    #
# --------------------------------------------------------------------------- #

def test_limit_reached(isolate):
    def _raise(_title):
        raise HevyCustomExerciseLimitError("limit")
    _set_create(isolate, _raise)
    _cleaned, _actions, wr = _run(_block())
    assert wr[0].saved is False and wr[0].reason_code == "limit_reached"


def test_invalid_exercise_field(isolate):
    def _raise(_title):
        raise HevyBadRequestError("equipment_category must be one of ...")
    _set_create(isolate, _raise)
    _cleaned, _actions, wr = _run(_block())
    assert wr[0].saved is False and wr[0].reason_code == "invalid_exercise_field"


def test_created_unconfirmed_keeps_the_no_retry_guidance(isolate):
    def _raise(_title):
        raise HevyCreateUnresolvedError("never surfaced")
    _set_create(isolate, _raise)
    _cleaned, actions, wr = _run(_block())
    assert wr[0].saved is False and wr[0].reason_code == "created_unconfirmed"
    # The verbatim no-retry guidance rides the action string regardless of pass-2.
    assert "Do NOT create it again" in actions[0]


def test_generic_failure_is_create_failed(isolate):
    def _raise(_title):
        raise RuntimeError("boom")
    _set_create(isolate, _raise)
    _cleaned, _actions, wr = _run(_block())
    assert wr[0].saved is False and wr[0].reason_code == "create_failed"


def test_not_connected_is_a_failed_write(monkeypatch):
    monkeypatch.setattr(chat_mod, "user_hevy_key", lambda db, uid: None)
    _cleaned, actions, wr = _run(_block())
    assert wr[0].saved is False and wr[0].reason_code == "create_failed"
    assert any("not connected" in a.lower() for a in actions)


def test_invalid_json_block_is_reported(isolate):
    bad = "<hevy_create_exercise>\n{not json}\n</hevy_create_exercise>"
    _cleaned, _actions, wr = _run(bad)
    assert wr[0].reason_code == "invalid_json"


def test_missing_title_is_invalid_shape(isolate):
    block = '<hevy_create_exercise>\n{"exercise_type":"duration"}\n</hevy_create_exercise>'
    _cleaned, _actions, wr = _run(block)
    assert wr[0].saved is False and wr[0].reason_code == "invalid_shape"


# --------------------------------------------------------------------------- #
# Affordance + footer wiring                                                   #
# --------------------------------------------------------------------------- #

def test_exercise_affordances_are_informational_not_bug():
    """The distinct exercise outcomes are stated plainly, never handed back to the user
    as a format-fix (system_issue) and never framed as a choice (user_resolvable)."""
    for code in ("already_present", "limit_reached", "invalid_exercise_field", "created_unconfirmed"):
        assert chat_mod._write_affordance(code) == "informational"
    # Malformed-block codes remain our-side issues, as in the routine/knowledge lanes.
    assert chat_mod._write_affordance("invalid_json") == "system_issue"


def test_exercise_writes_feed_the_footer():
    from routers.chat import WriteResult, _render_write_footer
    footer = _render_write_footer([
        WriteResult(saved=True, reason_code="created", reason="✓ ...", key="A"),
        WriteResult(saved=False, reason_code="limit_reached", reason="⚠️ ...", key="B"),
    ])
    assert footer == "⚠ 1 saved, 1 failed — limit reached"
