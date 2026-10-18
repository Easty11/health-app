"""
The reference gate (Q27 v1) - which reference governs a read: the user's own series, or a band.

`evaluate_reference(target, observations)` answers one question: may a LITERATURE band be shown
beside these readings? It answers "literature" only when ALL hold:

  1. the target is DECLARED "literature" on the taxonomy (Measure / Ratio `reference_kind`);
  2. every observation in the read carries COMPLETE provenance (administered_by, instrument and
     protocol - all three), and the instrument agrees with the protocol's declared instrument;
  3. for a ratio, both observations share ONE protocol (`Ratio.same_protocol`, now enforceable);
  4. a norm is cited for (target, protocol) in `reference/capability_norms_v1.json`.

Anything else is "internal" - the user's own baseline and trend govern - with the reason named. The
gate closes by default: a reading with no provenance (every legacy row) can never read as literature.

WHAT IT RETURNS IS A BAND, NEVER A JUDGEMENT. The result carries the norm record for display. It
carries no comparison of the reading to the band, no flag, no label and no score (G3, amended R8: no
number fires a verdict; the section 7 boundary, mechanised in `tests/test_protocols_norms.py`, which
scans this module for ordering operators and verdict vocabulary). When a band is per body mass, the
result also carries the body mass used and its source, so the arithmetic is visible rather than hidden.
"""
from __future__ import annotations

from typing import Any, Sequence

import models
from . import norms as norms_mod
from . import protocols as protocols_mod
from . import taxonomy

BODY_MASS_SOURCE = "load_events.BODYWEIGHT_KG"
_STANDARD_GRAVITY = 9.80665   # m/s^2: body weight (N) = body mass (kg) x this


def _internal(reason: str, protocol: str | None = None) -> dict[str, Any]:
    return {"governing": "internal", "protocol": protocol, "band": None, "reason": reason}


def _declaration(target: protocols_mod.Target) -> str | None:
    region_key, name = target
    if region_key == protocols_mod.RATIO_TARGET:
        ratio = taxonomy.ratio_by_key(name)
        return ratio.reference_kind if ratio else None
    measure = taxonomy.measure_for(region_key, name)
    return measure.reference_kind if measure else None


def _complete(obs: models.CapabilityObservation) -> bool:
    return None not in (obs.administered_by, obs.instrument, obs.protocol)


def _instrument_agrees(obs: models.CapabilityObservation) -> bool:
    proto = protocols_mod.by_key(obs.protocol)
    return proto is not None and proto.instrument == obs.instrument


def _body_mass_kg() -> float:
    import load_events   # lazy: keeps the engine package importable without the load transform
    return float(load_events.BODYWEIGHT_KG)


def _normalised(norm: norms_mod.Norm, value: float, mass_kg: float) -> float | None:
    if norm.normalisation == "per_body_mass_kg":
        return value / mass_kg
    if norm.normalisation == "per_body_weight":
        return value / (mass_kg * _STANDARD_GRAVITY)
    return None


def evaluate_reference(
    target: protocols_mod.Target,
    observations: Sequence[models.CapabilityObservation],
) -> dict[str, Any]:
    """`target` is `(region_key, measure_key)` or `("ratio", ratio_key)`; `observations` are the
    reading(s) it is computed from (one for a measure, numerator then denominator for a ratio)."""
    target = (target[0], target[1])
    declared = _declaration(target)
    if declared is None:
        return _internal("unknown target")
    if declared != "literature":
        return _internal("declaration internal")
    observations = list(observations)
    expected = 2 if target[0] == protocols_mod.RATIO_TARGET else 1
    if len(observations) != expected:
        return _internal("no observation" if not observations else "incomplete read")

    if not all(_complete(o) for o in observations):
        return _internal("no provenance")
    if not all(_instrument_agrees(o) for o in observations):
        return _internal("provenance inconsistent")

    protos = {o.protocol for o in observations}
    if len(protos) != 1:
        return _internal("protocol mismatch")
    protocol = protos.pop()

    norm = norms_mod.norm_for(target, protocol)
    if norm is None:
        return _internal("no norm for protocol", protocol)

    band = norms_mod.norm_as_dict(norm)
    result: dict[str, Any] = {
        "governing": "literature",
        "protocol": protocol,
        "band": band,
        "reason": f"provenance matches protocol {protocol}; norm {norm.id} is cited",
    }
    if norm.normalisation is not None:
        mass = _body_mass_kg()
        result["body_mass_kg"] = mass
        result["body_mass_source"] = BODY_MASS_SOURCE
        # Display arithmetic only (reading divided by mass): it sits beside the band, nothing reads it.
        result["value_normalised"] = _normalised(norm, observations[0].value, mass)
        result["normalisation"] = norm.normalisation
    return result
