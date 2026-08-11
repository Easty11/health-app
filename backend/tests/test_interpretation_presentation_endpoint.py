"""GET /interpretation/presentation + promote — the server-side eligibility gate (#202).

The gate is UNCONDITIONAL and server-side: a plain-register request whose row is not
`human_verified` renders the template, regardless of the client toggle. Promotion binds to
the base text (`payload_hash`). The missing-key path is fail-closed to the template.

Router functions are called directly with the in-memory `db_session`, matching
test_interpretation_endpoint.py — no HTTP/auth layer needed.
"""
from datetime import date

import models
from routers.interpretation import (
    get_presentation,
    promote_presentation,
)


def _user(db, email="p@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _report(db, user_id, collected, panel="Panel"):
    r = models.LabReport(
        user_id=user_id, lab_name="Lab", panel_name_raw=panel, collected_date=collected,
        source_completeness="sonic_dx_extract", source="file_extraction", overall_confidence=0.99,
    )
    db.add(r); db.commit(); db.refresh(r)
    return r


def _result(db, report_id, raw, canonical, value):
    db.add(models.LabResult(lab_report_id=report_id, marker_name_raw=raw,
                            marker_canonical=canonical, value_num=value, confidence=0.99))
    db.commit()


def _seed(db):
    u = _user(db)
    p = _report(db, u.id, date(2026, 1, 7), "Prior")
    c = _report(db, u.id, date(2026, 5, 30), "Current")
    _result(db, p.id, "AST", "ast", 40.0)
    _result(db, c.id, "AST", "ast", 47.0)
    return u


def test_clinical_register_serves_base_text(db_session):
    u = _seed(db_session)
    resp = get_presentation(register="clinical", current_user=u, db=db_session)
    assert resp["register_served"] == "clinical"
    assert resp["text"] and resp["draft"] is None
    assert len(resp["payload_hash"]) == 64


def test_plain_without_key_fails_closed_to_template(db_session, monkeypatch):
    """No ANTHROPIC_API_KEY -> generator gets client=None -> nothing generated or stored ->
    the plain request is served the clinical template, with no draft."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    u = _seed(db_session)
    clinical = get_presentation(register="clinical", current_user=u, db=db_session)
    plain = get_presentation(register="plain", current_user=u, db=db_session)
    assert plain["register_served"] == "clinical"
    assert plain["text"] == clinical["text"]
    assert plain["draft"] is None
    # nothing was persisted
    assert db_session.query(models.InterpretationRephrase).count() == 0


def test_promoted_overlay_is_served_for_plain(db_session, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    u = _seed(db_session)
    h = get_presentation(register="plain", current_user=u, db=db_session)["payload_hash"]
    # A human-verified overlay exists for this exact base text.
    db_session.add(models.InterpretationRephrase(
        payload_hash=h, register="plain", text="PLAIN OVERLAY TEXT", status="human_verified"))
    db_session.commit()

    resp = get_presentation(register="plain", current_user=u, db=db_session)
    assert resp["register_served"] == "plain"
    assert resp["text"] == "PLAIN OVERLAY TEXT"


def test_ai_draft_is_gated_until_promoted(db_session, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    u = _seed(db_session)
    h = get_presentation(register="plain", current_user=u, db=db_session)["payload_hash"]
    row = models.InterpretationRephrase(
        payload_hash=h, register="plain", text="DRAFT OVERLAY", status="ai_draft")
    db_session.add(row); db_session.commit(); db_session.refresh(row)

    # ai_draft -> still served the template, but the draft is returned for review
    gated = get_presentation(register="plain", current_user=u, db=db_session)
    assert gated["register_served"] == "clinical"
    assert gated["draft"]["status"] == "ai_draft" and gated["draft"]["id"] == row.id

    # promote, then the overlay is served
    promoted = promote_presentation(rephrase_id=row.id, current_user=u, db=db_session)
    assert promoted["status"] == "human_verified"
    served = get_presentation(register="plain", current_user=u, db=db_session)
    assert served["register_served"] == "plain"
    assert served["text"] == "DRAFT OVERLAY"
