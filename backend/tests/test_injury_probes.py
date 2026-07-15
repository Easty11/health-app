"""The probe tier's structural boundary (DECISIONS_LOG #85).

Two hard gates live here. They are the reason the probe tier is allowed to exist:
the app may elicit and educate, but must not prescribe or clear. That boundary is
enforced here rather than in prose so a later edit cannot quietly cross it.

Each gate carries NEGATIVE CONTROLS — strings the gate MUST catch. A gate that
cannot fail reports zero forever and is worth less than no gate at all
(FEEDBACK 10, false-green instruments). The controls prove the detector bites.
"""
from dataclasses import asdict
from datetime import date

import pytest

from injury_probes import (
    PROBE_QUESTIONS_PROVENANCE,
    PROBE_QUESTIONS_VERSION,
    PROBE_SETS,
    evaluate_escalation,
    is_probe_due,
    probe_anchor_date,
    resolve_probe_set,
)

# ── gate 1: elicitation-only ───────────────────────────────────────────────────

import re

# A rep/set scheme is a prescribed progression however it is phrased.
_REP_SCHEME = re.compile(r"\d+\s*(?:x|×)\s*\d+|\b\d+\s+(?:reps?|sets?)\b|\bsets? of\b", re.I)

# Imperative loading verbs — caught only at the START of a sentence or clause, which
# is what makes them imperatives. "Can you DO a heel raise" is an elicitation and must
# pass; "DO 3x10 heel raises" is an instruction and must not. A bare word-boundary
# search for these verbs would reject the module's own valid questions.
_IMPERATIVE_VERBS = (
    "do", "perform", "complete", "start", "begin", "progress", "increase", "add",
    "build", "load", "lift", "push", "repeat", "hold", "work up", "try",
)
_IMPERATIVE = re.compile(
    r"(?:^|[.;:!?]\s+)(?:" + "|".join(_IMPERATIVE_VERBS) + r")\b", re.I
)


def _prescribes(text: str) -> bool:
    """True when `text` instructs the user to load, rather than asking them."""
    return bool(_REP_SCHEME.search(text) or _IMPERATIVE.search(text))


@pytest.mark.parametrize(
    "bad",
    [
        "Do 3x10 heel raises",
        "Do 3×10 heel raises",
        "Perform 3 sets of 12 calf raises",
        "Start with 2x15 and progress one notch",
        "Increase the load to 20kg this week",
        "Load the calf daily.",
        "Can you heel raise? Progress to single-leg when it settles.",
    ],
)
def test_prescription_detector_catches_prescriptions(bad):
    """NEGATIVE CONTROL — the gate must bite. If this passes vacuously, gate 2 below
    proves nothing."""
    assert _prescribes(bad), f"detector failed to catch a prescription: {bad!r}"


@pytest.mark.parametrize(
    "good",
    [
        "Can you do a single-leg heel raise on that side, and does it hurt at the top?",
        "When weight goes through your forefoot, does it hurt?",
        "Compared with your last check, is pain when walking better, the same, or worse?",
    ],
)
def test_prescription_detector_permits_elicitations(good):
    """NEGATIVE CONTROL, other direction — a detector that rejects everything would
    pass the gate below while making the seed unauthorable."""
    assert not _prescribes(good), f"detector wrongly flagged an elicitation: {good!r}"


def test_every_probe_question_is_elicitation_only():
    """HARD GATE — no probe question may contain an imperative loading instruction.
    The probe asks whether you can and whether it hurts; it never tells you to load."""
    for injury_type, probe_set in PROBE_SETS.items():
        for q in probe_set.questions:
            assert not _prescribes(q.question), (
                f"{injury_type}.{q.key} prescribes loading: {q.question!r}"
            )


def test_every_probe_question_actually_asks():
    """An elicitation elicits. Guards the gate above from being satisfied by a
    declarative statement that merely avoids imperative verbs."""
    for injury_type, probe_set in PROBE_SETS.items():
        for q in probe_set.questions:
            assert q.question.strip().endswith("?"), (
                f"{injury_type}.{q.key} is not a question: {q.question!r}"
            )


# ── gate 2: referral-only ──────────────────────────────────────────────────────

# Escalation routes to a human. It does not replace one — so it may never grade,
# score, clear, or authorise.
_FORBIDDEN_VERDICT = re.compile(
    r"\bgrade\s*[0-9i]|\bgrade\b|\bseverity\b|\bsevere\b|\bmoderate\b|\bmild\b"
    r"|\bcleared?\b|\bclear to\b|\bsafe to\b|\bready to\b|\bgood to go\b"
    r"|\bfit to\b|\byou may now\b|\bscore\b|\bout for\b|\bweeks? off\b",
    re.I,
)


def _emits_verdict(text: str) -> bool:
    return bool(_FORBIDDEN_VERDICT.search(text))


@pytest.mark.parametrize(
    "bad",
    [
        "You are cleared to run",
        "This looks like a grade 2 strain",
        "Severity: moderate",
        "Safe to return to sport",
        "Readiness score 7 — good to go",
        "You're fit to train tomorrow",
        "Expect to be out for 3 weeks",
    ],
)
def test_verdict_detector_catches_verdicts(bad):
    """NEGATIVE CONTROL — the referral gate must bite."""
    assert _emits_verdict(bad), f"detector failed to catch a verdict: {bad!r}"


def test_escalation_is_referral_only():
    """HARD GATE — escalation output never emits a grade, clearance, severity, or a
    'safe to X' verdict. It routes to a human; it does not replace one."""
    esc = evaluate_escalation("calf_left", ["same", "worse", "worse"])
    assert esc is not None
    for field, value in asdict(esc).items():
        if isinstance(value, str):
            assert not _emits_verdict(value), (
                f"escalation.{field} emits a verdict: {value!r}"
            )


def test_escalation_refers_to_a_human():
    """The gate above is satisfied by an empty string. This is what makes the
    escalation an escalation."""
    esc = evaluate_escalation("calf_left", ["worse", "worse"])
    assert esc is not None
    assert "seeing someone" in esc.referral


def test_escalation_requires_a_trend_not_a_reading():
    """One bad report is noise, not a trend — no referral on a single 'worse'."""
    assert evaluate_escalation("calf_left", ["worse"]) is None
    assert evaluate_escalation("calf_left", ["worse", "same"]) is None
    assert evaluate_escalation("calf_left", []) is None
    assert evaluate_escalation("calf_left", ["better", "better"]) is None


# ── seed + fallback ────────────────────────────────────────────────────────────

def test_exactly_one_injury_type_is_seeded():
    """Incompleteness is the shipped state. If this fails because a type was added,
    that is fine — update it deliberately, and check the new set's provenance."""
    assert set(PROBE_SETS) == {"gastroc_strain"}


def test_provenance_declares_its_own_incompleteness():
    assert PROBE_QUESTIONS_VERSION == "v0"
    assert "unvalidated" in PROBE_QUESTIONS_PROVENANCE
    assert "incomplete by design" in PROBE_QUESTIONS_PROVENANCE


def test_gastroc_seed_has_the_specced_markers():
    keys = [q.key for q in PROBE_SETS["gastroc_strain"].questions]
    assert keys == ["walking_pain_trend", "single_leg_heel_raise", "forefoot_load_pain"]


def test_unrecognised_injury_type_falls_back_rather_than_fabricating():
    """An unknown or absent injury type resolves to None — the caller falls back to
    the generic soreness item. It must never borrow another type's questions."""
    assert resolve_probe_set({"injury_type": "acl_rupture"}) is None
    assert resolve_probe_set({"body_part": "calf"}) is None      # body_part is not a type
    assert resolve_probe_set({}) is None
    assert resolve_probe_set(None) is None


def test_calf_body_part_alone_does_not_summon_gastroc_probes():
    """The live right-hamstring entry refers S1-pattern symptoms TO the calf. A calf
    body_part is therefore not evidence of a gastroc strain, and must not be keyed on."""
    referred = {"body_part": "calf", "side": "right", "signal_type": "mechanical"}
    assert resolve_probe_set(referred) is None


# ── cadence ────────────────────────────────────────────────────────────────────

_GASTROC = {"injury_type": "gastroc_strain", "body_part": "calf", "side": "left"}


def test_cadence_counts_from_the_trajectory_declared_on_when_present():
    value = dict(_GASTROC, trajectory={"shape": "settling", "declared_on": "2026-07-10"})
    assert probe_anchor_date(value, date(2026, 7, 1)) == date(2026, 7, 10)


def test_cadence_falls_back_to_added_at_without_a_trajectory():
    assert probe_anchor_date(_GASTROC, date(2026, 7, 10)) == date(2026, 7, 10)


def test_probe_is_due_every_two_days_from_the_set_date_not_daily():
    """Acute soft tissue ~every 2 days. A daily fire trains dismissal."""
    added = date(2026, 7, 10)
    due = [
        d for d in range(0, 7)
        if is_probe_due(_GASTROC, added, date(2026, 7, 10 + d))
    ]
    assert due == [0, 2, 4, 6]


def test_probe_is_not_due_before_the_set_date():
    assert is_probe_due(_GASTROC, date(2026, 7, 10), date(2026, 7, 9)) is False


def test_cadence_is_a_property_of_the_injury_type():
    assert PROBE_SETS["gastroc_strain"].cadence_days == 2


def test_injury_type_without_an_authored_set_is_never_due():
    """Nothing authored means nothing to ask — not a daily generic fire."""
    assert is_probe_due({"body_part": "calf"}, date(2026, 7, 10), date(2026, 7, 10)) is False
