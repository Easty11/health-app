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
from pathlib import Path

import pytest

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
    # Truthful about what this proves: today the asset has no live entries, so the call
    # validated nothing. The synthetic cases below are the real cover.
    assert checked == 0, (
        "live bands now exist -- this assertion is the reminder that the synthetic "
        "controls below, not this call, are what has been exercising the validator"
    )


def test_deferred_haematocrit_is_shaped_but_not_live():
    asset = json.loads(ASSET.read_text(encoding="utf-8"))
    assert "haematocrit" not in asset["thresholds"], "must not be live without citations"
    d = asset["_deferred"]["haematocrit"]
    assert d["blocked_on"], "a deferred entry must name what blocks it"
    assert d["contested"] is True
    assert [b["value"] for b in d["intended_bands"]] == [0.50, 0.52, 0.54]
    for band in d["intended_bands"]:
        assert "evidence_refs" not in band, "deferred bands are uncited by definition"


def test_deferred_entries_are_not_validated_as_live():
    """_deferred is deliberately outside validate()'s reach: its bands are uncited, which
    is exactly the state that would fail I1 if they were live."""
    asset = json.loads(ASSET.read_text(encoding="utf-8"))
    assert validate(asset) == 0
    assert asset["_deferred"]["haematocrit"]["intended_bands"]


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
