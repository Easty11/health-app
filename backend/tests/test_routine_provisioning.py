"""End-to-end provisioning wiring for the title->id resolver (DECISIONS_LOG #60).

Exercises the chat routine-action path (routers.chat._process_routine_actions):
(a) title-only exercise resolves to the correct id and reaches create_routine
(b) a block that already carries an id is passed through untouched (opt-in, not forced)
(c) an unresolvable title skips the routine with a notice (no KeyError)
"""
import asyncio

import models
from routers import chat as chat_mod

USER = 3


class FakeHevyClient:
    def __init__(self):
        self.calls = []

    async def create_routine(self, title, exercises, folder_id=None):
        self.calls.append({"title": title, "exercises": exercises, "folder_id": folder_id})
        return {"routine": {"id": "fake"}}


def _tmpl(db, id_, title, is_custom, owner=None):
    db.add(models.HevyExerciseTemplate(
        id=id_, title=title, type="weight_reps", is_custom=is_custom, owner_user_id=owner,
    ))
    db.commit()


def _block(exercise_json: str) -> str:
    return (
        'Confirmed!\n<hevy_create_routine>\n'
        '{"title":"Push Day","exercises":[' + exercise_json + ']}\n'
        '</hevy_create_routine>'
    )


# ---------- (a) title-only -> resolved id, end-to-end ----------
def test_title_only_resolves_end_to_end(db_session):
    _tmpl(db_session, "0222DB42", "Bench Press (Barbell)", is_custom=False)
    client = FakeHevyClient()
    reply = _block('{"title":"Bench Press (Barbell)","sets":[{"type":"normal","reps":8}]}')

    cleaned, actions = asyncio.run(
        chat_mod._process_routine_actions(reply, client, USER, db_session)
    )

    assert len(client.calls) == 1
    ex = client.calls[0]["exercises"][0]
    assert ex["exercise_template_id"] == "0222DB42"   # title resolved to correct id
    assert "title" not in ex                          # title stripped after resolution
    assert any("created" in a for a in actions)
    assert "<hevy_create_routine>" not in cleaned      # block stripped from visible reply


# ---------- (b) existing id -> passed through untouched ----------
def test_existing_id_passthrough_untouched(db_session):
    # No template seeded — proves the id path never touches the resolver/DB.
    client = FakeHevyClient()
    reply = _block('{"exercise_template_id":"AAAA1111","sets":[{"type":"normal","reps":5}]}')

    _cleaned, _actions = asyncio.run(
        chat_mod._process_routine_actions(reply, client, USER, db_session)
    )

    assert client.calls[0]["exercises"][0]["exercise_template_id"] == "AAAA1111"


# ---------- (c) unresolvable title -> routine skipped with notice ----------
def test_unresolvable_title_skips_routine(db_session):
    client = FakeHevyClient()
    reply = _block('{"title":"Totally Made Up Lift","sets":[{"type":"normal","reps":5}]}')

    _cleaned, actions = asyncio.run(
        chat_mod._process_routine_actions(reply, client, USER, db_session)
    )

    assert client.calls == []                          # create_routine never called
    assert any("could not resolve" in a.lower() for a in actions)
