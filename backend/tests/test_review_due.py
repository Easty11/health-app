"""The standing review sweep and the Keep action — Q191 (GH#529), D6.

`GET /knowledge/review-due` is SURFACING ONLY (#223): it lists, it never lifts or re-dates. It lists
the confirmed constraints `constraint_due_tags` tags (`review due`, `exit due` on a passed on_date or
a gone parent) and the open / confirmed findings past `review_by`; never a proposal, never a future
date. `POST /knowledge/{constraints,findings}/{id}/review` sets `review_by` IN PLACE and nothing else —
the id, status, authority and `confirmed_on` are untouched, which a same-key rewrite cannot do
(`confirmed_on` is stamped by `/confirm` only and refused on a write).
"""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from load_metrics import _local_day
from routers import knowledge as knowledge_router
from routers.knowledge import (
    ConfirmIn, KnowledgeEntryIn, TypedEntryRefused, _confirm_entry, upsert_knowledge_entry,
)

TODAY = _local_day()
PAST = (TODAY - timedelta(days=10)).isoformat()
FUTURE = (TODAY + timedelta(days=30)).isoformat()
LATER = (TODAY + timedelta(days=60)).isoformat()


def _user(db, email="rdue@example.com"):
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


def _constraint(db, user, key, *, review_by=FUTURE, exit_=None, status="confirmed", parent="injury_x",
                tier="advisory", **over):
    value = {
        "scope": ({"tier": "engine", "region_keys": ["hinge"]} if tier == "engine"
                  else {"tier": "advisory", "text": f"text of {key}"}),
        "kind": "block", "parent_key": parent, "exit": exit_ or {"with_parent": True},
        "review_by": review_by, "status": status,
        "asserted_by": "user" if status == "confirmed" else None,
    }
    value.update(over)
    return upsert_knowledge_entry(user.id, KnowledgeEntryIn(
        type="constraint", key=key, value=value, source="api"), db)


def _finding(db, user, key, **over):
    value = {"statement": f"statement of {key}", "domain": "injury", "status": "open",
             "parent_key": "injury_x", "as_of": "2026-09-20",
             "basis": {"text": "b", "evidence": [{"door": "document", "ref": "r"}]},
             "derived_from_labs": False, "asserted_by": "user"}
    value.update(over)
    return upsert_knowledge_entry(user.id, KnowledgeEntryIn(
        type="finding", key=key, value=value, source="api"), db)


def _due(db, user):
    r = _client(db, user).get("/knowledge/review-due")
    assert r.status_code == 200, r.text
    return r.json()


def _by_key(body):
    return {i["key"]: i for i in body["items"]}


# ── the read ──────────────────────────────────────────────────────────────────

def test_it_lists_review_due_exit_due_on_date_and_parent_gone(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    _injury(db_session, u, "injury_gone")
    _constraint(db_session, u, "c_review", review_by=PAST)
    _constraint(db_session, u, "c_ondate", exit_={"on_date": PAST})
    _constraint(db_session, u, "c_parent", parent="injury_gone")
    gone = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, key="injury_gone").one()
    knowledge_router._resolve_entry(gone.id, knowledge_router.ResolutionIn(basis="healed", resolved_by="user"),
                                    "injury", u.id, db_session)
    _constraint(db_session, u, "c_clean")        # control: a future date, a live parent
    items = _by_key(_due(db_session, u))
    assert set(items) == {"c_review", "c_ondate", "c_parent"}
    assert items["c_review"]["tags"] == ["review due"] and items["c_review"]["days_overdue"] == 10
    assert items["c_ondate"]["tags"] == ["exit due"] and items["c_ondate"]["days_overdue"] == 10
    assert items["c_ondate"]["exit_on_date"] == PAST
    assert items["c_parent"]["tags"] == ["exit due"] and items["c_parent"]["days_overdue"] is None
    assert items["c_parent"]["parent_key"] == "injury_gone"


def test_a_row_can_be_both_review_due_and_exit_due(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    _constraint(db_session, u, "c_both", review_by=PAST, exit_={"on_date": (TODAY - timedelta(days=3)).isoformat()})
    item = _by_key(_due(db_session, u))["c_both"]
    assert item["tags"] == ["exit due", "review due"]
    assert item["days_overdue"] == 10          # the longest-overdue date


def test_a_proposal_is_never_listed_however_overdue(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    _constraint(db_session, u, "c_prop", review_by=PAST, status="proposed")
    _finding(db_session, u, "f_prop", status="proposed", asserted_by=None, review_by=PAST)
    assert _due(db_session, u)["items"] == []


def test_a_retired_row_is_not_listed(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    row = _constraint(db_session, u, "c_done", review_by=PAST)
    knowledge_router._resolve_entry(row.id, knowledge_router.ResolutionIn(basis="done", resolved_by="user"),
                                    "constraint", u.id, db_session)
    assert _due(db_session, u)["items"] == []


def test_a_review_date_of_today_is_due(db_session):
    """`constraint_due_tags` is `<=`: the sweep agrees with the chat section and the snapshot."""
    u = _user(db_session)
    _injury(db_session, u)
    _constraint(db_session, u, "c_today", review_by=TODAY.isoformat())
    item = _by_key(_due(db_session, u))["c_today"]
    assert item["days_overdue"] == 0


def test_findings_are_listed_only_past_review_by(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    _finding(db_session, u, "f_old", review_by=PAST)
    _finding(db_session, u, "f_future", review_by=FUTURE)
    _finding(db_session, u, "f_none")                       # review_by is optional on a finding
    items = _by_key(_due(db_session, u))
    assert set(items) == {"f_old"}
    assert items["f_old"]["type"] == "finding" and items["f_old"]["tags"] == ["review due"]
    assert items["f_old"]["days_overdue"] == 10 and items["f_old"]["what"] == "statement of f_old"


def test_a_lab_derived_finding_is_counted_never_carried(db_session):
    """The #60 firewall holds in the sweep: no statement of a lab interpretation leaves the server."""
    u = _user(db_session)
    _injury(db_session, u)
    _finding(db_session, u, "f_lab", derived_from_labs=True, review_by=PAST,
             statement="SECRET LAB INTERPRETATION")
    body = _due(db_session, u)
    assert body["items"] == [] and body["withheld_labs"] == 1
    assert "SECRET LAB INTERPRETATION" not in str(body)


def test_most_overdue_first_and_another_users_rows_stay_theirs(db_session):
    a, b = _user(db_session, "a@example.com"), _user(db_session, "b@example.com")
    for u in (a, b):
        _injury(db_session, u)
    _constraint(db_session, a, "c_a_new", review_by=(TODAY - timedelta(days=2)).isoformat())
    _constraint(db_session, a, "c_a_old", review_by=(TODAY - timedelta(days=40)).isoformat())
    _constraint(db_session, b, "c_b", review_by=PAST)
    assert [i["key"] for i in _due(db_session, a)["items"]] == ["c_a_old", "c_a_new"]
    assert [i["key"] for i in _due(db_session, b)["items"]] == ["c_b"]


def test_the_read_changes_nothing(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    _constraint(db_session, u, "c_review", review_by=PAST)
    snap = lambda: [(r.id, r.value, r.active) for r in db_session.query(models.UserKnowledgeEntry).order_by(models.UserKnowledgeEntry.id)]
    before = snap()
    _due(db_session, u)
    assert snap() == before


def test_the_sweep_lists_exactly_what_the_chat_tags(db_session):
    """One definition of "due": the sweep and the chat/MCP line formatter cannot disagree."""
    import typed_entries
    u = _user(db_session)
    _injury(db_session, u)
    _constraint(db_session, u, "c_review", review_by=PAST)
    _constraint(db_session, u, "c_ok")
    rows = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, active=True).all()
    live = typed_entries.active_keys(rows)
    tagged = {c["key"] for c in typed_entries.lift_constraints(rows)
              if typed_entries.constraint_due_tags(c, live, TODAY)}
    assert tagged == set(_by_key(_due(db_session, u)))


# ── Keep: the in-place review ────────────────────────────────────────────────

@pytest.fixture
def confirmed(db_session):
    """A constraint that reached `confirmed` the only way it can: proposed, then the confirm route."""
    u = _user(db_session)
    _injury(db_session, u)
    prop = _constraint(db_session, u, "c_keep", review_by=PAST, status="proposed", tier="engine")
    row = _confirm_entry(prop.id, ConfirmIn(asserted_by="clinician"), "constraint", u.id, db_session)
    assert row.value["confirmed_on"] and row.value["asserted_by"] == "clinician"
    return u, row


def test_keep_sets_review_by_and_nothing_else(db_session, confirmed):
    u, row = confirmed
    before = dict(row.value)
    r = _client(db_session, u).post(f"/knowledge/constraints/{row.id}/review", json={"review_by": LATER})
    assert r.status_code == 200, r.text
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()    # a fresh read
    assert fresh.id == row.id and fresh.active and fresh.superseded_by is None
    assert fresh.value == {**before, "review_by": LATER}
    for kept in ("status", "asserted_by", "confirmed_on", "scope", "exit", "parent_key", "kind"):
        assert fresh.value[kept] == before[kept]
    assert db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, key="c_keep").count() == 1


def test_a_kept_row_leaves_the_sweep(db_session, confirmed):
    u, row = confirmed
    assert "c_keep" in _by_key(_due(db_session, u))
    _client(db_session, u).post(f"/knowledge/constraints/{row.id}/review", json={"review_by": LATER})
    assert "c_keep" not in _by_key(_due(db_session, u))


def test_keep_is_why_the_route_exists_a_rewrite_cannot_carry_confirmed_on(db_session, confirmed):
    """The ruling's premise, pinned: the same-key api rewrite refuses the stamp, and without it the
    new row loses `confirmed_on`. If this ever stops holding, the route's Reverse-by has fired."""
    u, row = confirmed
    with pytest.raises(ValueError, match="confirmed_on"):
        upsert_knowledge_entry(u.id, KnowledgeEntryIn(
            type="constraint", key="c_keep", value={**row.value, "review_by": LATER}, source="api"), db_session)
    stripped = {k: v for k, v in row.value.items() if k != "confirmed_on"}
    new = upsert_knowledge_entry(u.id, KnowledgeEntryIn(
        type="constraint", key="c_keep", value={**stripped, "review_by": LATER}, source="api"), db_session)
    assert "confirmed_on" not in new.value and new.id != row.id


@pytest.mark.parametrize("review_by,why", [
    (TODAY.isoformat(), "today"), (PAST, "past"), ("not-a-date", "malformed"),
])
def test_keep_refuses_a_date_that_is_not_in_the_future(db_session, confirmed, review_by, why):
    u, row = confirmed
    r = _client(db_session, u).post(f"/knowledge/constraints/{row.id}/review", json={"review_by": review_by})
    assert r.status_code == 422, why
    assert db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one().value["review_by"] == PAST


def test_keep_refuses_a_proposal(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    prop = _constraint(db_session, u, "c_prop", status="proposed", tier="engine")
    r = _client(db_session, u).post(f"/knowledge/constraints/{prop.id}/review", json={"review_by": LATER})
    assert r.status_code == 409 and "confirmed or declined" in r.text
    assert db_session.query(models.UserKnowledgeEntry).filter_by(id=prop.id).one().value["review_by"] == FUTURE


def test_keep_refuses_a_retired_row(db_session, confirmed):
    u, row = confirmed
    knowledge_router._resolve_entry(row.id, knowledge_router.ResolutionIn(basis="done", resolved_by="user"),
                                    "constraint", u.id, db_session)
    r = _client(db_session, u).post(f"/knowledge/constraints/{row.id}/review", json={"review_by": LATER})
    assert r.status_code == 409


def test_keep_is_type_scoped_and_user_scoped(db_session, confirmed):
    u, row = confirmed
    other = _user(db_session, "other@example.com")
    c = _client(db_session, u)
    assert c.post(f"/knowledge/findings/{row.id}/review", json={"review_by": LATER}).status_code == 404
    assert c.post("/knowledge/constraints/999999/review", json={"review_by": LATER}).status_code == 404
    assert _client(db_session, other).post(
        f"/knowledge/constraints/{row.id}/review", json={"review_by": LATER}).status_code == 404
    assert db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one().value["review_by"] == PAST


def test_the_chat_channel_cannot_re_date_a_confirmed_row(db_session, confirmed):
    """Api only: the route has no chat door, and a chat rewrite of a past-`proposed` row is refused."""
    u, row = confirmed
    stripped = {k: v for k, v in row.value.items() if k != "confirmed_on"}   # past the stamped-field check
    with pytest.raises(TypedEntryRefused) as exc:
        upsert_knowledge_entry(u.id, KnowledgeEntryIn(
            type="constraint", key="c_keep", value={**stripped, "review_by": LATER}, source="chat"), db_session)
    assert exc.value.code in ("operator_only", "proposal_only")
    assert db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one().value["review_by"] == PAST


def test_keep_on_a_finding_is_the_same_in_place_redate(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    prop = _finding(db_session, u, "f_keep", status="proposed", asserted_by=None, review_by=PAST)
    row = _confirm_entry(prop.id, ConfirmIn(asserted_by="clinician"), "finding", u.id, db_session)
    before = dict(row.value)
    r = _client(db_session, u).post(f"/knowledge/findings/{row.id}/review", json={"review_by": LATER})
    assert r.status_code == 200, r.text
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert fresh.value == {**before, "review_by": LATER} and fresh.value["confirmed_on"]
    assert "f_keep" not in _by_key(_due(db_session, u))


def test_keep_on_an_open_finding_is_allowed_and_on_a_proposed_one_is_not(db_session):
    u = _user(db_session)
    _injury(db_session, u)
    opened = _finding(db_session, u, "f_open", review_by=PAST)
    prop = _finding(db_session, u, "f_prop", status="proposed", asserted_by=None, review_by=PAST)
    c = _client(db_session, u)
    assert c.post(f"/knowledge/findings/{opened.id}/review", json={"review_by": LATER}).status_code == 200
    assert c.post(f"/knowledge/findings/{prop.id}/review", json={"review_by": LATER}).status_code == 409
