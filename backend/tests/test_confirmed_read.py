"""Confirmed rows are visible and resolvable at any time (GH#622; DECISIONS_LOG "Confirmed rows are
visible and resolvable at any time").

Prod, 5 Nov 2026: #110 (the old ER cap, duplicated by the confirmed v2 cap) and #102 (the contact-return
block, overtaken by a confirmed caution) stayed confirmed and unreachable in-app until their
`review_by`. `GET /knowledge/confirmed` lists what the engine and the coach read — active CONFIRMED
constraints and active open / confirmed findings — so the Injuries page can show each with Resolve
before it is due. Gates:
  * the read lists a confirmed row that is NOT yet due, and leaves out proposals, retired rows,
    superseded rows, lab-derived findings and another user's rows;
  * resolve before `review_by` succeeds with a basis and is refused without one — the EXISTING resolve
    route, no parallel path;
  * a resolved row leaves the list;
  * the sweep is unchanged: the not-yet-due row is in `/confirmed` and not in `/review-due`, and a due
    row is in both.
Fixtures are synthetic placeholders.
"""
from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from load_metrics import _local_day
from routers import knowledge as knowledge_router
from routers.knowledge import KnowledgeEntryIn, upsert_knowledge_entry

TODAY = _local_day()
PAST = (TODAY - timedelta(days=10)).isoformat()
FUTURE = (TODAY + timedelta(days=30)).isoformat()


def _user(db, email="confirmed@example.com"):
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


def _injury(db, user, key="injury_x"):
    return upsert_knowledge_entry(user.id, KnowledgeEntryIn(
        type="injury", key=key, source="api",
        value={"body_part": "finger", "side": "left", "signal_type": "mechanical"}), db)


def _constraint(db, user, key, *, review_by=FUTURE, status="confirmed", parent="injury_x", source="api"):
    value = {"scope": {"tier": "advisory", "text": f"text of {key}"}, "kind": "block", "parent_key": parent,
             "exit": {"on_condition": "the clinician reviews it"}, "review_by": review_by, "status": status,
             "asserted_by": "user" if status == "confirmed" else None}
    return upsert_knowledge_entry(user.id, KnowledgeEntryIn(
        type="constraint", key=key, value=value, source=source), db)


def _finding(db, user, key, *, status="open", labs=False, review_by=None):
    value = {"statement": f"statement of {key}", "domain": "injury", "status": status, "parent_key": "injury_x",
             "as_of": "2026-09-20", "basis": {"text": "b"}, "derived_from_labs": labs,
             "asserted_by": None if status == "proposed" else "user"}
    if review_by:
        value["review_by"] = review_by
    return upsert_knowledge_entry(user.id, KnowledgeEntryIn(
        type="finding", key=key, value=value, source="api"), db)


def _confirmed(db, user):
    r = _client(db, user).get("/knowledge/confirmed")
    assert r.status_code == 200, r.text
    return r.json()


def _keys(body):
    return sorted(e["key"] for e in body)


# ── the read ──────────────────────────────────────────────────────────────────

def test_it_lists_confirmed_rows_that_are_not_yet_due_and_nothing_else(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    _constraint(db_session, u, "c_future")                                  # confirmed, review far off
    _constraint(db_session, u, "c_orphan", parent=None)                     # confirmed, no parent
    _constraint(db_session, u, "c_proposed", status="proposed")             # a proposal: not in force
    retired = _constraint(db_session, u, "c_retired")
    _finding(db_session, u, "f_open")                                       # open finding: read by the lifts
    _finding(db_session, u, "f_confirmed", status="confirmed")
    _finding(db_session, u, "f_proposed", status="proposed")
    _finding(db_session, u, "f_labs", labs=True)                            # #60 firewall: withheld
    # Retire one confirmed row through the existing route; it must leave the list.
    r = _client(db_session, u).post(f"/knowledge/constraints/{retired.id}/resolve",
                                    json={"basis": "no longer needed, the clinician said so", "resolved_by": "user"})
    assert r.status_code == 200, r.text
    # Another user's confirmed row stays theirs.
    other = _user(db_session, "other@example.com")
    _injury(db_session, other)
    _constraint(db_session, other, "c_theirs")

    body = _confirmed(db_session, u)
    assert _keys(body) == ["c_future", "c_orphan", "f_confirmed", "f_open"]
    by_key = {e["key"]: e for e in body}
    # The row is returned as stored: the card renders kind, scope, exit, review_by and authority from it.
    c = by_key["c_future"]["value"]
    assert (c["kind"], c["scope"]["text"], c["exit"], c["review_by"], c["asserted_by"], c["parent_key"]) == (
        "block", "text of c_future", {"on_condition": "the clinician reviews it"}, FUTURE, "user", "injury_x")
    assert by_key["c_orphan"]["value"]["parent_key"] is None


def test_a_superseded_row_is_not_listed_its_successor_is(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    first = _constraint(db_session, u, "c_same_key")
    second = _constraint(db_session, u, "c_same_key")                       # same key: supersedes
    body = _confirmed(db_session, u)
    assert [e["id"] for e in body] == [second.id] and first.id != second.id


# ── resolve before review_by: the existing route, basis required ──────────────

def test_resolve_before_review_by_succeeds_with_a_basis_and_the_row_leaves_the_list(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    row = _constraint(db_session, u, "c_early")
    assert _keys(_confirmed(db_session, u)) == ["c_early"]
    assert _client(db_session, u).get("/knowledge/review-due").json()["items"] == []   # not due
    r = _client(db_session, u).post(f"/knowledge/constraints/{row.id}/resolve",
                                    json={"basis": "overtaken by the clinician's v2 cap", "resolved_by": "clinician"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["active"] is False and out["superseded_by"] is None
    assert out["value"]["resolution"]["basis"] == "overtaken by the clinician's v2 cap"
    assert out["value"]["resolution"]["resolved_by"] == "clinician"
    assert _confirmed(db_session, u) == []


def test_resolve_without_a_basis_is_refused_and_the_row_stays_in_force(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    row = _constraint(db_session, u, "c_early")
    client = _client(db_session, u)
    blank = client.post(f"/knowledge/constraints/{row.id}/resolve", json={"basis": "   ", "resolved_by": "user"})
    assert blank.status_code == 422 and "basis is required" in blank.json()["detail"]
    missing = client.post(f"/knowledge/constraints/{row.id}/resolve", json={"resolved_by": "user"})
    assert missing.status_code == 422
    assert _keys(_confirmed(db_session, u)) == ["c_early"]


def test_a_finding_is_retracted_through_its_own_route_and_leaves_the_list(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    f = _finding(db_session, u, "f_open")
    r = _client(db_session, u).post(f"/knowledge/findings/{f.id}/retract",
                                    json={"basis": "superseded by the later scan", "resolved_by": "user"})
    assert r.status_code == 200, r.text
    assert r.json()["value"]["status"] == "retracted"
    assert _confirmed(db_session, u) == []


# ── the sweep is unchanged ────────────────────────────────────────────────────

def test_the_sweep_is_unchanged_a_due_row_is_in_both_lists_and_a_future_row_only_here(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    _constraint(db_session, u, "c_due", review_by=PAST)
    _constraint(db_session, u, "c_future")
    client = _client(db_session, u)
    due = client.get("/knowledge/review-due").json()
    assert [i["key"] for i in due["items"]] == ["c_due"]
    assert due["items"][0]["tags"] == ["review due"]
    assert _keys(_confirmed(db_session, u)) == ["c_due", "c_future"]


def test_the_read_changes_nothing(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    row = _constraint(db_session, u, "c_future")
    before = dict(row.value)
    _confirmed(db_session, u)
    db_session.refresh(row)
    assert row.value == before and row.active is True
