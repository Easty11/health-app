"""Typed `finding` entries — S2 of the typed-entries brief (#343).

G2's gates, each with its negative control:
  * the validator refuses every unknown key (top level, `basis`, an evidence item) and each missing
    required field; an evidence ref citing a non-canonical door is refused (Q22);
  * `retracted` / `superseded` are never written — `/retract` and a same-key rewrite stamp them
    (G1 ruling 3); retract without a basis is refused;
  * chat writes are proposals and chat never promotes one; proposed → open is an operator write;
  * a `derived_from_labs` finding is withheld wherever the #60 firewall withholds lab
    interpretation — the lift never carries its statement (the renderers read the lift, S4).
"""
import json
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
import typed_entries
from auth import get_current_user
from context_builder import _section_labs
from database import get_db
from load_metrics import _local_day
from reads.labs_reads import latest_lab_results
from routers import knowledge as knowledge_router
from routers.chat import _process_knowledge_updates
from routers.knowledge import (
    FINDING_REQUIRED,
    KnowledgeEntryIn,
    TypedEntryRefused,
    upsert_knowledge_entry,
    validate_finding,
)
# The #60 render-firewall fixture, reused rather than re-built (G2).
from test_labs_reads import _make_report, _make_result


def _user(db, email="finding@example.com"):
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


def _finding(**over):
    v = {
        "statement": "Left hamstring pain is laterality-paradoxical: provoked by right-leg loading",
        "domain": "injury",
        "status": "open",
        "parent_key": None,
        "as_of": "2026-09-20",
        "basis": {"text": "three sessions", "evidence": [
            {"door": "counted_workouts", "ref": "2026-09-14"},
        ]},
        "marker_status": "provocative",
        "derived_from_labs": False,
        "asserted_by": "user",
    }
    v.update(over)
    return v


def _proposal(**over):
    return _finding(status="proposed", asserted_by=None, **over)


def _write(db, user_id, value, key="f_laterality", source="api"):
    return upsert_knowledge_entry(user_id, KnowledgeEntryIn(
        type="finding", key=key, value=value, source=source,
    ), db)


def _chat(db, user_id, payload):
    block = f"OK.\n<knowledge_update>{json.dumps(payload)}</knowledge_update>\nDone."
    return _process_knowledge_updates(block, user_id, db)


def _get(db, row_id):
    return db.query(models.UserKnowledgeEntry).filter_by(id=row_id).one()


# ── shape ────────────────────────────────────────────────────────────────────

def test_valid_finding_round_trips_byte_identical(db_session):
    u = _user(db_session)
    value = _finding(review_by="2026-10-20")
    row = _write(db_session, u.id, value)
    assert _get(db_session, row.id).value == value


@pytest.mark.parametrize("where,bad", [
    ("top", {"note": "x"}),
    ("top", {"restrictions": []}),
    ("basis", {"source": "hevy"}),
    ("evidence", {"hevy_template_id": "ABC123"}),
])
def test_every_unknown_key_is_refused(where, bad):
    v = _finding()
    if where == "top":
        v.update(bad)
    elif where == "basis":
        v["basis"] = {**v["basis"], **bad}
    else:
        v["basis"]["evidence"][0].update(bad)
    with pytest.raises(ValueError, match="unknown field"):
        validate_finding(v)


@pytest.mark.parametrize("field", FINDING_REQUIRED)
def test_each_missing_required_field_is_refused(field):
    v = _finding()
    del v[field]
    with pytest.raises(ValueError, match="missing required"):
        validate_finding(v)


def test_optional_fields_may_be_absent():
    v = _finding()
    for f in ("parent_key", "marker_status"):
        del v[f]
    assert validate_finding(v) is v                       # negative control


@pytest.mark.parametrize("door", ["hevy_workouts", "hevy_sets", "samsung_hrv_readings", "Lab_Results"])
def test_evidence_citing_a_non_canonical_door_is_refused(door):
    v = _finding(basis={"evidence": [{"door": door, "ref": "x"}]})
    with pytest.raises(ValueError, match="canonical read door"):
        validate_finding(v)


@pytest.mark.parametrize("door", ["counted_workouts", "arbitrated_sessions", "lab_results", "document"])
def test_every_canonical_door_is_accepted(door):
    assert validate_finding(_finding(basis={"evidence": [{"door": door, "ref": "r1"}]}))


@pytest.mark.parametrize("basis", [{}, {"text": None, "evidence": []}, {"evidence": [{"door": "document", "ref": ""}]}])
def test_a_finding_without_grounds_is_refused(basis):
    with pytest.raises(ValueError):
        validate_finding(_finding(basis=basis))


@pytest.mark.parametrize("status", ["retracted", "superseded"])
def test_terminal_statuses_are_never_written(status):
    with pytest.raises(ValueError, match="never written"):
        validate_finding(_finding(status=status))


@pytest.mark.parametrize("over,match", [
    ({"domain": "medical"}, "finding.domain"),
    ({"status": "closed"}, "finding.status"),
    ({"marker_status": "positive"}, "marker_status"),
    ({"derived_from_labs": "no"}, "strict boolean"),
    ({"as_of": "last week"}, "as_of"),
    ({"asserted_by": None}, "required once status is 'open'"),
    ({"confirmed_on": "2026-09-27"}, "stamped by its route"),
    ({"resolution": {"basis": "x"}}, "stamped by its route"),
])
def test_bad_values_are_refused(over, match):
    with pytest.raises(ValueError, match=match):
        validate_finding(_finding(**over))


def test_finding_with_a_resolved_injury_parent_is_refused(db_session):
    """Q192 widens CONSTRAINT parenting only: a finding still needs an active parent."""
    u = _user(db_session)
    inj = models.UserKnowledgeEntry(
        user_id=u.id, type="injury", key="hamstring_left", value={"body_part": "hamstring"},
        source="api", added_at=date.today(), active=True,
    )
    db_session.add(inj)
    db_session.commit()
    knowledge_router._resolve_entry(
        inj.id, knowledge_router.ResolutionIn(basis="cleared", resolved_by="clinician"),
        "injury", u.id, db_session)
    with pytest.raises(TypedEntryRefused, match="names no active entry") as exc:
        _write(db_session, u.id, _finding(parent_key="hamstring_left"))
    assert exc.value.code == "invalid_parent"


# ── lifecycle ────────────────────────────────────────────────────────────────

def test_chat_proposal_saves_as_proposed(db_session):
    u = _user(db_session)
    _, _, results = _chat(db_session, u.id, {"type": "finding", "key": "f1", "value": _proposal()})
    assert results[0].saved is True
    (row,) = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, type="finding").all()
    assert row.value["status"] == "proposed" and row.source == "chat"


@pytest.mark.parametrize("status", ["open", "confirmed"])
def test_chat_cannot_write_past_proposed(db_session, status):
    u = _user(db_session)
    _, _, results = _chat(db_session, u.id, {"type": "finding", "key": "f1",
                                             "value": _finding(status=status)})
    assert results[0].saved is False and results[0].reason_code == "proposal_only"


def test_chat_cannot_promote_its_own_proposal(db_session):
    u = _user(db_session)
    prop = _write(db_session, u.id, _proposal(), source="chat")
    _, _, results = _chat(db_session, u.id, {"type": "finding", "key": "f_laterality",
                                             "value": _finding(status="open")})
    assert results[0].reason_code == "proposal_only"
    assert _get(db_session, prop.id).active


def test_chat_rewrite_of_its_proposal_stamps_superseded(db_session):
    u = _user(db_session)
    prop = _write(db_session, u.id, _proposal(), source="chat")
    _, _, results = _chat(db_session, u.id, {"type": "finding", "key": "f_laterality",
                                             "value": _proposal(statement="revised")})
    assert results[0].saved is True
    old = _get(db_session, prop.id)
    assert not old.active and old.superseded_by is not None
    assert old.value["status"] == "superseded"               # G1 ruling 3


def test_operator_promotes_proposed_to_open_by_upsert(db_session):
    u = _user(db_session)
    prop = _write(db_session, u.id, _proposal(), source="chat")
    new = _write(db_session, u.id, _finding(status="open"))
    assert new.value["status"] == "open"
    assert _get(db_session, prop.id).value["status"] == "superseded"


def test_chat_cannot_supersede_or_deactivate_an_open_finding(db_session):
    u = _user(db_session)
    row = _write(db_session, u.id, _finding())
    _, _, r1 = _chat(db_session, u.id, {"type": "finding", "key": "f_laterality", "value": _proposal()})
    _, _, r2 = _chat(db_session, u.id, {"type": "finding", "key": "f_laterality", "active": False})
    assert r1[0].reason_code == "operator_only" and r2[0].reason_code == "operator_only"
    fresh = _get(db_session, row.id)
    assert fresh.active and fresh.value["status"] == "open"


@pytest.mark.parametrize("start", ["proposed", "open"])
def test_upsert_confirming_is_refused_and_route_confirms(db_session, start):
    u = _user(db_session)
    row = _write(db_session, u.id, _proposal() if start == "proposed" else _finding())
    with pytest.raises(TypedEntryRefused) as exc:
        _write(db_session, u.id, _finding(status="confirmed"))
    assert exc.value.code == "confirm_via_route"
    r = _client(db_session, u).post(f"/knowledge/findings/{row.id}/confirm", json={"asserted_by": "clinician"})
    assert r.status_code == 200, r.text
    v = _get(db_session, row.id).value
    assert v["status"] == "confirmed" and v["asserted_by"] == "clinician"
    assert v["confirmed_on"] == str(_local_day())


def test_retract_requires_basis_and_stamps_retracted(db_session):
    u = _user(db_session)
    row = _write(db_session, u.id, _finding())
    c = _client(db_session, u)
    assert c.post(f"/knowledge/findings/{row.id}/retract",
                  json={"basis": "  ", "resolved_by": "user"}).status_code == 422
    assert _get(db_session, row.id).active                   # refused retract changes nothing
    r = c.post(f"/knowledge/findings/{row.id}/retract",
               json={"basis": "right-leg loading was not the driver", "resolved_by": "user"})
    assert r.status_code == 200, r.text
    fresh = _get(db_session, row.id)
    assert not fresh.active and fresh.superseded_by is None   # stays in the table
    assert fresh.value["status"] == "retracted"
    assert fresh.value["resolution"]["basis"] == "right-leg loading was not the driver"
    assert c.post(f"/knowledge/findings/{row.id}/retract",
                  json={"basis": "again", "resolved_by": "user"}).status_code == 409


def test_finding_routes_are_type_scoped(db_session):
    u = _user(db_session)
    inj = models.UserKnowledgeEntry(user_id=u.id, type="injury", key="k", value={},
                                    source="api", added_at=date.today(), active=True)
    db_session.add(inj)
    db_session.commit()
    c = _client(db_session, u)
    assert c.post(f"/knowledge/findings/{inj.id}/retract",
                  json={"basis": "x", "resolved_by": "user"}).status_code == 404
    assert c.post(f"/knowledge/findings/{inj.id}/confirm",
                  json={"asserted_by": "user"}).status_code == 404


def test_finding_and_constraint_keys_cannot_collide(db_session):
    u = _user(db_session)
    _write(db_session, u.id, _finding(), key="shared")
    with pytest.raises(TypedEntryRefused, match="held by an active"):
        upsert_knowledge_entry(u.id, KnowledgeEntryIn(type="constraint", key="shared", value={
            "scope": {"tier": "advisory", "text": "x"}, "kind": "caution",
            "exit": {"on_condition": "reviewed"}, "review_by": "2026-10-01",
            "status": "confirmed", "asserted_by": "user",
        }, source="api"), db_session)


# ── the read lift: what renders, and the #60 firewall ────────────────────────

def test_lift_reads_open_and_confirmed_only_newest_as_of_first(db_session):
    u = _user(db_session)
    _write(db_session, u.id, _proposal(), key="f_prop")
    _write(db_session, u.id, _finding(as_of="2026-09-01"), key="f_old")
    _write(db_session, u.id, _finding(as_of="2026-09-25"), key="f_new")
    gone = _write(db_session, u.id, _finding(), key="f_gone")
    _client(db_session, u).post(f"/knowledge/findings/{gone.id}/retract",
                                json={"basis": "wrong", "resolved_by": "user"})
    rows = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id).all()
    lifted = typed_entries.lift_findings(rows)
    assert [f["key"] for f in lifted["visible"]] == ["f_new", "f_old"]
    assert lifted["withheld_labs"] == 0


def test_lab_derived_finding_is_withheld_where_lab_interpretation_is(db_session):
    """The #60 fixture (`test_labs_reads`): a bilirubin result the standing render reports as
    generality only. A finding interpreting it must not reach any render surface either: the lift
    carries no statement, only a count. Control: the same finding NOT lab-derived is visible."""
    u = _user(db_session)
    report = _make_report(db_session, u.id, date(2026, 6, 1))
    _make_result(db_session, report.id, "Bilirubin", marker_canonical="bilirubin_total",
                 value_num=28.0, lab_flag="H", computed_flag="H")
    interp = "Bilirubin 28 umol/L above range, consistent with Gilbert's syndrome"
    _write(db_session, u.id, _finding(statement=interp, domain="clinical", derived_from_labs=True,
                                      basis={"evidence": [{"door": "lab_results", "ref": "bilirubin_total"}]}),
           key="f_lab")
    _write(db_session, u.id, _finding(), key="f_plain")

    rows = db_session.query(models.UserKnowledgeEntry).filter_by(user_id=u.id, active=True).all()
    lifted = typed_entries.lift_findings(rows)
    assert [f["key"] for f in lifted["visible"]] == ["f_plain"]
    assert lifted["withheld_labs"] == 1
    assert interp not in json.dumps(lifted, default=str)
    # The firewall it inherits is unchanged: the lab render still carries no value or interpretation.
    rendered = _section_labs(latest_lab_results(u.id, db_session))
    assert "28.0" not in rendered and "Gilbert" not in rendered


def test_lift_withholds_a_finding_whose_lab_flag_is_absent():
    """A row written around the validator with no `derived_from_labs` degrades to withheld."""
    row = models.UserKnowledgeEntry(id=1, type="finding", key="f", active=True,
                                    value={"status": "open", "as_of": "2026-09-01", "statement": "s"})
    assert typed_entries.lift_findings([row]) == {"visible": [], "withheld_labs": 1}


def test_lift_constraints_reads_confirmed_only():
    rows = [
        models.UserKnowledgeEntry(id=1, type="constraint", key="a", active=True, value={"status": "confirmed"}),
        models.UserKnowledgeEntry(id=2, type="constraint", key="b", active=True, value={"status": "proposed"}),
        models.UserKnowledgeEntry(id=3, type="constraint", key="c", active=False, value={"status": "confirmed"}),
    ]
    assert [c["key"] for c in typed_entries.lift_constraints(rows)] == ["a"]
