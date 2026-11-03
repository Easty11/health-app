"""Restrictions become constraint PROPOSALS from the injury card (DECISIONS_LOG "Restrictions become
constraint proposals from the injury card"; PR-B of the injury-lifecycle-in-app brief). The S6 seed
script (`scripts/seed_constraints.py`, #342) is retired; its planning logic is `engine.restriction_proposals`
behind `POST /knowledge/injuries/{id}/propose-constraints`, and its test moves here with the verbatim
prod-ledger fixture shapes.

THE FIXTURE EXPECTATION (the same ledger the operator's S6 dry-run was reviewed against):
  * id 29 (right hamstring) and id 18 (left) are RESOLVED → the route is 409 and the planner plans nothing;
  * id 94 (lumbar, active) carries 3 restrictions → 3 rows, now PROPOSED (not confirmed);
  * id 77 (finger, active) — its restrictions were not in the listing; the fixture has none → nothing.
Plus: had id 29 been active, its 3 restrictions would plan 3 rows (the control).

Gates: the route writes the plan in one transaction; the rows read back as proposals (listed by
/knowledge/proposals, rendered by nothing, engine-read by nothing); a second call creates nothing; a
DECLINED (resolved) twin is never re-created; `ra_flare` is skipped; a key clash is reported, not
written; the injury row is untouched; the route 404s on a constraint id; Confirm is the operator's act.
"""
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
import typed_entries
from auth import get_current_user
from database import get_db
from engine import restriction_proposals as rp
from engine import selection, taxonomy
from load_metrics import _local_day
from routers import knowledge as kn
from test_injury_sweep_prod_fixture import LUMBAR_94, PROD_LEDGER, RESTRICTIONS_29

REVIEW = _local_day() + timedelta(days=rp.REVIEW_DAYS)


def _row(db, **kw):
    row = models.UserKnowledgeEntry(type="injury", source="system", added_at=date(2026, 7, 1), **kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture
def ledger(db_session):
    u = models.User(email="seed@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    _row(db_session, id=18, user_id=u.id, key="injury_hamstring_left", active=False,
         value={"body_part": "hamstring", "side": "left", "restrictions": ["striding", "sprinting"]})
    _row(db_session, id=29, user_id=u.id, key="injury_hamstring_right", active=False,
         value={"body_part": "hamstring", "side": "right", "restrictions": RESTRICTIONS_29})
    for id_, key, active, body in PROD_LEDGER:
        _row(db_session, id=id_, user_id=u.id, key=key, active=active,
             value={"body_part": body, "signal_type": "mechanical", "restrictions": []})
    _row(db_session, id=94, user_id=u.id, key="injury_lumbar_spine", active=True, value=LUMBAR_94)
    app = FastAPI()
    app.include_router(kn.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: u
    return {"db": db_session, "user": u, "client": TestClient(app)}


def _snapshot(db):
    db.expire_all()
    return [(r.id, r.type, r.key, r.value, r.active) for r in
            db.query(models.UserKnowledgeEntry).order_by(models.UserKnowledgeEntry.id)]


def _propose(ledger, entry_id):
    return ledger["client"].post(f"/knowledge/injuries/{entry_id}/propose-constraints")


def _constraints(ledger):
    return ledger["db"].query(models.UserKnowledgeEntry).filter_by(
        user_id=ledger["user"].id, type="constraint").order_by(models.UserKnowledgeEntry.id).all()


# ── the fixture expectation ──────────────────────────────────────────────────

def test_prod_ledger_plan_matches_the_fixture_expectation(ledger):
    db, uid = ledger["db"], ledger["user"].id
    lumbar = db.get(models.UserKnowledgeEntry, 94)
    plan = rp.plan_restriction_proposals(db, uid, lumbar, REVIEW)
    assert [p["text"] for p in plan["planned"]] == LUMBAR_94["restrictions"]
    assert plan["existing"] == [] and plan["skipped"] == []
    for id_ in (18, 29):                                                  # resolved → nothing
        assert rp.plan_restriction_proposals(db, uid, db.get(models.UserKnowledgeEntry, id_), REVIEW)["planned"] == []
    assert rp.plan_restriction_proposals(db, uid, db.get(models.UserKnowledgeEntry, 77), REVIEW)["planned"] == []


def test_id_29_active_would_plan_its_three_restrictions_as_proposals(ledger):
    """Control: the resolved state is what keeps id 29 out, not the restriction strings."""
    db = ledger["db"]
    row = db.get(models.UserKnowledgeEntry, 29)
    row.active = True
    db.commit()
    planned = rp.plan_restriction_proposals(db, ledger["user"].id, row, REVIEW)["planned"]
    assert [p["text"] for p in planned] == RESTRICTIONS_29
    v = planned[0]["value"]
    assert v["scope"] == {"tier": "advisory", "text": "striding"}
    assert v["exit"] == {"with_parent": True} and v["parent_key"] == "injury_hamstring_right"
    assert (v["status"], v["asserted_by"], v["kind"], v["review_by"]) == ("proposed", None, "block", REVIEW.isoformat())
    kn.validate_constraint(v)                                              # the shape the write path accepts


# ── the route ────────────────────────────────────────────────────────────────

def test_the_route_writes_proposals_the_operator_confirms_and_nothing_reads_before_that(ledger):
    db, uid = ledger["db"], ledger["user"].id
    injuries_before = [r for r in _snapshot(db) if r[1] == "injury"]
    r = _propose(ledger, 94)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [p["text"] for p in body["planned"]] == LUMBAR_94["restrictions"]
    assert len(body["created"]) == 3 and body["existing"] == [] and body["skipped"] == []
    assert body["review_by"] == REVIEW.isoformat() and body["key"] == "injury_lumbar_spine"
    rows = _constraints(ledger)
    assert [r.id for r in rows] == body["created"]
    assert all(r.source == "system" and "proposed from injury_lumbar_spine.restrictions" in r.notes for r in rows)
    assert all((r.value["status"], r.value["asserted_by"]) == ("proposed", None) for r in rows)
    # Proposals: listed for the card, rendered by nothing, engine-read by nothing (G3: no confirmed row).
    listed = ledger["client"].get("/knowledge/proposals").json()
    assert sorted(p["id"] for p in listed) == sorted(body["created"])
    active = db.query(models.UserKnowledgeEntry).filter_by(user_id=uid, active=True).all()
    assert typed_entries.lift_constraints(active) == []
    assert selection.gather_active_constraints(db, uid) == []
    for region in taxonomy.all_regions():
        assert selection.is_contraindicated(region, taxonomy.SIDE_LEFT, profile_hard_stops=None,
                                            active_constraints=[]) == (False, None)
    assert [r for r in _snapshot(db) if r[1] == "injury"] == injuries_before   # the injury row untouched
    # The operator's act: Confirm on the card is the existing route, and only then does a reader see it.
    c = ledger["client"].post(f"/knowledge/constraints/{body['created'][0]}/confirm", json={"asserted_by": "user"})
    assert c.status_code == 200, c.text
    active = db.query(models.UserKnowledgeEntry).filter_by(user_id=uid, active=True).all()
    assert [c["scope"]["text"] for c in typed_entries.lift_constraints(active)] == [LUMBAR_94["restrictions"][0]]


def test_a_second_call_creates_nothing_and_lists_the_covers(ledger):
    first = _propose(ledger, 94).json()
    before = _snapshot(ledger["db"])
    second = _propose(ledger, 94).json()
    assert second["planned"] == [] and second["created"] == []
    assert [(e["text"], e["state"], e["id"]) for e in second["existing"]] == \
        [(t, "proposed", i) for t, i in zip(LUMBAR_94["restrictions"], first["created"])]
    assert _snapshot(ledger["db"]) == before


def test_a_declined_twin_is_never_recreated_and_reads_declined(ledger):
    db = ledger["db"]
    first = _propose(ledger, 94).json()
    d = ledger["client"].post(f"/knowledge/constraints/{first['created'][1]}/resolve",
                              json={"basis": "not an active restriction any more", "resolved_by": "user"})
    assert d.status_code == 200, d.text
    again = _propose(ledger, 94).json()
    assert again["created"] == []
    states = {e["text"]: e["state"] for e in again["existing"]}
    assert states == {LUMBAR_94["restrictions"][0]: "proposed", LUMBAR_94["restrictions"][1]: "declined",
                      LUMBAR_94["restrictions"][2]: "proposed"}
    assert len(_constraints(ledger)) == 3


def test_a_confirmed_twin_reads_confirmed(ledger):
    first = _propose(ledger, 94).json()
    ledger["client"].post(f"/knowledge/constraints/{first['created'][0]}/confirm", json={"asserted_by": "clinician"})
    again = _propose(ledger, 94).json()
    assert again["existing"][0]["state"] == "confirmed" and again["created"] == []


def test_ra_flare_token_is_skipped(ledger):
    _row(ledger["db"], id=200, user_id=ledger["user"].id, key="injury_hand", active=True,
         value={"body_part": "hand", "restrictions": ["ra_flare", "no heavy grip"]})
    body = _propose(ledger, 200).json()
    assert [s["text"] for s in body["skipped"]] == ["ra_flare"]
    assert [p["text"] for p in body["planned"]] == ["no heavy grip"] and len(body["created"]) == 1


def test_a_key_clash_is_reported_never_written(ledger):
    db = ledger["db"]
    key = "constraint_injury_lumbar_spine_end_range_lumbar_flexion_combined_with_twisting"
    db.add(models.UserKnowledgeEntry(user_id=ledger["user"].id, type="preference", key=key, value={},
                                     source="api", active=True))
    db.commit()
    body = _propose(ledger, 94).json()
    assert [s["why"] for s in body["skipped"]] == [f"key {key} is held by active row #{db.query(models.UserKnowledgeEntry).filter_by(key=key).one().id} of another shape"]
    assert len(body["created"]) == 2
    assert db.query(models.UserKnowledgeEntry).filter_by(key=key).one().type == "preference"


def test_the_write_is_one_transaction(ledger, monkeypatch):
    db = ledger["db"]
    real, calls = kn._stage_upsert_entry, []

    def flaky(*a, **kw):
        calls.append(1)
        if len(calls) == 2:
            raise ValueError("boom")
        return real(*a, **kw)

    monkeypatch.setattr(kn, "_stage_upsert_entry", flaky)
    r = _propose(ledger, 94)
    assert r.status_code == 422 and "boom" in r.json()["detail"]
    assert _constraints(ledger) == []


def test_the_route_is_type_scoped_and_refuses_a_resolved_injury(ledger):
    first = _propose(ledger, 94).json()
    assert _propose(ledger, first["created"][0]).status_code == 404        # a constraint id: 404, never planned
    assert _propose(ledger, 29).status_code == 409                          # resolved: its restrictions ended with it
    assert _propose(ledger, 999999).status_code == 404
    assert len(_constraints(ledger)) == 3


def test_another_users_injury_is_404(ledger):
    other = models.User(email="other@example.com", hashed_password="x")
    ledger["db"].add(other)
    ledger["db"].commit()
    _row(ledger["db"], id=300, user_id=other.id, key="injury_knee_left", active=True,
         value={"body_part": "knee", "restrictions": ["deep flexion"]})
    assert _propose(ledger, 300).status_code == 404
    assert ledger["db"].query(models.UserKnowledgeEntry).filter_by(user_id=other.id, type="constraint").count() == 0


def test_the_seed_script_is_gone():
    import importlib.util
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "scripts", "seed_constraints.py")
    assert not os.path.exists(path)
    assert importlib.util.find_spec("scripts.seed_constraints") is None
