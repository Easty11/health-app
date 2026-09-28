"""`GET /knowledge/proposals` (#346) — the list behind the Injuries page's Confirm buttons.

Lists active PROPOSED constraints and findings only; a confirmed or retired row, another user's
row, and a lab-derived finding (the #60 firewall) never appear. The readers are unchanged: a
proposal still reaches neither lift. Confirming one through the existing route moves it off the list.
SYNTHETIC fixtures only.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
import typed_entries
from auth import get_current_user
from database import get_db
from routers import knowledge as knowledge_router
from routers.knowledge import KnowledgeEntryIn, upsert_knowledge_entry


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _client(db, user):
    app = FastAPI()
    app.include_router(knowledge_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _put(db, uid, type_, key, value, source="chat"):
    return upsert_knowledge_entry(uid, KnowledgeEntryIn(type=type_, key=key, value=value, source=source), db)


def _constraint(**over):
    v = {"scope": {"tier": "advisory", "text": "cap on movement A"}, "kind": "cap",
         "exit": {"on_condition": "condition A"}, "review_by": "2026-01-15",
         "status": "proposed", "asserted_by": None}
    v.update(over)
    return v


def _finding(**over):
    v = {"statement": "Synthetic finding", "domain": "injury", "status": "proposed", "as_of": "2025-12-01",
         "basis": {"text": "x"}, "derived_from_labs": False, "asserted_by": None}
    v.update(over)
    return v


def test_lists_active_proposals_only(db_session):
    u = _user(db_session, "p@example.com")
    other = _user(db_session, "o@example.com")
    _put(db_session, u.id, "constraint", "c_prop", _constraint())
    _put(db_session, u.id, "finding", "f_prop", _finding())
    _put(db_session, u.id, "constraint", "c_conf", _constraint(status="confirmed", asserted_by="user"), source="api")
    _put(db_session, u.id, "finding", "f_open", _finding(status="open", asserted_by="user"), source="api")
    _put(db_session, u.id, "finding", "f_lab", _finding(derived_from_labs=True))
    _put(db_session, other.id, "finding", "f_other", _finding())
    gone = _put(db_session, u.id, "finding", "f_gone", _finding())
    gone.active = False
    db_session.commit()

    keys = [r["key"] for r in _client(db_session, u).get("/knowledge/proposals").json()]
    assert sorted(keys) == ["c_prop", "f_prop"]


def test_readers_are_unchanged_and_confirm_moves_a_row_off_the_list(db_session):
    u = _user(db_session, "p@example.com")
    row = _put(db_session, u.id, "constraint", "c_prop", _constraint())
    active = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, active=True).all()
    assert typed_entries.lift_constraints(active) == []          # a proposal changes nothing

    c = _client(db_session, u)
    assert c.post(f"/knowledge/constraints/{row.id}/confirm", json={"asserted_by": "clinician"}).status_code == 200
    assert c.get("/knowledge/proposals").json() == []
