"""The clearance sweep recognises constraints — S5 of the typed-entries brief (#NEXT).

G5 (ruled at G0, "S5 parent rule"):
  * `rehomed` also accepts a confirmed ACTIVE constraint whose `scope.text` carries the
    restriction, when it OUTLIVES the swept injury: parented to a DIFFERENT active entry, or no
    parent and no `with_parent`.
  * A constraint parented to the injury being swept is labelled `dies_with_parent` and does NOT
    re-home — the restriction still reads as an orphan (the S6 seed's rows are this shape).
  * An orphan's suggested action is "propose as constraint". A constraint hit in the entries store
    carries the constraint resolve route. No write, anywhere.
"""
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from routers import knowledge as knowledge_router
from routers.knowledge import KnowledgeEntryIn, upsert_knowledge_entry


def _user(db, email="sweep-c@example.com"):
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


def _injury(db, user_id, key, body_part, restrictions=(), active=True):
    row = models.UserKnowledgeEntry(
        user_id=user_id, type="injury", key=key, source="api", added_at=date.today(), active=active,
        value={"body_part": body_part, "side": "right", "signal_type": "mechanical",
               "restrictions": list(restrictions)},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _constraint(db, user_id, key, text, *, parent=None, with_parent=False, status="confirmed"):
    exit_ = {"with_parent": True} if with_parent else {"on_condition": "physio clears it"}
    return upsert_knowledge_entry(user_id, KnowledgeEntryIn(type="constraint", key=key, value={
        "scope": {"tier": "advisory", "text": text}, "kind": "block", "parent_key": parent,
        "exit": exit_, "review_by": "2026-10-15", "status": status,
        "asserted_by": "user" if status == "confirmed" else None,
    }, source="api"), db)


@pytest.fixture
def world(db_session):
    u = _user(db_session)
    ham = _injury(db_session, u.id, "injury_hamstring_right", "hamstring",
                  restrictions=["striding", "sprinting", "heavy hinging"])
    lumbar = _injury(db_session, u.id, "injury_lumbar_spine", "lumbar")
    return {"user": u, "ham": ham, "lumbar": lumbar}


def _audit(db, world):
    r = _client(db, world["user"]).get(f"/knowledge/injuries/{world['ham'].id}/sweep")
    assert r.status_code == 200, r.text
    return {a["restriction"]: a for a in r.json()["restriction_audit"]}


def test_unparented_constraint_rehomes(db_session, world):
    c = _constraint(db_session, world["user"].id, "c_stride", "no striding drills")
    a = _audit(db_session, world)["striding"]
    assert a["status"] == "rehomed" and a["suggested_action"] is None
    assert [x["entry_id"] for x in a["rehomed_to_constraints"]] == [c.id]


def test_constraint_parented_to_another_active_entry_rehomes(db_session, world):
    c = _constraint(db_session, world["user"].id, "c_hinge", "no heavy hinging",
                    parent="injury_lumbar_spine", with_parent=True)
    a = _audit(db_session, world)["heavy hinging"]
    assert a["status"] == "rehomed" and a["rehomed_to_constraints"][0]["entry_id"] == c.id


def test_constraint_parented_to_the_swept_injury_dies_with_it(db_session, world):
    """The pinned ruling: named, and the restriction STILL reads as an orphan."""
    c = _constraint(db_session, world["user"].id, "c_sprint", "no sprinting",
                    parent="injury_hamstring_right", with_parent=True)
    a = _audit(db_session, world)["sprinting"]
    assert a["status"] == "orphan"
    assert a["rehomed_to_constraints"] == [] and a["parent_resolved_survives"] == []
    assert [x["entry_id"] for x in a["dies_with_parent"]] == [c.id]
    assert a["suggested_action"] == "propose as constraint"


def test_constraint_parented_here_without_with_parent_survives_under_its_own_label(db_session, world):
    """G5 ruling 1: an on_condition exit outlives the injury. Cautious outcome (still ORPHAN), but
    it does NOT die — its own label and suggestion. `dies_with_parent` stays with_parent-only."""
    c = _constraint(db_session, world["user"].id, "c_sprint", "no sprinting",
                    parent="injury_hamstring_right", with_parent=False)
    a = _audit(db_session, world)["sprinting"]
    assert a["status"] == "orphan"
    assert a["dies_with_parent"] == [] and a["rehomed_to_constraints"] == []
    assert [x["entry_id"] for x in a["parent_resolved_survives"]] == [c.id]
    assert a["suggested_action"] == "re-parent or resolve — constraint keeps enforcing"


def test_after_the_injury_resolves_its_child_still_does_not_rehome(db_session, world):
    """Resolved row, parent now inactive — the child still reads as dying with it."""
    _constraint(db_session, world["user"].id, "c_sprint", "no sprinting",
                parent="injury_hamstring_right", with_parent=True)
    world["ham"].active = False
    db_session.commit()
    a = _audit(db_session, world)["sprinting"]
    assert a["status"] == "orphan" and len(a["dies_with_parent"]) == 1


@pytest.mark.parametrize("case", ["proposed", "resolved", "parent_inactive", "no_text_match"])
def test_constraints_that_must_not_rehome(db_session, world, case):
    u = world["user"].id
    if case == "proposed":
        _constraint(db_session, u, "c", "no striding", status="proposed")
    elif case == "resolved":
        row = _constraint(db_session, u, "c", "no striding")
        row.active = False
        db_session.commit()
    elif case == "parent_inactive":
        _injury(db_session, u, "injury_old_calf", "calf")
        _constraint(db_session, u, "c", "no striding", parent="injury_old_calf", with_parent=True)
        db_session.query(models.UserKnowledgeEntry).filter_by(key="injury_old_calf").one().active = False
        db_session.commit()
    else:
        _constraint(db_session, u, "c", "no jumping")
    a = _audit(db_session, world)["striding"]
    assert a["status"] == "orphan" and a["rehomed_to_constraints"] == []


def test_orphan_without_any_constraint_suggests_proposing_one(db_session, world):
    """Control: with no constraints at all, the #340 audit is unchanged apart from the new fields."""
    audit = _audit(db_session, world)
    assert {r: a["status"] for r, a in audit.items()} == {
        "striding": "orphan", "sprinting": "orphan", "heavy hinging": "orphan"}
    assert all(a["suggested_action"] == "propose as constraint" for a in audit.values())
    assert all(a["dies_with_parent"] == [] and a["rehomed_to_constraints"] == [] for a in audit.values())


def test_a_constraint_hit_carries_its_resolve_route(db_session, world):
    c = _constraint(db_session, world["user"].id, "c_ham", "no hamstring end-range stretching")
    r = _client(db_session, world["user"]).get(f"/knowledge/injuries/{world['ham'].id}/sweep").json()
    hit = next(h for h in r["hits"] if h["store"] == "user_knowledge_entries" and h["row_id"] == c.id)
    assert hit["action"] == "resolve"
    assert hit["action_route"] == f"POST /knowledge/constraints/{c.id}/resolve"


def test_the_sweep_still_never_writes(db_session, world):
    _constraint(db_session, world["user"].id, "c_sprint", "no sprinting",
                parent="injury_hamstring_right", with_parent=True)
    _constraint(db_session, world["user"].id, "c_stride", "no striding")

    def snap():
        db_session.expire_all()
        return [(r.id, r.type, r.key, r.value, r.active, r.superseded_by) for r in
                db_session.query(models.UserKnowledgeEntry).order_by(models.UserKnowledgeEntry.id)]
    before = snap()
    _audit(db_session, world)
    assert snap() == before
