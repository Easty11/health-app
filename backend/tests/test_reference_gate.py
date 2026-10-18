"""The reference gate (Q27 v1): `evaluate_reference` shows a literature band only when the declaration,
the provenance, the protocol agreement and a cited norm ALL hold - and every other case is "internal"
with the reason named. It returns a band, never a comparison.
"""
import json

import pytest

import load_events
import models
from engine import observations as obs
from engine import reference
from engine.reference import evaluate_reference
from routers.engine import get_observations

SEATED = "hhd_shoulder_rot_seated_neutral_make"
PRONE = "hhd_shoulder_rot_prone_90_90_make"
THIRTY = "hhd_shoulder_rot_seated_30_30_30_make"
ER = ("shoulder_er", "hhd_force_n")
IR = ("shoulder_ir", "hhd_force_n")
ER_IR = ("ratio", "er_ir")


def _user(db, email="gate@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _rec(db, uid, target, value=120.0, protocol=SEATED, side="left", prov=True, **kw):
    prov_kw = {}
    if prov:
        prov_kw = dict(administered_by="ep", instrument="hhd", protocol=protocol)
    return obs.record_observation(db, uid, region_key=target[0], measure_key=target[1],
                                  value=value, side=side, method="manual", source="manual",
                                  **prov_kw, **kw)


class _Stub:
    def __init__(self, uid):
        self.id = uid


# ── the happy path, and its display arithmetic ───────────────────────────────

def test_declaration_literature_plus_full_provenance_plus_a_cited_norm_is_literature(db_session):
    u = _user(db_session)
    row = _rec(db_session, u.id, ER, value=150.0)
    out = evaluate_reference(ER, [row])
    assert out["governing"] == "literature" and out["protocol"] == SEATED
    assert out["band"]["id"] == "westrick2013_er_neutral"
    assert out["band"]["value"] == {"mean": 0.20, "sd": 0.04}
    assert out["band"]["citation"]["pmid"] == "24381696"
    # the per-body arithmetic is visible, with its source
    assert out["body_mass_source"] == "load_events.BODYWEIGHT_KG"
    assert out["body_mass_kg"] == load_events.BODYWEIGHT_KG
    assert out["value_normalised"] == pytest.approx(150.0 / (load_events.BODYWEIGHT_KG * 9.80665))
    assert out["normalisation"] == "per_body_weight"


def test_a_per_kg_norm_divides_by_body_mass(db_session):
    u = _user(db_session)
    row = obs.record_observation(
        db_session, u.id, region_key="hip_adduction", measure_key="squeeze_hhd_n", value=306.0,
        side="bilateral", administered_by="ep", instrument="hhd", protocol="hhd_squeeze_supine_45_make")
    out = evaluate_reference(("hip_adduction", "squeeze_hhd_n"), [row])
    assert out["governing"] == "literature" and out["band"]["unit"] == "N/kg"
    assert out["value_normalised"] == pytest.approx(306.0 / load_events.BODYWEIGHT_KG)


def test_a_ratio_with_one_shared_protocol_is_literature(db_session):
    u = _user(db_session)
    out = evaluate_reference(ER_IR, [_rec(db_session, u.id, ER, protocol=PRONE),
                                     _rec(db_session, u.id, IR, protocol=PRONE)])
    assert out["governing"] == "literature" and out["band"]["id"] == "riemann2010_er_ir_hhd"
    assert out["band"]["value"] == {"low": 0.86, "high": 0.99}
    assert "value_normalised" not in out          # a ratio is already unitless


def test_a_unitless_ratio_band_for_the_hip_ratio(db_session):
    u = _user(db_session)
    p = "hhd_hip_add_abd_sidelying_eccentric"
    add = _rec(db_session, u.id, ("hip_adduction", "hhd_force_n"), protocol=p, value=180.0)
    abd = _rec(db_session, u.id, ("hip_abduction", "hhd_force_n"), protocol=p, value=150.0)
    out = evaluate_reference(("ratio", "add_abd"), [add, abd])
    assert out["governing"] == "literature" and out["band"]["citation"]["pmid"] == "28185809"


# ── each failure arm is internal, with the reason named ──────────────────────

def test_a_declaration_of_internal_is_internal_even_with_full_provenance(db_session):
    u = _user(db_session)
    p = "hhd_hip_add_abd_sidelying_eccentric"
    row = _rec(db_session, u.id, ("hip_adduction", "hhd_force_n"), protocol=p)
    out = evaluate_reference(("hip_adduction", "hhd_force_n"), [row])
    assert out == {"governing": "internal", "protocol": None, "band": None,
                   "reason": "declaration internal"}


def test_no_provenance_is_internal_forever(db_session):
    u = _user(db_session)
    row = _rec(db_session, u.id, ER, prov=False)
    assert (row.administered_by, row.instrument, row.protocol) == (None, None, None)
    out = evaluate_reference(ER, [row])
    assert out["governing"] == "internal" and out["reason"] == "no provenance" and out["band"] is None


def test_one_unprovenanced_half_of_a_ratio_makes_the_ratio_internal(db_session):
    u = _user(db_session)
    out = evaluate_reference(ER_IR, [_rec(db_session, u.id, ER, protocol=SEATED),
                                     _rec(db_session, u.id, IR, prov=False)])
    assert out["governing"] == "internal" and out["reason"] == "no provenance"


def test_a_ratio_whose_halves_used_different_protocols_is_internal(db_session):
    u = _user(db_session)
    out = evaluate_reference(ER_IR, [_rec(db_session, u.id, ER, protocol=SEATED),
                                     _rec(db_session, u.id, IR, protocol=PRONE)])
    assert out["governing"] == "internal" and out["reason"] == "protocol mismatch"


def test_a_protocol_with_no_cited_norm_for_the_target_is_internal(db_session):
    u = _user(db_session)
    row = _rec(db_session, u.id, ER, protocol=THIRTY)      # Westrick did not cite 30-30-30 for ER force
    out = evaluate_reference(ER, [row])
    assert out["governing"] == "internal" and out["reason"] == "no norm for protocol"
    assert out["protocol"] == THIRTY and out["band"] is None


def test_inconsistent_provenance_that_bypassed_the_write_guard_is_internal(db_session):
    u = _user(db_session)
    row = _rec(db_session, u.id, ER)
    row.instrument = "cable"                 # a row corrupted after the write guard
    assert evaluate_reference(ER, [row])["reason"] == "provenance inconsistent"


def test_no_observation_and_an_incomplete_ratio_read_are_internal(db_session):
    u = _user(db_session)
    assert evaluate_reference(ER, [])["reason"] == "no observation"
    assert evaluate_reference(ER_IR, [_rec(db_session, u.id, ER)])["reason"] == "incomplete read"
    assert evaluate_reference(("nope", "nope"), [])["reason"] == "unknown target"


def test_a_measure_declared_internal_never_reads_literature_whatever_the_norm_registry_holds(db_session):
    """slhb_reps has a protocol but no norm and an internal declaration: the declaration arm fires first."""
    u = _user(db_session)
    row = obs.record_observation(db_session, u.id, region_key="knee_flexion", measure_key="slhb_reps",
                                 value=18.0, side="left", administered_by="self",
                                 instrument="bodyweight", protocol="slhb_to_fatigue")
    assert evaluate_reference(("knee_flexion", "slhb_reps"), [row])["reason"] == "declaration internal"


# ── it returns a band, never a comparison ────────────────────────────────────

_ALLOWED_KEYS = {"governing", "protocol", "band", "reason", "body_mass_kg", "body_mass_source",
                 "value_normalised", "normalisation"}


def test_the_result_carries_no_comparison_flag_or_grade(db_session):
    u = _user(db_session)
    cases = [
        evaluate_reference(ER, [_rec(db_session, u.id, ER, value=1.0)]),          # absurdly low
        evaluate_reference(ER, [_rec(db_session, u.id, ER, value=9e6, side="right")]),   # absurdly high
        evaluate_reference(ER, [_rec(db_session, u.id, ER, prov=False, side="right")]),
    ]
    for out in cases:
        assert set(out) <= _ALLOWED_KEYS, set(out) - _ALLOWED_KEYS
    # the same band and the same reason whatever the reading: the reading does not steer the gate
    a, b = cases[0], cases[1]
    assert a["band"] == b["band"] and a["reason"] == b["reason"]


def test_the_gate_is_wired_into_get_observations(db_session):
    u = _user(db_session)
    _rec(db_session, u.id, ER, value=150.0)
    _rec(db_session, u.id, ER, value=130.0, side="right", prov=False)
    out = get_observations(region_key="shoulder_er", measure_key="hhd_force_n", side=None,
                           since=None, current_user=_Stub(u.id), db=db_session)
    assert out["latest"]["left"]["reference"]["governing"] == "literature"
    assert out["latest"]["right"]["reference"]["reason"] == "no provenance"
    # the response restates no verdict
    text = json.dumps(out, default=str).lower()
    for word in ("cleared", "safe to", "deficit", "severity"):
        assert word not in text


def test_the_body_mass_source_constant_names_the_one_real_source():
    assert reference.BODY_MASS_SOURCE == "load_events.BODYWEIGHT_KG"
    assert isinstance(load_events.BODYWEIGHT_KG, float)
