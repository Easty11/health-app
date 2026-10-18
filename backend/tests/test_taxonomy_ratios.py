"""Taxonomy v1 (Q27): the Ratio type, `reference_kind`, and the joint-action measures.

A Ratio is a DERIVED read across two declared measures — a taxonomy declaration, not a
Region and not a Measure, and never a stored observation. This file pins:

  * the declarations themselves (er_ir, add_abd) and that they resolve;
  * `validate_ratio` refusing each way a declaration can be incoherent, with the bad case
    built first so the validator is shown to be able to fail (FEEDBACK 10, 57);
  * G3 (amended, R8): no numeric threshold lives on any Ratio or Measure, and no number in the
    tier fires a verdict — norms are data in `reference/capability_norms_v1.json`;
  * `reference_kind` is a closed vocabulary, the default is the restrictive one, the gate is
    stated to FAIL CLOSED, and a declaration is "literature" exactly when a norm is cited for it
    (the pin runs both ways, so a later admission edits the declaration and the norm together);
  * the new measures accept and refuse sides the way their INSTRUMENT allows.
"""
import dataclasses
from dataclasses import replace

import pytest

import models
from engine import observations as obs
from engine import taxonomy
from engine.taxonomy import Confidence, Measure, Ratio, validate_ratio
from routers.engine import get_taxonomy


def _ok(**kw):
    base = dict(key="t", label="t", numerator=("shoulder_er", "hhd_force_n"),
                denominator=("shoulder_ir", "hhd_force_n"), reference_kind="literature",
                expectation="x", confidence=Confidence.GUESSING)
    base.update(kw)
    return Ratio(**base)


# ── the declarations ─────────────────────────────────────────────────────────

def test_the_two_declared_ratios():
    assert [r.key for r in taxonomy.all_ratios()] == ["er_ir", "add_abd"]
    er_ir, add_abd = taxonomy.ratio_by_key("er_ir"), taxonomy.ratio_by_key("add_abd")
    assert er_ir.numerator == ("shoulder_er", "hhd_force_n")
    assert er_ir.denominator == ("shoulder_ir", "hhd_force_n")
    assert add_abd.numerator == ("hip_adduction", "hhd_force_n")
    assert add_abd.denominator == ("hip_abduction", "hhd_force_n")
    for r in (er_ir, add_abd):
        # R6: both ratios have a cited norm (Riemann 2010; Mosler 2016), so both are literature.
        assert r.same_side and r.same_protocol and r.reference_kind == "literature"
        assert r.confidence is Confidence.GUESSING
        # The retired isokinetic 0.66-0.75 text must not come back (it was torque, not HHD force).
        assert "0.66" not in r.expectation and "isokinetic" not in r.expectation.lower()
    assert taxonomy.ratio_by_key("h_q") is None      # R3: no H:Q ratio


def test_every_declared_ratio_validates_against_the_live_taxonomy():
    for r in taxonomy.all_ratios():
        validate_ratio(r)


def test_ratios_are_derived_never_stored():
    """A ratio key that was also a region or measure key could be written as an observation
    row; none is, so a ratio can only ever be computed at read time from two observations."""
    region_keys = {r.key for r in taxonomy.all_regions()}
    measure_keys = {m.key for r in taxonomy.all_regions() for m in r.measures}
    for r in taxonomy.all_ratios():
        assert r.key not in region_keys and r.key not in measure_keys
    with pytest.raises(ValueError, match="unknown region_key"):
        obs.record_observation(None, 1, region_key="er_ir", measure_key="hhd_force_n",
                               side=taxonomy.SIDE_LEFT, value=1.0)


def test_ratios_for_region_finds_both_roles():
    assert [r.key for r in taxonomy.ratios_for_region("shoulder_er")] == ["er_ir"]
    assert [r.key for r in taxonomy.ratios_for_region("shoulder_ir")] == ["er_ir"]
    assert [r.key for r in taxonomy.ratios_for_region("hip_abduction")] == ["add_abd"]
    assert taxonomy.ratios_for_region("hinge") == ()
    assert taxonomy.ratios_for_region("knee_flexion") == ()      # R3: absolute + LSI only
    assert taxonomy.ratios_for_region("no_such_region") == ()


def test_copenhagen_exposure_does_not_feed_add_abd():
    """Copenhagen stays tagged hip_adduction (exposure) but the ratio reads HHD force only."""
    add_abd = taxonomy.ratio_by_key("add_abd")
    assert add_abd.numerator[1] == "hhd_force_n"
    assert "exposure only" in taxonomy.by_key("hip_adduction").expectation


# ── validate_ratio: each way a declaration can be wrong ──────────────────────

@pytest.mark.parametrize("bad,match", [
    (dict(numerator=("shoulder_xx", "hhd_force_n")), "numerator region 'shoulder_xx' is not in the taxonomy"),
    (dict(denominator=("nope", "hhd_force_n")), "denominator region 'nope' is not in the taxonomy"),
    (dict(numerator=("shoulder_er", "hhd_nope")), "numerator measure 'hhd_nope' is not declared"),
    (dict(denominator=("shoulder_ir", "aslr_deg")), "denominator measure 'aslr_deg' is not declared"),
    (dict(denominator=("shoulder_er", "hhd_force_n")), "the same reading"),
    (dict(denominator=("ankle_plantarflexion", "sl_heel_raise_reps")), "units differ"),
    (dict(numerator=("hip_adduction", "squeeze_mmhg"), denominator=("hip_abduction", "hhd_force_n")),
     "units differ"),
    (dict(reference_kind="peer_reviewed"), "reference_kind"),
    (dict(key=""), "key is empty"),
    (dict(confidence="guessing"), "confidence must be a Confidence"),
])
def test_validate_ratio_refuses_each_incoherent_declaration(bad, match):
    validate_ratio(_ok())                       # the control: the unmodified base is valid
    with pytest.raises(ValueError, match=match):
        validate_ratio(_ok(**bad))


def test_same_side_needs_both_measures_per_side():
    """same_side pairs left with left; a measure that cannot carry a side cannot be paired."""
    bilateral_a = Measure("a_x", "N", True, per_side=False)
    bilateral_b = Measure("b_x", "N", True, per_side=False)
    regions = {
        "ra": replace(taxonomy.by_key("hip_abduction"), key="ra", measures=(bilateral_a,)),
        "rb": replace(taxonomy.by_key("hip_abduction"), key="rb", measures=(bilateral_b,)),
    }
    r = Ratio("t", "t", ("ra", "a_x"), ("rb", "b_x"), "internal", "x", Confidence.GUESSING)
    with pytest.raises(ValueError, match="same_side=True needs both measures per-side"):
        validate_ratio(r, regions)
    validate_ratio(replace(r, same_side=False), regions)      # the same pair, not claiming sides


def test_a_duplicate_ratio_key_is_refused_at_declaration(monkeypatch):
    monkeypatch.setattr(taxonomy, "_RATIOS", taxonomy._RATIOS + (taxonomy._RATIOS[0],))
    with pytest.raises(ValueError, match="declared twice"):
        taxonomy._validate_declared_ratios()


# ── reference_kind ───────────────────────────────────────────────────────────

def test_reference_kind_is_a_closed_vocabulary_with_the_restrictive_default():
    assert taxonomy.REFERENCE_KINDS == ("internal", "literature")
    assert Measure("k", "N", True).reference_kind == "internal"
    assert Measure("k", "N", True, reference_kind="literature").reference_kind == "literature"
    with pytest.raises(ValueError, match="reference_kind"):
        Measure("k", "N", True, reference_kind="lit")
    with pytest.raises(ValueError, match="reference_kind"):
        _ok(reference_kind="lit")


def test_the_gate_is_stated_to_fail_closed_in_the_measure_and_ratio_docstrings():
    """Operator ruling: an observation with no administered_by / protocol provenance is evaluated
    as internal. Nothing evaluates it yet (no consumer, no provenance columns), so the contract
    is pinned where it is stated."""
    for doc in (Measure.__doc__, Ratio.__doc__):
        flat = " ".join(doc.split())
        assert "FAILS CLOSED" in flat and "administered_by" in flat and 'as "internal"' in flat


def test_every_literature_declaration_has_a_cited_norm_and_every_internal_one_has_none():
    """The fail-closed inverse of the old pin (R8). A declaration is "literature" exactly when at
    least one norm in the registry names it, under a DECLARED protocol, with a PMID and a DOI. A
    future admission must flip the declaration and add the norm in ONE change; a norm with no
    flipped declaration (or a flip with no norm) fails here."""
    from engine import norms, protocols

    def cited(target):
        ns = norms.norms_for_target(target)
        return bool(ns) and all(
            protocols.by_key(pk) is not None and n.citation.get("pmid") and n.citation.get("doi")
            for n in ns for pk in n.protocols)

    for r in taxonomy.all_regions():
        for m in r.measures:
            has = bool(norms.norms_for_target((r.key, m.key)))
            if m.reference_kind == "literature":
                assert cited((r.key, m.key)), (r.key, m.key)
            else:
                assert not has, ("internal measure with a norm", r.key, m.key)
    for ratio in taxonomy.all_ratios():
        has = bool(norms.norms_for_target((protocols.RATIO_TARGET, ratio.key)))
        if ratio.reference_kind == "literature":
            assert cited((protocols.RATIO_TARGET, ratio.key)), ratio.key
        else:
            assert not has, ("internal ratio with a norm", ratio.key)


def test_the_v1_measures_are_declared_as_briefed():
    got = {(r.key, m.key): (m.unit, m.per_side, m.higher_is_better, m.reference_kind)
           for r in taxonomy.all_regions() for m in r.measures if r.group == "H"}
    assert got == {
        ("shoulder_er", "hhd_force_n"): ("N", True, True, "literature"),
        ("shoulder_ir", "hhd_force_n"): ("N", True, True, "literature"),
        ("hip_adduction", "hhd_force_n"): ("N", True, True, "internal"),
        ("hip_adduction", "squeeze_hhd_n"): ("N", False, True, "literature"),
        ("hip_adduction", "squeeze_mmhg"): ("mmHg", False, True, "literature"),
        ("hip_abduction", "hhd_force_n"): ("N", True, True, "internal"),
        ("ankle_plantarflexion", "sl_heel_raise_reps"): ("count", True, True, "literature"),
        ("knee_flexion", "hhd_force_n"): ("N", True, True, "internal"),
        ("knee_flexion", "slhb_reps"): ("count", True, True, "internal"),
    }
    # R7: knee_flexion declares an isometric HHD and the single-leg bridge; NO NordBord measure until
    # the EP confirms the instrument; still no H:Q ratio and no knee_extension (R3).
    knee = taxonomy.by_key("knee_flexion")
    assert [m.key for m in knee.measures] == ["hhd_force_n", "slhb_reps"]
    assert taxonomy.by_key("knee_extension") is None
    assert "No H:Q ratio" in knee.expectation
    # R7a: the declared OUTCOME is a three-part hamstring strain-risk profile, stated in the text.
    for part in ("(a) absolute capacity", "(b) left/right", "(c) endurance"):
        assert part in knee.expectation
    assert not any("nordbord" in m.key for m in knee.measures)


# ── G3: no numeric threshold in code ─────────────────────────────────────────

def test_no_numeric_threshold_field_on_ratio_or_measure():
    import re
    for cls in (Ratio, Measure, taxonomy.Region):
        for f in dataclasses.fields(cls):
            assert f.type not in ("int", "float"), (cls.__name__, f.name)
    for r in taxonomy.all_ratios():
        for f in dataclasses.fields(r):
            v = getattr(r, f.name)
            assert not (isinstance(v, (int, float)) and not isinstance(v, bool)), (r.key, f.name)
    # A band is DATA in the norms JSON (R8), never quoted in declaration text: no decimal number or
    # percentage appears in a ratio's expectation.
    for r in taxonomy.all_ratios():
        assert not re.search(r"\d+\.\d+|%", r.expectation), r.key


# ── sides follow the instrument, through the real write path ─────────────────

def _user(db):
    u = models.User(email="ratios@example.com", hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_hhd_is_per_side_and_the_squeeze_is_bilateral_only(db_session):
    u = _user(db_session)
    row = obs.record_observation(db_session, u.id, region_key="hip_adduction",
                                 measure_key="hhd_force_n", side=taxonomy.SIDE_LEFT,
                                 value=210.0, method="manual", source="manual")
    assert row.unit == "N" and row.side == "left"
    obs.record_observation(db_session, u.id, region_key="hip_adduction",
                           measure_key="squeeze_mmhg", side=taxonomy.SIDE_BILATERAL,
                           value=180.0, method="manual", source="manual")
    with pytest.raises(ValueError):
        obs.record_observation(db_session, u.id, region_key="hip_adduction",
                               measure_key="squeeze_mmhg", side=taxonomy.SIDE_LEFT,
                               value=180.0, method="manual", source="manual")
    with pytest.raises(ValueError):
        obs.record_observation(db_session, u.id, region_key="hip_adduction",
                               measure_key="hhd_force_n", side=taxonomy.SIDE_BILATERAL,
                               value=210.0, method="manual", source="manual")


def test_the_retired_key_is_refused_on_write(db_session):
    """R1 fallout: `shoulder_er_ir` no longer resolves, so any caller still naming it is refused
    loudly. (A STORED row naming it is the V2 prod check — this is only the write side.)"""
    u = _user(db_session)
    with pytest.raises(ValueError, match="unknown region_key"):
        obs.record_observation(db_session, u.id, region_key="shoulder_er_ir",
                               measure_key="hhd_force_n", side=taxonomy.SIDE_LEFT,
                               value=100.0, method="manual", source="manual")


# ── serialisation ────────────────────────────────────────────────────────────

def test_as_dict_carries_reference_kind_and_the_taxonomy_endpoint_lists_ratios():
    d = taxonomy.as_dict(taxonomy.by_key("hip_adduction"))
    assert {m["key"]: m["reference_kind"] for m in d["measures"]} == {
        "hhd_force_n": "internal", "squeeze_hhd_n": "literature", "squeeze_mmhg": "literature"}
    knee = {m["key"]: m for m in taxonomy.as_dict(taxonomy.by_key("knee_flexion"))["measures"]}
    assert set(knee) == {"hhd_force_n", "slhb_reps"}
    assert taxonomy.as_dict(taxonomy.by_key("ankle_df"))["measures"][0]["reference_kind"] == "internal"
    body = get_taxonomy()
    assert body["version"] == "v1"
    assert {r["key"] for r in body["regions"]} >= {"shoulder_er", "shoulder_ir", "hip_abduction",
                                                   "ankle_plantarflexion"}
    assert "shoulder_er_ir" not in {r["key"] for r in body["regions"]}
    by = {r["key"]: r for r in body["ratios"]}
    assert by["er_ir"]["numerator"] == {"region": "shoulder_er", "measure": "hhd_force_n"}
    assert by["add_abd"]["denominator"] == {"region": "hip_abduction", "measure": "hhd_force_n"}
    assert by["er_ir"]["reference_kind"] == "literature" and by["er_ir"]["same_side"] is True
    assert by["add_abd"]["reference_kind"] == "literature"
    assert by["er_ir"]["confidence"] == "guessing"
