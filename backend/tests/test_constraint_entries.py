"""Typed `constraint` entries — S1 of the typed-entries brief (#342).

G1's gates, each with its negative control:
  * the validator refuses every unknown key (top level, `scope`, `exit`) and each missing
    required field; `pattern_keys` / `exercise_template_ids` are refused (G0 D1 — region keys
    are the only engine vocabulary in v1);
  * an engine-tier row without scope is refused; `with_parent` without a parent is refused;
    a constraint with no exit is refused;
  * `parent_key` must name one of the user's ACTIVE rows, of ANY type (G0 R3);
  * confirm is the ONLY proposed → confirmed path: a chat write carrying `confirmed` is refused,
    an api upsert carrying `confirmed` over a proposal is refused, the route succeeds;
  * D4: a typed key cannot collide with another type's active row (either direction), and chat
    can neither supersede nor deactivate a confirmed row.
"""
import json
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from load_metrics import _local_day
from routers import knowledge as knowledge_router
from routers.chat import _process_knowledge_updates
from routers.knowledge import (
    CONSTRAINT_REQUIRED,
    KnowledgeEntryIn,
    TypedEntryRefused,
    upsert_knowledge_entry,
    validate_constraint,
)


def _user(db, email="constraint@example.com"):
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


def _injury(db, user_id, key="hamstring_right", active=True):
    row = models.UserKnowledgeEntry(
        user_id=user_id, type="injury", key=key,
        value={"body_part": "hamstring", "side": "right", "signal_type": "mechanical",
               "restrictions": ["no striding/sprinting"]},
        source="api", added_at=date.today(), active=active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _engine(**over):
    v = {
        "scope": {"tier": "engine", "region_keys": ["hinge"]},
        "kind": "block",
        "parent_key": None,
        "exit": {"on_date": "2026-11-01"},
        "review_by": "2026-10-15",
        "status": "confirmed",
        "asserted_by": "user",
    }
    v.update(over)
    return v


def _advisory(**over):
    v = {
        "scope": {"tier": "advisory", "text": "no striding or sprinting"},
        "kind": "block",
        "parent_key": "hamstring_right",
        "exit": {"with_parent": True},
        "review_by": "2026-10-15",
        "status": "proposed",
        "asserted_by": None,
    }
    v.update(over)
    return v


def _write(db, user_id, value, key="c_hinge", source="api", expires_at=None):
    return upsert_knowledge_entry(user_id, KnowledgeEntryIn(
        type="constraint", key=key, value=value, source=source, expires_at=expires_at,
    ), db)


def _chat(db, user_id, payload):
    block = f"OK.\n<knowledge_update>{json.dumps(payload)}</knowledge_update>\nDone."
    return _process_knowledge_updates(block, user_id, db)


def _rows(db, user_id, **kw):
    return db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id, **kw).all()


# ── shape ────────────────────────────────────────────────────────────────────

def test_valid_engine_constraint_round_trips_byte_identical(db_session):
    u = _user(db_session)
    value = _engine(detail="post-op; surgeon's order")
    row = _write(db_session, u.id, value)
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert fresh.value == value
    assert fresh.type == "constraint" and fresh.active


def test_valid_advisory_proposal_with_null_authority_is_accepted(db_session):
    u = _user(db_session)
    _injury(db_session, u.id)
    row = _write(db_session, u.id, _advisory())
    assert row.value["status"] == "proposed" and row.value["asserted_by"] is None


@pytest.mark.parametrize("where,bad", [
    ("top", {"active": True}),
    ("top", {"note": "x"}),
    ("scope", {"pattern_keys": ["hinge"]}),              # D1 — no pattern layer yet
    ("scope", {"exercise_template_ids": ["ABC123"]}),     # D1 — Hevy ids, never gated
    ("exit", {"on_review": True}),
])
def test_every_unknown_key_is_refused(where, bad):
    v = _engine()
    if where == "top":
        v.update(bad)
    else:
        v[where] = {**v[where], **bad}
    with pytest.raises(ValueError, match="unknown field"):
        validate_constraint(v)


@pytest.mark.parametrize("stamped", [
    {"confirmed_on": "2026-09-27"},
    {"resolution": {"resolved_on": "2026-09-27", "basis": "x", "resolved_by": "user"}},
])
def test_route_stamped_fields_are_refused_on_write(stamped):
    with pytest.raises(ValueError, match="stamped by its route"):
        validate_constraint(_engine(**stamped))


@pytest.mark.parametrize("field", CONSTRAINT_REQUIRED)
def test_each_missing_required_field_is_refused(field):
    v = _engine()
    del v[field]
    with pytest.raises(ValueError, match="missing required"):
        validate_constraint(v)


def test_optional_fields_may_be_absent():
    v = _engine()
    del v["parent_key"]
    assert validate_constraint(v) is v                     # negative control: not required


@pytest.mark.parametrize("scope", [
    {"tier": "engine"},
    {"tier": "engine", "region_keys": []},
    {"tier": "engine", "text": "no hinging"},
])
def test_engine_tier_without_scope_is_refused(scope):
    with pytest.raises(ValueError, match=">=1 scoping key"):
        validate_constraint(_engine(scope=scope))


def test_engine_tier_refuses_an_unknown_region_key():
    with pytest.raises(ValueError, match="unknown region key"):
        validate_constraint(_engine(scope={"tier": "engine", "region_keys": ["hamstring"]}))


@pytest.mark.parametrize("kind", ["cap", "caution"])
def test_engine_tier_accepts_block_only(kind):
    """G2 ruling 2: no dose seam for an engine cap; a boolean gate cannot express a caution."""
    with pytest.raises(ValueError, match="advisory-tier only"):
        validate_constraint(_engine(kind=kind))
    assert validate_constraint(_advisory(kind=kind))                   # control: advisory takes them


@pytest.mark.parametrize("side", ["left", "right", "bilateral"])
def test_engine_tier_side_is_optional_and_closed(side):
    assert validate_constraint(_engine(scope={"tier": "engine", "region_keys": ["hinge"], "side": side}))
    with pytest.raises(ValueError, match="scope.side"):
        validate_constraint(_engine(scope={"tier": "engine", "region_keys": ["hinge"], "side": "both"}))


def test_advisory_tier_carries_no_side():
    with pytest.raises(ValueError, match="engine-tier only"):
        validate_constraint(_advisory(scope={"tier": "advisory", "text": "x", "side": "right"}))


def test_advisory_tier_requires_text_and_carries_no_scoping_keys():
    with pytest.raises(ValueError, match="text is required"):
        validate_constraint(_advisory(scope={"tier": "advisory"}))
    with pytest.raises(ValueError, match="engine-tier only"):
        validate_constraint(_advisory(scope={"tier": "advisory", "text": "x", "region_keys": ["hinge"]}))


@pytest.mark.parametrize("exit_", [{}, {"with_parent": False}, {"on_date": None, "on_condition": None}])
def test_a_constraint_with_no_exit_is_refused(exit_):
    with pytest.raises(ValueError, match="at least one exit"):
        validate_constraint(_engine(exit=exit_))


def test_with_parent_without_a_parent_is_refused():
    with pytest.raises(ValueError, match="requires a parent_key"):
        validate_constraint(_engine(exit={"with_parent": True}, parent_key=None))


@pytest.mark.parametrize("over,match", [
    ({"kind": "forbid"}, "constraint.kind"),
    ({"status": "active"}, "constraint.status"),
    ({"asserted_by": "coach"}, "asserted_by"),
    ({"asserted_by": None}, "required once status is 'confirmed'"),
    ({"review_by": "next month"}, "review_by"),
    ({"exit": {"with_parent": "yes"}, "parent_key": "p"}, "strict boolean"),
])
def test_bad_values_are_refused(over, match):
    with pytest.raises(ValueError, match=match):
        validate_constraint(_engine(**over))


# ── parent_key (R3: any type, the user's ACTIVE rows) ────────────────────────

def test_parent_may_be_any_entry_type(db_session):
    u = _user(db_session)
    db_session.add(models.UserKnowledgeEntry(
        user_id=u.id, type="supplement", key="creatine", value={"active": True},
        source="api", added_at=date.today(), active=True,
    ))
    db_session.commit()
    row = _write(db_session, u.id, _advisory(parent_key="creatine"))
    assert row.value["parent_key"] == "creatine"


@pytest.mark.parametrize("case", ["missing", "inactive", "other_user", "self"])
def test_parent_must_name_an_active_row_of_this_user(db_session, case):
    u = _user(db_session)
    if case == "inactive":
        _injury(db_session, u.id, active=False)
    if case == "other_user":
        _injury(db_session, _user(db_session, "other@example.com").id)
    key = "hamstring_right" if case == "self" else "c1"
    with pytest.raises(TypedEntryRefused) as exc:
        _write(db_session, u.id, _advisory(), key=key)
    assert exc.value.code == "invalid_parent"
    assert _rows(db_session, u.id, type="constraint") == []


def test_expires_at_is_refused(db_session):
    u = _user(db_session)
    with pytest.raises(TypedEntryRefused, match="expires_at"):
        _write(db_session, u.id, _engine(), expires_at=date(2026, 12, 1))


# ── confirm is the only proposed → confirmed path ────────────────────────────

def test_chat_write_carrying_confirmed_is_refused_and_leaves_no_row(db_session):
    u = _user(db_session)
    _, _, results = _chat(db_session, u.id, {"type": "constraint", "key": "c_hinge", "value": _engine()})
    assert results[0].saved is False and results[0].reason_code == "proposal_only"
    assert _rows(db_session, u.id, type="constraint") == []


def test_chat_proposal_with_authority_is_refused(db_session):
    u = _user(db_session)
    _, _, results = _chat(db_session, u.id, {"type": "constraint", "key": "c_hinge",
                                             "value": _engine(status="proposed")})
    assert results[0].reason_code == "proposal_only"


def test_chat_proposal_is_saved_as_proposed(db_session):
    """Negative control for the two refusals above: the proposal shape saves."""
    u = _user(db_session)
    _, _, results = _chat(db_session, u.id, {"type": "constraint", "key": "c_hinge",
                                             "value": _engine(status="proposed", asserted_by=None)})
    assert results[0].saved is True
    (row,) = _rows(db_session, u.id, type="constraint")
    assert row.source == "chat" and row.value["status"] == "proposed"


def test_upsert_confirming_a_proposal_is_refused(db_session):
    u = _user(db_session)
    proposed = _write(db_session, u.id, _engine(status="proposed", asserted_by=None))
    with pytest.raises(TypedEntryRefused) as exc:
        _write(db_session, u.id, _engine())
    assert exc.value.code == "confirm_via_route"
    db_session.refresh(proposed)
    assert proposed.active and proposed.value["status"] == "proposed"
    assert len(_rows(db_session, u.id, type="constraint")) == 1


def test_operator_direct_confirmed_write_with_no_proposal_is_accepted(db_session):
    """Negative control: an api write minting a confirmed row (the S6 seed's path) is not a
    transition, so it is not refused."""
    u = _user(db_session)
    assert _write(db_session, u.id, _engine()).value["status"] == "confirmed"


def test_confirm_route_confirms_and_stamps_authority(db_session):
    u = _user(db_session)
    row = _write(db_session, u.id, _engine(status="proposed", asserted_by=None))
    c = _client(db_session, u)
    r = c.post(f"/knowledge/constraints/{row.id}/confirm", json={"asserted_by": "clinician"})
    assert r.status_code == 200, r.text
    assert r.json()["value"]["status"] == "confirmed"
    assert r.json()["value"]["asserted_by"] == "clinician"
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert fresh.value["status"] == "confirmed" and fresh.active
    assert fresh.value["confirmed_on"] == str(_local_day())       # G1 ruling 2 — stamped here only
    # Twice is an error, not a no-op.
    assert c.post(f"/knowledge/constraints/{row.id}/confirm",
                  json={"asserted_by": "user"}).status_code == 409


def test_confirm_route_refusals(db_session):
    u = _user(db_session)
    inj = _injury(db_session, u.id)
    row = _write(db_session, u.id, _engine(status="proposed", asserted_by=None))
    c = _client(db_session, u)
    assert c.post(f"/knowledge/constraints/{row.id}/confirm",
                  json={"asserted_by": "coach"}).status_code == 422
    assert c.post("/knowledge/constraints/{}/confirm".format(inj.id),
                  json={"asserted_by": "user"}).status_code == 404          # cross-type 404
    other = _user(db_session, "someone@example.com")
    assert _client(db_session, other).post(
        f"/knowledge/constraints/{row.id}/confirm", json={"asserted_by": "user"}
    ).status_code == 404


def test_confirm_refused_once_the_parent_exit_has_fired(db_session):
    u = _user(db_session)
    inj = _injury(db_session, u.id)
    row = _write(db_session, u.id, _advisory())
    inj.active = False
    db_session.commit()
    r = _client(db_session, u).post(f"/knowledge/constraints/{row.id}/confirm",
                                    json={"asserted_by": "user"})
    assert r.status_code == 409 and "already fired" in r.text


def test_resolve_route_retires_with_basis(db_session):
    u = _user(db_session)
    row = _write(db_session, u.id, _engine())
    c = _client(db_session, u)
    assert c.post(f"/knowledge/constraints/{row.id}/resolve",
                  json={"basis": " ", "resolved_by": "user"}).status_code == 422
    r = c.post(f"/knowledge/constraints/{row.id}/resolve",
               json={"basis": "cleared at 6-week review", "resolved_by": "clinician"})
    assert r.status_code == 200, r.text
    fresh = db_session.query(models.UserKnowledgeEntry).filter_by(id=row.id).one()
    assert not fresh.active and fresh.superseded_by is None
    assert fresh.value["resolution"]["basis"] == "cleared at 6-week review"


# ── D4: key collision + chat cannot retire a confirmed row ───────────────────

def test_constraint_cannot_take_an_active_injury_key(db_session):
    u = _user(db_session)
    inj = _injury(db_session, u.id)
    with pytest.raises(TypedEntryRefused) as exc:
        _write(db_session, u.id, _engine(), key="hamstring_right")
    assert exc.value.code == "key_collision"
    db_session.refresh(inj)
    assert inj.active and inj.superseded_by is None


def test_injury_cannot_take_an_active_constraint_key(db_session):
    u = _user(db_session)
    c = _write(db_session, u.id, _engine())
    with pytest.raises(TypedEntryRefused, match="key_collision|held by an active"):
        upsert_knowledge_entry(u.id, KnowledgeEntryIn(
            type="injury", key="c_hinge", value={"body_part": "knee"}, source="api",
        ), db_session)
    db_session.refresh(c)
    assert c.active


def test_untyped_same_key_rewrite_is_unchanged(db_session):
    """Negative control: an injury rewriting its own key still supersedes (existing behaviour)."""
    u = _user(db_session)
    old = _injury(db_session, u.id)
    new = upsert_knowledge_entry(u.id, KnowledgeEntryIn(
        type="injury", key="hamstring_right", value={"body_part": "hamstring"}, source="chat",
    ), db_session)
    db_session.refresh(old)
    assert not old.active and old.superseded_by == new.id


def test_chat_cannot_supersede_a_confirmed_constraint(db_session):
    u = _user(db_session)
    confirmed = _write(db_session, u.id, _engine())
    _, _, results = _chat(db_session, u.id, {"type": "constraint", "key": "c_hinge",
                                             "value": _engine(status="proposed", asserted_by=None)})
    assert results[0].saved is False and results[0].reason_code == "operator_only"
    db_session.refresh(confirmed)
    assert confirmed.active and confirmed.value["status"] == "confirmed"


def test_chat_may_rewrite_its_own_proposal(db_session):
    """Negative control: a proposal is chat's to revise."""
    u = _user(db_session)
    first = _write(db_session, u.id, _engine(status="proposed", asserted_by=None), source="chat")
    _, _, results = _chat(db_session, u.id, {"type": "constraint", "key": "c_hinge",
                                             "value": _engine(status="proposed", asserted_by=None,
                                                              review_by="2026-10-30")})
    assert results[0].saved is True
    db_session.refresh(first)
    assert not first.active and first.superseded_by is not None


def test_chat_cannot_deactivate_a_confirmed_constraint(db_session):
    u = _user(db_session)
    confirmed = _write(db_session, u.id, _engine())
    _, _, results = _chat(db_session, u.id, {"type": "constraint", "key": "c_hinge", "active": False})
    assert results[0].saved is False and results[0].reason_code == "operator_only"
    db_session.refresh(confirmed)
    assert confirmed.active


def test_chat_may_withdraw_a_proposal(db_session):
    """Negative control for the deactivation guard."""
    u = _user(db_session)
    proposed = _write(db_session, u.id, _engine(status="proposed", asserted_by=None))
    _, _, results = _chat(db_session, u.id, {"type": "constraint", "key": "c_hinge", "active": False})
    assert results[0].saved is True and results[0].reason_code == "deactivated"
    db_session.refresh(proposed)
    assert not proposed.active


# ── S1 VERIFY: injury restrictions untouched ─────────────────────────────────

def test_injury_restrictions_are_untouched_by_a_constraint_write(db_session):
    from engine import selection
    u = _user(db_session)
    inj = _injury(db_session, u.id)
    before = selection.gather_active_injuries(db_session, u.id)
    _write(db_session, u.id, _advisory(status="confirmed", asserted_by="user"), key="c_stride")
    db_session.refresh(inj)
    assert inj.value["restrictions"] == ["no striding/sprinting"]
    assert selection.gather_active_injuries(db_session, u.id) == before
