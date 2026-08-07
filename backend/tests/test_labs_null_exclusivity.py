"""A ref-less row may null the exclusivity bools; the contract coerces them to False.

The `R U-Creatinine` row on the SNP Albumin/Creat Ratio report (collected 2026-08-04)
has no reference interval — printed `—`, above the results table. The extractor emitted
`ref_high_exclusive: null` for it, and `ResultItem` declared a bare `bool`, so Pydantic
refused the body BEFORE `confirm_lab_report` ran. `#177`'s banner named the field
verbatim: `results.0.ref_high_exclusive: Input should be a valid boolean`.

The fix coerces rather than loosens: the field stays strictly `bool`, matching the
non-nullable column, so no migration is needed and nothing downstream sees `None`.

These tests exercise the VALIDATOR, which is where the 422 was raised — one layer below
the handler, per `FEEDBACK` §23's fake-below-the-defect rule. A test that built
`ResultItem` with `ref_high_exclusive=False` in Python would never touch the coercion
and would have passed against the broken code, so every case here goes through
`model_validate` on a raw dict, the way a request body actually arrives.
"""
import pytest
from pydantic import ValidationError

from routers.labs import ResultItem


def _row(**over):
    """The captured shape: a ref-less row. `ref_raw` is the em-dash the lab printed."""
    base = {
        "marker_name_raw": "R U-Creatinine",
        "value_num": 8.6,
        "unit_canonical": "mmol/L",
        "ref_low": None,
        "ref_high": None,
        "ref_raw": "—",
    }
    base.update(over)
    return base


# ---------- the captured failure ----------

def test_null_ref_high_exclusive_coerces_to_false():
    """The exact field the banner named. Was a 422; must now validate as False."""
    row = ResultItem.model_validate(_row(ref_high_exclusive=None))
    assert row.ref_high_exclusive is False


def test_null_ref_low_exclusive_coerces_to_false():
    """The flag the capture did NOT name. Covered deliberately: which side the model
    nulls is nondeterministic, and fixing only the observed one re-opens this on the
    next report shape (a `>x` floor-only row leaves the ceiling absent instead)."""
    row = ResultItem.model_validate(_row(ref_low_exclusive=None))
    assert row.ref_low_exclusive is False


def test_both_flags_null_together():
    """An absent-ref row has no bound on either side, so the model may null both."""
    row = ResultItem.model_validate(_row(ref_low_exclusive=None, ref_high_exclusive=None))
    assert row.ref_low_exclusive is False
    assert row.ref_high_exclusive is False


# ---------- what must NOT change ----------

@pytest.mark.parametrize("low,high", [(True, True), (True, False), (False, True), (False, False)])
def test_wellformed_booleans_pass_through_unchanged(low, high):
    """The coercion touches null and nothing else — a genuine `true` stays true.
    `<x` (ref_high_exclusive=true) and `>x` (ref_low_exclusive=true) are real, common
    rows, and silently flattening either to False would corrupt the interval."""
    row = ResultItem.model_validate(_row(ref_low_exclusive=low, ref_high_exclusive=high))
    assert row.ref_low_exclusive is low
    assert row.ref_high_exclusive is high


def test_absent_flags_still_default_to_false():
    """Omitted is not the same as null, and the pre-existing default must survive the
    validator being added — `mode="before"` runs on provided values, so this asserts the
    field default was not disturbed."""
    row = ResultItem.model_validate(_row())
    assert row.ref_low_exclusive is False
    assert row.ref_high_exclusive is False


def test_a_genuinely_invalid_value_is_still_refused():
    """The contract is coerced on null ONLY — it is not loosened into accepting
    anything. A string that is not boolean-ish must still fail closed, or this fix would
    have traded a legible 422 for silent data corruption."""
    with pytest.raises(ValidationError) as exc:
        ResultItem.model_validate(_row(ref_high_exclusive="not-a-bool"))
    assert "ref_high_exclusive" in str(exc.value)


# ---------- the class, not just the field ----------

def test_no_other_resultitem_field_can_be_nulled_into_a_422():
    """`ResultItem` is the per-row surface a sparse document hits, so its non-Optional
    scalars are the fail-closed points. After this fix the only one left is
    `marker_name_raw`, which is always present on a row that exists at all — a row
    without a name is not a row.

    This asserts the CLASS is closed at this level rather than trusting that it is, so a
    future field added as a bare scalar trips here instead of in production on whatever
    sparse shape finds it first. NOTE the deliberate limit: `field_confidence`'s four
    floats are non-Optional too, but they live on `FieldConfidence`, they validated on
    this report, and they are left alone per this change's scope — see the decision entry
    and `OPEN_QUESTIONS`.
    """
    nullable_ok = set()
    for name, field in ResultItem.model_fields.items():
        probe = _row(**{name: None})
        try:
            ResultItem.model_validate(probe)
            nullable_ok.add(name)
        except ValidationError:
            pass

    refuses_null = set(ResultItem.model_fields) - nullable_ok
    assert refuses_null == {"marker_name_raw"}, (
        f"unexpected fail-closed-on-null fields: {sorted(refuses_null)}"
    )
