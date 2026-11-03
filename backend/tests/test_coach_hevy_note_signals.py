"""A Hevy exercise note that reports pain or a limit is an injury signal the coach proposes from
(DECISIONS_LOG "A Hevy exercise note that reports pain or a limit is an injury signal"; PR-D of the
injury-lifecycle-in-app brief). Guidance only: the notes were already in the prompt (`render_workout`
prints each exercise's note for the ten most recent workouts), so the change is one paragraph.

End to end through the real `/chat`: Hevy faked at the TRANSPORT layer (the real client parses the real
JSON, #166 companion rule) with a workout whose exercise note reads "R shoulder posterior pain at 32 kg,
stopped set 3"; the model faked at the client layer. Fixture 1: the model emits a constraint proposal
parented to `injury_shoulder_right`, quoting the date and exercise; it lands `proposed` / `asserted_by`
null and the prompt the model saw carried both the note and the paragraph. Fixture 2 (GH#609): the model
writes the same note to a free-text category instead; the PROMPT forbids it, and the write path's refusal
is the stamp issue's proposed guard, pinned here as a strict xfail so landing it must flip this test.
"""
import json
from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import connectors.hevy as hevy_connector
import context_builder
import models
from auth import get_current_user
from database import get_db
from encryption import encrypt
from routers import chat as chat_router

NOTE = "R shoulder posterior pain at 32 kg, stopped set 3"
WORKOUT = {
    "id": "w-1", "title": "Upper A", "description": None,
    "start_time": "2026-11-02T07:40:00+00:00", "end_time": "2026-11-02T08:50:00+00:00",
    "exercises": [{
        "index": 0, "title": "Seated DB Press", "exercise_template_id": "TPL1", "superset_id": None,
        "notes": NOTE,
        "sets": [{"index": 0, "type": "normal", "weight_kg": 32, "reps": 8, "rpe": None, "custom_metric": None}],
    }],
}
PARAGRAPH = "A HEVY EXERCISE NOTE IS AN INJURY SIGNAL."
PROPOSAL = {
    "scope": {"tier": "advisory", "text": "2026-11-02, Seated DB Press: " + NOTE + " -- cap the press at 32 kg"},
    "kind": "cap", "parent_key": "injury_shoulder_right", "exit": {"with_parent": True}, "review_by": "2026-12-01",
}


def _kb(obj):
    return "<knowledge_update>" + json.dumps(obj) + "</knowledge_update>"


class _FakeMessages:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def create(self, **kw):
        self.calls.append(kw)
        text = self.replies.pop(0) if self.replies else "Draft."
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


@pytest.fixture
def world(db_session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    u = models.User(email="hevy-note@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    db_session.add(models.UserIntegration(user_id=u.id, provider="hevy", api_key_encrypted=encrypt("test-key")))
    db_session.add(models.UserKnowledgeEntry(
        user_id=u.id, type="injury", key="injury_shoulder_right", source="api", added_at=date(2026, 10, 1),
        active=True, value={"body_part": "shoulder", "side": "right", "signal_type": "mechanical"}))
    db_session.commit()

    # Hevy at the transport: the count, the ten most recent workouts (ours), and nothing else.
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/workouts/count"):
            body = {"workout_count": 1}
        elif path.endswith("/workouts"):
            body = {"page": 1, "page_count": 1, "workouts": [WORKOUT]}
        else:
            body = {"page": 1, "page_count": 1, "routines": [], "routine_folders": []}
        return httpx.Response(200, content=json.dumps(body), headers={"content-type": "application/json"})

    real_client = httpx.AsyncClient

    def faked_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(hevy_connector.httpx, "AsyncClient", faked_client)

    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: u

    def send(replies, message="how did the press go?"):
        fake = SimpleNamespace(messages=_FakeMessages(replies))
        monkeypatch.setattr(chat_router.anthropic, "Anthropic", lambda api_key=None: fake)
        r = TestClient(app).post("/chat", json={"message": message, "conversation_history": []})
        assert r.status_code == 200, r.text
        return r.json(), fake.messages.calls

    return {"send": send, "db": db_session, "user": u}


def test_the_note_reaches_the_prompt_and_the_proposal_lands_as_a_proposal(world):
    body, calls = world["send"]([_kb({"type": "constraint", "key": "constraint_shoulder_right_press_cap", "value": PROPOSAL})])
    system = calls[0]["system"]
    assert NOTE in system and "Seated DB Press" in system                 # the note was already in context
    assert PARAGRAPH in system                                             # and the guidance names it a signal
    wr = body["write_results"][0]
    assert wr["saved"] is True and wr["retried"] is False, wr
    (row,) = world["db"].query(models.UserKnowledgeEntry).filter_by(user_id=world["user"].id, type="constraint").all()
    assert (row.value["status"], row.value["asserted_by"], row.value["parent_key"]) == ("proposed", None, "injury_shoulder_right")
    assert row.value["scope"]["text"].startswith("2026-11-02, Seated DB Press: ")
    assert row.source == "chat"


@pytest.mark.xfail(strict=True, reason="GH#609: the free-text rule is prompt-only; the write path has no "
                                       "guard yet. Landing the guard must flip this to a pass (strict).")
def test_a_free_text_write_of_the_same_note_is_refused_by_the_write_path(world):
    body, _ = world["send"]([_kb({"category": "Injury History", "content": "2026-11-02 Seated DB Press: " + NOTE})])
    assert body["write_results"][0]["saved"] is False
    assert world["db"].query(models.UserKnowledge).filter_by(user_id=world["user"].id).count() == 0


def test_the_prompt_forbids_the_free_text_route_for_a_note():
    section = context_builder._section_knowledge_update()
    assert PARAGRAPH in section and "Never write it to a free-text category." in section
    valid = next(ln for ln in section.splitlines() if ln.startswith("Valid categories:"))
    assert "Injury History" not in valid and "Constraints" not in valid
    assert section.count("confirms it on the Injuries page") == 1          # the existing sentence, not duplicated
    assert "Quote the workout date and the exercise" in section
