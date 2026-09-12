"""The Hevy routine lane folded onto the WriteResult substrate (Q144).

A failed or collided routine create can no longer be narrated as success — it
yields a `WriteResult(saved=False, ...)` with a Hevy code, paired 1:1 with its
action string, exactly like the knowledge/schedule lane (#283/#284). These pin
the chat-lane orchestration; the connector floor itself lives in
test_hevy_routine_hardening.py.
"""
import asyncio

from connectors.hevy import RoutineAlreadyExists
from routers import chat as chat_mod

USER = 5


def _block(exercise_json: str = '{"exercise_template_id":"AAAA1111","sets":[{"type":"normal","reps":5}]}') -> str:
    return (
        "Done!\n<hevy_create_routine>\n"
        '{"title":"Push Day","exercises":[' + exercise_json + "]}\n"
        "</hevy_create_routine>"
    )


class _CollidingClient:
    async def create_routine(self, title, exercises, folder_id=None):
        raise RoutineAlreadyExists(title, folder_id, [{"id": "r1", "title": title, "folder_id": folder_id}])


class _FailingClient:
    async def create_routine(self, title, exercises, folder_id=None):
        raise RuntimeError("Hevy API error 502")


def test_collision_yields_already_exists_write_result(db_session):
    _cleaned, actions, write_results = asyncio.run(
        chat_mod._process_routine_actions(_block(), _CollidingClient(), USER, db_session)
    )
    assert len(write_results) == 1
    wr = write_results[0]
    assert wr.saved is False
    assert wr.reason_code == "already_exists"
    assert wr.key == "Push Day"
    # Paired 1:1 with the action string — the anti-gloss invariant.
    assert wr.reason in actions


def test_already_exists_is_user_resolvable():
    """The collision offers the user a choice (rename vs update), like day_time_clash —
    never handed back as a format-fix (system_issue)."""
    assert chat_mod._write_affordance("already_exists") == "user_resolvable"


def test_generic_create_failure_is_create_failed(db_session):
    _cleaned, _actions, write_results = asyncio.run(
        chat_mod._process_routine_actions(_block(), _FailingClient(), USER, db_session)
    )
    assert write_results[0].saved is False
    assert write_results[0].reason_code == "create_failed"


def test_hevy_not_connected_is_a_failed_write(db_session):
    _cleaned, actions, write_results = asyncio.run(
        chat_mod._process_routine_actions(_block(), None, USER, db_session)
    )
    assert write_results[0].saved is False
    assert write_results[0].reason_code == "create_failed"
    assert any("not connected" in a.lower() for a in actions)


def test_invalid_json_block_is_reported(db_session):
    bad = "<hevy_create_routine>\n{not json}\n</hevy_create_routine>"
    _cleaned, _actions, write_results = asyncio.run(
        chat_mod._process_routine_actions(bad, _FailingClient(), USER, db_session)
    )
    assert write_results[0].reason_code == "invalid_json"


def test_routine_writes_feed_the_deterministic_footer():
    """A collided routine write reaches the always-on footer, counted with any
    knowledge writes — the hard floor if pass-2 misreports."""
    from routers.chat import WriteResult, _render_write_footer

    footer = _render_write_footer([
        WriteResult(saved=True, reason_code="created", reason="✓ Routine 'A' created in Hevy", key="A"),
        WriteResult(saved=False, reason_code="already_exists", reason="⚠️ ...", key="B"),
    ])
    assert footer == "⚠ 1 saved, 1 failed — already exists"
