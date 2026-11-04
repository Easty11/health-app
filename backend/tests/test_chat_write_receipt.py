"""The coach's reply carries a server-rendered receipt of what it wrote (GH#612; DECISIONS_LOG "The
coach's reply carries a server-rendered receipt").

Prod, 4 Nov 2026: turn 1 of the clinician debrief announced "constraint proposals" and emitted none;
its findings saved, so the footer read as a clean save and the operator read the prose. The receipt
is built from `write_results` — header, every action line (a typed save names its parent), the tally —
so a write that did not happen cannot be listed, and the header says nothing else was written. End to
end through the real `/chat`, the model faked at the transport layer (#166). Gates:
  * the model says it will propose constraints and emits only a finding → the receipt lists the
    finding, with its parent, and no constraint line;
  * one saved and one refused write → both listed, the refusal with its reason, the tally truthful;
  * a turn with no writes → no receipt block, the prose untouched;
  * a model echo of the header is stripped, so the header appears exactly once;
  * `write_results` carries the type and parent as fields; the prompt carries the guidance.
Fixtures are synthetic placeholders.
"""
import json
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import context_builder
import models
from auth import get_current_user
from database import get_db
from routers import chat as chat_router

INJURY = "injury_part_a_left"
FINDING = {"statement": "<what the review showed>", "domain": "injury", "as_of": "2026-11-04",
           "parent_key": INJURY, "basis": {"text": "<the transcript>"}, "derived_from_labs": False}
BAD_CONSTRAINT = {"scope": {"tier": "engine", "region_keys": ["deep_squat"], "side": "left"}, "kind": "block",
                  "parent_key": INJURY, "exit": {"with_parent": True}, "review_by": "2026-12-02"}


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


def _kb(payload):
    return "<knowledge_update>" + json.dumps(payload) + "</knowledge_update>"


@pytest.fixture
def chat(db_session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    u = models.User(email="receipt@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    db_session.add(models.UserKnowledgeEntry(
        user_id=u.id, type="injury", key=INJURY, source="api", added_at=date(2026, 10, 1), active=True,
        value={"body_part": "knee", "side": "left", "signal_type": "mechanical"}))
    db_session.commit()
    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: u
    client = TestClient(app)

    def send(replies, message="here is the clinician's summary"):
        fake = _FakeClient(replies)
        monkeypatch.setattr(chat_router.anthropic, "Anthropic", lambda api_key=None: fake)
        r = client.post("/chat", json={"message": message, "conversation_history": []})
        assert r.status_code == 200, r.text
        return r.json(), fake.messages.calls

    return {"send": send, "db": db_session, "user": u}


def _receipt(response: str) -> list[str]:
    """The lines from the receipt header to the end of the reply."""
    assert chat_router._RECEIPT_HEADER in response, response
    return response[response.index(chat_router._RECEIPT_HEADER):].splitlines()


# ── an announced step with no write is not in the receipt ────────────────────

def test_an_announced_constraint_with_no_block_is_absent_from_the_receipt(chat):
    body, _ = chat["send"]([
        "Recording the finding now, and I'll add three constraint proposals for the knee.\n"
        + _kb({"type": "finding", "key": "finding_knee_review", "value": FINDING})])
    lines = _receipt(body["response"])
    assert lines[0] == chat_router._RECEIPT_HEADER
    assert lines[1] == f"✓ Finding entry saved: finding_knee_review (re: {INJURY})"
    assert lines[-1] == "✓ 1 saved"
    assert not any("Constraint" in ln for ln in lines)
    assert body["response"].count(chat_router._RECEIPT_HEADER) == 1
    (wr,) = body["write_results"]
    assert (wr["saved"], wr["entry_type"], wr["parent_key"], wr["key"]) == (
        True, "finding", INJURY, "finding_knee_review")


# ── one saved and one refused: both listed, the tally truthful ───────────────

def test_a_saved_and_a_refused_write_are_both_listed_with_the_reason(chat):
    body, calls = chat["send"]([
        "Recording both.\n" + _kb({"type": "finding", "key": "finding_knee_review", "value": FINDING})
        + _kb({"type": "constraint", "key": "constraint_knee_deep", "value": BAD_CONSTRAINT})])
    lines = _receipt(body["response"])
    assert lines[1] == f"✓ Finding entry saved: finding_knee_review (re: {INJURY})"
    assert lines[2].startswith("✗ Constraint entry NOT saved: constraint_knee_deep — ")
    assert "unknown region key(s) ['deep_squat']" in lines[2] and "valid keys:" in lines[2]
    assert lines[-1] == "⚠ 1 saved, 1 failed — invalid shape"
    saved, refused = body["write_results"]
    assert saved["saved"] is True and saved["entry_type"] == "finding"
    assert refused["saved"] is False and refused["entry_type"] == "constraint"
    assert refused["parent_key"] == INJURY and refused["reason_code"] == "invalid_shape"
    # The Q185 in-turn retry and the pass-2 narration fired (the fake answered each with no block);
    # neither changes what the receipt lists.
    assert len(calls) >= 2


# ── no writes, no receipt ─────────────────────────────────────────────────────

def test_a_turn_with_no_writes_has_no_receipt_block(chat):
    body, _ = chat["send"](["Here is the answer, nothing to record."], message="a question")
    assert body["response"] == "Here is the answer, nothing to record."
    assert chat_router._RECEIPT_HEADER not in body["response"]
    assert body["write_results"] == []


# ── a model echo of the header is stripped ────────────────────────────────────

def test_a_model_echo_of_the_receipt_header_is_stripped(chat):
    body, _ = chat["send"]([
        "Recording it.\n" + chat_router._RECEIPT_HEADER + "\n✓ Finding entry saved: finding_knee_review\n"
        + _kb({"type": "finding", "key": "finding_knee_review", "value": FINDING})])
    assert body["response"].count(chat_router._RECEIPT_HEADER) == 1
    assert body["response"].count("✓ Finding entry saved: finding_knee_review") == 1
    assert body["response"].startswith("Recording it.")


def test_strip_footer_echo_covers_the_receipt_header():
    out = chat_router._strip_footer_echo("prose\n" + chat_router._RECEIPT_HEADER + "\nmore prose")
    assert "Receipt" not in out and out.startswith("prose") and out.endswith("more prose")


# ── the guidance rides the prompt; the receipt is the guarantee ──────────────

def test_the_prompt_says_a_step_with_no_receipt_line_was_not_written():
    """One sentence, byte-neutral against the #43 guard (operator-ruled 5 Nov 2026: the receipt
    carries the guarantee, so the guidance fits the existing budget or goes)."""
    section = context_builder._section_knowledge_update()
    assert "line is in the receipt; no line, not written — say so." in section
