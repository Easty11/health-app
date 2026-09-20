"""Plan of record on the Phase card (#319, closing the #318 §44 divergence).

  (a) `context_builder.plan_of_record_stale` is the SINGLE definition of the STALE flag — the
      chat render (`_section_training_plan`) and the route below both call it, so the card cannot
      diverge from the chat context. Unit-tested here for the four input shapes.
  (b) `GET /engine/plan-of-record` returns `{macro, revised_on, revised_by, stale}` for the current
      plan, `null` when none is set, and carries that same `stale` flag (never re-derived client-side).
"""
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

import context_builder
import models
from auth import get_current_user
from database import get_db
from routers import engine as engine_router
from routers.knowledge import TRAINING_PLAN_KEY


def _user(db, email="por-route@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(engine_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _plan(db, uid, macro="## Offseason\nPhase 1 base; buffer rule.", revised_on="2026-08-15",
          revised_by="coach"):
    db.add(models.UserKnowledgeEntry(
        user_id=uid, type="training_plan", key=TRAINING_PLAN_KEY,
        value={"macro": macro, "revised_on": revised_on, "revised_by": revised_by},
        source="api", active=True))
    db.commit()


def _phase(db, uid, entered_on, review_on):
    ph = models.TrainingPhase(
        user_id=uid, label="base", probe_posture="held", entered_on=entered_on,
        asserted_by="user", asserted_on=entered_on, source="api", review_on=review_on,
    )
    db.add(ph)
    db.commit()


# --------------------------------------------------------------------------- #
# (a) the shared STALE predicate                                              #
# --------------------------------------------------------------------------- #

_PLAN = {"macro": "x", "revised_on": "2026-08-15", "revised_by": "coach"}


def test_plan_of_record_stale_is_the_one_definition():
    phase_due = {"review_due": True, "review_on": "2026-09-01"}
    # revised BEFORE a passed review → stale.
    assert context_builder.plan_of_record_stale(_PLAN, phase_due) is True
    # revised AFTER the review date → not stale.
    assert context_builder.plan_of_record_stale({**_PLAN, "revised_on": "2026-09-15"}, phase_due) is False
    # review not yet due → never stale, whatever the revised_on.
    assert context_builder.plan_of_record_stale(_PLAN, {"review_due": False, "review_on": "2026-09-01"}) is False
    # absent / unparseable inputs → False, never a crash.
    assert context_builder.plan_of_record_stale(None, phase_due) is False
    assert context_builder.plan_of_record_stale(_PLAN, None) is False
    assert context_builder.plan_of_record_stale({**_PLAN, "revised_on": "nonsense"}, phase_due) is False


# --------------------------------------------------------------------------- #
# (b) the route                                                               #
# --------------------------------------------------------------------------- #

def test_route_returns_null_when_no_plan(db_session):
    u = _user(db_session)
    r = _client(db_session, u).get("/engine/plan-of-record")
    assert r.status_code == 200 and r.json() is None


def test_route_returns_plan_and_stale_flag_when_due(db_session):
    """A plan revised BEFORE a phase's now-passed review → the route says stale, the SAME verdict
    the chat section renders (both via plan_of_record_stale)."""
    u = _user(db_session, email="stale@example.com")
    _plan(db_session, u.id, revised_on="2026-08-15")
    # review date in the past relative to the sandbox clock (2026-09-20) → review_due True.
    _phase(db_session, u.id, entered_on=date(2026, 8, 1), review_on=date(2026, 9, 1))
    body = _client(db_session, u).get("/engine/plan-of-record").json()
    assert body["macro"].startswith("## Offseason")
    assert body["revised_on"] == "2026-08-15" and body["revised_by"] == "coach"
    assert body["stale"] is True


def test_route_not_stale_when_revised_after_review(db_session):
    u = _user(db_session, email="fresh@example.com")
    _plan(db_session, u.id, revised_on="2026-09-15")
    _phase(db_session, u.id, entered_on=date(2026, 8, 1), review_on=date(2026, 9, 1))
    body = _client(db_session, u).get("/engine/plan-of-record").json()
    assert body["stale"] is False


def test_route_not_stale_with_no_open_phase(db_session):
    """A plan but no open phase → nothing to be stale against → stale False (phase None path)."""
    u = _user(db_session, email="nophase@example.com")
    _plan(db_session, u.id, revised_on="2026-08-15")
    body = _client(db_session, u).get("/engine/plan-of-record").json()
    assert body is not None and body["stale"] is False
