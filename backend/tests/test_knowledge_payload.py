"""Knowledge-update parse failures (prod, 1 Nov 2026): `Extra data: line 1 column 3918 (char 3917)`.

`json.loads` was handed one valid JSON value followed by more content, the whole block was dropped,
and the user was told to mention it again. Gates, in three layers:

  * the tolerant reader (`parse_knowledge_payload`): two concatenated objects, trailing prose, code
    fences, leading prose, arrays and comma-separated objects are all read; text that starts like JSON
    but does not decode is an ERROR (never a silent skip) while the objects before it are kept;
  * the processor: the same inputs through `_process_knowledge_updates` write every object, the tool
    channel writes an `updates` array, a failure logs the RAW payload, and ignored trailing text is
    logged;
  * end to end through `/chat`, the model faked at the transport layer (#166): the tool is offered,
    an unparseable block gets exactly ONE retry carrying the parser's message, a retry never rewrites
    what the turn already saved, a failed retry is final (then pass-2), and the pass-2 instruction no
    longer invites the user to repeat themselves.
Fixtures are synthetic placeholders.
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
from knowledge_payload import (
    RECORD_KNOWLEDGE_TOOL,
    RECORD_KNOWLEDGE_TOOL_NAME,
    extract_tool_updates,
    parse_knowledge_payload,
    strip_code_fences,
    updates_from_tool_input,
)
from routers import chat as chat_router
from routers.chat import _process_knowledge_updates

A = {"category": "Goals", "content": "run a 10k"}
B = {"category": "Recovery", "content": "sleeps better after a long walk"}


# ── the tolerant reader ──────────────────────────────────────────────────────

def test_two_concatenated_objects_are_both_read():
    parsed = parse_knowledge_payload(json.dumps(A) + json.dumps(B))
    assert parsed.values == [A, B] and parsed.error is None and parsed.trailing == ""


def test_the_prod_failure_is_reproduced_and_read():
    """First object exactly 3917 chars, a second straight after it: the literal prod error string."""
    base = len(json.dumps({"category": "Goals", "content": ""}))
    first = json.dumps({"category": "Goals", "content": "x" * (3917 - base)})
    assert len(first) == 3917
    raw = first + json.dumps(B)
    with pytest.raises(json.JSONDecodeError) as exc:
        json.loads(raw)
    assert str(exc.value) == "Extra data: line 1 column 3918 (char 3917)"
    parsed = parse_knowledge_payload(raw)
    assert len(parsed.values) == 2 and parsed.values[1] == B and parsed.error is None


def test_trailing_prose_is_dropped_and_reported_as_trailing():
    parsed = parse_knowledge_payload(json.dumps(A) + "\n\nLet me know if you want that changed.")
    assert parsed.values == [A] and parsed.error is None
    assert parsed.trailing == "Let me know if you want that changed."


def test_trailing_prose_after_two_objects():
    parsed = parse_knowledge_payload(json.dumps(A) + " " + json.dumps(B) + " Done!")
    assert parsed.values == [A, B] and parsed.trailing == "Done!"


@pytest.mark.parametrize("wrap", [
    "```json\n{p}\n```",
    "```\n{p}\n```",
    "```json {p} ```",
    "```json\n{p}\n```\nHope that helps.",
])
def test_code_fences_are_stripped(wrap):
    parsed = parse_knowledge_payload(wrap.replace("{p}", json.dumps(A)))
    assert parsed.values == [A] and parsed.error is None


def test_leading_prose_is_skipped():
    parsed = parse_knowledge_payload("Here is the update: " + json.dumps(A))
    assert parsed.values == [A] and parsed.error is None


def test_an_array_of_objects_is_flattened_and_commas_between_objects_are_tolerated():
    assert parse_knowledge_payload(json.dumps([A, B])).values == [A, B]
    assert parse_knowledge_payload(json.dumps(A) + ",\n" + json.dumps(B)).values == [A, B]


def test_braces_inside_strings_do_not_split_an_object():
    tricky = {"category": "Other", "content": 'a } then { "quoted" text'}
    assert parse_knowledge_payload(json.dumps(tricky) + json.dumps(B)).values == [tricky, B]


def test_a_malformed_second_object_is_an_error_not_a_silent_skip():
    parsed = parse_knowledge_payload(json.dumps(A) + '{"category": "Recovery", "content": ')
    assert parsed.values == [A]                       # the intact write is kept
    assert parsed.error and "char" in parsed.error    # the broken one is reported


@pytest.mark.parametrize("raw", ["", "   ", "{not json", "no json here at all"])
def test_nothing_decodable_is_an_error(raw):
    parsed = parse_knowledge_payload(raw)
    assert parsed.values == [] and parsed.error


def test_strip_code_fences_keeps_the_inside():
    assert strip_code_fences("```json\n{\"a\": 1}\n```") == '{"a": 1}'


# ── the structured channel ───────────────────────────────────────────────────

def test_the_tool_schema_is_an_array_of_update_objects():
    schema = RECORD_KNOWLEDGE_TOOL["input_schema"]
    assert RECORD_KNOWLEDGE_TOOL["name"] == RECORD_KNOWLEDGE_TOOL_NAME == "record_knowledge_updates"
    assert schema["required"] == ["updates"]
    updates = schema["properties"]["updates"]
    assert updates["type"] == "array" and updates["minItems"] == 1 and updates["items"]["type"] == "object"


def test_tool_input_reading():
    assert updates_from_tool_input({"updates": [A, B]}) == ([A, B], None)
    items, err = updates_from_tool_input({"updates": json.dumps(A) + json.dumps(B)})   # stringified
    assert items == [A, B] and err is None
    assert updates_from_tool_input({"updates": 7})[1]
    assert updates_from_tool_input({})[1]
    assert updates_from_tool_input("nope")[1]


def test_extract_tool_updates_ignores_other_blocks_and_other_tools():
    content = [
        SimpleNamespace(type="text", text="hello"),
        SimpleNamespace(type="tool_use", name="something_else", input={"updates": [B]}),
        SimpleNamespace(type="tool_use", name=RECORD_KNOWLEDGE_TOOL_NAME, input={"updates": [A]}),
        SimpleNamespace(type="tool_use", name=RECORD_KNOWLEDGE_TOOL_NAME, input={"updates": "{broken"}),
    ]
    items, errors = extract_tool_updates(content)
    assert items == [A] and len(errors) == 1
    assert extract_tool_updates(None) == ([], [])


# ── the processor ────────────────────────────────────────────────────────────

def _user(db, email="payload@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _block(raw):
    return f"<knowledge_update>{raw}</knowledge_update>"


def _kb_rows(db, user):
    return {r.category: r.content for r in db.query(models.UserKnowledge).filter_by(user_id=user.id)}


def test_two_concatenated_objects_in_one_block_both_save(db_session):
    u = _user(db_session)
    cleaned, actions, results = _process_knowledge_updates(
        "Noted.\n" + _block(json.dumps(A) + json.dumps(B)), u.id, db_session)
    assert [r.saved for r in results] == [True, True] and len(actions) == 2
    assert _kb_rows(db_session, u) == {"Goals": "run a 10k", "Recovery": "sleeps better after a long walk"}
    assert cleaned == "Noted."                                  # the block never reaches the user


def test_trailing_text_in_a_block_saves_and_is_logged(db_session, caplog):
    caplog.set_level(logging.WARNING, logger="routers.chat")
    u = _user(db_session, "trail@example.com")
    _, _, results = _process_knowledge_updates(
        _block(json.dumps(A) + "\nThat should cover it."), u.id, db_session)
    assert [r.saved for r in results] == [True]
    assert "ignored" in caplog.text and "That should cover it." in caplog.text


def test_a_malformed_second_object_saves_the_first_and_reports_the_second(db_session):
    u = _user(db_session, "partial@example.com")
    _, _, results = _process_knowledge_updates(
        _block(json.dumps(A) + '{"category": "Recovery", "content": '), u.id, db_session)
    by_code = sorted(r.reason_code for r in results)
    assert by_code == ["invalid_json", "saved"]
    assert _kb_rows(db_session, u) == {"Goals": "run a 10k"}


def test_a_parse_failure_logs_the_raw_payload(db_session, caplog):
    caplog.set_level(logging.WARNING, logger="routers.chat")
    u = _user(db_session, "raw@example.com")
    raw = json.dumps(A) + '{"category": "Recovery", "content": '
    _, _, results = _process_knowledge_updates(_block(raw), u.id, db_session)
    assert "invalid_json" in [r.reason_code for r in results]
    # The block regex trims surrounding whitespace, so the logged payload is the stripped text.
    assert "parse failed" in caplog.text and f"raw_len={len(raw.strip())}" in caplog.text
    assert "Recovery" in caplog.text                            # what came after the first object


def test_tool_updates_save_as_an_array_and_a_bad_tool_call_is_loud(db_session):
    u = _user(db_session, "tool@example.com")
    _, _, results = _process_knowledge_updates(
        "Done.", u.id, db_session, tool_updates=[A, B], tool_errors=["`updates` was str, not an array"])
    assert sorted(r.reason_code for r in results) == ["invalid_json", "saved", "saved"]
    assert _kb_rows(db_session, u).keys() == {"Goals", "Recovery"}


def test_a_non_object_update_is_refused_not_dropped(db_session):
    u = _user(db_session, "nonobj@example.com")
    _, _, results = _process_knowledge_updates("", u.id, db_session, tool_updates=["just a string", 3])
    assert [r.reason_code for r in results] == ["invalid_shape", "invalid_shape"]


# ── end to end through /chat ─────────────────────────────────────────────────

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


def _tool(*updates):
    return SimpleNamespace(type="tool_use", name=RECORD_KNOWLEDGE_TOOL_NAME, input={"updates": list(updates)})


def _text(s):
    return SimpleNamespace(type="text", text=s)


@pytest.fixture
def chat(db_session, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    u = models.User(email="payload-chat@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: u
    client = TestClient(app)

    def send(replies, message="remember this"):
        fake = _FakeClient(replies)
        monkeypatch.setattr(chat_router.anthropic, "Anthropic", lambda api_key=None: fake)
        r = client.post("/chat", json={"message": message, "conversation_history": []})
        assert r.status_code == 200, r.text
        return r.json(), fake.messages.calls

    return {"send": send, "db": db_session, "user": u}


def test_the_main_call_offers_the_tool_and_an_updates_array_saves(chat):
    body, calls = chat["send"]([[_text("Saved both."), _tool(A, B)]])
    assert [t["name"] for t in calls[0]["tools"]] == [RECORD_KNOWLEDGE_TOOL_NAME]
    assert len(calls) == 1                                      # saved: no retry, no pass-2
    assert [w["saved"] for w in body["write_results"]] == [True, True]
    assert _kb_rows(chat["db"], chat["user"]).keys() == {"Goals", "Recovery"}
    assert "✓ 2 saved" in body["response"]


def test_a_tool_only_reply_still_renders_the_footer(chat):
    body, _ = chat["send"]([[_tool(A)]])
    assert body["write_results"][0]["saved"] is True and body["response"].strip()


def test_an_unparseable_block_is_retried_once_with_the_parser_message_and_the_fix_saves(chat, caplog):
    caplog.set_level(logging.INFO, logger="routers.chat")
    bad = _block('{"category": "Goals", "content": ')
    draft = "Noting that. " + bad
    body, calls = chat["send"]([draft, [_tool(A)]])
    assert len(calls) == 2                                      # draft + ONE retry; no pass-2 (it saved)
    retry_user = calls[1]["messages"][-1]["content"]
    assert "could not be parsed" in retry_user and "char" in retry_user and RECORD_KNOWLEDGE_TOOL_NAME in retry_user
    assert calls[1]["messages"][-2] == {"role": "assistant", "content": draft}   # its own draft, replayed
    assert [t["name"] for t in calls[1]["tools"]] == [RECORD_KNOWLEDGE_TOOL_NAME]
    (wr,) = body["write_results"]
    assert wr["saved"] is True and wr["retried"] is True
    assert _kb_rows(chat["db"], chat["user"]) == {"Goals": "run a 10k"}
    assert "parse failed" in caplog.text and "outcome=1 saved, 0 not saved" in caplog.text


def test_a_failed_json_retry_is_final_and_pass2_fires_once(chat):
    bad = _block('{"category": "Goals", "content": ')
    body, calls = chat["send"]([bad, _block('{"still": broken'), "Narration."])
    assert len(calls) == 3                                      # draft + one retry + pass-2 — never a 2nd retry
    (wr,) = body["write_results"]
    assert wr["saved"] is False and wr["reason_code"] == "invalid_json" and wr["retried"] is True
    assert _kb_rows(chat["db"], chat["user"]) == {}
    assert "NOT saved" in body["response"] or "failed" in body["response"]


def test_a_retry_that_returns_nothing_usable_keeps_the_failure(chat, caplog):
    caplog.set_level(logging.INFO, logger="routers.chat")
    body, calls = chat["send"]([_block("{broken"), "Sorry, no.", "Narration."])
    assert len(calls) == 3
    assert body["write_results"][0]["reason_code"] == "invalid_json"
    assert "outcome=no_usable_update" in caplog.text


def test_the_retry_never_rewrites_what_the_turn_already_saved(chat):
    good = _block(json.dumps(A))
    bad = _block('{"category": "Recovery", "content": ')
    # The retry resends BOTH (the model ignores "do not resend"): only the unsaved one may land.
    body, calls = chat["send"]([good + "\n" + bad, [_tool(A, B)]])
    assert len(calls) == 2
    assert "Already saved this turn" in calls[1]["messages"][-1]["content"]
    assert sorted(w["reason_code"] for w in body["write_results"]) == ["saved", "saved"]
    assert _kb_rows(chat["db"], chat["user"]) == {          # Goals is NOT appended a second time
        "Goals": "run a 10k", "Recovery": "sleeps better after a long walk"}


def test_a_malformed_tool_call_is_retried_like_a_bad_block(chat):
    broken = SimpleNamespace(type="tool_use", name=RECORD_KNOWLEDGE_TOOL_NAME, input={"updates": "not an array"})
    # `updates` as a string that is not JSON -> a loud invalid_json, then the one retry fixes it.
    body, calls = chat["send"]([[broken], [_tool(A)]])
    assert len(calls) == 2 and body["write_results"][0]["saved"] is True


def test_a_transport_error_on_the_json_retry_keeps_the_failure(chat, monkeypatch):
    class _Boom(_FakeMessages):
        def create(self, **kw):
            self.calls.append(kw)
            if len(self.calls) == 2:
                raise RuntimeError("upstream down")
            return super().create(**kw)

    fake = _FakeClient([])
    fake.messages = _Boom([_block("{broken"), "unused", "Narration."])
    monkeypatch.setattr(chat_router.anthropic, "Anthropic", lambda api_key=None: fake)
    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_db] = lambda: chat["db"]
    app.dependency_overrides[get_current_user] = lambda: chat["user"]
    r = TestClient(app).post("/chat", json={"message": "m", "conversation_history": []})
    assert r.status_code == 200
    assert r.json()["write_results"][0]["reason_code"] == "invalid_json"


def test_a_clean_block_turn_makes_no_retry_call(chat):
    body, calls = chat["send"](["ok " + _block(json.dumps(A) + json.dumps(B))])
    assert len(calls) == 1 and [w["saved"] for w in body["write_results"]] == [True, True]


# ── the user is never asked to repeat themselves ─────────────────────────────

def test_pass2_no_longer_invites_the_user_to_repeat_themselves():
    flat = " ".join(chat_router._PASS2_SYSTEM.split())
    assert "NEVER ask the user to repeat, re-send, re-mention or re-state" in flat
    assert "it is saved only if it is written again" not in flat
    assert "ALREADY retried it once" in flat
    assert "Do NOT promise to retry" in flat                    # the earlier pin still holds


def test_the_pass2_call_carries_that_instruction_after_a_failed_retry(chat):
    _, calls = chat["send"]([_block("{broken"), _block("{broken again"), "Narration."])
    assert calls[2]["system"] == chat_router._PASS2_SYSTEM
    assert "re-mention" in calls[2]["system"]
