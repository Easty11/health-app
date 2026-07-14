"""End-to-end provisioning wiring for the title->id resolver (DECISIONS_LOG #60).

Exercises the chat routine-action path (routers.chat._process_routine_actions):
(a) title-only exercise resolves to the correct id and reaches create_routine
(b) a block that already carries an id is passed through untouched (opt-in, not forced)
(c) an unresolvable title skips the routine with a notice (no KeyError)
(d) id+title together — the prompt forbids it (#82), so this pins what happens
    when the model does it anyway. Only reachable since #82 permitted titles.
(e) an unresolved title's warning names ranked candidates (#83), and still
    provisions nothing.
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


# ---------- (d) id + title together — id wins, title is inert ----------
def test_id_and_title_together_uses_id_and_ignores_title(db_session):
    """#82 tells the model to emit id XOR title, never both. Models err, and this
    path only became reachable once titles were permitted at all. The id must win
    (the resolver skips any exercise already carrying one) and the stray title
    must not reach Hevy — create_routine builds its payload from an allowlist, so
    it is dropped by construction rather than by a guard that could rot.
    """
    _tmpl(db_session, "0222DB42", "Bench Press (Barbell)", is_custom=False)
    client = FakeHevyClient()
    reply = _block(
        '{"exercise_template_id":"0222DB42","title":"Some Other Lift",'
        '"sets":[{"type":"normal","reps":8}]}'
    )

    _cleaned, actions = asyncio.run(
        chat_mod._process_routine_actions(reply, client, USER, db_session)
    )

    assert len(client.calls) == 1
    ex = client.calls[0]["exercises"][0]
    assert ex["exercise_template_id"] == "0222DB42"   # the id the model gave, not a re-resolve
    assert any("created" in a.lower() for a in actions)


# ---------- (e) unresolved title -> warning names candidates (#83) ----------
def test_unresolved_title_warning_names_candidates(db_session):
    """The live-probe miss, end-to-end: the model emits 'Bulgarian Split Squat',
    the catalogue holds only the qualified variants. Fail-closed is UNCHANGED —
    the routine is still not created — but the warning now carries the exact
    titles to copy, and the model sees it next turn (the reply, actions appended,
    is echoed back as conversation history).
    """
    _tmpl(db_session, "B5D3A742", "Bulgarian Split Squat (Dumbbell)", is_custom=False)
    _tmpl(db_session, "A1B2C3D4", "Bulgarian Split Squat (Barbell)", is_custom=False)
    client = FakeHevyClient()
    reply = _block('{"title":"Bulgarian Split Squat","sets":[{"type":"normal","reps":8}]}')

    _cleaned, actions = asyncio.run(
        chat_mod._process_routine_actions(reply, client, USER, db_session)
    )

    assert client.calls == []                       # fail-closed, unchanged
    warning = " ".join(actions)
    assert "did you mean" in warning.lower()
    assert "Bulgarian Split Squat (Dumbbell)" in warning
    assert "Bulgarian Split Squat (Barbell)" in warning


def test_unresolved_title_with_no_candidates_says_so(db_session):
    """A miss resembling nothing must not print an empty 'did you mean:' — it
    says there is nothing to suggest."""
    _tmpl(db_session, "C7973E0E", "Leg Press (Machine)", is_custom=False)
    client = FakeHevyClient()
    reply = _block('{"title":"Zercher Moonwalk Press","sets":[{"type":"normal","reps":5}]}')

    _cleaned, actions = asyncio.run(
        chat_mod._process_routine_actions(reply, client, USER, db_session)
    )

    assert client.calls == []
    warning = " ".join(actions)
    assert "no similar exercise found" in warning
    assert "did you mean" not in warning.lower()
