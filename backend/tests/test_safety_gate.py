"""Gate 3 (safety_gate) and the second arm of gate 1.

The live asset has no entries, so every test here supplies a SYNTHETIC `thresholds`
dict. That is deliberate: a suite pointed only at the live asset would exercise the
`no_asset` path and nothing else, and would pass while the resolution order, the band
selection and every band_change value went unverified.

The news_gate arm tests matter most. The three existing exact-dict asserts on news_gate
(`fsh`, `ast`, `vitamin_d` in test_interpretation_producer_foundation) currently pass
WITHOUT exercising the safety arm at all -- with no live asset, band_change is always
null and `basis` is never touched. They are inert with respect to the thing they would
protect, which is the FEEDBACK 11 shape. The tests below can fail today.
"""
from __future__ import annotations

from datetime import date

import pytest

from interpretation.gates import news_gate, safety_gate
from reads.labs_reads import LabRow

BANDS = [
    {"band_key": "watch", "value": 0.50, "grade": "low",
     "evidence_refs": ["10.0000/a"], "note": "n"},
    {"band_key": "elevated", "value": 0.52, "grade": "moderate",
     "evidence_refs": ["10.0000/b"], "note": "n"},
    {"band_key": "high", "value": 0.54, "grade": "moderate",
     "evidence_refs": ["10.0000/c"], "note": "n"},
]

ASSET = {"thresholds": {"haematocrit": {
    "direction": "above",
    "value_plausibility": [0.20, 0.70],
    "contested": True,
    "bands": BANDS,
}}}


def _row(value, *, marker="haematocrit", unit=None, operator=None):
    return LabRow(
        marker_name_raw="Haematocrit", marker_canonical=marker, value_num=value,
        value_operator=operator, value_qualitative=None, unit_canonical=unit,
        ref_low=None, ref_high=None, ref_low_exclusive=False, ref_high_exclusive=False,
        lab_flag=None, computed_flag=None, is_derived=False,
        collected_date=date(2026, 7, 1),
    )


# ---------- undecidable paths ----------

def test_no_asset_entry():
    g = safety_gate(_row(0.55, marker="ferritin"), None, thresholds=ASSET)
    assert g["status"] is None and g["undecidable_reason"] == "no_asset"


def test_no_value():
    g = safety_gate(_row(None), None, thresholds=ASSET)
    assert g["status"] is None and g["undecidable_reason"] == "no_value"


def test_unit_mismatch_when_unit_is_established():
    """Uses `ferritin`, which HAS an established unit in marker_canonical."""
    asset = {"thresholds": {"ferritin": {"direction": "above", "bands": [
        {"band_key": "high", "value": 300, "grade": "low", "evidence_refs": ["x"]}]}}}
    g = safety_gate(_row(400, marker="ferritin", unit="mg/L"), None, thresholds=asset)
    assert g["status"] is None and g["undecidable_reason"] == "unit_mismatch"


def test_matching_unit_is_not_a_mismatch():
    """Control for the above: same marker and asset, correct unit, decides."""
    asset = {"thresholds": {"ferritin": {"direction": "above", "bands": [
        {"band_key": "high", "value": 300, "grade": "low", "evidence_refs": ["x"]}]}}}
    g = safety_gate(_row(400, marker="ferritin", unit="ug/L"), None, thresholds=asset)
    assert g["status"] == "in_band" and g["band_key"] == "high"


def test_implausible_value_when_unit_is_null():
    """haematocrit has unit_established null, so plausibility is the only guard.
    7.0 is a percent-scale value in a fraction-scale asset."""
    g = safety_gate(_row(7.0), None, thresholds=ASSET)
    assert g["status"] is None and g["undecidable_reason"] == "implausible_value"


def test_plausible_value_is_not_rejected():
    """Control: proves the rejection is about the window, not about the null unit."""
    g = safety_gate(_row(0.55), None, thresholds=ASSET)
    assert g["status"] == "in_band"


# ---------- band selection ----------

@pytest.mark.parametrize("value,expected", [
    (0.49, None), (0.50, "watch"), (0.51, "watch"),
    (0.52, "elevated"), (0.53, "elevated"), (0.54, "high"), (0.60, "high"),
])
def test_highest_breached_band_wins(value, expected):
    g = safety_gate(_row(value), None, thresholds=ASSET)
    assert g["band_key"] == expected
    assert g["status"] == ("in_band" if expected else "not_in_band")


def test_band_carries_its_own_evidence_and_contested_flag():
    g = safety_gate(_row(0.53), None, thresholds=ASSET)
    assert g["evidence_refs"] == ["10.0000/b"]
    assert g["threshold_value"] == 0.52
    assert g["contested"] is True
    assert g["direction"] == "above"


def test_direction_below_selects_the_lowest_breached_band():
    asset = {"thresholds": {"haematocrit": {
        "direction": "below", "value_plausibility": [0.10, 0.70], "bands": [
            {"band_key": "low", "value": 0.40, "grade": "low", "evidence_refs": ["x"]},
            {"band_key": "very_low", "value": 0.35, "grade": "moderate", "evidence_refs": ["y"]},
        ]}}}
    assert safety_gate(_row(0.36), None, thresholds=asset)["band_key"] == "low"
    assert safety_gate(_row(0.34), None, thresholds=asset)["band_key"] == "very_low"


# ---------- censoring ----------

def test_censored_agreeing_operator_past_a_band_is_decidable():
    """'>0.55' with direction above: the true value is at least 0.55, so the 0.54
    band is cleared whatever the real number is. Censoring destroys a magnitude,
    not necessarily a threshold comparison."""
    g = safety_gate(_row(0.55, operator=">"), None, thresholds=ASSET)
    assert g["status"] == "in_band" and g["band_key"] == "high"


def test_censored_agreeing_operator_below_all_bands_is_indeterminate():
    """'>0.30' is NOT 'not in band' -- the true value is unbounded above and could
    sit in any band. Reporting not_in_band would be a false negative on a safety
    gate, the one direction never to be wrong in."""
    g = safety_gate(_row(0.30, operator=">"), None, thresholds=ASSET)
    assert g["status"] is None and g["undecidable_reason"] == "censored_indeterminate"


def test_censored_opposing_operator_is_indeterminate():
    g = safety_gate(_row(0.45, operator="<"), None, thresholds=ASSET)
    assert g["status"] is None and g["undecidable_reason"] == "censored_indeterminate"


def test_uncensored_control_for_the_same_value():
    """Pairs with both censored tests: 0.45 uncensored decides cleanly, so the
    indeterminate verdicts above are about the operator, not the value."""
    assert safety_gate(_row(0.45), None, thresholds=ASSET)["status"] == "not_in_band"


# ---------- band_change ----------

def test_first_observation_in_band_when_no_prior():
    g = safety_gate(_row(0.53), None, thresholds=ASSET)
    assert g["band_change"] == "first_observation_in_band"


def test_first_observation_in_band_when_prior_undecidable():
    g = safety_gate(_row(0.53), _row(None), thresholds=ASSET)
    assert g["band_change"] == "first_observation_in_band"


def test_entered():
    g = safety_gate(_row(0.51), _row(0.48), thresholds=ASSET)
    assert g["band_change"] == "entered" and g["band_key"] == "watch"


def test_escalated():
    g = safety_gate(_row(0.53), _row(0.51), thresholds=ASSET)
    assert g["band_change"] == "escalated"


def test_de_escalated():
    g = safety_gate(_row(0.51), _row(0.55), thresholds=ASSET)
    assert g["band_change"] == "de_escalated"


def test_exited():
    g = safety_gate(_row(0.48), _row(0.53), thresholds=ASSET)
    assert g["band_change"] == "exited" and g["status"] == "not_in_band"


def test_no_band_change_when_both_out():
    g = safety_gate(_row(0.48), _row(0.47), thresholds=ASSET)
    assert g["band_change"] is None and g["status"] == "not_in_band"


def test_no_band_change_when_band_is_unchanged():
    """The level gate fires on a LEVEL, so status stays in_band; but band_change is
    null because nothing transitioned. This is the pair that keeps a persistently
    elevated value surfacing via should_surface without re-reporting it as news."""
    g = safety_gate(_row(0.53), _row(0.525), thresholds=ASSET)
    assert g["status"] == "in_band" and g["band_change"] is None


# ---------- news_gate: the second arm ----------

def test_news_gate_unchanged_when_safety_gate_omitted():
    d = {"crossed_ref": None, "magnitude": "within_noise", "direction": "flat"}
    assert news_gate(d) == {"is_news": False, "basis": ["flat_vs_prior"]}


def test_news_gate_unchanged_when_band_change_is_null():
    d = {"crossed_ref": None, "magnitude": "within_noise", "direction": "flat"}
    g = safety_gate(_row(0.53), _row(0.525), thresholds=ASSET)   # in_band, no change
    assert news_gate(d, safety_gate=g) == {"is_news": False, "basis": ["flat_vs_prior"]}


def test_news_gate_shape_is_exactly_two_keys_when_the_safety_arm_fires():
    """The added guard. Three existing tests pin news_gate's dict whole, but with no
    live asset they never exercise this path -- they would notice a sibling key only
    once an asset lands. This fails TODAY if the arm is added as a key instead of a
    basis entry."""
    d = {"crossed_ref": None, "magnitude": "within_noise", "direction": "flat"}
    g = safety_gate(_row(0.53), _row(0.48), thresholds=ASSET)     # entered
    out = news_gate(d, safety_gate=g)

    assert set(out.keys()) == {"is_news", "basis"}, \
        f"news_gate must return exactly is_news+basis; got {sorted(out)}"
    assert out["is_news"] is True
    assert "safety_band_entered" in out["basis"], "must append to basis"
    assert "safety_band_entered" not in out, "must NOT be a sibling key"
    assert out["basis"][0] == "flat_vs_prior", "delta basis is preserved, not replaced"


@pytest.mark.parametrize("change,prior", [
    ("first_observation_in_band", None),
    ("entered", 0.48),
    ("escalated", 0.51),
    ("de_escalated", 0.55),
    ("exited", 0.53),
])
def test_every_band_change_forces_news_and_names_itself(change, prior):
    cur = 0.48 if change == "exited" else (0.53 if change != "de_escalated" else 0.51)
    d = {"crossed_ref": None, "magnitude": "within_noise", "direction": "flat"}
    g = safety_gate(_row(cur), _row(prior) if prior is not None else None, thresholds=ASSET)
    assert g["band_change"] == change
    out = news_gate(d, safety_gate=g)
    assert out["is_news"] is True
    assert f"safety_band_{change}" in out["basis"]
    assert set(out.keys()) == {"is_news", "basis"}


def test_safety_arm_fires_on_a_first_observation_where_the_delta_arm_cannot():
    """delta_obj None is 'not news' on the delta arm. A band change overrides that:
    a first-ever draw sitting at 0.53 must surface."""
    g = safety_gate(_row(0.53), None, thresholds=ASSET)
    out = news_gate(None, safety_gate=g)
    assert out == {"is_news": True,
                   "basis": ["no_prior_first_observation", "safety_band_first_observation_in_band"]}
