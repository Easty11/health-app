"""A proposal can be edited before it is confirmed or declined (GH#617; DECISIONS_LOG "An edit is a
superseding proposal").

The 4 Nov 2026 debrief left unparented and over-broad proposals, and the only correction path was
Decline then ask the coach again. `POST /knowledge/{constraints,findings}/{id}/edit` writes a
SUPERSEDING proposal through the one upsert and every existing validator. Gates:
  * edit → the successor is `proposed`, `asserted_by` null, `source: "api"`, its notes name the
    predecessor; the predecessor is inactive with `superseded_by`, its value and source intact;
  * an off-vocabulary region key is refused with the valid set named, verbatim from the validator;
  * a confirmed row, a superseded row and a non-editable field are refused, each with its reason;
  * re-parenting a proposal onto an injury puts it in that injury's appointment-brief scope (the
    GH#613 re-parent path), through the one loader both the route and the MCP tool call;
  * `parent_key` goes through the existing `invalid_parent` checks.
Fixtures are synthetic placeholders.
"""
import json
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import appointment_brief as ab
import mcp_server
import models
from auth import get_current_user
from database import get_db
from routers import knowledge as knowledge_router
from routers.knowledge import (
    EDIT_NOTES_PREFIX,
    PROPOSAL_EDITABLE_FIELDS,
    ConfirmIn,
    KnowledgeEntryIn,
    _confirm_entry,
    upsert_knowledge_entry,
)

INJURY = "injury_part_a_left"


def _user(db, email="edit@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(knowledge_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _injury(db, uid, key=INJURY, part="part a", side="left"):
    row = models.UserKnowledgeEntry(
        user_id=uid, type="injury", key=key, source="api", added_at=date(2025, 11, 1), active=True,
        value={"body_part": part, "side": side, "signal_type": "mechanical"},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _constraint(**over):
    v = {"scope": {"tier": "engine", "region_keys": ["squat", "knee_flexion"], "side": "left"},
         "kind": "block", "parent_key": None, "exit": {"on_condition": "cleared by the clinician"},
         "review_by": "2026-12-02", "status": "proposed", "asserted_by": None,
         "detail": "the coach's original detail"}
    v.update(over)
    return v


def _finding(**over):
    v = {"statement": "The coach's original statement", "domain": "injury", "status": "proposed",
         "parent_key": None, "as_of": "2026-11-04", "basis": {"text": "the coach's basis"},
         "derived_from_labs": False, "asserted_by": None}
    v.update(over)
    return v


def _chat_write(db, uid, type_, key, value):
    """A proposal as the coach writes it: source chat, proposed, no authority."""
    return upsert_knowledge_entry(uid, KnowledgeEntryIn(type=type_, key=key, value=value, source="chat"), db)


def _rows(db, uid, key):
    return db.query(models.UserKnowledgeEntry).filter_by(user_id=uid, key=key).order_by(
        models.UserKnowledgeEntry.id).all()


@pytest.fixture
def world(db_session):
    u = _user(db_session)
    _injury(db_session, u.id)
    return u


# ── the edit is a superseding proposal ────────────────────────────────────────

def test_edit_supersedes_the_proposal_and_keeps_the_coachs_original(db_session, world):
    original = _chat_write(db_session, world.id, "constraint", "c_knee", _constraint())
    original_value = dict(original.value)
    r = _client(db_session, world).post(f"/knowledge/constraints/{original.id}/edit", json={
        "value": {"scope": {"tier": "engine", "region_keys": ["squat"], "side": "left"},
                  "parent_key": INJURY, "detail": "deep loaded flexion only"}})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["id"] != original.id and out["key"] == "c_knee" and out["active"] is True
    assert out["source"] == "api" and out["notes"] == f"{EDIT_NOTES_PREFIX}{original.id}"
    assert out["value"]["status"] == "proposed" and out["value"]["asserted_by"] is None
    assert out["value"]["scope"]["region_keys"] == ["squat"] and out["value"]["parent_key"] == INJURY
    assert out["value"]["detail"] == "deep loaded flexion only"
    # Fields not sent ride unchanged from the predecessor.
    assert out["value"]["kind"] == "block" and out["value"]["exit"] == original_value["exit"]
    assert out["value"]["review_by"] == original_value["review_by"]

    before, after = _rows(db_session, world.id, "c_knee")
    assert before.id == original.id and after.id == out["id"]
    assert before.active is False and before.superseded_by == after.id
    assert before.value == original_value and before.source == "chat"      # the coach's original, intact
    assert after.superseded_by is None


def test_a_finding_edit_supersedes_the_same_way(db_session, world):
    original = _chat_write(db_session, world.id, "finding", "f_knee", _finding())
    r = _client(db_session, world).post(f"/knowledge/findings/{original.id}/edit", json={
        "value": {"statement": "Edited statement", "parent_key": INJURY, "as_of": "2026-11-05",
                  "basis": {"text": "edited basis"}}})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["value"]["statement"] == "Edited statement" and out["value"]["parent_key"] == INJURY
    assert out["value"]["as_of"] == "2026-11-05" and out["value"]["basis"] == {"text": "edited basis"}
    assert out["value"]["status"] == "proposed" and out["value"]["asserted_by"] is None
    assert out["value"]["domain"] == "injury" and out["value"]["derived_from_labs"] is False
    before = _rows(db_session, world.id, "f_knee")[0]
    assert before.active is False and before.superseded_by == out["id"] and before.source == "chat"
    # G1 ruling 3 (existing): a superseded finding reads `superseded` in its own value; every other
    # field of the coach's original is untouched.
    assert before.value["status"] == "superseded"
    assert {k: v for k, v in before.value.items() if k != "status"} == {
        k: v for k, v in _finding().items() if k != "status"}


def test_asserted_by_is_still_null_after_the_edit(db_session, world):
    original = _chat_write(db_session, world.id, "constraint", "c_a", _constraint())
    out = _client(db_session, world).post(f"/knowledge/constraints/{original.id}/edit",
                                           json={"value": {"review_by": "2027-01-10"}}).json()
    assert out["value"]["asserted_by"] is None and out["value"]["status"] == "proposed"
    assert "confirmed_on" not in out["value"]


def test_edit_never_confirms_and_confirm_stays_a_separate_act(db_session, world):
    original = _chat_write(db_session, world.id, "constraint", "c_a", _constraint())
    c = _client(db_session, world)
    edited = c.post(f"/knowledge/constraints/{original.id}/edit", json={"value": {"review_by": "2027-01-10"}}).json()
    assert [p["id"] for p in c.get("/knowledge/proposals").json()] == [edited["id"]]
    r = c.post(f"/knowledge/constraints/{edited['id']}/confirm", json={"asserted_by": "clinician"})
    assert r.status_code == 200 and r.json()["value"]["status"] == "confirmed"
    assert r.json()["value"]["asserted_by"] == "clinician"


# ── refusals, each with its reason ────────────────────────────────────────────

def test_an_off_vocabulary_region_is_refused_with_the_valid_set_named(db_session, world):
    original = _chat_write(db_session, world.id, "constraint", "c_a", _constraint())
    r = _client(db_session, world).post(f"/knowledge/constraints/{original.id}/edit", json={
        "value": {"scope": {"tier": "engine", "region_keys": ["deep_squat"], "side": "left"}}})
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert "unknown region key(s) ['deep_squat']" in detail and "valid keys:" in detail
    assert "'squat'" in detail and "'knee_flexion'" in detail
    # Nothing written: the proposal is still the one active row under its key.
    (only,) = _rows(db_session, world.id, "c_a")
    assert only.id == original.id and only.active is True


def test_editing_a_confirmed_row_is_refused(db_session, world):
    original = _chat_write(db_session, world.id, "constraint", "c_a", _constraint())
    _confirm_entry(original.id, ConfirmIn(asserted_by="user"), "constraint", world.id, db_session)
    r = _client(db_session, world).post(f"/knowledge/constraints/{original.id}/edit",
                                         json={"value": {"review_by": "2027-01-10"}})
    assert r.status_code == 409, r.text
    assert "is 'confirmed'" in r.json()["detail"] and "only a proposal is edited" in r.json()["detail"]
    assert f"/knowledge/constraints/{original.id}/review" in r.json()["detail"]


def test_editing_a_superseded_row_is_refused(db_session, world):
    original = _chat_write(db_session, world.id, "constraint", "c_a", _constraint())
    c = _client(db_session, world)
    c.post(f"/knowledge/constraints/{original.id}/edit", json={"value": {"review_by": "2027-01-10"}})
    r = c.post(f"/knowledge/constraints/{original.id}/edit", json={"value": {"review_by": "2027-02-10"}})
    assert r.status_code == 409, r.text
    assert "inactive (superseded by a later write)" in r.json()["detail"]


def test_a_non_editable_field_and_an_empty_edit_are_refused(db_session, world):
    original = _chat_write(db_session, world.id, "constraint", "c_a", _constraint())
    c = _client(db_session, world)
    r = c.post(f"/knowledge/constraints/{original.id}/edit", json={"value": {"status": "confirmed"}})
    assert r.status_code == 422 and "['status'] cannot be edited" in r.json()["detail"]
    assert ", ".join(PROPOSAL_EDITABLE_FIELDS["constraint"]) in r.json()["detail"]
    r = c.post(f"/knowledge/constraints/{original.id}/edit", json={"value": {}})
    assert r.status_code == 422 and "nothing to edit" in r.json()["detail"]
    # Type-scoped: a constraint id through the findings route is a 404 that reveals nothing.
    assert c.post(f"/knowledge/findings/{original.id}/edit", json={"value": {"as_of": "2026-01-01"}}).status_code == 404


def test_parent_key_goes_through_the_invalid_parent_checks(db_session, world):
    original = _chat_write(db_session, world.id, "constraint", "c_a", _constraint())
    r = _client(db_session, world).post(f"/knowledge/constraints/{original.id}/edit",
                                         json={"value": {"parent_key": "injury_nowhere"}})
    assert r.status_code == 422 and "names no active entry" in r.json()["detail"]
    r = _client(db_session, world).post(f"/knowledge/constraints/{original.id}/edit",
                                         json={"value": {"parent_key": "c_a"}})
    assert r.status_code == 422 and "must not name the entry itself" in r.json()["detail"]


# ── the GH#613 re-parent path: into the appointment brief's scope ─────────────

def _appointment(db, uid, key="appt_knee"):
    upsert_knowledge_entry(uid, KnowledgeEntryIn(type="appointment", key=key, source="api", value={
        "clinician": "Clinician A", "practice": None, "at": "2026-12-01T09:00", "kind": "follow_up",
        "since": "2026-11-01", "scope": {"parent_keys": [INJURY]}, "asks": [], "logistics": [],
        "status": "planned"}), db)
    return key


def test_re_parenting_a_proposal_puts_it_in_the_injurys_brief_scope(db_session, world, monkeypatch):
    orphan = _chat_write(db_session, world.id, "constraint", "c_orphan", _constraint(
        scope={"tier": "advisory", "text": "ORPHAN CAP TEXT"}, kind="cap"))
    key = _appointment(db_session, world.id)
    assert "ORPHAN CAP TEXT" not in json.dumps(ab.load_appointment_brief(db_session, world.id, key))

    c = _client(db_session, world)
    edited = c.post(f"/knowledge/constraints/{orphan.id}/edit", json={"value": {"parent_key": INJURY}}).json()
    assert edited["value"]["parent_key"] == INJURY
    # A proposal never renders in the brief (its hard exclusion): the edited row is in scope, and
    # shows once the operator confirms it -- a separate act, done here as the test's own step.
    assert "ORPHAN CAP TEXT" not in json.dumps(ab.load_appointment_brief(db_session, world.id, key))
    _confirm_entry(edited["id"], ConfirmIn(asserted_by="clinician"), "constraint", world.id, db_session)

    brief = ab.load_appointment_brief(db_session, world.id, key)
    current = next(s for s in brief["sections"] if s["module"] == "current_constraints")
    assert [(x["key"], x["parent_key"]) for x in current["items"]] == [("c_orphan", INJURY)]
    assert "ORPHAN CAP TEXT" in json.dumps(current)
    # The same object through the MCP read door (one assembly behind both surfaces).
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: world.id)
    out = mcp_server.get_appointment_brief(key)
    assert json.loads(out.split("\n\n", 1)[1]) == brief


# ── the card's enums mirror the validator's tuples ────────────────────────────

def test_the_edit_forms_enums_mirror_the_validator():
    """No route serves the constraint vocabulary; the card's selects read a mirrored constant in
    `components/InjuryActions.jsx`, pinned here (the injuryVocabulary.js pattern)."""
    import re
    from pathlib import Path
    from routers import knowledge as kn
    src = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "InjuryActions.jsx").read_text()

    def listed(name):
        m = re.search(rf"const {name} = \[(.*?)\]", src, re.S)
        assert m is not None, f"{name} is not defined in InjuryActions.jsx"
        return re.findall(r"'([^']+)'", m.group(1))

    assert listed("CONSTRAINT_KINDS") == list(kn.CONSTRAINT_KINDS)
    assert set(listed("CONSTRAINT_SIDES")) == set(kn.CONSTRAINT_SIDES)
