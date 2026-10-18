"""Protocol registry + norms registry (Q27 v1 remainders).

Pins:
  * every protocol resolves on the taxonomy, names a legal instrument, and the registry is validated
    at import (each way a declaration can be incoherent is built first, with a valid control);
  * every norm resolves to a declared protocol and target, obeys the unit rule, and carries a PMID
    and a DOI; the shipped JSON is pure ASCII;
  * G3 (amended R8) mechanised: no ordering operator is applied to a norm value, and no verdict
    vocabulary appears, in the four modules that handle norms and ratios. The checker is shown to
    bite on a synthetic violation first (FEEDBACK 10, false-green instruments).
"""
import ast
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from engine import norms, protocols, taxonomy
from engine.protocols import Protocol, RATIO_TARGET

ENGINE = Path(__file__).resolve().parent.parent / "engine"
NORMS_JSON = Path(__file__).resolve().parent.parent / "reference" / "capability_norms_v1.json"


# ── protocols ────────────────────────────────────────────────────────────────

def test_the_declared_protocols_are_exactly_the_briefed_ten():
    assert [p.key for p in protocols.all_protocols()] == [
        "hhd_shoulder_rot_seated_neutral_make", "hhd_shoulder_rot_seated_30_30_30_make",
        "hhd_shoulder_rot_prone_90_90_make", "hhd_shoulder_rot_supine_45abd_make",
        "hhd_hip_add_abd_sidelying_eccentric", "hhd_squeeze_supine_45_make",
        "sphyg_squeeze_supine_45", "heel_rise_10deg_incline_to_fatigue",
        "hhd_knee_flexion_prone_90_make", "slhb_to_fatigue",
    ]
    # No NordBord / isokinetic protocol until the EP confirms the instrument.
    assert not [p for p in protocols.all_protocols() if p.instrument in ("nordbord", "isokinetic")]


def test_every_protocol_target_resolves_and_the_instrument_is_legal():
    for p in protocols.all_protocols():
        protocols.validate_protocol(p)
        assert p.instrument in protocols.INSTRUMENTS
        assert p.description.strip() and "@@" not in p.description


def test_no_protocol_description_leaves_a_placeholder_or_hides_an_unconfirmed_detail():
    by = {p.key: p for p in protocols.all_protocols()}
    assert "60 cycles/min" in by["heel_rise_10deg_incline_to_fatigue"].description
    assert "60 cm box" in by["slhb_to_fatigue"].description
    assert "CEILING" in by["sphyg_squeeze_supine_45"].description


@pytest.mark.parametrize("bad,match", [
    (dict(key=""), "key is empty"),
    (dict(instrument="laser"), "instrument 'laser'"),
    (dict(targets=()), "no targets"),
    (dict(targets=(("shoulder_er", "hhd_force_n"),) * 2), "declared twice"),
    (dict(targets=(("shoulder_er", "hhd_nope"),)), "not a declared measure"),
    (dict(targets=((RATIO_TARGET, "no_such_ratio"),)), "ratio target 'no_such_ratio'"),
    (dict(description="  "), "description is empty"),
])
def test_validate_protocol_refuses_each_incoherent_declaration(bad, match):
    base = protocols.by_key("hhd_shoulder_rot_seated_neutral_make")
    protocols.validate_protocol(base)                    # the control
    with pytest.raises(ValueError, match=match):
        protocols.validate_protocol(replace(base, **bad))


def test_a_duplicate_protocol_key_is_refused(monkeypatch):
    monkeypatch.setattr(protocols, "_PROTOCOLS", protocols._PROTOCOLS + (protocols._PROTOCOLS[0],))
    with pytest.raises(ValueError, match="declared twice"):
        protocols._validate_declared()


def test_covers_is_exact():
    assert protocols.covers("hhd_squeeze_supine_45_make", ("hip_adduction", "squeeze_hhd_n"))
    assert not protocols.covers("hhd_squeeze_supine_45_make", ("hip_adduction", "hhd_force_n"))
    assert not protocols.covers("nope", ("hip_adduction", "squeeze_hhd_n"))


# ── norms ────────────────────────────────────────────────────────────────────

def test_the_shipped_norms_json_is_pure_ascii_and_parses():
    raw = NORMS_JSON.read_text(encoding="utf-8")
    assert raw.isascii()
    json.loads(raw)


def test_every_norm_resolves_to_a_declared_protocol_and_target():
    assert len(norms.all_norms()) == 9
    for n in norms.all_norms():
        assert n.kind == "reference"
        assert n.citation["pmid"] and n.citation["doi"]
        assert n.verified_against in norms.VERIFIED_AGAINST
        for pk in n.protocols:
            assert protocols.covers(pk, n.target), (n.id, pk)


def test_the_admitted_norm_values_are_as_ruled():
    by = {n.id: n for n in norms.all_norms()}
    assert by["riemann2010_er_ir_hhd"].value == {"low": 0.86, "high": 0.99}
    assert by["westrick2013_er_neutral"].value == {"mean": 0.20, "sd": 0.04}
    assert by["westrick2013_er_supine45"].value == {"mean": 0.22, "sd": 0.05}
    assert by["westrick2013_ir_neutral"].value == {"mean": 0.27, "sd": 0.06}
    assert by["westrick2013_ir_supine45"].value == {"mean": 0.26, "sd": 0.05}
    assert by["mosler2016_add_abd_ratio"].value == {"mean": 1.2, "sd": 0.2}
    assert by["mosler2016_squeeze_hhd"].value == {"mean": 3.6, "sd": 0.8}
    assert by["mosler2016_squeeze_hhd"].unit == "N/kg"
    assert by["delahunt2011_squeeze_mmhg"].value == {"mean": 236.8, "sd": 47.3}
    assert by["hebertlosier2017_sl_heel_raise"].value == {"median": 24.0}
    # Mosler's Nm/kg torque figures are NOT admitted for force.
    assert not [n for n in norms.all_norms()
                if n.target == ("hip_adduction", "hhd_force_n")
                or n.target == ("hip_abduction", "hhd_force_n")]


def test_lookup_is_by_target_and_protocol():
    t = ("shoulder_er", "hhd_force_n")
    assert norms.norm_for(t, "hhd_shoulder_rot_seated_neutral_make").id == "westrick2013_er_neutral"
    assert norms.norm_for(t, "hhd_shoulder_rot_supine_45abd_make").id == "westrick2013_er_supine45"
    assert norms.norm_for(t, "hhd_shoulder_rot_prone_90_90_make") is None
    assert norms.norm_for((RATIO_TARGET, "er_ir"), "hhd_shoulder_rot_prone_90_90_make").id == \
        "riemann2010_er_ir_hhd"
    # a protocol with no norm admitted
    assert norms.norm_for(("knee_flexion", "slhb_reps"), "slhb_to_fatigue") is None


def _good_record():
    return json.loads(NORMS_JSON.read_text(encoding="utf-8"))["norms"][-1]   # heel raise (count)


def _load_with(tmp_path, record):
    p = tmp_path / "n.json"
    p.write_text(json.dumps({"norms": [record]}), encoding="utf-8")
    return norms._load(p)


@pytest.mark.parametrize("edit,match", [
    (dict(id=""), "id is empty"),
    (dict(kind="threshold"), "kind must be 'reference'"),
    (dict(target={"region": "ankle_plantarflexion", "measure": "nope"}), "not a declared measure"),
    (dict(target={"ratio": "h_q"}), "ratio 'h_q' is not declared"),
    (dict(unit="reps/kg"), "is not the measure's unit"),
    (dict(unit="count/kg"), "needs normalisation 'per_body_mass_kg'"),
    (dict(normalisation="per_body_mass_kg"), "takes no normalisation"),
    (dict(value={"median": 24, "mean": 1}), "value must be one of"),
    (dict(value={"low": 5, "high": 1}), "wrong way round"),
    (dict(value={"median": "24"}), "must be numeric"),
    (dict(population=""), "population is required"),
    (dict(n=0), "positive integer"),
    (dict(n=-5), "positive integer"),
    (dict(citation={"pmid": "1"}), "pmid and a doi"),
    (dict(citation={"doi": "10.1/x"}), "pmid and a doi"),
    (dict(verified_against="hearsay"), "verified_against"),
    (dict(protocols=[]), "no protocols"),
    (dict(protocols=["nope"]), "is not declared"),
    (dict(protocols=["hhd_squeeze_supine_45_make"]), "does not produce target"),
])
def test_the_norm_loader_refuses_each_incoherent_record(tmp_path, edit, match):
    norms_ok, _ = _load_with(tmp_path, _good_record())              # the control
    assert len(norms_ok) == 1
    with pytest.raises(ValueError, match=match):
        _load_with(tmp_path, {**_good_record(), **edit})


def test_the_unit_rule_for_force_and_ratio_norms(tmp_path):
    force = {**_good_record(),
             "target": {"region": "shoulder_er", "measure": "hhd_force_n"},
             "protocols": ["hhd_shoulder_rot_seated_neutral_make"]}
    _load_with(tmp_path, {**force, "unit": "N"})                                         # own unit
    _load_with(tmp_path, {**force, "unit": "N/kg", "normalisation": "per_body_mass_kg"})  # per kg
    _load_with(tmp_path, {**force, "unit": "ratio", "normalisation": "per_body_weight"})  # fraction
    with pytest.raises(ValueError, match="per_body_weight"):
        _load_with(tmp_path, {**force, "unit": "ratio"})
    count = {**_good_record(), "unit": "ratio", "normalisation": "per_body_weight"}      # not a force
    with pytest.raises(ValueError, match="force"):
        _load_with(tmp_path, count)
    ratio = {**_good_record(), "target": {"ratio": "er_ir"},
             "protocols": ["hhd_shoulder_rot_seated_neutral_make"], "unit": "ratio",
             "value": {"mean": 0.9, "sd": 0.1}}
    _load_with(tmp_path, ratio)
    with pytest.raises(ValueError, match="ratio target needs unit 'ratio'"):
        _load_with(tmp_path, {**ratio, "unit": "N"})


def test_two_norms_may_not_claim_the_same_target_and_protocol(tmp_path):
    p = tmp_path / "n.json"
    r = _good_record()
    p.write_text(json.dumps({"norms": [r, {**r, "id": "other"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="already covered"):
        norms._load(p)


# ── G3 mechanised: no number fires a verdict ─────────────────────────────────

_ORDERING = (ast.Lt, ast.Gt, ast.LtE, ast.GtE)
_NORMISH = re.compile(r"norm|band|\blow\b|\bhigh\b|\bmean\b|\bsd\b|\bmedian\b", re.I)
_VERDICT_WORDS = re.compile(r"\b(pass|fail|clear|deficit|grade)\b", re.I)
_STRICT = ("reference.py", "norms.py")        # no ordering operator AT ALL in these two
_ALL_FOUR = ("reference.py", "norms.py", "ratios.py", "log_strength.py")


def _violations(src: str, strict: bool) -> list[str]:
    out = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Compare) and any(isinstance(op, _ORDERING) for op in node.ops):
            text = ast.unparse(node)
            if strict or _NORMISH.search(text):
                out.append(f"ordering comparison: {text}")
    for m in _VERDICT_WORDS.finditer(src):
        out.append(f"verdict word: {m.group(0)!r}")
    return out


@pytest.mark.parametrize("bad", [
    "if reading < norm['low']:\n    flag = 1",
    "ok = value >= band['mean'] - band['sd']",
    "result = 'pass' if x == 1 else 'fail'",
    "deficit = 1",
    "grade = 2",
    "cleared = clear(x)",
])
def test_the_no_comparison_checker_bites_on_a_synthetic_violation(bad):
    assert _violations(bad, strict=True), f"checker missed: {bad!r}"


def test_the_checker_permits_a_date_window_comparison_outside_the_strict_modules():
    assert _violations("recent = (today - day).days <= CURRENCY_DAYS", strict=False) == []
    assert _violations("recent = (today - day).days <= CURRENCY_DAYS", strict=True)


@pytest.mark.parametrize("name", _ALL_FOUR)
def test_no_norm_is_compared_and_no_verdict_word_appears(name):
    src = (ENGINE / name).read_text(encoding="utf-8")
    assert _violations(src, strict=name in _STRICT) == []


def test_the_norms_module_exposes_no_comparison_function():
    public = [n for n in dir(norms) if not n.startswith("_")]
    for n in public:
        assert not re.search(r"compare|within|exceed|meets|below|above|deficit|grade|score", n), n
