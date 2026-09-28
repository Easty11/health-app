"""Q185 — one bounded in-turn retry for a knowledge write refused FOR SHAPE (ruled 2026-09-28).

End to end through the real `/chat` endpoint; the model is faked at the client (transport) layer,
scripted per call. Gates:
  * a shape refusal triggers exactly ONE retry call, which carries the validator's message verbatim
    and the model's own draft; a corrected block saves, `retried=True`, and no pass-2 call fires;
  * cap 1: a retry that is refused again stays refused (never retried twice), and pass-2 fires;
  * never retried: a key clash, an operator-only/proposal refusal, a bad-JSON block;
  * the retry accepts only one block for the SAME key — a different key or an extra block is ignored;
  * every retry outcome is logged.
"""
import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from routers import chat as chat_router


class _FakeMessages:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def create(self, **kw):
        self.calls.append(kw)
        text = self.replies.pop(0) if self.replies else "Draft."
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


class _FakeClient:
    def __init__(self, replies):
        self.messages = _FakeMessages(replies)


def _kb(value, key="constraint_right_er_cap", type_="constraint", **extra):
    return "<knowledge_update>" + json.dumps({"type": type_, "key": key, "value": value, **extra}) + "</knowledge_update>"


GOOD = {"scope": {"tier": "advisory", "text": "right shoulder ER capped at 11.25 kg"}, "kind": "cap",
        "exit": {"on_condition": "pain-free at 11.25 kg"}, "review_by": "2026-10-26"}
BAD_SIDE = {**GOOD, "scope": {**GOOD["scope"], "side": "right"}}          # prod refusal 1
BAD_TIER = {**GOOD, "scope": {"tier": "engine-enforced", "region_keys": ["hinge"]}}   # prod refusal 2


@pytest.fixture
def chat(db_session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    u = models.User(email="retry@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: u
    client = TestClient(app)

    def send(replies, message="set that constraint"):
        fake = _FakeClient(replies)
        monkeypatch.setattr(chat_router.anthropic, "Anthropic", lambda api_key=None: fake)
        r = client.post("/chat", json={"message": message, "conversation_history": []})
        assert r.status_code == 200, r.text
        return r.json(), fake.messages.calls

    return {"send": send, "db": db_session, "user": u}


def _rows(chat):
    return chat["db"].query(models.UserKnowledgeEntry).filter_by(user_id=chat["user"].id).all()


@pytest.mark.parametrize("bad", [BAD_SIDE, BAD_TIER])
def test_a_shape_refusal_is_retried_once_and_the_fix_saves(chat, bad, caplog):
    caplog.set_level(logging.INFO, logger="routers.chat")
    first = "Proposing it.\n" + _kb(bad)
    body, calls = chat["send"]([first, _kb(GOOD)])
    assert len(calls) == 2                                   # draft + ONE retry; no pass-2 (it saved)
    retry_msg = calls[1]["messages"][-1]["content"]
    wr = body["write_results"][0]
    assert wr["saved"] is True and wr["retried"] is True and wr["reason_code"] == "saved"
    assert calls[1]["messages"][-2] == {"role": "assistant", "content": first}   # its own draft
    assert calls[1]["system"] == calls[0]["system"]          # same write-shape instructions
    (row,) = _rows(chat)
    assert row.value["scope"] == GOOD["scope"] and row.value["status"] == "proposed"
    assert "outcome=saved" in caplog.text
    # The validator's message, verbatim — recovered by re-running the validator on the bad value.
    from routers.knowledge import validate_constraint
    with pytest.raises(ValueError) as exc:
        validate_constraint({**bad, "status": "proposed", "asserted_by": None})
    assert str(exc.value) in retry_msg


def test_cap_one_a_second_refusal_is_final_and_pass2_fires(chat, caplog):
    caplog.set_level(logging.INFO, logger="routers.chat")
    body, calls = chat["send"](["x " + _kb(BAD_SIDE), _kb(BAD_TIER), "Corrected narration."])
    assert len(calls) == 3                                   # draft + one retry + pass-2 — never a 2nd retry
    wr = body["write_results"][0]
    assert wr["saved"] is False and wr["retried"] is True and wr["reason_code"] == "invalid_shape"
    assert "engine-enforced" in wr["validator_message"]      # the retry's own refusal is reported
    assert _rows(chat) == []
    assert "outcome=invalid_shape" in caplog.text


def test_unknown_region_refusal_names_the_valid_set_for_the_retry(chat):
    bad = {**GOOD, "kind": "block", "scope": {"tier": "engine", "region_keys": ["shoulder"]}}
    body, calls = chat["send"]([_kb(bad), _kb(GOOD)])
    assert "valid keys:" in calls[1]["messages"][-1]["content"]
    assert "shoulder_er_ir" in calls[1]["messages"][-1]["content"]
    assert body["write_results"][0]["saved"] is True


def _seed(chat, type_, key, value, source="api"):
    from routers.knowledge import KnowledgeEntryIn, upsert_knowledge_entry
    upsert_knowledge_entry(chat["user"].id, KnowledgeEntryIn(type=type_, key=key, value=value, source=source),
                           chat["db"])


@pytest.mark.parametrize("case", ["proposal_only", "operator_only", "key_collision", "invalid_json"])
def test_non_shape_refusals_are_never_retried(chat, case):
    if case == "proposal_only":
        block = _kb({**GOOD, "status": "confirmed", "asserted_by": "user"})
    elif case == "operator_only":
        _seed(chat, "constraint", "constraint_right_er_cap", {**GOOD, "status": "confirmed", "asserted_by": "user"})
        block = _kb({**GOOD, "review_by": "2026-11-01"})
    elif case == "key_collision":
        _seed(chat, "injury", "constraint_right_er_cap", {"body_part": "shoulder"})
        block = _kb(GOOD)
    else:
        block = "<knowledge_update>{not json</knowledge_update>"
    body, calls = chat["send"](["x " + block, "Corrected narration."])
    assert len(calls) == 2                                    # draft + pass-2 only: no retry call
    assert body["write_results"][0]["retried"] is False
    assert body["write_results"][0]["reason_code"] == case


def test_retry_accepts_only_one_block_for_the_same_key(chat, caplog):
    caplog.set_level(logging.INFO, logger="routers.chat")
    other = _kb(GOOD, key="constraint_something_else")
    body, calls = chat["send"](["x " + _kb(BAD_SIDE), other, "Narration."])
    assert len(calls) == 3                                    # the retry fired, then pass-2
    assert body["write_results"][0]["saved"] is False and body["write_results"][0]["retried"] is False
    assert _rows(chat) == []                                  # the other-key block was NOT written
    assert "outcome=no_single_block" in caplog.text


def test_retry_writes_the_fixed_block_and_ignores_extras(chat):
    extra = _kb({"body_part": "knee"}, key="injury_knee", type_="injury")
    body, calls = chat["send"](["x " + _kb(BAD_SIDE), _kb(GOOD) + "\n" + extra])
    assert body["write_results"][0]["saved"] is True
    assert [r.key for r in _rows(chat)] == ["constraint_right_er_cap"]     # the injury extra ignored


def test_a_transport_error_on_retry_keeps_the_refusal(chat, monkeypatch):
    class _Boom(_FakeMessages):
        def create(self, **kw):
            self.calls.append(kw)
            if len(self.calls) == 2:
                raise RuntimeError("upstream down")
            return super().create(**kw)

    fake = _FakeClient([])
    fake.messages = _Boom(["x " + _kb(BAD_SIDE), "unused", "Narration."])
    monkeypatch.setattr(chat_router.anthropic, "Anthropic", lambda api_key=None: fake)
    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_db] = lambda: chat["db"]
    app.dependency_overrides[get_current_user] = lambda: chat["user"]
    r = TestClient(app).post("/chat", json={"message": "m", "conversation_history": []})
    assert r.status_code == 200
    wr = r.json()["write_results"][0]
    assert wr["saved"] is False and wr["reason_code"] == "invalid_shape"


def test_a_clean_turn_makes_no_retry_call(chat):
    body, calls = chat["send"](["x " + _kb(GOOD)])
    assert len(calls) == 1 and body["write_results"][0]["saved"] is True


def test_two_retry_blocks_for_the_same_key_are_ambiguous_and_refused(chat, caplog):
    caplog.set_level(logging.INFO, logger="routers.chat")
    twice = _kb(GOOD) + "\n" + _kb({**GOOD, "kind": "caution"})
    body, calls = chat["send"](["x " + _kb(BAD_SIDE), twice, "Narration."])
    assert body["write_results"][0]["saved"] is False and _rows(chat) == []
    assert "outcome=no_single_block" in caplog.text
