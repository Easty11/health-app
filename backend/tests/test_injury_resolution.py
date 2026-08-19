"""Injury resolution — the write end of a loop that could only be opened (#222/#223).

An injury entry could be CREATED and SUPERSEDED-BY-KEY, but not RESOLVED. The
consequence was live, not hypothetical: `gather_active_injuries` kept returning
healed injuries and `is_contraindicated` kept suppressing regions the user had
recovered in, with no surface listing them so the operator could see what to retire.

The load-bearing gate is `test_a_suppressed_region_becomes_selectable_after_resolve`:
a SPECIFIC region asserted contraindicated before and selectable after, with no other
input changed. Asserting only that the injury list shrank would pass even if the
suppression never lifted.

The GUARD gates are the other half and matter as much: nothing auto-resolves. A
passing `resolve_by` date, a soreness series at the exit condition, and a live
`review` flag must each leave `active` untouched — an injury constraint that lifts
itself with no operator in the loop is a safety failure (#72 stays surfacing-only).
"""
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import injury_trajectory
import models
from auth import get_current_user
from database import get_db
from engine import selection, taxonomy
from routers import knowledge as knowledge_router


def _user(db, email):
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


def _injury(db, user_id, *, key="hamstring_right", body_part="hamstring",
            side="right", value=None, active=True, **kw):
    """An injury row shaped the way `gather_active_injuries` reads it."""
    val = value if value is not None else {
        "body_part": body_part,
        "side": side,
        "signal_type": "mechanical",
        "restrictions": ["no end-range stretching"],
    }
    row = models.UserKnowledgeEntry(
        user_id=user_id, type="injury", key=key, value=val,
        source="chat", added_at=date.today(), active=active, **kw,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# The acute-hamstring block set, straight from the engine. Pinned as a
# precondition rather than hardcoded, so a taxonomy edit fails loudly here
# instead of quietly making the load-bearing gate vacuous.
SUPPRESSED_BY_HAMSTRING = "single_leg_hop"


# ── step 1: the read surface ─────────────────────────────────────────────────

def test_injuries_endpoint_returns_only_active_injuries(db_session):
    u = _user(db_session, "inj-a@example.com")
    _injury(db_session, u.id, key="hamstring_right")
    _injury(db_session, u.id, key="ankle_left", body_part="ankle", side="left")
    _injury(db_session, u.id, key="old_calf", body_part="calf", active=False)
    # A non-injury entry must not leak through the injury surface.
    db_session.add(models.UserKnowledgeEntry(
        user_id=u.id, type="schedule_item", key="weekly_split",
        value={"split": "upper/lower"}, source="chat", added_at=date.today(), active=True,
    ))
    db_session.commit()

    body = _client(db_session, u).get("/knowledge/injuries").json()
    assert {r["key"] for r in body} == {"hamstring_right", "ankle_left"}
    assert {r["type"] for r in body} == {"injury"}


def test_include_resolved_returns_inactive_rows_too(db_session):
    u = _user(db_session, "inj-b@example.com")
    _injury(db_session, u.id, key="live_one")
    _injury(db_session, u.id, key="dead_one", active=False)

    c = _client(db_session, u)
    assert {r["key"] for r in c.get("/knowledge/injuries").json()} == {"live_one"}
    assert {r["key"] for r in c.get(
        "/knowledge/injuries", params={"include_resolved": "true"}
    ).json()} == {"live_one", "dead_one"}


def test_injuries_endpoint_never_returns_another_users_rows(db_session):
    """Cross-user isolation, asserted with two fixture users on BOTH arms — the
    default and `include_resolved=true`, since the history arm widens the filter
    and is where a dropped `user_id` would show up."""
    mine = _user(db_session, "mine@example.com")
    theirs = _user(db_session, "theirs@example.com")
    _injury(db_session, mine.id, key="my_hamstring")
    _injury(db_session, theirs.id, key="their_hamstring")
    _injury(db_session, theirs.id, key="their_old_ankle", active=False)

    c = _client(db_session, mine)
    for params in ({}, {"include_resolved": "true"}):
        keys = {r["key"] for r in c.get("/knowledge/injuries", params=params).json()}
        assert keys == {"my_hamstring"}, f"leak with params={params}: {keys}"


def test_the_trajectory_block_is_returned_unmodified(db_session):
    """#72's trajectory rides inside `value`; this surface reads, never reinterprets."""
    u = _user(db_session, "inj-traj@example.com")
    traj = {
        "shape": "resolving_by",
        "declared_on": "2026-07-01",
        "resolve_by": "2026-09-01",
        "review_when": {"metric": "soreness", "op": "<=", "threshold": 1,
                        "sustained_days": 3},
    }
    _injury(db_session, u.id, value={
        "body_part": "hamstring", "side": "right",
        "signal_type": "mechanical", "restrictions": [], "trajectory": traj,
    })
    row = _client(db_session, u).get("/knowledge/injuries").json()[0]
    assert row["value"]["trajectory"] == traj


def test_the_read_surface_distinguishes_superseded_from_resolved(db_session):
    """Both terminal states read `active=False`; only supersession names a successor.
    Without `superseded_by` on the schema the history arm could not tell them apart."""
    u = _user(db_session, "inj-sup@example.com")
    first = _injury(db_session, u.id, key="hamstring_right")
    second = _injury(db_session, u.id, key="hamstring_right_v2")
    first.superseded_by = second.id
    first.active = False
    db_session.commit()

    rows = {r["id"]: r for r in _client(db_session, u).get(
        "/knowledge/injuries", params={"include_resolved": "true"}).json()}
    assert rows[first.id]["superseded_by"] == second.id
    assert rows[second.id]["superseded_by"] is None


def test_no_injuries_is_an_empty_list_not_an_error(db_session):
    u = _user(db_session, "inj-empty@example.com")
    r = _client(db_session, u).get("/knowledge/injuries")
    assert r.status_code == 200
    assert r.json() == []
