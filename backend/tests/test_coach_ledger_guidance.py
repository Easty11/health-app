"""Coach guidance for typed ledger writes, and the two refusals that guarantee it (GH#627; GH#608 R2
and R3; DECISIONS_LOG #499, #500 and the R1–R3 ruling entry).

The 4 Nov 2026 clinician debrief: zero of seven coach-authored proposals parented (#499), a resolved calf
strain written as a new active injury row twice with six engine defaults staged (#500), and a coach
rewrite that replaced a precise operator record with "mild re-strain" (GH#608 E1). Four sentences sit
beside the write shapes (#313 / FEEDBACK §45); two of them are enforced in the write path, and the
receipt (#498) shows the refusal. End to end through the real `/chat`, the model faked at the transport
layer (#166); the prompt the model saw is asserted to carry each sentence. Gates:
  (a) a turn naming the knee yields a proposal parented to the knee, and the receipt names the parent;
  (b) a healed event yields a finding, no injury row, and no engine default is staged;
  (c) a chat proposal that sets `asserted_by` is refused (`proposal_only`) and listed as refused;
  (d) a chat rewrite of a row the operator wrote or edited in-app (`source: "api"`) is refused
      (`operator_only`), the refusal names Edit, the row is untouched, and a chat deactivation of it is
      refused the same way; chat may still rewrite and withdraw its own proposals.
The prompt-byte guard (#43, `test_current_state.py`) is met by trimming: 11707 → 11702 (−5).
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
from routers.knowledge import (
    EDIT_NOTES_PREFIX, KnowledgeEntryIn, TypedEntryRefused, chat_may_not_rewrite_operator_row,
    upsert_knowledge_entry,
)

KNEE = "injury_knee_left"
CAP = {"scope": {"tier": "advisory", "text": "<side> knee: deep loaded flexion capped at <load>"}, "kind": "cap",
       "exit": {"on_condition": "<the clinician's review>"}, "review_by": "2026-12-02"}


class _FakeMessages:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def create(self, **kw):
        self.calls.append(kw)
        r = self.replies.pop(0) if self.replies else "Draft."
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=r)], stop_reason="end_turn")


class _FakeClient:
    def __init__(self, replies):
        self.messages = _FakeMessages(replies)


def _kb(payload):
    return "<knowledge_update>" + json.dumps(payload) + "</knowledge_update>"


def _rows(db, uid, type_=None):
    q = db.query(models.UserKnowledgeEntry).filter_by(user_id=uid)
    if type_:
        q = q.filter_by(type=type_)
    return q.order_by(models.UserKnowledgeEntry.id).all()


def _proposed_constraints(db, uid):
    return [r for r in _rows(db, uid, "constraint") if r.active and (r.value or {}).get("status") == "proposed"]


@pytest.fixture
def chat(db_session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    u = models.User(email="guidance@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    db_session.add(models.UserKnowledgeEntry(
        user_id=u.id, type="injury", key=KNEE, source="api", added_at=date(2026, 11, 1), active=True,
        value={"body_part": "knee", "side": "left", "signal_type": "mechanical"}))
    db_session.commit()
    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: u
    client = TestClient(app)

    def send(replies, message):
        fake = _FakeClient(replies)
        monkeypatch.setattr(chat_router.anthropic, "Anthropic", lambda api_key=None: fake)
        r = client.post("/chat", json={"message": message, "conversation_history": []})
        assert r.status_code == 200, r.text
        return r.json(), fake.messages.calls

    return {"send": send, "db": db_session, "user": u}


def _receipt(response: str) -> list[str]:
    assert chat_router._RECEIPT_HEADER in response, response
    return response[response.index(chat_router._RECEIPT_HEADER):].splitlines()


# ── (a) parent_key whenever the turn names the injury ────────────────────────

A_SENTENCE = "`parent_key`: the injury's key whenever the turn names the injury it belongs to"


def test_a_turn_naming_the_knee_yields_a_proposal_parented_to_the_knee(chat):
    body, calls = chat["send"](
        ["Recording the knee cap.\n" + _kb({"type": "constraint", "key": "constraint_knee_left_cap",
                                            "value": {**CAP, "parent_key": KNEE}})],
        message="Aubrey said to cap deep loaded flexion on the left knee until she reviews it")
    assert A_SENTENCE in calls[0]["system"]                       # the guidance the model saw
    assert "`parent_key`: as for a constraint." in calls[0]["system"]
    lines = _receipt(body["response"])
    assert lines[1] == f"✓ Constraint entry saved: constraint_knee_left_cap (re: {KNEE})"
    (wr,) = body["write_results"]
    assert (wr["saved"], wr["entry_type"], wr["parent_key"]) == (True, "constraint", KNEE)
    (row,) = _proposed_constraints(chat["db"], chat["user"].id)
    assert row.value["parent_key"] == KNEE and row.source == "chat" and row.value["asserted_by"] is None


# ── (b) a resolved event is a finding, never an injury row ───────────────────

B_SENTENCE = ("An event described as already resolved is a `type=\"finding\"` (domain \"injury\", parented to\n"
              "  the standing injury row where one exists), never a new or reopened injury row; a resolved\n"
              "  episode's key is never reused.")


def test_a_healed_event_yields_a_finding_and_stages_no_engine_default(chat):
    db, uid = chat["db"], chat["user"].id
    assert _proposed_constraints(db, uid) == []
    body, calls = chat["send"](
        ["Noting it as a finding, not a new injury.\n" + _kb({
            "type": "finding", "key": "finding_calf_left_oct2026_resolved",
            "value": {"statement": "<a late-October left calf strain, resolved within a week per the clinician>",
                      "domain": "injury", "as_of": "2026-11-04", "basis": {"text": "<the clinician's summary>"},
                      "derived_from_labs": False}})],
        message="Aubrey said the late-October calf strain is resolved, it was minor")
    assert B_SENTENCE in calls[0]["system"]
    lines = _receipt(body["response"])
    assert lines[1] == "✓ Finding entry saved: finding_calf_left_oct2026_resolved"
    assert [r.key for r in _rows(db, uid, "injury")] == [KNEE]    # no injury row written or reopened
    assert _proposed_constraints(db, uid) == []                    # no engine default staged
    (f,) = _rows(db, uid, "finding")
    assert f.value["status"] == "proposed" and f.value["domain"] == "injury"


# ── (c) authority is never set on a proposal ──────────────────────────────────

def test_a_chat_proposal_that_sets_asserted_by_is_refused_and_the_receipt_says_so(chat):
    body, calls = chat["send"](
        ["Recording it as the clinician's.\n" + _kb({"type": "constraint", "key": "constraint_knee_left_cap",
                                                      "value": {**CAP, "parent_key": KNEE, "asserted_by": "clinician"}})],
        message="record the knee cap as Aubrey's")
    assert "Never send status, asserted_by, confirmed_on, resolution or any other key." in calls[0]["system"]
    lines = _receipt(body["response"])
    assert lines[1].startswith("✗ Constraint entry NOT saved: constraint_knee_left_cap — ")
    assert "is a PROPOSAL" in lines[1] and "asserted_by null" in lines[1]
    assert lines[-1] == "⚠ 0 saved, 1 failed — proposal_only"
    (wr,) = body["write_results"]
    assert wr["saved"] is False and wr["reason_code"] == "proposal_only" and wr["retried"] is False
    assert _proposed_constraints(chat["db"], chat["user"].id) == []


# ── (d) the coach never supersedes an operator-written row ───────────────────

D_SENTENCE = "Never\nrewrite a row the user wrote or edited in-app (it is refused; they use Edit on its card)."


def _operator_proposal(db, uid, key="constraint_knee_left_cap"):
    """The row the in-app Edit writes (GH#617): a superseding PROPOSAL with `source: "api"` and the
    predecessor named in `notes`; here written directly, as an operator PowerShell write would be too."""
    return upsert_knowledge_entry(uid, KnowledgeEntryIn(
        type="constraint", key=key, source="api", notes=f"{EDIT_NOTES_PREFIX}0",
        value={**CAP, "parent_key": KNEE, "detail": "the operator's precise detail",
               "status": "proposed", "asserted_by": None}), db)


def test_a_chat_rewrite_of_an_operator_edited_proposal_is_refused_and_names_edit(chat):
    db, uid = chat["db"], chat["user"].id
    mine = _operator_proposal(db, uid)
    before = dict(mine.value)
    body, calls = chat["send"](
        ["Updating the knee cap.\n" + _kb({"type": "constraint", "key": "constraint_knee_left_cap",
                                           "value": {**CAP, "parent_key": KNEE, "detail": "mild"}})],
        message="the knee cap is just mild now")
    assert D_SENTENCE in calls[0]["system"]
    lines = _receipt(body["response"])
    assert lines[1].startswith("✗ Constraint entry NOT saved: constraint_knee_left_cap — ")
    assert "written or edited by you in the app" in lines[1] and "correct it with Edit on its card" in lines[1]
    assert "Only you can do this: edit it yourself with Edit on its card" in lines[1]
    assert f"POST /knowledge/constraints/{mine.id}/edit" in lines[1]
    assert lines[-1] == "⚠ 0 saved, 1 failed — yours to change"
    (wr,) = body["write_results"]
    assert wr["saved"] is False and wr["reason_code"] == "operator_only" and wr["retried"] is False
    db.refresh(mine)
    assert mine.active is True and mine.superseded_by is None and mine.value == before   # untouched
    assert [r.id for r in _rows(db, uid, "constraint")] == [mine.id]                   # nothing written


def test_a_chat_deactivation_of_an_operator_proposal_is_refused_the_same_way(chat):
    db, uid = chat["db"], chat["user"].id
    mine = _operator_proposal(db, uid)
    body, _ = chat["send"](
        ["Dropping the knee cap.\n" + _kb({"type": "constraint", "key": "constraint_knee_left_cap", "active": False})],
        message="drop the knee cap")
    lines = _receipt(body["response"])
    assert lines[1].startswith("✗ Constraint entry NOT removed: constraint_knee_left_cap — you wrote or edited it in the app")
    assert "Edit on its card" in lines[1]
    (wr,) = body["write_results"]
    assert wr["saved"] is False and wr["reason_code"] == "operator_only"
    db.refresh(mine)
    assert mine.active is True


def test_chat_may_still_rewrite_and_withdraw_its_own_proposal(chat):
    """Negative control: the R3 discriminator is the row's SOURCE. A chat-written proposal is chat's to
    rewrite (same-key supersede) and to withdraw; an engine default (`system`) is not an operator row."""
    db, uid = chat["db"], chat["user"].id
    first = upsert_knowledge_entry(uid, KnowledgeEntryIn(
        type="constraint", key="constraint_knee_left_cap", source="chat",
        value={**CAP, "parent_key": KNEE, "status": "proposed", "asserted_by": None}), db)
    body, _ = chat["send"](
        ["Tightening it.\n" + _kb({"type": "constraint", "key": "constraint_knee_left_cap",
                                   "value": {**CAP, "parent_key": KNEE, "detail": "tightened"}})],
        message="tighten the knee cap")
    assert _receipt(body["response"])[1] == f"✓ Constraint entry saved: constraint_knee_left_cap (re: {KNEE})"
    db.refresh(first)
    assert first.active is False and first.superseded_by is not None
    system_row = SimpleNamespace(type="constraint", source="system", value={"status": "proposed"})
    assert chat_may_not_rewrite_operator_row(system_row) is False
    assert chat_may_not_rewrite_operator_row(SimpleNamespace(type="injury", source="api", value={})) is False


def test_the_guard_is_in_the_upsert_itself_not_only_the_chat_router(chat):
    """Every chat writer passes `upsert_knowledge_entry`; the refusal lives there (#221's ordering: no
    row is staged before it fires) and the operator's own api write over the same key still works."""
    db, uid = chat["db"], chat["user"].id
    mine = _operator_proposal(db, uid)
    with pytest.raises(TypedEntryRefused) as exc:
        upsert_knowledge_entry(uid, KnowledgeEntryIn(
            type="constraint", key="constraint_knee_left_cap", source="chat",
            value={**CAP, "parent_key": KNEE, "status": "proposed", "asserted_by": None}), db)
    assert exc.value.code == "operator_only" and "Edit on its card" in str(exc.value)
    db.rollback()
    again = upsert_knowledge_entry(uid, KnowledgeEntryIn(
        type="constraint", key="constraint_knee_left_cap", source="api",
        value={**CAP, "parent_key": KNEE, "status": "proposed", "asserted_by": None, "detail": "re-edited"}), db)
    db.refresh(mine)
    assert mine.superseded_by == again.id and again.source == "api"


# ── the prompt-byte guard is met by trimming ──────────────────────────────────

def test_the_four_sentences_ride_the_prompt_within_the_trimmed_budget():
    section = context_builder._section_knowledge_update()
    for s in (A_SENTENCE, B_SENTENCE, D_SENTENCE, "Never send status, asserted_by"):
        assert s in section
    assert len(section.encode()) <= 11707, "the #43 budget is met by trimming, never by raising it"
