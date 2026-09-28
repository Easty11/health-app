"""`type="appointment"` rows — the write half of the appointment brief (#345).

Every refusal path of the validator and the DB-aware write rules, plus the chat channel: a chat
write is `planned` (stamped), chat may not set a later status, rewrite or retire a row past
`planned`, and the coach's write shape is GENERATED from the validator's tuples (#45).

Fixtures are SYNTHETIC ONLY (placeholder parts, conditions and text) — the repo is public.
"""
import copy
import json
import re

import pytest

import context_builder
import models
from routers.chat import _process_knowledge_updates
from routers.knowledge import (
    APPOINTMENT_ASK_FIELDS, APPOINTMENT_AUDIENCES, APPOINTMENT_FIELDS, APPOINTMENT_KINDS,
    APPOINTMENT_MODULES, APPOINTMENT_OPTION_FIELDS, APPOINTMENT_REQUEST_FIELDS,
    APPOINTMENT_RESOLVES_FIELDS, APPOINTMENT_SCOPE_FIELDS, APPOINTMENT_SECTIONS_FIELDS,
    KnowledgeEntryIn, ResolutionIn, TypedEntryRefused, _resolve_entry, upsert_knowledge_entry,
    validate_appointment,
)


def _user(db, email="appt@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _injury(db, uid, key="injury_part_a_left", **over):
    value = {"body_part": "part a", "side": "left", "signal_type": "mechanical",
             "restrictions": ["movement a"], **over}
    return upsert_knowledge_entry(uid, KnowledgeEntryIn(type="injury", key=key, value=value, source="api"), db)


def _appt(**over):
    v = {
        "clinician": "Clinician A",
        "practice": None,
        "at": "2026-01-15T13:00",
        "kind": "follow_up",
        "since": "2025-12-01",
        "scope": {"parent_keys": ["injury_part_a_left"]},
        "asks": [{"id": "a1", "text": "Ask one", "priority": 1}],
        "logistics": ["Bring report A"],
        "status": "planned",
    }
    v.update(over)
    return v


def _write(db, uid, value, key="appt_20260115_a", source="api", expires_at=None):
    return upsert_knowledge_entry(uid, KnowledgeEntryIn(
        type="appointment", key=key, value=value, source=source, expires_at=expires_at), db)


# ── shape validator: every refusal path ───────────────────────────────────────

def test_a_follow_up_value_validates_unchanged():
    v = _appt()
    assert validate_appointment(v) is v and v == _appt()


@pytest.mark.parametrize("mutate,match", [
    (lambda v: v.update(extra=1), r"unknown field"),
    (lambda v: v.pop("clinician"), r"missing required"),
    (lambda v: v.pop("scope"), r"missing required"),
    (lambda v: v.update(scope={"parent_keys": []}), r"non-empty list"),
    (lambda v: v.update(scope={}), r"non-empty list"),
    (lambda v: v.update(scope={"parent_keys": ["k"], "hops": 2}), r"unknown field"),
    (lambda v: v.update(scope={"parent_keys": ["k", "k"]}), r"must not repeat"),
    (lambda v: v.update(kind="consult"), r"kind"),
    (lambda v: v.update(audience="patient"), r"audience"),
    (lambda v: v.pop("since"), r"since is required"),
    (lambda v: v.update(since="yesterday"), r"ISO date"),
    (lambda v: v.update(at="2026-01-15"), r"needs a time"),
    (lambda v: v.update(at="15 Jan 13:00"), r"ISO datetime"),
    (lambda v: v.update(at="2026-01-15T13:00+00:00"), r"Brisbane local"),
    (lambda v: v.update(status="done"), r"status"),
    (lambda v: v["asks"][0].update(extra=1), r"asks\[0\]: unknown field"),
    (lambda v: v["asks"][0].pop("text"), r"missing required"),
    (lambda v: v["asks"][0].update(priority=2), r"priority must be an integer 1..1"),
    (lambda v: v["asks"][0].update(priority=True), r"priority"),
    (lambda v: v["asks"].append({"id": "a1", "text": "Ask two", "priority": 2}), r"repeats"),
    (lambda v: v["asks"][0].update(resolves={"entry_key": "k", "why": "x"}), r"resolves: unknown field"),
    (lambda v: v["asks"][0].update(options=[{"option": "x", "implication": "y", "pick": 1}]),
     r"options\[0\]: unknown field"),
    (lambda v: v["asks"][0].update(options=[{"option": "x"}]), r"implication must be a non-empty"),
    (lambda v: v.update(logistics=["ok", ""]), r"logistics\[1\]"),
    (lambda v: v.update(sections={"add": ["summary"]}), r"unknown module"),
    (lambda v: v.update(sections={"add": ["background"], "drop": ["background"]}), r"both added and dropped"),
    (lambda v: v.update(sections={"move": []}), r"unknown field"),
    (lambda v: v.update(request={"ask": "x", "justification": "y"}), r"only for kind 'request'"),
    (lambda v: v.update(detail=3), r"detail"),
])
def test_every_shape_refusal(mutate, match):
    v = copy.deepcopy(_appt())
    mutate(v)
    with pytest.raises(ValueError, match=match):
        validate_appointment(v)


def test_request_kind_needs_its_block_and_checks_it():
    base = _appt(kind="request", since=None)
    base.pop("since")
    with pytest.raises(ValueError, match="request is required"):
        validate_appointment(base)
    ok = {**base, "request": {"ask": "Referral A", "justification": "Reason A",
                              "evidence": [{"door": "document", "ref": "doc-a"}], "alternatives": ["Option B"]}}
    assert validate_appointment(ok) is ok
    for bad, match in [
        ({"ask": "x"}, "missing required"),
        ({"ask": "x", "justification": "y", "evidence": [{"door": "hevy", "ref": "r"}]}, "canonical read door"),
        ({"ask": "x", "justification": "y", "why": 1}, "unknown field"),
    ]:
        with pytest.raises(ValueError, match=match):
            validate_appointment({**base, "request": bad})


def test_since_is_optional_for_intro_and_brisbane_offset_is_accepted():
    v = _appt(kind="intro", at="2026-01-15T13:00+10:00")
    v.pop("since")
    assert validate_appointment(v) is v


# ── DB-aware write rules ──────────────────────────────────────────────────────

def test_write_stores_verbatim(db_session):
    u = _user(db_session)
    _injury(db_session, u.id)
    row = _write(db_session, u.id, _appt())
    assert row.type == "appointment" and row.value == _appt() and row.active


def test_dangling_parent_key_is_refused(db_session):
    u = _user(db_session)
    with pytest.raises(TypedEntryRefused, match="names no active injury") as exc:
        _write(db_session, u.id, _appt())
    assert exc.value.code == "invalid_parent"
    assert db_session.query(models.UserKnowledgeEntry).filter_by(type="appointment").count() == 0


def test_parent_key_must_be_an_injury_row(db_session):
    u = _user(db_session)
    upsert_knowledge_entry(u.id, KnowledgeEntryIn(type="preference", key="injury_part_a_left",
                                                   value={"x": 1}, source="api"), db_session)
    with pytest.raises(TypedEntryRefused, match="names no active injury"):
        _write(db_session, u.id, _appt())


def test_a_resolved_injury_is_in_scope_only_if_resolved_on_or_after_since(db_session):
    u = _user(db_session)
    inj = _injury(db_session, u.id)
    _resolve_entry(inj.id, ResolutionIn(basis="cleared", resolved_by="user", resolved_on="2025-12-01"),
                   "injury", u.id, db_session)
    assert _write(db_session, u.id, _appt(since="2025-12-01")).active          # boundary: on `since`
    with pytest.raises(TypedEntryRefused, match="resolved on/after since"):
        _write(db_session, u.id, _appt(since="2025-12-02"), key="appt_b")
    intro = _appt(kind="intro")
    intro.pop("since")
    with pytest.raises(TypedEntryRefused, match="only with a `since`"):
        _write(db_session, u.id, intro, key="appt_c")


def test_expires_at_is_refused(db_session):
    from datetime import date
    u = _user(db_session)
    _injury(db_session, u.id)
    with pytest.raises(TypedEntryRefused, match="expires_at must be null") as exc:
        _write(db_session, u.id, _appt(), expires_at=date(2026, 2, 1))
    assert exc.value.code == "expires_at_refused"


def test_an_appointment_key_cannot_take_another_types_key(db_session):
    u = _user(db_session)
    _injury(db_session, u.id)
    with pytest.raises(TypedEntryRefused, match="held by an active 'injury'"):
        _write(db_session, u.id, _appt(), key="injury_part_a_left")


def test_operator_moves_status_past_planned(db_session):
    u = _user(db_session)
    _injury(db_session, u.id)
    _write(db_session, u.id, _appt())
    row = _write(db_session, u.id, _appt(status="attended"))
    assert row.value["status"] == "attended"


# ── chat channel ──────────────────────────────────────────────────────────────

def _chat(db, uid, data):
    block = f"<knowledge_update>\n{json.dumps(data)}\n</knowledge_update>"
    _, _, results = _process_knowledge_updates(block, uid, db)
    return results[0]


def test_chat_write_is_stamped_planned(db_session):
    u = _user(db_session)
    _injury(db_session, u.id)
    value = _appt()
    value.pop("status")
    r = _chat(db_session, u.id, {"type": "appointment", "key": "appt_a", "value": value})
    assert r.saved, r.reason
    row = db_session.query(models.UserKnowledgeEntry).filter_by(key="appt_a", active=True).one()
    assert row.value["status"] == "planned" and row.source == "chat"


@pytest.mark.parametrize("st", ["attended", "closed"])
def test_chat_may_not_set_status_past_planned(db_session, st):
    u = _user(db_session)
    _injury(db_session, u.id)
    r = _chat(db_session, u.id, {"type": "appointment", "key": "appt_a", "value": _appt(status=st)})
    assert not r.saved and r.reason_code == "operator_only"
    assert db_session.query(models.UserKnowledgeEntry).filter_by(type="appointment").count() == 0


def test_chat_may_edit_asks_on_a_planned_row(db_session):
    u = _user(db_session)
    _injury(db_session, u.id)
    _write(db_session, u.id, _appt(), key="appt_a")
    edited = _appt(asks=[{"id": "a1", "text": "Ask one", "priority": 2},
                         {"id": "a2", "text": "Ask two", "priority": 1}])
    edited.pop("status")
    r = _chat(db_session, u.id, {"type": "appointment", "key": "appt_a", "value": edited})
    assert r.saved, r.reason
    row = db_session.query(models.UserKnowledgeEntry).filter_by(key="appt_a", active=True).one()
    assert [a["id"] for a in row.value["asks"]] == ["a1", "a2"]


def test_chat_may_not_rewrite_or_retire_an_attended_row(db_session):
    u = _user(db_session)
    _injury(db_session, u.id)
    _write(db_session, u.id, _appt(status="attended"), key="appt_a")
    value = _appt()
    value.pop("status")
    r = _chat(db_session, u.id, {"type": "appointment", "key": "appt_a", "value": value})
    assert not r.saved and r.reason_code == "operator_only"
    r = _chat(db_session, u.id, {"type": "appointment", "key": "appt_a", "active": False})
    assert not r.saved and r.reason_code == "operator_only"
    row = db_session.query(models.UserKnowledgeEntry).filter_by(key="appt_a", active=True).one()
    assert row.value["status"] == "attended"


# ── the coach's write shape is generated from the validator ───────────────────

SHAPE = context_builder._appointment_write_shape()


def _words(text):
    return set(re.findall(r"[a-z_]+", text))


@pytest.mark.parametrize("vocab", [
    [f for f in APPOINTMENT_FIELDS if f != "status"], APPOINTMENT_KINDS, APPOINTMENT_AUDIENCES,
    APPOINTMENT_SCOPE_FIELDS, APPOINTMENT_ASK_FIELDS, APPOINTMENT_RESOLVES_FIELDS,
    APPOINTMENT_OPTION_FIELDS, APPOINTMENT_SECTIONS_FIELDS, APPOINTMENT_REQUEST_FIELDS,
    APPOINTMENT_MODULES,
])
def test_every_validator_name_is_in_the_shape(vocab):
    assert [v for v in vocab if v not in _words(SHAPE)] == []


def test_the_shape_rides_the_knowledge_update_section_and_never_offers_a_later_status():
    assert SHAPE in context_builder._section_knowledge_update()
    assert "never send `status`" in SHAPE and "never mark" in SHAPE
    assert "attended\"" not in SHAPE and "\"closed" not in SHAPE


def test_the_template_writes_as_a_planned_proposal_once_its_placeholder_is_filled(db_session):
    u = _user(db_session)
    _injury(db_session, u.id)
    block = re.search(r"<knowledge_update>\n(\{.*?\})\n</knowledge_update>", SHAPE).group(1)
    data = json.loads(block.replace("<injury key>", "injury_part_a_left"))
    assert data["type"] == "appointment" and "status" not in data["value"]
    r = _chat(db_session, u.id, data)
    assert r.saved, r.reason


def test_the_template_carries_no_user_specific_values():
    assert "SHAPE TEMPLATES" not in SHAPE  # its own line, not the typed-entry one
    assert "never a fact about this user" in SHAPE
    assert "injury_" not in SHAPE


# ── the planned-appointments context section ─────────────────────────────────

def test_context_section_renders_planned_rows_only(db_session):
    u = _user(db_session)
    _injury(db_session, u.id)
    _write(db_session, u.id, _appt(), key="appt_planned")
    _write(db_session, u.id, _appt(status="closed"), key="appt_closed")
    rows = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, active=True).all()
    sec = context_builder._section_appointments(rows)
    assert sec.startswith("## Appointments") and "appt_planned" in sec and "appt_closed" not in sec
    assert json.dumps(_appt(), ensure_ascii=False) in sec
    assert context_builder._section_appointments([r for r in rows if r.type != "appointment"]) == ""
