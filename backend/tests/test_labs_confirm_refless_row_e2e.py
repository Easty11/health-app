"""End-to-end: the SNP Albumin/Creat Ratio report ingests — the cure, not the instrument.

This is the report that opened the thread. It could not be saved: `results.0`
(`R U-Creatinine`) has no reference interval, the extractor emitted
`ref_high_exclusive: null`, and `ResultItem` declared a bare `bool` — so FastAPI refused
the body with a request-validation 422 and `confirm_lab_report` never ran. `#177`'s
banner named the field verbatim:

    results.0.ref_high_exclusive: Input should be a valid boolean

These tests drive the ROUTE over a standalone app (the `test_hevy_sync_wiring` /
`_boom_app` precedent) rather than calling `confirm_lab_report` directly, and that choice
is the whole point: the 422 was raised by Pydantic BEFORE the handler, so a test that
called the handler object would construct `ResultItem` in Python, skip request validation
entirely, and pass against the broken code. Fake below the defect, never at it
(`FEEDBACK` §23).

The body reproduces the captured report's SHAPE — three unmapped urine-ACR markers, the
lead row ref-less. It is a faithful reconstruction from the report and the captured
`loc`, not a byte-copy of the live payload.
"""
import models
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from auth import get_current_user
from database import get_db
from routers import labs

COLLECTED = "2026-08-04T08:35:00+10:00"


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(labs.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _user(db, email="refless@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _body():
    """The captured shape. `results[0]` carries the null that caused the 422 — it is the
    fixture's reason for existing, so it is written as a literal `None`, not omitted."""
    return {
        "report": {
            "lab_name": "Sullivan Nicolaides Pathology",
            "lab_provider_group": "Sonic Healthcare",
            "panel_name_raw": "Albumin/Creat Ratio",
            "dates": {"collected": COLLECTED},
            "source_completeness": "sonic_dx_extract",
            "extraction": {"extracted_at": COLLECTED, "model": "test"},
        },
        "results": [
            {
                # No reference interval on the report — printed as an em-dash, and sited
                # above the results table. Nothing for the flags to be exclusive about.
                "marker_name_raw": "R U-Creatinine",
                "value_raw": "8.6",
                "value_num": 8.6,
                "unit_raw": "mmol/L",
                "unit_canonical": "mmol/L",
                "ref_low": None,
                "ref_high": None,
                "ref_low_exclusive": None,   # <-- the defect
                "ref_high_exclusive": None,  # <-- the defect (the one the banner named)
                "ref_raw": "—",
                "lab_flag": None,
                "computed_flag": None,
                "field_confidence": {"name": 0.98, "value": 0.97, "unit": 0.97, "ref": 0.95},
            },
            {
                "marker_name_raw": "R U-Albumin",
                "value_raw": "<5",
                "value_num": 5.0,
                "value_operator": "<",
                "unit_raw": "mg/L",
                "unit_canonical": "mg/L",
                "ref_low": None,
                "ref_high": None,
                "ref_low_exclusive": None,
                "ref_high_exclusive": None,
                "ref_raw": "—",
                "field_confidence": {"name": 0.98, "value": 0.96, "unit": 0.97, "ref": 0.95},
            },
            {
                "marker_name_raw": "R U-Albumin/Creat",
                "value_raw": "0.6",
                "value_num": 0.6,
                "unit_raw": "mg/mmol",
                "unit_canonical": "mg/mmol",
                "ref_low": None,
                "ref_high": 3.5,
                "ref_high_exclusive": False,
                "ref_low_exclusive": None,
                "ref_raw": "<3.5",
                "field_confidence": {"name": 0.97, "value": 0.98, "unit": 0.96, "ref": 0.96},
            },
        ],
    }


@pytest.fixture()
def saved(db_session):
    """POST the captured body once; every assertion below reads this one result."""
    user = _user(db_session)
    res = _client(db_session, user).post("/labs/confirm", json=_body())
    return res, db_session, user


def test_the_report_saves_201(saved):
    """The cure. Was 422 with a list-form detail naming results.0.ref_high_exclusive."""
    res, _, _ = saved
    assert res.status_code == 201, res.text


def test_three_rows_written_all_unmapped(saved):
    """Unmapped is a response signal (#58), never a failure — urine ACR is not in the
    canonical map and cataloguing it is a separate track. All three rows still persist."""
    res, _, _ = saved
    body = res.json()
    assert body["result_count"] == 3
    assert sorted(body["unmapped"]) == ["R U-Albumin", "R U-Albumin/Creat", "R U-Creatinine"]
    assert body["duplicates"] == []


def test_refless_row_stored_with_false_not_null(saved):
    """The acceptance gate: the ref-less lead row lands with non-null `False` flags,
    matching the column's own `nullable=False, server_default=false`."""
    res, db, user = saved
    row = (
        db.query(models.LabResult)
        .filter_by(lab_report_id=res.json()["lab_report_id"], marker_name_raw="R U-Creatinine")
        .one()
    )
    assert row.ref_low is None
    assert row.ref_high is None
    assert row.ref_low_exclusive is False
    assert row.ref_high_exclusive is False
    assert row.computed_flag is None
    assert row.value_num == 8.6


def test_a_real_exclusive_bound_on_the_same_report_is_not_flattened(saved):
    """`R U-Albumin/Creat` carries a genuine `<3.5` ceiling. The coercion must touch only
    the null flags on the sparse rows and leave a real bound's semantics intact — a
    regression here would silently widen every reference interval in the corpus."""
    res, db, _ = saved
    row = (
        db.query(models.LabResult)
        .filter_by(lab_report_id=res.json()["lab_report_id"], marker_name_raw="R U-Albumin/Creat")
        .one()
    )
    assert row.ref_high == 3.5
    assert row.ref_high_exclusive is False   # as sent
    assert row.ref_low_exclusive is False    # coerced from null


def test_report_is_not_marked_zero_row(saved):
    """`zero_row_reason` must stay null: three rows landed, so neither the
    all-declined nor the nothing-extractable fault applies."""
    res, db, _ = saved
    report = db.get(models.LabReport, res.json()["lab_report_id"])
    assert report.zero_row_reason is None
