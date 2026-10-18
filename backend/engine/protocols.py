"""
Protocol registry (Q27 v1) — HOW a capability measurement is produced.

An observation's `protocol` (engine/observations.py) names one entry here. A protocol says which
INSTRUMENT is used, which declared measure(s) or ratio it produces a reading for, and what the
operator or the EP must actually do. It is the finer field behind the coarse `METHODS` / `SOURCES`
tags (which are unchanged): `method` says the occasion (a battery, a probe), `protocol` says the test.

Why this exists: a literature norm is only comparable to a reading taken the way the norm's authors
took it (same position, same make-versus-break contraction, same instrument). The reference gate
(engine/reference.py) therefore shows a literature band for an observation only when the observation's
protocol is one the norm was cited for. A reading with no protocol is evaluated as "internal".

The registry is code, validated at import: an unknown instrument, a target that does not resolve on
the taxonomy, or a duplicate key fails loudly rather than yielding a protocol nothing can record
against. No NordBord / isokinetic protocol is declared: the EP has not confirmed that instrument, and
declaring one first would invent the protocol the EP is later asked to describe.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import taxonomy

# Where the reading came from physically. Closed vocabulary; `observations.INSTRUMENTS` re-exports it.
# `bodyweight` is "no instrument": the athlete's own mass, counted (reps to fatigue).
INSTRUMENTS = frozenset({
    "hhd", "sphygmomanometer", "nordbord", "isokinetic", "bodyweight", "cable", "machine",
})

# A target is `(region_key, measure_key)` for a measure, or `("ratio", ratio_key)` for a ratio.
RATIO_TARGET = "ratio"
Target = tuple[str, str]


@dataclass(frozen=True)
class Protocol:
    key: str
    instrument: str
    targets: tuple[Target, ...]            # the brief's `measure_keys`
    description: str                       # what the operator / EP must do
    citation_pmids: tuple[str, ...] = ()

    def is_ratio_target(self, target: Target) -> bool:
        return target[0] == RATIO_TARGET


_SHOULDER_ROT_TARGETS: tuple[Target, ...] = (
    ("shoulder_er", "hhd_force_n"), ("shoulder_ir", "hhd_force_n"), (RATIO_TARGET, "er_ir"),
)

_PROTOCOLS: tuple[Protocol, ...] = (
    Protocol(
        "hhd_shoulder_rot_seated_neutral_make", "hhd", _SHOULDER_ROT_TARGETS,
        "Seated, arm at the side (0 deg abduction), elbow 90 deg, 5 s maximal isometric MAKE test, "
        "dynamometer proximal to the wrist styloid, best of two trials (Riemann 2010; Westrick 2013 "
        "neutral). Westrick's Methods confirm the 5 s make test, two trials and the dynamometer "
        "placement; the Riemann Methods were not reachable.",
        ("20850997", "24381696"),
    ),
    Protocol(
        "hhd_shoulder_rot_seated_30_30_30_make", "hhd", _SHOULDER_ROT_TARGETS,
        "Seated, 30 deg abduction / 30 deg scaption / 30 deg diagonal, elbow 90 deg, 5 s maximal "
        "isometric MAKE test, dynamometer proximal to the wrist styloid, best of two trials "
        "(Riemann 2010 - the position Riemann recommends).",
        ("20850997",),
    ),
    Protocol(
        "hhd_shoulder_rot_prone_90_90_make", "hhd", _SHOULDER_ROT_TARGETS,
        "Prone, 90 deg abduction, elbow 90 deg, 5 s maximal isometric MAKE test, dynamometer proximal "
        "to the wrist styloid, best of two trials (Riemann 2010).",
        ("20850997",),
    ),
    Protocol(
        "hhd_shoulder_rot_supine_45abd_make", "hhd", _SHOULDER_ROT_TARGETS,
        "Supine, 45 deg abduction, 0 deg flexion, bolster under the arm, 5 s maximal isometric MAKE "
        "test, best of two trials (Westrick 2013).",
        ("24381696",),
    ),
    Protocol(
        "hhd_hip_add_abd_sidelying_eccentric", "hhd",
        (("hip_adduction", "hhd_force_n"), ("hip_abduction", "hhd_force_n"), (RATIO_TARGET, "add_abd")),
        "Side-lying eccentric (BREAK) test with a hand-held dynamometer, as in Mosler 2016 (the Thorborg "
        "protocol attribution is UNCONFIRMED: the Mosler Methods were not reachable).",
        ("28185809",),
    ),
    Protocol(
        "hhd_squeeze_supine_45_make", "hhd",
        (("hip_adduction", "squeeze_hhd_n"),),
        "Supine, 45 deg hip flexion, dynamometer between the knees, maximal isometric squeeze "
        "(Mosler 2016).",
        ("28185809",),
    ),
    Protocol(
        "sphyg_squeeze_supine_45", "sphygmomanometer",
        (("hip_adduction", "squeeze_mmhg"),),
        "Supine, 45 deg hip flexion, cuff between the knees pre-inflated per Delahunt 2011, three "
        "repetitions (whether Delahunt analysed the best or the mean is UNCONFIRMED: Methods not "
        "reachable). CEILING: the "
        "cuff maxes at about 300 mmHg (Toohey 2017) - a reading at the cuff maximum is censored, not a "
        "value; record it with confidence=guessing.",
        ("21429785", "28891759"),
    ),
    Protocol(
        "heel_rise_10deg_incline_to_fatigue", "bodyweight",
        (("ankle_plantarflexion", "sl_heel_raise_reps"),),
        "Single-leg heel rises to fatigue standing on a 10 deg incline (Hebert-Losier 2017). "
        "Methods from the paper's accepted manuscript: metronome at 60 cycles/min; lift the heel as high "
        "as possible with the knee and trunk straight; fingertip support on a wall at shoulder height "
        "allowed; habitual shoes; the test ends when the heel cannot be lifted, the pace, knee angle or "
        "trunk position cannot be held, or the wall is needed for assistance (one verbal reminder "
        "first). Cadence confirmed from the accepted manuscript, not the published PDF.",
        ("28886865",),
    ),
    Protocol(
        "hhd_knee_flexion_prone_90_make", "hhd",
        (("knee_flexion", "hhd_force_n"),),
        "Prone, knee 90 deg, 5 s maximal isometric make, dynamometer proximal to the ankle, per side. "
        "No literature norm is admitted: evaluated against the user's own baseline (internal).",
        (),
    ),
    Protocol(
        "slhb_to_fatigue", "bodyweight",
        (("knee_flexion", "slhb_reps"),),
        "Single-leg hamstring bridge, per side: supine, one heel on a 60 cm box, test knee at about 20 deg "
        "flexion, arms crossed over the chest, the other leg held vertical; push through the heel, lift the "
        "buttocks, touch the ground and extend the hip to 0 deg without resting; repetitions to failure "
        "(one warning when form is lost, stop at the next technique fault). No metronome cadence in the "
        "Freckleton 2014 protocol. No literature norm is admitted: evaluated against the user's own "
        "baseline (internal); the paper is cited as grounding only.",
        ("23918443",),
    ),
)


def validate_protocol(p: Protocol) -> None:
    """Raise ValueError unless `p` is coherent against the live taxonomy."""
    if not p.key:
        raise ValueError("Protocol: key is empty")
    if p.instrument not in INSTRUMENTS:
        raise ValueError(f"Protocol {p.key!r}: instrument {p.instrument!r} is not one of {sorted(INSTRUMENTS)}")
    if not p.targets:
        raise ValueError(f"Protocol {p.key!r}: no targets")
    if len(set(p.targets)) != len(p.targets):
        raise ValueError(f"Protocol {p.key!r}: a target is declared twice")
    if not p.description.strip():
        raise ValueError(f"Protocol {p.key!r}: description is empty")
    for region_key, name in p.targets:
        if region_key == RATIO_TARGET:
            if taxonomy.ratio_by_key(name) is None:
                raise ValueError(f"Protocol {p.key!r}: ratio target {name!r} is not declared")
        elif taxonomy.measure_for(region_key, name) is None:
            raise ValueError(
                f"Protocol {p.key!r}: target ({region_key!r}, {name!r}) is not a declared measure"
            )


def _validate_declared() -> dict[str, Protocol]:
    seen: dict[str, Protocol] = {}
    for p in _PROTOCOLS:
        if p.key in seen:
            raise ValueError(f"Protocol {p.key!r} is declared twice")
        validate_protocol(p)
        seen[p.key] = p
    return seen


_BY_KEY: dict[str, Protocol] = _validate_declared()


def all_protocols() -> tuple[Protocol, ...]:
    return _PROTOCOLS


def by_key(key: str) -> Protocol | None:
    return _BY_KEY.get(key)


def covers(protocol_key: str, target: Target) -> bool:
    """True when `protocol_key` is a declared protocol that produces `target`."""
    p = _BY_KEY.get(protocol_key)
    return p is not None and target in p.targets


def protocol_as_dict(p: Protocol) -> dict:
    return {
        "key": p.key,
        "instrument": p.instrument,
        "targets": [{"region": r, "measure": m} if r != RATIO_TARGET else {"ratio": m}
                    for r, m in p.targets],
        "description": p.description,
        "citation_pmids": list(p.citation_pmids),
    }
