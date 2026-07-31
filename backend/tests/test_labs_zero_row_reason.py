"""A report that contributed no rows records WHY — decline and fault are different events.

`#156` working correctly and a document that could not be read produce the same row count and,
until this field, the same stored evidence: nothing. The confirm response carried `duplicates`,
but nothing persisted it, so after the fact the two were indistinguishable. Filtering the results
list on row count alone would therefore have hidden unparseable documents along with correctly
declined re-uploads — absence-as-emptiness one layer along from the failure `#157` fixed.

These tests are the non-vacuity guard for that filter (G4): they assert the two cases are
DIFFERENT in the store, not merely that each is individually representable.
"""
from datetime import datetime

import models
from routers.labs import (
    ExtractionResult, ReportDates, ReportEnvelope, ReportExtractionMeta,
    ResultItem, confirm_lab_report, get_lab_results,
)

_E2 = datetime(2026, 5, 30, 9, 0, 0)


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _confirm(db, user, panel, results, on_duplicate="skip", filename=None):
    from routers.labs import ReportSourceDoc
    envelope = ExtractionResult(
        report=ReportEnvelope(
            lab_name="Sullivan Nicolaides Pathology", panel_name_raw=panel,
            dates=ReportDates(collected=_E2),
            source_completeness="sonic_dx_extract",
            source_doc=ReportSourceDoc(filename=filename) if filename else None,
            extraction=ReportExtractionMeta(extracted_at=_E2, model="test"),
        ),
        results=results,
    )
    return confirm_lab_report(envelope, on_duplicate=on_duplicate, current_user=user, db=db)


def _report(db, report_id):
    return db.get(models.LabReport, report_id)


# ---------- the three states ----------

def test_a_report_that_contributed_rows_records_no_reason(db_session):
    """NULL is the signal for "this report carries values". A non-null reason on a report with
    rows would make the results filter drop a real result."""
    user = _user(db_session, "rows@example.com")
    res = _confirm(db_session, user, "PSA", [
        ResultItem(marker_name_raw="Total PSA", value_num=0.7),
    ])
    assert res.result_count == 1
    assert _report(db_session, res.lab_report_id).zero_row_reason is None


def test_an_all_declined_reupload_records_all_markers_declined(db_session):
    """Case 1 — the system worked. Every marker was already stored, so nothing was written."""
    user = _user(db_session, "declined@example.com")
    psa = ResultItem(marker_name_raw="Total PSA", value_num=0.7)
    _confirm(db_session, user, "PSA", [psa])
    second = _confirm(db_session, user, "PSA", [psa])

    assert second.result_count == 0
    assert _report(db_session, second.lab_report_id).zero_row_reason == "all_markers_declined"


def test_an_unparseable_document_is_recorded_rather_than_500(db_session):
    """Case 2 — a FAULT. Pre-change this tripped `assert row_confidences`, which raised before
    `db.commit()`: the upload left no trace at all and returned a 500. A graph or chart PDF with
    no results table is a real document the operator uploaded and is owed a record of.

    This is also what makes the migration's backfill provably safe — the fault value was
    unreachable before this change, so no legacy zero-row report can be one."""
    user = _user(db_session, "graph@example.com")
    res = _confirm(db_session, user, "Homocysteine Graph", [],
                   filename="Homocysteine Graph.pdf")

    assert res.result_count == 0
    assert res.duplicates == []
    report = _report(db_session, res.lab_report_id)
    assert report is not None, "the upload event must be recorded, not lost to a 500"
    assert report.zero_row_reason == "no_values_extracted"
    assert report.source_doc_filename == "Homocysteine Graph.pdf"
    assert report.overall_confidence == 0.0


# ---------- G4 non-vacuity: the two zero-row cases are DIFFERENT in the store ----------

def test_declined_and_unparseable_are_distinguishable(db_session):
    """THE assertion the results filter depends on. Both reports have zero rows; a filter keyed
    on row count cannot tell them apart, and would hide the fault along with the repeat. Keyed on
    `zero_row_reason` it can. Asserted as an inequality so a future change collapsing the two
    values fails here rather than silently re-hiding faults."""
    user = _user(db_session, "both@example.com")
    psa = ResultItem(marker_name_raw="Total PSA", value_num=0.7)
    _confirm(db_session, user, "PSA", [psa])
    declined = _confirm(db_session, user, "PSA", [psa])
    unparseable = _confirm(db_session, user, "Graph", [], filename="graph.pdf")

    a = _report(db_session, declined.lab_report_id)
    b = _report(db_session, unparseable.lab_report_id)

    # both are genuinely zero-row — the premise the filter would otherwise act on
    assert db_session.query(models.LabResult).filter(
        models.LabResult.lab_report_id == a.id).count() == 0
    assert db_session.query(models.LabResult).filter(
        models.LabResult.lab_report_id == b.id).count() == 0

    assert a.zero_row_reason != b.zero_row_reason, \
        "a decline and a fault must not collapse to one value — the filter depends on it"
    assert a.zero_row_reason == "all_markers_declined"
    assert b.zero_row_reason == "no_values_extracted"


# ---------- the read-back carries what the history view needs ----------

def test_the_readback_exposes_filename_and_reason(db_session):
    """The upload history renders from `GET /labs/results` — VERIFIED as the existing consumer
    rather than adding an endpoint. It needs two fields the projection did not carry: which
    document a report came from, and why it contributed nothing. Both are provenance/ingest
    status, not interpretation, so #47's boundary is untouched."""
    user = _user(db_session, "readback@example.com")
    psa = ResultItem(marker_name_raw="Total PSA", value_num=0.7)
    _confirm(db_session, user, "PSA", [psa], filename="20260530__PSA.pdf")
    _confirm(db_session, user, "PSA", [psa], filename="20260530__PSA.pdf")
    _confirm(db_session, user, "Graph", [], filename="Homocysteine Graph.pdf")

    out = get_lab_results(current_user=user, db=db_session)
    by_reason = {r.zero_row_reason: r for r in out}

    assert by_reason[None].source_doc_filename == "20260530__PSA.pdf"
    assert len(by_reason[None].results) == 1
    assert by_reason["all_markers_declined"].source_doc_filename == "20260530__PSA.pdf"
    assert by_reason["all_markers_declined"].results == []
    assert by_reason["no_values_extracted"].source_doc_filename == "Homocysteine Graph.pdf"
    assert by_reason["no_values_extracted"].results == []


def test_the_reason_is_scoped_to_the_user(db_session):
    """#42 — a second user's identical document collides with nothing, so it writes rows and
    carries no reason. The guard's user scoping is what makes this true; asserted here because
    the history view is per-user and a leak would show one operator another's upload."""
    a = _user(db_session, "a@example.com")
    b = _user(db_session, "b@example.com")
    psa = ResultItem(marker_name_raw="Total PSA", value_num=0.7)
    _confirm(db_session, a, "PSA", [psa])
    a_second = _confirm(db_session, a, "PSA", [psa])
    b_first = _confirm(db_session, b, "PSA", [psa])

    assert _report(db_session, a_second.lab_report_id).zero_row_reason == "all_markers_declined"
    assert _report(db_session, b_first.lab_report_id).zero_row_reason is None
    assert b_first.result_count == 1
