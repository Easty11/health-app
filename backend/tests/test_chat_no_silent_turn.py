"""Q187 — a chat turn never ends silent, and a typed write needs no in-chat confirmation.

Prod, 28 Sep 2026: the coach asked "Do you confirm?" before a finding write. The operator's "yes" came
back as an EMPTY bubble (HTTP 200) and nothing was written. Re-sending the original request wrote the
row first time. End to end through the real `/chat` endpoint, the model faked at the transport layer
(#166). Gates:
  * a first-turn finding request that carries the block writes a proposal (no second turn needed);
  * a reply that is empty, has no content blocks, is only <thinking>, or is only a mimicked save line
    never renders empty, and it says nothing was saved;
  * a typed block with no key, and a legacy block with no content, are REPORTED refusals, not silent drops;
  * the prompt tells the coach to write proposals directly and never to ask for confirmation in chat.
Fixtures are synthetic placeholders.
"""
import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import context_builder
import models
from auth import get_current_user
from database import get_db
from routers import chat as chat_router


class _FakeMessages:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def create(self, **kw):
        self.calls.append(kw)
        r = self.replies.pop(0) if self.replies else "Draft."
        content = r if isinstance(r, list) else [SimpleNamespace(type="text", text=r)]
        return SimpleNamespace(content=content, stop_reason="end_turn")


class _FakeClient:
    def __init__(self, replies):
        self.messages = _FakeMessages(replies)


FINDING = {"statement": "<what the imaging shows>", "domain": "injury", "as_of": "2026-01-01",
           "basis": {"text": "<the report>"}, "derived_from_labs": False}


def _kb(payload):
    return "<knowledge_update>" + json.dumps(payload) + "</knowledge_update>"


@pytest.fixture
def chat(db_session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    u = models.User(email="silent@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: u
    client = TestClient(app)

    def send(replies, message="record the imaging finding", history=()):
        fake = _FakeClient(replies)
        monkeypatch.setattr(chat_router.anthropic, "Anthropic", lambda api_key=None: fake)
        r = client.post("/chat", json={"message": message, "conversation_history": list(history)})
        assert r.status_code == 200, r.text
        return r.json(), fake.messages.calls

    return {"send": send, "db": db_session, "user": u}


def _rows(chat):
    return chat["db"].query(models.UserKnowledgeEntry).filter_by(user_id=chat["user"].id).all()


# ── the write lands on the FIRST turn ────────────────────────────────────────

def test_a_finding_request_writes_a_proposal_on_the_first_turn(chat):
    body, calls = chat["send"](["Recording that as a proposed finding.\n" + _kb(
        {"type": "finding", "key": "finding_example_imaging", "value": FINDING})])
    assert len(calls) == 1
    (wr,) = body["write_results"]
    assert wr["saved"] is True and wr["key"] == "finding_example_imaging"
    (row,) = _rows(chat)
    assert row.type == "finding" and row.value["status"] == "proposed"
    assert "✓ 1 saved" in body["response"]


# ── a turn never renders empty ───────────────────────────────────────────────

@pytest.mark.parametrize("reply", [
    "",                                        # the model returned no text
    [],                                        # no content blocks at all (was an IndexError → 500)
    "<thinking>the user said yes, so I will record it</thinking>",   # scratch only
])
def test_an_empty_turn_renders_a_visible_no_write_notice(chat, reply, caplog):
    caplog.set_level(logging.INFO, logger="routers.chat")
    body, _ = chat["send"]([reply], message="yes")
    assert body["response"] == chat_router._EMPTY_TURN_NOTICE
    assert "nothing was saved" in body["response"]
    assert body["write_results"] == [] and _rows(chat) == []
    assert "empty reply after processing" in caplog.text


@pytest.mark.parametrize("claim", [
    "✓ Finding entry saved: finding_example_imaging",    # the per-entry grammar, no block
    "✓ 1 saved",                                        # the tally grammar, no block
])
def test_a_mimicked_save_with_no_block_says_nothing_was_saved(chat, claim):
    body, _ = chat["send"]([claim], message="yes")
    assert body["response"] == chat_router._NO_WRITE_NOTICE
    assert body["write_results"] == [] and _rows(chat) == []


def test_prose_plus_a_mimicked_save_keeps_the_prose_and_adds_the_notice(chat):
    body, _ = chat["send"](["Done, that's on your record.\n✓ Finding entry saved: finding_example_imaging"],
                           message="yes")
    assert body["response"].startswith("Done, that's on your record.")
    assert body["response"].endswith(chat_router._NO_WRITE_NOTICE)
    assert "✓ Finding entry saved" not in body["response"]


def test_a_real_write_gets_no_no_write_notice(chat):
    body, _ = chat["send"]([_kb({"type": "finding", "key": "finding_example_imaging", "value": FINDING})])
    assert chat_router._NO_WRITE_NOTICE not in body["response"]
    assert chat_router._EMPTY_TURN_NOTICE not in body["response"]
    assert body["response"].strip()                       # block-only reply still shows the footer


def test_a_plain_conversational_turn_is_untouched(chat):
    body, _ = chat["send"](["Here is the answer."], message="a question")
    assert body["response"] == "Here is the answer."


def test_turn_metadata_is_logged_without_the_text(chat, caplog):
    caplog.set_level(logging.INFO, logger="routers.chat")
    chat["send"](["private health detail " + _kb({"type": "finding", "key": "finding_example_imaging",
                                                   "value": FINDING})])
    assert "stop_reason=end_turn" in caplog.text and "write_blocks=1" in caplog.text
    assert "private health detail" not in caplog.text


# ── silent drops are now reported refusals ───────────────────────────────────

def test_a_typed_block_with_no_key_is_refused_not_dropped(chat):
    body, calls = chat["send"](["Recording it.\n" + _kb({"type": "finding", "value": FINDING})])
    (wr,) = body["write_results"]
    assert wr["saved"] is False and wr["reason_code"] == "invalid_shape"
    assert "no top-level `key`" in wr["reason"]
    assert _rows(chat) == []
    assert "NOT saved" in body["response"]
    assert len(calls) == 2                                   # draft + pass-2; no retry (no key to retry)


def test_a_legacy_block_with_no_content_is_refused_not_dropped(chat):
    body, _ = chat["send"]([_kb({"category": "Goals", "content": ""})])
    (wr,) = body["write_results"]
    assert wr["saved"] is False and wr["reason_code"] == "invalid_shape"
    assert "no content" in wr["reason"]
    assert body["response"].strip()


# ── the prompt: write directly, never confirm in chat ────────────────────────

SECTION = " ".join(context_builder._section_knowledge_update().split())


def test_prompt_says_write_proposals_directly():
    assert "you write the proposal DIRECTLY" in SECTION
    assert "emit the block in THAT reply" in SECTION
    assert "Never ask for confirmation in chat first" in SECTION
    assert 'A "yes" typed in chat confirms nothing and writes nothing' in SECTION
    assert "with its Confirm button" in SECTION


def test_prompt_no_longer_carries_the_ambiguous_confirm_line():
    # "the user confirms it themselves" read as "ask them in chat" — the origin of the yes-turn hang.
    assert "the user confirms it themselves" not in SECTION


def test_prompt_says_a_yes_turn_must_carry_the_block():
    assert "that reply MUST contain the block" in SECTION
    assert "A reply without the block records nothing" in SECTION


def test_schedule_clarifying_questions_are_for_missing_facts_not_consent():
    profile = " ".join(context_builder._section_user_profile(None).split())
    assert "These questions are for MISSING FACTS only" in profile
    assert "Never ask permission or confirmation to write" in profile
