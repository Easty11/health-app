"""Injury-type-specific probe questions — the probe tier (DECISIONS_LOG #89/#90).

The app's role on return-from-injury is EDUCATE and PROBE, never CLEAR. This module
is the probe half: it elicits and dates injury-specific markers. It does not
interpret them into a clearance, a prescription, or a grade — and that boundary is
enforced by the tests in `tests/test_injury_probes.py`, not by this docstring.

Two structural rules, both tested:

  1. Every probe question is an ELICITATION string. It asks whether you can do a
     thing and whether it hurts. It never instructs you to load. "Can you do a
     single-leg heel raise, and does it hurt at the top?" is a probe. "Do 3x10 heel
     raises" is a prescribed progression and is rejected by the gate.
  2. Escalation is REFERRAL-ONLY. A worsening trend routes to a human. It never
     emits a grade, a severity score, a clearance, or a "safe to X" verdict.

Keying — why `injury_type` and not `body_part`: ledger entries carry `body_part` +
`signal_type` and no injury type (see seed_engine.py). Keying probes on body_part
alone would mis-serve them: the live right-hamstring entry refers S1-pattern
symptoms *to the calf*, so a "calf" body_part is not evidence of a gastroc strain.
`injury_type` is therefore read from an explicit optional field in the entry's JSON
`value`, alongside `trajectory` — no migration, same additive pattern. An entry with
no `injury_type`, or an unrecognised one, resolves to None and the caller falls back
to the existing generic soreness item (checkin_v2.derive_soreness_items) — never to
a fabricated question set.

Provenance: these question sets are AUTHORED, not drawn from a validated clinical
question bank. Exactly one injury type is seeded. Incompleteness is the shipped
state and is declared in PROBE_QUESTIONS_PROVENANCE — adding an injury type is a
manual authoring step, and the check-in machinery consumes it automatically.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

# Bump when a question set changes, so a recorded probe response can say which
# version elicited it. Mirrors TAXONOMY_VERSION.
PROBE_QUESTIONS_VERSION = "v0"

PROBE_QUESTIONS_PROVENANCE = (
    "authored; one worked example (gastroc strain); unvalidated; "
    "per-injury-type sets are incomplete by design."
)


@dataclass(frozen=True)
class ProbeQuestion:
    """A single elicitation. `question` must ask, never instruct — see module docstring."""
    key: str
    question: str


@dataclass(frozen=True)
class ProbeSet:
    """The probe questions and cadence for one injury type. Cadence is a property of
    the injury type and is versioned with the question set."""
    injury_type: str
    cadence_days: int
    questions: tuple[ProbeQuestion, ...]


# ── seeded question sets ───────────────────────────────────────────────────────
# ONE worked example. Do not pad this map from intuition — an unrecognised type
# falling back to generic soreness is the honest behaviour; a fabricated question
# set is a false-green. Adding a type means authoring its markers deliberately.

PROBE_SETS: dict[str, ProbeSet] = {
    "gastroc_strain": ProbeSet(
        injury_type="gastroc_strain",
        # Acute soft tissue: ~every 2 days. A daily "how's the calf" trains dismissal.
        cadence_days=2,
        questions=(
            ProbeQuestion(
                "walking_pain_trend",
                "Compared with your last check, is pain when walking better, "
                "the same, or worse?",
            ),
            ProbeQuestion(
                "single_leg_heel_raise",
                "Can you do a single-leg heel raise on that side, and does it "
                "hurt at the top?",
            ),
            ProbeQuestion(
                "forefoot_load_pain",
                "When weight goes through your forefoot, does it hurt?",
            ),
        ),
    ),
}


def resolve_probe_set(value: dict[str, Any] | None) -> ProbeSet | None:
    """The probe set for an injury ledger entry's JSON `value`, or None when the
    entry declares no `injury_type` or declares one with no authored set. None means
    "fall back to the generic soreness item" — never "invent questions"."""
    injury_type = str((value or {}).get("injury_type", "")).strip().lower()
    return PROBE_SETS.get(injury_type)


# ── cadence ────────────────────────────────────────────────────────────────────

def probe_anchor_date(value: dict[str, Any] | None, added_at: date | None) -> date | None:
    """The set-date a cadence counts from: the trajectory's `declared_on` if the entry
    declares one, else the ledger row's `added_at`."""
    declared = ((value or {}).get("trajectory") or {}).get("declared_on")
    if declared:
        try:
            return date.fromisoformat(str(declared)[:10])
        except ValueError:
            pass
    return added_at


def is_probe_due(
    value: dict[str, Any] | None, added_at: date | None, today: date
) -> bool:
    """Whether this injury's probe is due today — cadence counted in whole days from
    the entry's set-date, at the interval its injury type declares. False for an
    injury type with no authored set (nothing to ask), and before the set-date."""
    probe_set = resolve_probe_set(value)
    if probe_set is None:
        return False
    anchor = probe_anchor_date(value, added_at)
    if anchor is None:
        return False
    elapsed = (today - anchor).days
    if elapsed < 0:
        return False
    return elapsed % probe_set.cadence_days == 0


# ── escalation (referral-only) ─────────────────────────────────────────────────

# A worsening trend is not a severity reading. These messages route to a human and
# say nothing about how bad it is or what the user may now do. The referral-only
# gate in the test suite asserts that property against this module's whole output
# surface — keep new messages inside it.
_REFERRAL_TEXT = (
    "This isn't following the expected course — consider seeing someone about it."
)

_WORSE = "worse"

# How many consecutive worsening reports before referral surfaces. One bad day is
# noise; the point is a trend, not a reading.
_WORSENING_RUN = 2


@dataclass(frozen=True)
class ProbeEscalation:
    """A referral prompt. Carries no grade, severity, or clearance — by construction
    it has nowhere to put one."""
    injury_key: str
    reason: str
    referral: str = _REFERRAL_TEXT


def evaluate_escalation(
    injury_key: str, walking_pain_trend: list[str]
) -> ProbeEscalation | None:
    """Referral prompt when the walking-pain trend is climbing — `walking_pain_trend`
    is the ascending series of answers to that probe ("better"/"same"/"worse").

    Returns None when there's nothing to refer. Probe RESPONSES have no storage yet
    (daily_records stores soreness, not probe answers), so the caller supplies the
    series; this stays a pure function and the storage decision lands separately.
    """
    tail = [str(v).strip().lower() for v in walking_pain_trend[-_WORSENING_RUN:]]
    if len(tail) < _WORSENING_RUN or not all(v == _WORSE for v in tail):
        return None
    return ProbeEscalation(
        injury_key=injury_key,
        reason=f"walking pain reported worse {_WORSENING_RUN} probes running",
    )
