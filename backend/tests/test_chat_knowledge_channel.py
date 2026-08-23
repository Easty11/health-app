"""The chat call site asserts its own channel; the model does not get a vote (#230).

`_process_knowledge_updates` parses a `<knowledge_update>` block out of an ASSISTANT
turn. Such a block arrived via chat by construction of the router -- there is no
reachable case where the model knows the channel better than the code that just
parsed it. The call site previously read `data.get("source", "chat")`, which meant a
model-supplied literal was trusted, and the fallback was the same silent default
`#230` removed one layer up.

The prompt half is pinned here too. `_section_user_profile` taught a
`<knowledge_update>` template that included `"source": "chat"`. A prompt that keeps
showing a field the code no longer reads asserts a contract the code does not hold --
the same defect `#230` closed on the model comment, in a surface with no other gate.
"""
import json

import context_builder
import models
from routers.chat import _process_knowledge_updates


def _user(db, email="chat-channel@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _block(payload: dict) -> str:
    return f"Noted.\n<knowledge_update>{json.dumps(payload)}</knowledge_update>\nDone."


def _only_entry(db, user_id):
    rows = db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id).all()
    assert len(rows) == 1, rows
    return rows[0]


# Conforms to the validated `schedule_item` shape (#233). These tests are about the
# CHANNEL a write lands under, not about the shape -- but the write path now refuses a
# non-conforming value, so a minimal-but-invalid fixture would fail here for a reason
# that has nothing to do with what is under test.
BASE = {"type": "schedule_item", "key": "physio_2026_08",
        "value": {
            "activity": "physio",
            "days": ["monday"],
            "hard": True,
            "expected_load": "light",
            "time_of_day": "morning",
            "same_day_training": False,
            "duration_weeks": None,
            "season_end": None,
        }}


def test_a_model_supplied_source_is_ignored_not_honoured(db_session):
    """The case this change exists for. The model asks for `system`; the row lands
    `chat`, because the router -- not the reply it is parsing -- knows the channel."""
    u = _user(db_session)

    _, actions = _process_knowledge_updates(
        _block({**BASE, "source": "system"}), u.id, db_session)

    assert _only_entry(db_session, u.id).source == "chat"
    assert any("saved" in a for a in actions), actions


def test_a_block_with_no_source_still_lands_as_chat(db_session):
    """Negative control for the case above -- the write must still SUCCEED. `source`
    is required at the schema (#230), so a call site that stopped supplying it would
    turn every chat-authored entry into a `Failed to save knowledge` action rather
    than a wrong label, and the assertion above would pass on an empty table."""
    u = _user(db_session, "chat-channel-nosource@example.com")

    _process_knowledge_updates(_block(BASE), u.id, db_session)

    assert _only_entry(db_session, u.id).source == "chat"


def test_a_model_supplied_source_that_is_not_a_declared_member_is_also_ignored(db_session):
    """A literal `SOURCE_VALUES` would refuse cannot reach the validator at all, so
    it costs a mislabelled row rather than a swallowed exception. Pins that the fix
    is "the call site decides", not "the validator catches it late"."""
    u = _user(db_session, "chat-channel-junk@example.com")

    _process_knowledge_updates(
        _block({**BASE, "source": "operator"}), u.id, db_session)

    assert _only_entry(db_session, u.id).source == "chat"


def test_the_prompt_no_longer_teaches_a_source_field(db_session):
    """The ungated half. Prompt surfaces have no behavioural test behind them, so
    this is the only thing standing between the template and a re-added line that
    documents a field the parser now discards."""
    section = context_builder._section_user_profile(None)

    assert "<knowledge_update>" in section, "template moved -- re-aim this assertion"
    assert '"source"' not in section
