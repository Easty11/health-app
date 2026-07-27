"""Schema guard for backend/reference/safety_thresholds.json.

The asset carries POLICY constants, not measured ones, and the rule that matters most is
negative: a band names a level and its sources and NEVER names an action. That is enforced
here rather than by care, because the failure is silent in the direction that does harm --
a `recommended_action` key would read as helpful and cross the line the platform does not
cross.

Every rule below is exercised against a SYNTHETIC violation as well as the live asset.
A schema test run only against an asset with zero live entries passes vacuously: it would
report green while validating nothing, which is the shape FEEDBACK 11 and 17 name. The
synthetic cases are what make the green mean something today.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from interpretation.gates import news_gate, safety_gate
from reads.labs_reads import LabRow

ASSET = Path(__file__).resolve().parent.parent / "reference" / "safety_thresholds.json"
MARKER_CANONICAL = Path(__file__).resolve().parent.parent / "reference" / "marker_canonical.json"

BAND_FIELDS = {"band_key", "value", "grade", "evidence_refs", "note"}
DIRECTIONS = {"above", "below"}
GRADES = {"low", "moderate", "high"}


class SchemaError(AssertionError):
    """Raised by validate(). A distinct type so the negative controls assert on the
    failure they intend, not on any AssertionError the test itself might raise."""


def _unit_established() -> dict[str, object]:
    entries = json.loads(MARKER_CANONICAL.read_text(encoding="utf-8"))["entries"]
    return {e["marker_canonical"]: e.get("unit_established") for e in entries}


def validate(asset: dict, units: dict | None = None) -> int:
    """Validate the live `thresholds` block. Returns the number of live bands checked,
    so a caller can distinguish 'valid' from 'nothing was looked at'."""
    units = units if units is not None else _unit_established()
    checked = 0

    for marker, entry in asset.get("thresholds", {}).items():
        if entry.get("direction") not in DIRECTIONS:
            raise SchemaError(f"{marker}: direction must be one of {sorted(DIRECTIONS)}")

        # A marker with no established unit cannot be unit-checked, so it must declare a
        # plausibility window instead. Without one, an implausible value is undetectable.
        if units.get(marker, "__missing__") is None and "value_plausibility" not in entry:
            raise SchemaError(
                f"{marker}: unit_established is null, so value_plausibility is required"
            )

        bands = entry.get("bands", [])
        if not bands:
            raise SchemaError(f"{marker}: a live entry must carry at least one band")

        for band in bands:
            extra = set(band) - BAND_FIELDS
            if extra:
                raise SchemaError(
                    f"{marker}.{band.get('band_key')}: forbidden key(s) {sorted(extra)}. "
                    f"A band names a level and its sources, never an action."
                )
            missing = {"band_key", "value", "grade", "evidence_refs"} - set(band)
            if missing:
                raise SchemaError(f"{marker}: band missing {sorted(missing)}")
            if band["grade"] not in GRADES:
                raise SchemaError(f"{marker}.{band['band_key']}: grade must be in {sorted(GRADES)}")
            if not band["evidence_refs"]:
                raise SchemaError(
                    f"{marker}.{band['band_key']}: empty evidence_refs violates I1 (#95). "
                    f"Uncited bands stay in _deferred."
                )
            checked += 1

    return checked


# --------------------------------------------------------------------------------------
# The live asset
# --------------------------------------------------------------------------------------

def test_asset_parses_and_is_pure_ascii():
    raw = ASSET.read_text(encoding="utf-8")
    assert raw.isascii(), "safety_thresholds.json must be pure ASCII (#98 guard)"
    assert raw.count(chr(0x2014)) == 0, "literal em dash present; use the escaped form"
    json.loads(raw)


def test_live_asset_validates():
    asset = json.loads(ASSET.read_text(encoding="utf-8"))
    checked = validate(asset)
    # The live asset now carries the three haematocrit bands. validate() walks every band
    # and raises on any I1 / schema violation, so the count is what confirms it looked:
    # three validated, none rejected. The synthetic controls below still carry the negative
    # cases (an uncited or action-bearing band) the live asset must never contain.
    assert checked == 3, "expected exactly the three live haematocrit bands to validate"


def test_haematocrit_is_live_and_no_longer_deferred():
    asset = json.loads(ASSET.read_text(encoding="utf-8"))
    hct = asset["thresholds"]["haematocrit"]
    assert hct["direction"] == "above"
    assert "value_plausibility" in hct, "null unit_established requires a plausibility window"
    assert hct["contested"] is True
    assert [b["value"] for b in hct["bands"]] == [0.50, 0.52, 0.54]
    ref_sets = [tuple(b["evidence_refs"]) for b in hct["bands"]]
    assert all(ref_sets), "a live band must carry non-empty evidence_refs (I1)"
    assert len(set(ref_sets)) == 3, "each band rests on its own citation, not a shared one"
    assert "haematocrit" not in asset.get("_deferred", {}), "promoted, not duplicated"


def test_deferred_is_now_empty_and_outside_validate():
    """_deferred held only haematocrit; promoted, it is empty. validate() reads solely
    `thresholds`, so nothing parked in _deferred could ever gate."""
    asset = json.loads(ASSET.read_text(encoding="utf-8"))
    assert asset.get("_deferred", {}) == {}


# --------------------------------------------------------------------------------------
# Negative controls -- each must RAISE. These are what make the green above meaningful.
# --------------------------------------------------------------------------------------

def _live(**band_overrides) -> dict:
    band = {"band_key": "watch", "value": 0.50, "grade": "low",
            "evidence_refs": ["10.0000/placeholder"], "note": "n"}
    band.update(band_overrides)
    return {"thresholds": {"haematocrit": {
        "direction": "above", "value_plausibility": [0.2, 0.7], "bands": [band]}}}


def test_control_a_valid_synthetic_entry_passes():
    """Positive control: the validator accepts a well-formed live entry. Without this,
    every raise below could be the validator rejecting everything."""
    assert validate(_live(), units={"haematocrit": None}) == 1


def test_recommended_action_is_rejected():
    with pytest.raises(SchemaError, match="never an action"):
        validate(_live(recommended_action="reduce dose"), units={"haematocrit": None})


@pytest.mark.parametrize("key", ["intervention", "action", "advice", "do"])
def test_any_imperative_field_is_rejected(key):
    with pytest.raises(SchemaError, match="forbidden key"):
        validate(_live(**{key: "x"}), units={"haematocrit": None})


def test_empty_evidence_refs_is_rejected():
    with pytest.raises(SchemaError, match="I1"):
        validate(_live(evidence_refs=[]), units={"haematocrit": None})


def test_null_unit_without_plausibility_is_rejected():
    asset = _live()
    del asset["thresholds"]["haematocrit"]["value_plausibility"]
    with pytest.raises(SchemaError, match="value_plausibility is required"):
        validate(asset, units={"haematocrit": None})


def test_null_unit_with_plausibility_is_accepted():
    """Paired with the above: proves the rejection is about the missing window, not about
    the null unit itself."""
    assert validate(_live(), units={"haematocrit": None}) == 1


def test_bad_direction_is_rejected():
    asset = _live()
    asset["thresholds"]["haematocrit"]["direction"] = "sideways"
    with pytest.raises(SchemaError, match="direction"):
        validate(asset, units={"haematocrit": None})


def test_bad_grade_is_rejected():
    with pytest.raises(SchemaError, match="grade"):
        validate(_live(grade="catastrophic"), units={"haematocrit": None})


def test_live_entry_without_bands_is_rejected():
    asset = _live()
    asset["thresholds"]["haematocrit"]["bands"] = []
    with pytest.raises(SchemaError, match="at least one band"):
        validate(asset, units={"haematocrit": None})


# --------------------------------------------------------------------------------------
# The gate fires (S2) -- safety_gate against the LIVE asset, not a synthetic one.
# --------------------------------------------------------------------------------------

def _hct_row(value, *, marker="haematocrit", unit=None):
    return LabRow(
        marker_name_raw="Haematocrit", marker_canonical=marker, value_num=value,
        value_operator=None, value_qualitative=None, unit_canonical=unit,
        ref_low=None, ref_high=None, ref_low_exclusive=False, ref_high_exclusive=False,
        lab_flag=None, computed_flag=None, is_derived=False, collected_date=date(2026, 7, 1),
    )


def test_live_safety_gate_fires_for_haematocrit():
    """Gate 3 against the LIVE asset (no synthetic thresholds passed): a haematocrit at
    0.53 resolves in the cited 'elevated' band. This is the capability the citations
    unlock -- before this branch safety_gate returned no_asset for every marker."""
    g = safety_gate(_hct_row(0.53), None)
    assert g["undecidable_reason"] is None
    assert g["status"] == "in_band"
    assert g["band_key"] == "elevated"
    assert g["threshold_value"] == 0.52
    assert g["evidence_refs"] == ["10.1097/JU.0000000000002437"]


def test_live_safety_gate_is_no_asset_for_an_unbanded_marker():
    """Negative control: a marker with no authored band still resolves no_asset against
    the live asset. Without it, the positive above proves only that something returned."""
    g = safety_gate(_hct_row(400, marker="ferritin", unit="ug/L"), None)
    assert g["status"] is None
    assert g["undecidable_reason"] == "no_asset"


def test_live_gate1_safety_arm_fires_on_first_observation():
    """S2's question, answered: with the band populated, gate 1's safety arm fires on a
    first-ever haematocrit in band -- band_change is first_observation_in_band, so it does
    NOT wait for a prior. The delta arm alone is 'not news' on a first observation."""
    g = safety_gate(_hct_row(0.53), None)
    assert g["band_change"] == "first_observation_in_band"
    out = news_gate(None, safety_gate=g)
    assert out["is_news"] is True
    assert "safety_band_first_observation_in_band" in out["basis"]
    assert set(out.keys()) == {"is_news", "basis"}
