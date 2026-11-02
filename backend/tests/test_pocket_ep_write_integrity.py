"""Pocket EP write integrity (prod, 1-2 Nov 2026) — what a chat turn may claim, and what it may link.

  * an appointment ask may link only a row whose injury is in `scope.parent_keys`; the refusal names
    the key to add, and the model gets one in-turn retry to add it;
  * `operator_only` is the user's own record: the outcome line names the route and the pass-2
    instruction says the user can do it themselves (no "raise it with someone");
  * a reply that says a check-in / soreness rating was saved gets a plain notice, whatever else the
    turn wrote, because chat has no check-in lane.

The model is faked at the client (transport) layer. Fixtures are SYNTHETIC ONLY.
"""
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from routers import chat as chat_router
from routers.chat import (
    _CHECKIN_NO_WRITE_NOTICE, _PASS2_SYSTEM, _claims_a_checkin_write, _process_knowledge_updates,
    _write_affordance,
)
from routers.knowledge import KnowledgeEntryIn, TypedEntryRefused, upsert_knowledge_entry

A, B = "injury_part_a_left", "injury_part_b_right"
CONSTRAINT_B = "constraint_part_b_cap"


def _user(db):
    u = models.User(email="pocket@example.com", hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _put(db, uid, type_, key, value):
    return upsert_knowledge_entry(uid, KnowledgeEntryIn(type=type_, key=key, value=value, source="api"), db)


def _world(db):
    u = _user(db)
    for key, part, side in ((A, "part a", "left"), (B, "part b", "right")):
        _put(db, u.id, "injury", key, {"body_part": part, "side": side, "signal_type": "mechanical",
                                       "restrictions": ["movement a"]})
    _put(db, u.id, "constraint", CONSTRAINT_B, {
        "scope": {"tier": "advisory", "text": "no movement b under load"}, "kind": "block",
        "parent_key": B, "exit": {"with_parent": True}, "review_by": "2026-12-01",
        "status": "confirmed", "asserted_by": "user"})
    return u


def _appt(parent_keys, asks):
    return {"clinician": "Clinician A", "practice": None, "at": "2026-11-04T15:30", "kind": "follow_up",
            "since": "2026-10-01", "scope": {"parent_keys": parent_keys}, "asks": asks, "status": "planned"}


def _ask(resolves_key=None, id_="a1"):
    ask = {"id": id_, "text": "Ask one", "priority": 1}
    if resolves_key:
        ask["resolves"] = {"entry_key": resolves_key, "note": None}
    return ask


# ── item 4: an ask can only link a row whose injury is in scope ───────────────

def test_an_ask_linking_a_row_outside_scope_is_refused_naming_the_key_to_add(db_session):
    u = _world(db_session)
    with pytest.raises(TypedEntryRefused) as exc:
        _put(db_session, u.id, "appointment", "appt_a", _appt([A], [_ask(CONSTRAINT_B)]))
    assert exc.value.code == "invalid_parent"
    assert B in str(exc.value) and "scope.parent_keys" in str(exc.value) and "a1" in str(exc.value)
    assert db_session.query(models.UserKnowledgeEntry).filter_by(type="appointment").count() == 0


def test_the_same_ask_saves_once_its_injury_is_in_scope(db_session):
    u = _world(db_session)
    _put(db_session, u.id, "appointment", "appt_a", _appt([A, B], [_ask(CONSTRAINT_B)]))
    assert db_session.query(models.UserKnowledgeEntry).filter_by(type="appointment").count() == 1


def test_an_ask_naming_an_injury_outside_scope_is_refused_too(db_session):
    u = _world(db_session)
    with pytest.raises(TypedEntryRefused) as exc:
        _put(db_session, u.id, "appointment", "appt_a", _appt([A], [_ask(B)]))
    assert exc.value.code == "invalid_parent" and B in str(exc.value)


def test_a_link_to_nothing_and_an_ask_with_no_link_stay_tolerated(db_session):
    u = _world(db_session)
    _put(db_session, u.id, "appointment", "appt_a",
         _appt([A], [_ask("constraint_does_not_exist"), {"id": "a2", "text": "Two", "priority": 2}]))


# ── item 4, end to end: the refusal is retried once and the fix saves ─────────

class _FakeMessages:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def create(self, **kw):
        self.calls.append(kw)
        text = self.replies.pop(0) if self.replies else "Draft."
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


@pytest.fixture
def chat(db_session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    u = _world(db_session)
    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: u
    client = TestClient(app)

    def send(replies, message="plan it"):
        fake = SimpleNamespace(messages=_FakeMessages(replies))
        monkeypatch.setattr(chat_router.anthropic, "Anthropic", lambda api_key=None: fake)
        r = client.post("/chat", json={"message": message, "conversation_history": []})
        assert r.status_code == 200, r.text
        return r.json(), fake.messages.calls

    return {"send": send, "db": db_session, "user": u}


def _kb(type_, key, value, **extra):
    return "<knowledge_update>" + json.dumps({"type": type_, "key": key, "value": value, **extra}) + "</knowledge_update>"


def test_the_scope_refusal_is_retried_once_and_the_fix_saves(chat):
    bad = _kb("appointment", "appt_a", _appt([A], [_ask(CONSTRAINT_B)]))
    good = _kb("appointment", "appt_a", _appt([A, B], [_ask(CONSTRAINT_B)]))
    body, calls = chat["send"](["Planning it.\n" + bad, good])
    assert len(calls) == 2                                   # draft + ONE retry; it saved, so no pass-2
    assert B in calls[1]["messages"][-1]["content"]          # the retry is told which key to add
    wr = body["write_results"][0]
    assert wr["saved"] is True and wr["retried"] is True


# ── item 3: operator_only names the route and tells the user they can do it ───

def test_operator_only_retire_names_the_resolve_route(chat):
    body, calls = chat["send"](['Removing it.\n<knowledge_update>{"type": "constraint", "key": "%s", '
                                '"active": false}</knowledge_update>' % CONSTRAINT_B, "Narration."])
    row = chat["db"].query(models.UserKnowledgeEntry).filter_by(key=CONSTRAINT_B, active=True).one()
    wr = body["write_results"][0]
    assert not wr["saved"] and wr["reason_code"] == "operator_only"
    assert f"POST /knowledge/constraints/{row.id}/resolve" in wr["reason"]
    assert "only you can retire it" in wr["reason"]
    assert any(f"/knowledge/constraints/{row.id}/resolve" in a for a in body["actions_taken"])


def test_operator_only_on_an_injury_points_at_the_injuries_page(chat):
    inj = chat["db"].query(models.UserKnowledgeEntry).filter_by(key=A, active=True).one()
    from routers.knowledge import operator_route_hint
    assert "/injuries" in operator_route_hint(inj)


def test_operator_only_on_a_rewrite_names_the_route_not_a_retry(chat):
    value = {"scope": {"tier": "advisory", "text": "no movement b under load"}, "kind": "block",
             "parent_key": B, "exit": {"with_parent": True}, "review_by": "2026-12-02"}
    body, _ = chat["send"]([_kb("constraint", CONSTRAINT_B, value), "Narration."])
    wr = body["write_results"][0]
    assert wr["reason_code"] == "operator_only" and wr["retried"] is False
    assert "Only you can do this: retire it yourself with POST /knowledge/constraints/" in wr["reason"]
    assert "retry with a corrected block" not in wr["reason"]


def test_pass2_gets_the_user_can_resolve_instruction_and_the_route(chat):
    body, calls = chat["send"](['<knowledge_update>{"type": "constraint", "key": "%s", "active": false}'
                                '</knowledge_update>' % CONSTRAINT_B, "Narration."])
    assert _write_affordance("operator_only") == "user_can_resolve"
    pass2 = calls[-1]
    assert "user_can_resolve" in pass2["system"] and "IS the operator" in pass2["system"]
    assert "NEVER say to raise it with" in pass2["system"]
    content = pass2["messages"][0]["content"]
    assert "[NOT SAVED · user_can_resolve]" in content and "/knowledge/constraints/" in content


def test_pass2_instruction_does_not_send_the_user_to_someone_else():
    assert "whoever manages" not in _PASS2_SYSTEM


# ── item 2: a check-in write claimed in prose, whatever the receipt holds ─────

@pytest.mark.parametrize("sentence", [
    "I've updated your check-in soreness for the calf.",
    "Your check-in has been saved with soreness 3.",
    "Soreness update logged.",
    "Done - recorded in today's check-in.",
    "The soreness rating was saved.",
])
def test_a_check_in_save_claim_is_detected(sentence):
    assert _claims_a_checkin_write(sentence)


@pytest.mark.parametrize("sentence", [
    "I can't update your check-in from chat; enter it on the check-in screen.",
    "Want me to log that in your check-in?",
    "Your check-in shows soreness 3 today.",
    "I've saved the calf injury entry.",
    "Soreness tracking for the calf is set up through the injury entry.",
])
def test_a_denial_a_question_or_an_unrelated_save_is_not_a_claim(sentence):
    assert not _claims_a_checkin_write(sentence)


def test_the_claim_gets_a_notice_even_when_other_writes_saved(chat):
    block = _kb("injury", "injury_part_c", {"body_part": "part c", "side": "left",
                                            "signal_type": "mechanical", "restrictions": ["movement c"]})
    body, _ = chat["send"](["Recording the injury. I've updated your check-in soreness too.\n" + block])
    assert body["write_results"][0]["saved"] is True
    assert body["response"].count(_CHECKIN_NO_WRITE_NOTICE) == 1
    assert "✓ 1 saved" in body["response"]                   # the real receipt is still there


def test_an_honest_reply_gets_no_notice(chat):
    body, _ = chat["send"](["Noted. Enter today's soreness on the check-in screen."])
    assert _CHECKIN_NO_WRITE_NOTICE not in body["response"]


def test_the_systems_own_action_lines_never_trip_the_guard(db_session):
    u = _world(db_session)
    _, actions, results = _process_knowledge_updates(
        _kb("injury", "injury_check_in_x", {"body_part": "part c", "side": "left",
                                            "signal_type": "mechanical", "restrictions": ["movement c"]}),
        u.id, db_session)
    assert results[0].saved and not _claims_a_checkin_write("\n".join(actions).replace("injury_check_in_x", "k"))
