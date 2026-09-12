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

    _, actions, _ = _process_knowledge_updates(
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


# ---------- the write-result contract (#283, Q143a) ----------
# The gloss the origin transcript showed — "saved / locked" narrated while calls
# returned ✗ — was possible because success was only inferable from prose. Every block
# now yields a machine-checkable WriteResult; a client hard-gates on `saved`.

def _clash_block(key: str, activity: str) -> str:
    return _block({
        "type": "schedule_item", "key": key,
        "value": {"activity": activity, "days": ["monday"], "hard": True,
                  "expected_load": "light", "time_of_day": "morning",
                  "same_day_training": False, "duration_weeks": None, "season_end": None},
    })


def test_a_successful_save_yields_saved_true(db_session):
    u = _user(db_session, "wr-save@example.com")
    _, actions, results = _process_knowledge_updates(_block(BASE), u.id, db_session)
    assert len(results) == 1
    assert results[0].saved is True
    assert results[0].reason_code == "saved"
    assert results[0].key == "physio_2026_08"
    # The structured reason is the SAME string a reader sees — never a second source of truth.
    assert results[0].reason in actions


def test_a_day_time_clash_yields_saved_false_with_a_stable_code(db_session):
    u = _user(db_session, "wr-clash@example.com")
    _process_knowledge_updates(_clash_block("physio_2026_08", "physio"), u.id, db_session)
    # Second commitment, same day + same (morning) band, no acknowledgement → refused.
    _, _, results = _process_knowledge_updates(
        _clash_block("gym_2026_08", "gym"), u.id, db_session)
    assert results[-1].saved is False
    assert results[-1].reason_code == "day_time_clash"


def test_an_unknown_field_yields_saved_false_with_the_unknown_field_code(db_session):
    """The WS2 failure mode (`unknown field(s) ['active']`) is now a typed, gateable
    outcome — the code is type-derived (ScheduleItemInvalid), never parsed from prose."""
    u = _user(db_session, "wr-unknown@example.com")
    bad = {**BASE, "value": {**BASE["value"], "active": False}}  # `active` belongs at top level
    _, _, results = _process_knowledge_updates(_block(bad), u.id, db_session)
    assert results[0].saved is False
    assert results[0].reason_code == "unknown_field"


def test_a_deactivation_of_a_missing_key_is_not_found_not_a_success(db_session):
    u = _user(db_session, "wr-notfound@example.com")
    _, _, results = _process_knowledge_updates(
        _block({"type": "schedule_item", "key": "never_existed", "active": False}),
        u.id, db_session)
    assert results[0].saved is False
    assert results[0].reason_code == "not_found"


def test_a_successful_deactivation_is_saved_true(db_session):
    u = _user(db_session, "wr-deact@example.com")
    _process_knowledge_updates(_block(BASE), u.id, db_session)  # create physio_2026_08
    _, _, results = _process_knowledge_updates(
        _block({"type": "schedule_item", "key": "physio_2026_08", "active": False}),
        u.id, db_session)
    assert results[0].saved is True
    assert results[0].reason_code == "deactivated"


def test_a_mixed_batch_reports_per_row_not_a_rollup(db_session):
    """The exact origin shape: several blocks in one turn, some saved and some not. A
    single top-level flag would reintroduce the gloss — the result must be per-row."""
    u = _user(db_session, "wr-batch@example.com")
    # Block 1 saves (monday/morning). Block 2 clashes (same day+band, no ack). Block 3
    # saves (a different day). One reply, three blocks.
    b1 = _clash_block("a_2026_08", "A")
    b2 = _clash_block("b_2026_08", "B")  # clashes with A
    b3 = _block({"type": "schedule_item", "key": "c_2026_08",
                 "value": {"activity": "C", "days": ["tuesday"], "hard": True,
                           "expected_load": "light", "time_of_day": "morning",
                           "same_day_training": False, "duration_weeks": None,
                           "season_end": None}})
    reply = b1 + "\n" + b2 + "\n" + b3
    _, _, results = _process_knowledge_updates(reply, u.id, db_session)
    assert [r.saved for r in results] == [True, False, True]
    assert [r.reason_code for r in results] == ["saved", "day_time_clash", "saved"]


def test_write_results_pair_one_to_one_with_action_strings(db_session):
    """Invariant: `record()` appends to both lists together, so a reader's prose and the
    machine flag can never disagree."""
    u = _user(db_session, "wr-pair@example.com")
    _, actions, results = _process_knowledge_updates(
        _clash_block("x_2026_08", "X") + "\n" + _clash_block("x_2026_08", "X"),
        u.id, db_session)
    assert len(actions) == len(results)
    assert [r.reason for r in results] == actions


def test_the_prompt_no_longer_teaches_a_source_field(db_session):
    """The ungated half. Prompt surfaces have no behavioural test behind them, so
    this is the only thing standing between the template and a re-added line that
    documents a field the parser now discards."""
    section = context_builder._section_user_profile(None)

    assert "<knowledge_update>" in section, "template moved -- re-aim this assertion"
    assert '"source"' not in section
