"""
Norms registry (Q27 v1) — published reference values, held as DATA for display.

Loads `reference/capability_norms_v1.json` and validates it at import. A norm is a citation-backed
number for one declared target (a measure, or a ratio) under one or more declared protocols. It is
shown as a BAND by `engine/reference.py`, and only when an observation's protocol matches.

G3 (amended, Q27 v1 R8): NO NUMBER FIRES A VERDICT. This module therefore exposes lookup and
serialisation and nothing else - there is no comparison function here, no method that takes a
reading, and nothing that returns a flag. Norm values never appear as Python constants: they are
JSON, edited by hand with a citation, and pinned by `tests/test_protocols_norms.py`. That test also
scans this module and the gate for ordering comparisons and verdict vocabulary (the section 7
boundary, mechanised), so the module is written without ordering operators on purpose: positivity
and ordering checks below go through `abs` / `sorted` / `==`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import protocols as protocols_mod
from . import taxonomy

_NORMS_PATH = Path(__file__).resolve().parent.parent / "reference" / "capability_norms_v1.json"

# What a per-body-mass norm is divided by. Closed vocabulary.
#   per_body_mass_kg - a "<unit>/kg" norm: reading (unit) divided by body mass in kg.
#   per_body_weight  - a dimensionless norm: reading (N) divided by body weight (mass x g).
NORMALISATIONS = frozenset({"per_body_mass_kg", "per_body_weight"})
VERIFIED_AGAINST = frozenset({"full_text", "abstract_only"})
_VALUE_SHAPES = (("mean", "sd"), ("median",), ("low", "high"))

Target = tuple[str, str]


@dataclass(frozen=True)
class Norm:
    id: str
    target: Target
    protocols: tuple[str, ...]
    unit: str
    value: dict[str, float]
    population: str
    n: int
    citation: dict[str, Any]
    verified_against: str
    normalisation: str | None = None
    notes: str = ""
    unit_note: str = ""
    also_cited: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    kind: str = "reference"


def _target_of(raw: dict, where: str) -> Target:
    if "ratio" in raw:
        return (protocols_mod.RATIO_TARGET, raw["ratio"])
    if "region" in raw and "measure" in raw:
        return (raw["region"], raw["measure"])
    raise ValueError(f"{where}: target must be {{region, measure}} or {{ratio}}, got {raw!r}")


def _target_unit(target: Target) -> str:
    """The unit a norm's own unit must derive from; 'ratio' for a ratio target."""
    region_key, name = target
    if region_key == protocols_mod.RATIO_TARGET:
        return "ratio"
    return taxonomy.measure_for(region_key, name).unit


def _validate_value(where: str, value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"{where}: value must be an object")
    shapes = [s for s in _VALUE_SHAPES if set(value) == set(s)]
    if len(shapes) != 1:
        raise ValueError(f"{where}: value must be one of {list(_VALUE_SHAPES)}, got keys {sorted(value)}")
    for k, v in value.items():
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{where}: value[{k!r}] must be numeric, got {v!r}")
    if set(value) == {"low", "high"} and sorted((value["low"], value["high"])) != [value["low"], value["high"]]:
        raise ValueError(f"{where}: low and high are the wrong way round")
    return {k: float(v) for k, v in value.items()}


def _validate_unit(where: str, target: Target, unit: str, normalisation: str | None) -> None:
    base = _target_unit(target)
    is_ratio_target = target[0] == protocols_mod.RATIO_TARGET
    if normalisation is not None and normalisation not in NORMALISATIONS:
        raise ValueError(f"{where}: normalisation {normalisation!r} is not one of {sorted(NORMALISATIONS)}")
    if is_ratio_target:
        if unit != "ratio" or normalisation is not None:
            raise ValueError(f"{where}: a ratio target needs unit 'ratio' and no normalisation")
        return
    if unit == base:
        if normalisation is not None:
            raise ValueError(f"{where}: a norm in the measure's own unit takes no normalisation")
    elif unit == f"{base}/kg":
        if normalisation != "per_body_mass_kg":
            raise ValueError(f"{where}: unit {unit!r} needs normalisation 'per_body_mass_kg'")
    elif unit == "ratio":
        if normalisation != "per_body_weight" or base != "N":
            raise ValueError(
                f"{where}: unit 'ratio' on a measure needs normalisation 'per_body_weight' and a force (N) measure"
            )
    else:
        raise ValueError(
            f"{where}: unit {unit!r} is not the measure's unit {base!r}, '{base}/kg' or 'ratio'"
        )


def _load(path: Path = _NORMS_PATH) -> tuple[tuple[Norm, ...], dict[tuple[Target, str], Norm]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    norms: list[Norm] = []
    by_pair: dict[tuple[Target, str], Norm] = {}
    ids: set[str] = set()
    for rec in raw["norms"]:
        nid = rec.get("id") or ""
        where = f"norm {nid!r}"
        if not nid or nid in ids:
            raise ValueError(f"{where}: id is empty or duplicated")
        ids.add(nid)
        if rec.get("kind") != "reference":
            raise ValueError(f"{where}: kind must be 'reference'")
        target = _target_of(rec.get("target") or {}, where)
        if target[0] == protocols_mod.RATIO_TARGET:
            if taxonomy.ratio_by_key(target[1]) is None:
                raise ValueError(f"{where}: ratio {target[1]!r} is not declared")
        elif taxonomy.measure_for(*target) is None:
            raise ValueError(f"{where}: target {target!r} is not a declared measure")
        _validate_unit(where, target, rec.get("unit"), rec.get("normalisation"))
        value = _validate_value(where, rec.get("value"))
        if not rec.get("population"):
            raise ValueError(f"{where}: population is required")
        n = rec.get("n")
        if isinstance(n, bool) or not isinstance(n, int) or n == 0 or abs(n) != n:
            raise ValueError(f"{where}: n must be a positive integer")
        cit = rec.get("citation") or {}
        if not cit.get("pmid") or not cit.get("doi"):
            raise ValueError(f"{where}: citation needs a pmid and a doi")
        if rec.get("verified_against") not in VERIFIED_AGAINST:
            raise ValueError(f"{where}: verified_against must be one of {sorted(VERIFIED_AGAINST)}")
        protos = tuple(rec.get("protocols") or ())
        if not protos:
            raise ValueError(f"{where}: no protocols")
        for pk in protos:
            if protocols_mod.by_key(pk) is None:
                raise ValueError(f"{where}: protocol {pk!r} is not declared")
            if not protocols_mod.covers(pk, target):
                raise ValueError(f"{where}: protocol {pk!r} does not produce target {target!r}")
        norm = Norm(
            id=nid, target=target, protocols=protos, unit=rec["unit"], value=value,
            population=rec["population"], n=n, citation=dict(cit),
            verified_against=rec["verified_against"], normalisation=rec.get("normalisation"),
            notes=rec.get("notes", ""), unit_note=rec.get("unit_note", ""),
            also_cited=tuple(rec.get("also_cited", ())),
        )
        for pk in protos:
            if (target, pk) in by_pair:
                raise ValueError(f"{where}: ({target!r}, {pk!r}) is already covered by {by_pair[(target, pk)].id!r}")
            by_pair[(target, pk)] = norm
        norms.append(norm)
    return tuple(norms), by_pair


_NORMS, _BY_PAIR = _load()


def all_norms() -> tuple[Norm, ...]:
    return _NORMS


def norm_for(target: Target, protocol: str) -> Norm | None:
    """The norm cited for `target` under `protocol`, or None. A lookup, not a judgement."""
    return _BY_PAIR.get((tuple(target), protocol))


def norms_for_target(target: Target) -> tuple[Norm, ...]:
    return tuple(n for n in _NORMS if n.target == tuple(target))


def norm_as_dict(norm: Norm) -> dict[str, Any]:
    t = norm.target
    return {
        "id": norm.id,
        "target": {"ratio": t[1]} if t[0] == protocols_mod.RATIO_TARGET
                  else {"region": t[0], "measure": t[1]},
        "protocols": list(norm.protocols),
        "kind": norm.kind,
        "unit": norm.unit,
        "normalisation": norm.normalisation,
        "value": dict(norm.value),
        "population": norm.population,
        "n": norm.n,
        "citation": dict(norm.citation),
        "also_cited": [dict(c) for c in norm.also_cited],
        "verified_against": norm.verified_against,
        "unit_note": norm.unit_note,
        "notes": norm.notes,
    }
