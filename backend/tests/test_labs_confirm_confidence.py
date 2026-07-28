"""confirm_lab_report derives overall_confidence from the rows (#146).

The first ingestion run produced reports whose model-reported overall_confidence
was 0.0 despite per-row confidences of 0.92-0.99 and correct values: the field
defaulted to 0.0 when omitted and was seeded by the prompt example. It is now
derived at confirm as min(row confidences) — the same per-row values written to
each LabResult — so an omitted field can no longer read as a certain zero.

confirm_lab_report is called directly with an explicit user + db, bypassing the
auth dependency; the derivation is the unit under test, not the HTTP layer.
"""
from datetime import datetime

import models
from routers.labs import (
    ExtractionResult, FieldConfidence, ReportDates, ReportEnvelope,
    ReportExtractionMeta, ResultItem, confirm_lab_report,
)

_COLLECTED = datetime(2026, 5, 30, 9, 0, 0)


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _envelope(results):
    """A minimal valid ExtractionResult. Note: ReportExtractionMeta no longer HAS
    an overall_confidence field — the model cannot report it, by construction."""
    return ExtractionResult(
        report=ReportEnvelope(
            lab_name="Sullivan Nicolaides",
            panel_name_raw="Androgens",
            dates=ReportDates(collected=_COLLECTED),
            source_completeness="sonic_dx_extract",
            extraction=ReportExtractionMeta(extracted_at=_COLLECTED, model="test"),
        ),
        results=results,
    )


def _result(name, fc):
    return ResultItem(marker_name_raw=name, value_num=1.0, unit_canonical="U/L",
                      field_confidence=FieldConfidence(**fc))


def _stored(db, report_id):
    return db.get(models.LabReport, report_id)


def test_overall_confidence_is_derived_nonzero_when_model_omits_it(db_session):
    """G2 positive: extraction carries NO overall_confidence, yet the stored report
    scores the min over its rows' field confidences (0.92), never a defaulted 0.0."""
    user = _user(db_session, "derive@example.com")
    body = _envelope([
        _result("AST", {"name": 0.99, "value": 0.99, "unit": 0.98, "ref": 0.97}),
        _result("ALT", {"name": 0.95, "value": 0.93, "unit": 0.92, "ref": 0.96}),
    ])
    resp = confirm_lab_report(body, current_user=user, db=db_session)

    stored = _stored(db_session, resp.lab_report_id)
    assert stored.overall_confidence != 0.0
    assert stored.overall_confidence == 0.92  # min over both rows' field-min


def test_overall_confidence_low_row_drags_it_down_negative_control(db_session):
    """G2 negative control: a single low-confidence row scores the report low, so
    the derivation cannot be passing on a hardcoded constant. min propagates the
    worst row (implemented over mean, per #146 — a bad row must not hide)."""
    user = _user(db_session, "control@example.com")
    body = _envelope([
        _result("AST", {"name": 0.99, "value": 0.99, "unit": 0.98, "ref": 0.97}),
        _result("ALT", {"name": 0.40, "value": 0.95, "unit": 0.95, "ref": 0.95}),
    ])
    resp = confirm_lab_report(body, current_user=user, db=db_session)

    stored = _stored(db_session, resp.lab_report_id)
    assert stored.overall_confidence == 0.40  # the bad row wins; not a constant

    # and it matches the worst per-row confidence actually written
    rows = db_session.query(models.LabResult).filter_by(lab_report_id=resp.lab_report_id).all()
    assert min(r.confidence for r in rows) == 0.40


def test_overall_confidence_defaults_to_one_when_no_field_confidence(db_session):
    """A row with no field_confidence contributes 1.0 (the per-row rule), so a
    report of only such rows scores 1.0 — the derivation reads the same fallback
    the row records use, not a separate path."""
    user = _user(db_session, "nofc@example.com")
    body = _envelope([ResultItem(marker_name_raw="AST", value_num=1.0, unit_canonical="U/L")])
    resp = confirm_lab_report(body, current_user=user, db=db_session)
    assert _stored(db_session, resp.lab_report_id).overall_confidence == 1.0
