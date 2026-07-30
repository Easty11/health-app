"""Schema + coverage guard for `marker_interpretation[*].mechanism`.

`mechanism` is authored prose, so the failures worth guarding are the ones a reader would
not notice: a group member added to `marker_groups.json` with no mechanism authored for it
(silent gap - the field would simply be absent for that marker), an invented
`protocol_factors_referenced` key (the committed view fixture carries exactly this defect:
`["training_load"]`, which is not a declared factor anywhere), and prose that drifts from
explaining physiology into addressing the user (the `#47` line).

I1 does NOT bind this text: `#95` extends the citation requirement to `marker_interpretation`
constants that *influence a gate*, and mechanism prose influences none - so `evidence_refs`
is deliberately not required here, exactly as `stable_rationale` (authored prose, uncited)
already is. Recorded so a later reader does not "fix" a missing citation that was never owed.

Every rule is exercised against a SYNTHETIC violation as well as the live asset: a coverage
test over an asset that happens to be complete passes vacuously, and the negative controls
are what make today's green mean something (the shape FEEDBACK 11/17 name).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_REFERENCE = Path(__file__).resolve().parent.parent / "reference"
_LEVER_DICTIONARY = _REFERENCE / "lever_dictionary.json"
_MARKER_GROUPS = _REFERENCE / "marker_groups.json"

_MECHANISM_FIELDS = {"text", "protocol_factors_referenced"}

# Second-person address is the cheap structural proxy for the #47 line: a mechanism explains
# the marker, never this user's result. "you"/"your" is what a directive rewrite reaches for
# first ("you should", "your level is high"), so it is the tripwire worth setting.
_SECOND_PERSON = (" you ", " you.", " your ", " your.", "you should", "your result")


class SchemaError(AssertionError):
    """Distinct type so a negative control asserts on the failure it intends, never on an
    incidental AssertionError raised by the test body itself."""


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _group_members(groups: dict) -> set[str]:
    return {m["marker_canonical"] for g in groups["groups"] for m in g["members"]}


def _declared_factor_vocabulary(dictionary: dict) -> set[str]:
    """The declared-factor keys the asset actually joins to (#145). `protocol_factors_referenced`
    draws on this namespace; anything outside it is invented."""
    return {k for node in dictionary["levers"].values()
            for k in node.get("declared_factor_keys", [])}


def validate(dictionary: dict, groups: dict) -> None:
    """Raise SchemaError on the first violation. Shared by the live asset and the
    synthetic-violation controls, so both exercise the identical rule set."""
    members = _group_members(groups)
    vocabulary = _declared_factor_vocabulary(dictionary)
    interpretation = dictionary["marker_interpretation"]

    for marker in sorted(members):
        entry = interpretation.get(marker)
        if entry is None or "mechanism" not in entry:
            raise SchemaError(f"{marker} is a group member with no authored mechanism")
        mechanism = entry["mechanism"]
        if set(mechanism) != _MECHANISM_FIELDS:
            raise SchemaError(f"{marker}.mechanism fields {sorted(mechanism)} != "
                              f"{sorted(_MECHANISM_FIELDS)}")
        text = mechanism["text"]
        if not isinstance(text, str) or not text.strip():
            raise SchemaError(f"{marker}.mechanism.text is empty")
        lowered = " " + text.lower()
        for probe in _SECOND_PERSON:
            if probe in lowered:
                raise SchemaError(f"{marker}.mechanism.text addresses the user ({probe!r}) - #47")
        factors = mechanism["protocol_factors_referenced"]
        if not isinstance(factors, list):
            raise SchemaError(f"{marker}.mechanism.protocol_factors_referenced is not a list")
        for factor in factors:
            if factor not in vocabulary:
                raise SchemaError(f"{marker}.mechanism references undeclared factor {factor!r} "
                                  f"(vocabulary: {sorted(vocabulary)})")


# ---------- the live asset ----------

def test_live_asset_passes_and_is_not_vacuous():
    dictionary, groups = _load(_LEVER_DICTIONARY), _load(_MARKER_GROUPS)
    members = _group_members(groups)
    assert len(members) == 15, f"expected 15 group members, found {len(members)} - update this guard"
    assert _declared_factor_vocabulary(dictionary), "no declared-factor vocabulary - factor rule vacuous"
    validate(dictionary, groups)


def test_every_group_member_is_covered():
    """Coverage stated as a set equality, so a member added to marker_groups.json without a
    mechanism fails here rather than surfacing as a silently absent field."""
    dictionary, groups = _load(_LEVER_DICTIONARY), _load(_MARKER_GROUPS)
    covered = {m for m, e in dictionary["marker_interpretation"].items() if "mechanism" in e}
    assert _group_members(groups) - covered == set()


# ---------- synthetic violations: the controls that make the green mean something ----------

def _asset_pair():
    return _load(_LEVER_DICTIONARY), _load(_MARKER_GROUPS)


def test_missing_mechanism_is_caught():
    dictionary, groups = _asset_pair()
    del dictionary["marker_interpretation"]["ast"]["mechanism"]
    with pytest.raises(SchemaError, match="no authored mechanism"):
        validate(dictionary, groups)


def test_new_group_member_without_a_mechanism_is_caught():
    """The live failure mode: marker_groups gains a member, nobody authors its mechanism."""
    dictionary, groups = _asset_pair()
    groups["groups"][0]["members"].append({"marker_canonical": "prolactin", "role": "invented"})
    with pytest.raises(SchemaError, match="prolactin"):
        validate(dictionary, groups)


def test_empty_text_is_caught():
    dictionary, groups = _asset_pair()
    dictionary["marker_interpretation"]["ast"]["mechanism"]["text"] = "   "
    with pytest.raises(SchemaError, match="is empty"):
        validate(dictionary, groups)


def test_undeclared_factor_key_is_caught():
    """`training_load` is precisely the defect the committed view fixture carries - it is not
    a declared factor anywhere, so a mechanism must not reference it."""
    dictionary, groups = _asset_pair()
    dictionary["marker_interpretation"]["ast"]["mechanism"]["protocol_factors_referenced"] = ["training_load"]
    with pytest.raises(SchemaError, match="undeclared factor"):
        validate(dictionary, groups)


def test_extra_field_is_caught():
    """Guards the shape while `confidence` is undecided: a per-marker value invented into the
    asset fails here rather than becoming a fait accompli."""
    dictionary, groups = _asset_pair()
    dictionary["marker_interpretation"]["ast"]["mechanism"]["confidence"] = "Likely"
    with pytest.raises(SchemaError, match="fields"):
        validate(dictionary, groups)


@pytest.mark.parametrize("prose", [
    "Your AST is high, so you should reduce training.",
    "This marker tells you what to do next.",
])
def test_second_person_prose_is_caught(prose):
    """Detector positive control: the #47 tripwire must actually fire, or its silence on the
    live asset means nothing."""
    dictionary, groups = _asset_pair()
    dictionary["marker_interpretation"]["ast"]["mechanism"]["text"] = prose
    with pytest.raises(SchemaError, match="addresses the user"):
        validate(dictionary, groups)
