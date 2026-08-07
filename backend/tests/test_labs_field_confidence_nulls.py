"""A not-expressed field confidence is null, and nothing downstream may read it as zero.

The last unpatched instance of the `#177`/`#178` null-on-sparse-row family.
`FieldConfidence` declared four bare `float`s, so a row for which the model emitted
`ref: null` — the honest answer when the report prints no reference interval — was
refused by request validation before `confirm_lab_report` ran, exactly as
`ref_high_exclusive` was in `#178`.

Unlike `#178` this ships WITHOUT a captured production 422. The pattern is the one
already proven twice; what is new is only which field it lands on. The trigger shape
(a ref-less row) demonstrably exists in the corpus — it is the same `R U-Creatinine`
row — and whether the extractor scores a `ref` it never read is nondeterministic.

Loosening alone would have RELOCATED the failure rather than fixed it, so the arms are
tested together:
  * contract      — `float | None`, so the body validates at all
  * derivation    — `min()` over a None-bearing list raises TypeError -> 500
  * (frontend)    — `null < 0.85` is true in JS -> false "suspect"  [see frontend suite]

The route-level cases drive HTTP, not the handler: the 422 lives in request validation,
so a test constructing `ResultItem` in Python would skip the defect entirely
(`FEEDBACK` §23 — fake below the defect, never at it).
"""
from datetime import datetime

import models
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from starlette.testclient import TestClient

from auth import get_current_user
from database import get_db
from routers import labs
from routers.labs import (
    ExtractionResult, FieldConfidence, ReportDates, ReportEnvelope,
    ReportExtractionMeta, ResultItem, confirm_lab_report,
)

COLLECTED = datetime(2026, 8, 4, 8, 35, 0)
COLLECTED_ISO = "2026-08-04T08:35:00+10:00"


def _user(db, email="fc@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ---------- arm 1: the contract ----------

def test_null_ref_confidence_validates():
    """The ref-less row's honest output. Was a 422 naming field_confidence.ref."""
    fc = FieldConfidence.model_validate({"name": 0.99, "value": 0.98, "unit": 0.97, "ref": None})
    assert fc.ref is None
    assert fc.name == 0.99


def test_omitted_subfield_validates():
    """Omitting the key is as legitimate as sending null, and must not be a 422 either."""
    fc = FieldConfidence.model_validate({"name": 0.99, "value": 0.98, "unit": 0.97})
    assert fc.ref is None


def test_all_four_null_validates():
    fc = FieldConfidence.model_validate({"name": None, "value": None, "unit": None, "ref": None})
    assert (fc.name, fc.value, fc.unit, fc.ref) == (None, None, None, None)


def test_all_four_present_is_unchanged():
    """The overwhelmingly common case must be untouched by the loosening."""
    fc = FieldConfidence.model_validate({"name": 0.99, "value": 0.98, "unit": 0.97, "ref": 0.96})
    assert (fc.name, fc.value, fc.unit, fc.ref) == (0.99, 0.98, 0.97, 0.96)


def test_a_non_numeric_confidence_is_still_refused():
    """Loosened to accept null, NOT loosened into accepting anything. Trading a legible
    422 for silent corruption would be a worse outcome than the bug."""
    with pytest.raises(ValidationError):
        FieldConfidence.model_validate({"name": "high", "value": 0.98, "unit": 0.97, "ref": 0.96})


# ---------- arm 2: the derivation ----------

def _envelope(results):
    return ExtractionResult(
        report=ReportEnvelope(
            lab_name="Sullivan Nicolaides",
            panel_name_raw="Albumin/Creat Ratio",
            dates=ReportDates(collected=COLLECTED),
            source_completeness="sonic_dx_extract",
            extraction=ReportExtractionMeta(extracted_at=COLLECTED, model="test"),
        ),
        results=results,
    )


def _row(name, fc):
    return ResultItem(marker_name_raw=name, value_num=1.0, unit_canonical="U/L",
                      field_confidence=FieldConfidence(**fc) if fc is not None else None)


def _confirm(db, user, results):
    return confirm_lab_report(body=_envelope(results), current_user=user, db=db)


def test_derivation_ignores_null_and_mins_over_expressed(db_session):
    """`min()` over a list mixing float and None raises TypeError — a 500, one layer
    DEEPER than the 422 this change removes. The filter is what stops the loosening
    from merely relocating the failure."""
    user = _user(db_session, "derive-null@example.com")
    res = _confirm(db_session, user, [_row("AST", {"name": 0.99, "value": 0.92, "unit": 0.97, "ref": None})])

    report = db_session.get(models.LabReport, res.lab_report_id)
    assert report.overall_confidence == pytest.approx(0.92)   # min over the three expressed


def test_all_null_confidence_scores_the_same_as_an_absent_object(db_session):
    """Both mean "no confidence was expressed" and must not score differently — an
    all-null object falling to 0.0 would resurrect exactly #146's ambiguity, where a
    silent default was indistinguishable from a genuine zero."""
    user = _user(db_session, "derive-allnull@example.com")

    all_null = _confirm(db_session, user, [_row("AST", {"name": None, "value": None, "unit": None, "ref": None})])
    absent = _confirm(db_session, _user(db_session, "derive-absent@example.com"), [_row("ALT", None)])

    assert db_session.get(models.LabReport, all_null.lab_report_id).overall_confidence == 1.0
    assert db_session.get(models.LabReport, absent.lab_report_id).overall_confidence == 1.0


def test_worst_expressed_row_still_propagates(db_session):
    """§6's rule is unchanged: overall is the min across rows, so one bad row cannot
    hide behind a good one — including when the bad row also carries a null."""
    user = _user(db_session, "derive-multi@example.com")
    res = _confirm(db_session, user, [
        _row("AST", {"name": 0.99, "value": 0.99, "unit": 0.98, "ref": 0.97}),
        _row("ALT", {"name": 0.99, "value": 0.61, "unit": 0.98, "ref": None}),
    ])

    assert db_session.get(models.LabReport, res.lab_report_id).overall_confidence == pytest.approx(0.61)


# ---------- route level: the failure actually being removed ----------

def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(labs.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _body(fc):
    return {
        "report": {
            "lab_name": "Sullivan Nicolaides Pathology",
            "panel_name_raw": "Albumin/Creat Ratio",
            "dates": {"collected": COLLECTED_ISO},
            "source_completeness": "sonic_dx_extract",
            "extraction": {"extracted_at": COLLECTED_ISO, "model": "test"},
        },
        "results": [{
            "marker_name_raw": "R U-Creatinine",
            "value_num": 8.6,
            "unit_canonical": "mmol/L",
            "ref_low": None,
            "ref_high": None,
            "ref_raw": "—",
            "field_confidence": fc,
        }],
    }


def test_route_accepts_a_null_ref_confidence(db_session):
    """The whole point: 201, not 422 (contract) and not 500 (derivation)."""
    user = _user(db_session, "route-null@example.com")
    res = _client(db_session, user).post(
        "/labs/confirm", json=_body({"name": 0.98, "value": 0.97, "unit": 0.97, "ref": None}))

    assert res.status_code == 201, res.text
    assert res.json()["result_count"] == 1


def test_route_stores_the_derived_confidence_not_a_zero(db_session):
    """A null sub-field must not drag the stored row confidence to 0 — that is the
    silent-corruption version of this bug, and it would look like a successful save."""
    user = _user(db_session, "route-stored@example.com")
    res = _client(db_session, user).post(
        "/labs/confirm", json=_body({"name": 0.98, "value": 0.97, "unit": 0.97, "ref": None}))

    row = db_session.query(models.LabResult).filter_by(
        lab_report_id=res.json()["lab_report_id"]).one()
    assert row.confidence == pytest.approx(0.97)


def test_route_accepts_an_omitted_subfield(db_session):
    user = _user(db_session, "route-omit@example.com")
    res = _client(db_session, user).post(
        "/labs/confirm", json=_body({"name": 0.98, "value": 0.97, "unit": 0.97}))

    assert res.status_code == 201, res.text


# ---------- the class ----------

def test_no_remaining_row_level_scalar_fails_closed_on_null():
    """The claim `#179` makes, asserted rather than trusted: after this change no
    row-level non-Optional scalar can be nulled into a 422 except `marker_name_raw`,
    which is always present on a row that exists at all.

    Scope is deliberate. This covers ROW-level fields — `ResultItem` and its nested
    `FieldConfidence`. It does NOT cover the report-level required scalars
    (`lab_name`, `panel_name_raw`, `source_completeness`), which stay fail-closed on
    purpose: a report missing its lab name is a genuine extraction fault to surface,
    not a sparse row to tolerate. See `#179` and `Q86`.
    """
    fc_nullable = set()
    for fname in FieldConfidence.model_fields:
        try:
            FieldConfidence.model_validate({fname: None})
            fc_nullable.add(fname)
        except ValidationError:
            pass
    assert fc_nullable == set(FieldConfidence.model_fields), (
        f"FieldConfidence still fails closed on: "
        f"{sorted(set(FieldConfidence.model_fields) - fc_nullable)}"
    )

    base = {"marker_name_raw": "X"}
    ri_nullable = set()
    for fname in ResultItem.model_fields:
        try:
            ResultItem.model_validate({**base, fname: None})
            ri_nullable.add(fname)
        except ValidationError:
            pass
    assert set(ResultItem.model_fields) - ri_nullable == {"marker_name_raw"}
