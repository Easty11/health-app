"""The ingest path is held to a PERSISTENCE standard, not a response-success one.

Nothing in the suite read the database back after a confirm. Every existing lab test asserts
on the `ConfirmResponse` — `result_count`, `duplicates`, `unmapped` — which is the handler
describing its own behaviour. A path that returned 201 and wrote nothing would satisfy all of
them. That is precisely the shape that survived: ten `lab_reports` rows carry zero
`lab_results`, and the response said so in a field no caller read.

So these tests confirm a document and then query `LabResult` DIRECTLY, asserting the row
exists with the value that went in. The response object is not the evidence; the row is.

`confirm_lab_report` is called directly with an explicit user + db, bypassing the auth
dependency — the same pattern as `test_labs_confirm_duplicates.py`.
"""
from datetime import date, datetime

import models
from routers.labs import (
    ExtractionResult, ReportDates, ReportEnvelope, ReportExtractionMeta,
    ResultItem, confirm_lab_report,
)

_E1 = datetime(2026, 1, 7, 9, 0, 0)
_E2 = datetime(2026, 5, 30, 9, 0, 0)


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _confirm(db, user, collected, panel, results, on_duplicate="skip"):
    envelope = ExtractionResult(
        report=ReportEnvelope(
            lab_name="Sullivan Nicolaides Pathology", panel_name_raw=panel,
            dates=ReportDates(collected=collected),
            source_completeness="sonic_dx_extract",
            extraction=ReportExtractionMeta(extracted_at=collected, model="test"),
        ),
        results=results,
    )
    return confirm_lab_report(envelope, on_duplicate=on_duplicate, current_user=user, db=db)


def _stored(db, report_id):
    """Read the rows back from the database. Deliberately NOT via the response object."""
    return db.query(models.LabResult).filter(
        models.LabResult.lab_report_id == report_id).all()


# ---------- the standard itself ----------

def test_a_confirmed_result_is_present_in_the_database_with_its_value(db_session):
    """THE assertion that was missing. A confirmed marker is proven present in `lab_results`
    with the value, unit and reference bounds that were submitted — read back from the
    database, not echoed from the handler's return.

    This mirrors the real PSA document (`Total PSA` -> `psa`, 0.7 ug/L, 2026-05-30) because
    that is the report the operator watched render on the confirm screen and then found
    empty."""
    user = _user(db_session, "persist@example.com")
    res = _confirm(db_session, user, _E2, "Prostate Specific Antigen (PSA)", [
        ResultItem(marker_name_raw="Total PSA", value_num=0.7,
                   unit_canonical="ug/L", ref_high=3.0),
    ])

    rows = _stored(db_session, res.lab_report_id)
    assert len(rows) == 1, "the confirmed result must exist as a row, not merely a 201"
    row = rows[0]
    assert row.marker_name_raw == "Total PSA"
    assert row.marker_canonical == "psa"
    assert row.value_num == 0.7
    assert row.unit_canonical == "ug/L"
    assert row.ref_high == 3.0

    # and the report envelope points at the right draw
    report = db_session.get(models.LabReport, res.lab_report_id)
    assert report is not None and report.collected_date == date(2026, 5, 30)
    assert report.user_id == user.id                                          # #42


def test_every_marker_in_a_multi_analyte_panel_persists(db_session):
    """The write loop skips by row index. An off-by-one or a key-shaped skip set would drop
    a row silently while still returning 201, so the whole panel is read back rather than
    spot-checked on one marker."""
    user = _user(db_session, "panel@example.com")
    submitted = {
        "Haemoglobin": 153.0, "Haematocrit": 0.47, "Platelets": 274.0,
        "Neutrophils": 3.46, "Lymphocytes": 2.29,
    }
    res = _confirm(db_session, user, _E2, "Haematology", [
        ResultItem(marker_name_raw=name, value_num=value) for name, value in submitted.items()
    ])

    rows = _stored(db_session, res.lab_report_id)
    assert {r.marker_name_raw: r.value_num for r in rows} == submitted
    assert res.result_count == len(submitted)


# ---------- non-vacuity: this one fails against the pre-fix handler ----------

def test_a_marker_repeated_in_one_document_still_persists_once(db_session):
    """NON-VACUOUS. Pre-fix this wrote ZERO rows and returned 201.

    The skip set was keyed by MARKER, and the write loop tested membership by marker — so an
    intra-batch repeat suppressed every row carrying that marker, including the first, which
    had nothing to collide with. The marker reached no row anywhere. That is genuine loss,
    unlike the database-collision case where skipping is correct precisely because the value
    is already stored.

    The first occurrence must land; the repeat is reported as a duplicate and not written."""
    user = _user(db_session, "repeat@example.com")
    res = _confirm(db_session, user, _E2, "Chemistry", [
        ResultItem(marker_name_raw="Novel Unmapped Analyte", value_num=4.2),
        ResultItem(marker_name_raw="Novel Unmapped Analyte", value_num=4.2),
    ])

    rows = _stored(db_session, res.lab_report_id)
    assert len(rows) == 1, "the first occurrence had nothing to collide with — it must persist"
    assert rows[0].value_num == 4.2
    assert res.result_count == 1
    assert len(res.duplicates) == 1 and res.duplicates[0].action == "skipped"


def test_a_repeat_does_not_suppress_the_other_markers_around_it(db_session):
    """The row-indexed skip must not spill onto neighbouring rows. Ordering is deliberate:
    the repeat sits in the middle, so an index error would take a real marker with it."""
    user = _user(db_session, "neighbour@example.com")
    res = _confirm(db_session, user, _E2, "Chemistry", [
        ResultItem(marker_name_raw="Ferritin", value_num=181.0),
        ResultItem(marker_name_raw="Novel Unmapped Analyte", value_num=4.2),
        ResultItem(marker_name_raw="Novel Unmapped Analyte", value_num=4.2),
        ResultItem(marker_name_raw="Iron", value_num=12.0),
    ])

    rows = _stored(db_session, res.lab_report_id)
    assert {r.marker_name_raw: r.value_num for r in rows} == {
        "Ferritin": 181.0, "Novel Unmapped Analyte": 4.2, "Iron": 12.0,
    }
    assert res.result_count == 3


# ---------- #156 re-verified now that persistence is asserted (Step 4) ----------

def test_the_psa_reupload_collides_and_the_original_row_survives(db_session):
    """`#156` demonstrated on the case that prompted this branch, with the database read back.

    Production reports 1 and 43 are the same PSA document at 2026-05-30; report 43 holds zero
    rows. This asserts the mechanism: the second confirm writes nothing, names the collision,
    and — the part no previous test checked — the ORIGINAL row is still present and unchanged.
    A guard that skipped the incoming row by deleting the stored one would pass every
    response-shaped assertion and fail this."""
    user = _user(db_session, "psa@example.com")
    psa = ResultItem(marker_name_raw="Total PSA", value_num=0.7,
                     unit_canonical="ug/L", ref_high=3.0)
    first = _confirm(db_session, user, _E2, "Prostate Specific Antigen (PSA)", [psa])
    second = _confirm(db_session, user, _E2, "Prostate Specific Antigen (PSA)", [psa])

    assert second.result_count == 0
    assert len(second.duplicates) == 1
    collision = second.duplicates[0]
    assert collision.marker == "psa"
    assert collision.existing_lab_report_id == first.lab_report_id
    assert collision.action == "skipped"
    assert _stored(db_session, second.lab_report_id) == []

    survivors = _stored(db_session, first.lab_report_id)
    assert len(survivors) == 1 and survivors[0].value_num == 0.7, \
        "the stored result must survive a re-upload of its own document"


def test_a_changed_value_on_reupload_is_reported_with_both_values(db_session):
    """The dangerous re-upload is not the identical one — it is the CORRECTED one, where the
    incoming value differs and `skip` discards the correction. `DuplicateCollision` carries
    both values precisely so the caller can tell the two apart without another round trip;
    this asserts they are actually populated, since a caller acting on them is the whole
    remediation path for a corrected result (`keep_both`, per the endpoint docstring)."""
    user = _user(db_session, "corrected@example.com")
    _confirm(db_session, user, _E2, "Prostate Specific Antigen (PSA)", [
        ResultItem(marker_name_raw="Total PSA", value_num=0.7, unit_canonical="ug/L"),
    ])
    second = _confirm(db_session, user, _E2, "Prostate Specific Antigen (PSA)", [
        ResultItem(marker_name_raw="Total PSA", value_num=1.9, unit_canonical="ug/L"),
    ])

    collision = second.duplicates[0]
    assert collision.existing_value_num == 0.7
    assert collision.incoming_value_num == 1.9, "the discarded correction must be visible"
    assert second.result_count == 0


def test_keep_both_actually_persists_the_second_row(db_session):
    """`keep_both` is the documented escape hatch for a legitimate second value. It is only an
    escape hatch if the row lands — asserted against the database, not the response."""
    user = _user(db_session, "keepboth@example.com")
    first = _confirm(db_session, user, _E2, "PSA", [
        ResultItem(marker_name_raw="Total PSA", value_num=0.7),
    ])
    second = _confirm(db_session, user, _E2, "PSA (repeat)", [
        ResultItem(marker_name_raw="Total PSA", value_num=1.9),
    ], on_duplicate="keep_both")

    assert [r.value_num for r in _stored(db_session, second.lab_report_id)] == [1.9]
    assert [r.value_num for r in _stored(db_session, first.lab_report_id)] == [0.7]


def test_a_different_draw_persists_as_a_second_row_not_a_collision(db_session):
    """A genuine second draw is the substrate the delta arm reads. If the guard ever widened
    to key on marker alone, this would start returning zero rows and the series would quietly
    stop growing — the failure would look exactly like the one this branch investigated."""
    user = _user(db_session, "draws@example.com")
    a = _confirm(db_session, user, _E1, "PSA", [ResultItem(marker_name_raw="Total PSA", value_num=0.5)])
    b = _confirm(db_session, user, _E2, "PSA", [ResultItem(marker_name_raw="Total PSA", value_num=0.7)])

    assert a.duplicates == [] and b.duplicates == []
    both = (db_session.query(models.LabResult)
            .join(models.LabReport, models.LabReport.id == models.LabResult.lab_report_id)
            .filter(models.LabReport.user_id == user.id,
                    models.LabResult.marker_canonical == "psa")
            .order_by(models.LabReport.collected_date).all())
    assert [r.value_num for r in both] == [0.5, 0.7]
