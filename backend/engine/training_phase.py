"""Training-phase ledger — the exposure engine's DOING-NOW axis (Q112, #270).

Concern-split from `profile.py`. The profile is the standing *building toward*; a phase is
the current *doing now* — a probe posture, an optional capacity allow-list, an optional
phase-scoped A/B microcycle — recorded as an append-only, exactly-one-open-per-user ledger
structurally identical to `cbti_blocks`.

Boundaries this module holds (see the Q112 brief / #270):
  • The engine NEVER branches on `label` — a name, not a control.
  • `Capacity` is a MOVEMENT-QUALITY axis only (mobility/stability/strength/power/endurance).
    Aerobic / VO2 / recovery posture is training-load, not a capacity; a phase RECORDS it in
    `intent` prose and nothing gates it. `capacities` is never extended with energy-system
    members.
  • The ledger is HISTORY + CURRENT, never a plan: no future-dated `entered_on`, no
    auto-close, `review_on` is a prompt. The offseason is authored one phase at a time.

Provenance domains are IMPORTED, never redeclared: `ASSERTED_BY_VALUES` (#227) from
`engine.profile`, `SOURCE_VALUES` (#230) from `routers.knowledge`. Slot validation reuses
`_slot_int` / `resolve_capacity`. Local-day is the single-source `_local_day()` (#Q42).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

import models
from load_metrics import _local_day
from . import taxonomy
from .profile import (
    ASSERTED_BY_VALUES,
    _MAX_SLOT_MINUTES,
    _MIN_SLOT_MINUTES,
    _slot_int,
)

# Imported, not redeclared (#230). `routers.knowledge` does not import this module, so the
# import is acyclic; it is the canonical home for the write-source domain.
from routers.knowledge import SOURCE_VALUES

# ── domains local to the phase ledger ────────────────────────────────────────
PROBE_POSTURE_VALUES = ("suppressed", "held")

# Microcycle bounds. `sub_cycle_days` is one A/B leg's length; a leg shorter than 3 days is
# not a training block and longer than 28 (four weeks) is a mesocycle, not a sub-cycle.
_MIN_SUB_CYCLE_DAYS = 3
_MAX_SUB_CYCLE_DAYS = 28
_MAX_SUB_CYCLES = 4
# `sessions_per_cycle` is per sub-cycle (NOT per week — a new token, no cross-store rename).
# 0 = a declared-but-dormant slot (distinct from an absent one), mirroring
# `weekly_template.sessions_per_week`; the ceiling admits up-to-daily across the longest
# 28-day sub-cycle.
_MIN_SESSIONS_PER_CYCLE = 0
_MAX_SESSIONS_PER_CYCLE = 28

_MICRO_SLOT_FIELDS = ("capacity", "sessions_per_cycle", "minutes")


class NoOpenPhase(Exception):
    """Raised by `close_phase` when the user is already at zero-open (baseline). The router
    turns it into a 404 — closing nothing is an error, not a silent no-op (mirrors the
    already-inactive 409 on injury/schedule resolution)."""


# --------------------------------------------------------------------------- #
# Validation (fail-closed) — pure, no session touched.                        #
# --------------------------------------------------------------------------- #

def _parse_iso_date(value: Any, field: str) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD), got {type(value).__name__}")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must be an ISO date (YYYY-MM-DD), got {value!r}")


def validate_microcycle(value: Any) -> dict[str, Any]:
    """Validate a phase-scoped A/B microcycle, raising ValueError with a field-located
    message. Returned UNCHANGED, never canonicalised — PUT/GET is byte-identical (mirrors
    `validate_weekly_template`).

    Shape: `{"sub_cycle_days": int, "sub_cycles": [{"label"?: str, "slots": [slot, ...]}]}`.
    A slot is the `weekly_template` slot shape EXCEPT the count key is `sessions_per_cycle`.
    The duplicate-capacity check is PER-SUB-CYCLE, not template-wide: the same capacity in A
    and B at different doses is the point; a duplicate WITHIN one sub-cycle is the error.
    """
    if not isinstance(value, dict):
        raise ValueError("microcycle must be an object with 'sub_cycle_days' and 'sub_cycles'")
    extra = sorted(set(value) - {"sub_cycle_days", "sub_cycles"})
    if extra:
        raise ValueError(f"microcycle: unknown field(s) {extra}")

    scd = value.get("sub_cycle_days")
    if isinstance(scd, bool) or not isinstance(scd, int):
        raise ValueError(
            f"microcycle.sub_cycle_days must be an integer, got {type(scd).__name__}"
        )
    if not (_MIN_SUB_CYCLE_DAYS <= scd <= _MAX_SUB_CYCLE_DAYS):
        raise ValueError(
            f"microcycle.sub_cycle_days must be {_MIN_SUB_CYCLE_DAYS}-{_MAX_SUB_CYCLE_DAYS}, got {scd}"
        )

    sub_cycles = value.get("sub_cycles")
    if not isinstance(sub_cycles, list):
        raise ValueError("microcycle.sub_cycles must be a list")
    if not (1 <= len(sub_cycles) <= _MAX_SUB_CYCLES):
        raise ValueError(
            f"microcycle.sub_cycles must have 1-{_MAX_SUB_CYCLES} entries, got {len(sub_cycles)}"
        )

    for j, sc in enumerate(sub_cycles):
        if not isinstance(sc, dict):
            raise ValueError(f"microcycle.sub_cycles[{j}] must be an object")
        extra = sorted(set(sc) - {"label", "slots"})
        if extra:
            raise ValueError(f"microcycle.sub_cycles[{j}]: unknown field(s) {extra}")
        label = sc.get("label")
        if label is not None and not isinstance(label, str):
            raise ValueError(f"microcycle.sub_cycles[{j}].label must be a string or null")
        slots = sc.get("slots")
        if not isinstance(slots, list) or not slots:
            raise ValueError(f"microcycle.sub_cycles[{j}].slots must be a non-empty list")

        where = f"microcycle.sub_cycles[{j}].slots"
        seen: dict[taxonomy.Capacity, int] = {}
        for i, slot in enumerate(slots):
            if not isinstance(slot, dict):
                raise ValueError(f"{where}[{i}] must be an object")
            unknown = sorted(set(slot) - set(_MICRO_SLOT_FIELDS))
            if unknown:
                raise ValueError(f"{where}[{i}]: unknown field(s) {unknown}")
            cap = taxonomy.resolve_capacity(slot.get("capacity"))
            if cap is None:
                raise ValueError(
                    f"{where}[{i}].capacity: unknown capacity {slot.get('capacity')!r} "
                    f"— one of {taxonomy.capacity_tokens()}"
                )
            if cap in seen:                       # per-sub-cycle only
                raise ValueError(
                    f"{where}[{i}].capacity: duplicate capacity {cap.name} within this "
                    f"sub-cycle (already at [{seen[cap]}]) — cross-sub-cycle repeats are allowed"
                )
            seen[cap] = i
            _slot_int(slot, "sessions_per_cycle",
                      _MIN_SESSIONS_PER_CYCLE, _MAX_SESSIONS_PER_CYCLE, i, where=where)
            _slot_int(slot, "minutes", _MIN_SLOT_MINUTES, _MAX_SLOT_MINUTES, i, where=where)

    return value


def validate_training_phase(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a phase-open payload, raising ValueError (→ 422) on any fault. Returns a
    NORMALISED dict ready for `models.TrainingPhase(**...)`: dates parsed to `date`,
    `capacities`/`microcycle` kept BYTE-IDENTICAL (stored verbatim).

    The monotonic-history check (`entered_on >= the prior open row's entered_on`) needs the
    ledger and lives in `open_phase`; every check here is pure. `close_prior_reason` is an
    open-path control, not a phase field — strip it before calling this.
    """
    label = payload.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ValueError("label is required — a non-empty string")

    intent = payload.get("intent")
    if intent is not None and not isinstance(intent, str):
        raise ValueError("intent must be a string or null")

    probe_posture = payload.get("probe_posture")
    if probe_posture is None:
        raise ValueError(f"probe_posture is required — one of {list(PROBE_POSTURE_VALUES)}")
    if probe_posture not in PROBE_POSTURE_VALUES:
        raise ValueError(
            f"probe_posture: unknown value {probe_posture!r} — one of {list(PROBE_POSTURE_VALUES)}"
        )

    capacities = payload.get("capacities")
    if capacities is not None:
        if not isinstance(capacities, list):
            raise ValueError("capacities must be a list of capacity tokens or null")
        seen: set[str] = set()
        for tok in capacities:
            cap = taxonomy.resolve_capacity(tok)
            if cap is None:
                raise ValueError(
                    f"capacities: unknown capacity {tok!r} — one of {taxonomy.capacity_tokens()}"
                )
            if cap.value in seen:
                raise ValueError(f"capacities: duplicate capacity {tok!r}")
            seen.add(cap.value)

    microcycle = payload.get("microcycle")
    if microcycle is not None:
        validate_microcycle(microcycle)

    # `entered_on` defaults to the operator-local day (S7) when omitted — the common case
    # is "open this phase now". A supplied value may backdate within the allowed window.
    entered_raw = payload.get("entered_on")
    entered_on = _local_day() if entered_raw is None else _parse_iso_date(entered_raw, "entered_on")
    if entered_on > _local_day():
        raise ValueError(
            "entered_on must not be in the future (operator-local day) — a future-dated "
            "phase is a scheduler, which the ledger is not"
        )

    review_on_raw = payload.get("review_on")
    review_on: date | None = None
    if review_on_raw is not None:
        review_on = _parse_iso_date(review_on_raw, "review_on")
        if review_on < entered_on:
            raise ValueError("review_on must be on or after entered_on")

    asserted_by = payload.get("asserted_by")
    if asserted_by not in ASSERTED_BY_VALUES:
        raise ValueError(
            f"asserted_by is required — one of {list(ASSERTED_BY_VALUES)}, got {asserted_by!r}"
        )
    asserted_on = _parse_iso_date(payload.get("asserted_on"), "asserted_on")

    source = payload.get("source")
    if source not in SOURCE_VALUES:
        raise ValueError(f"source is required — one of {list(SOURCE_VALUES)}, got {source!r}")

    return {
        "label": label,
        "intent": intent,
        "probe_posture": probe_posture,
        "capacities": capacities,          # verbatim
        "microcycle": microcycle,          # verbatim
        "entered_on": entered_on,
        "review_on": review_on,
        "asserted_by": asserted_by,
        "asserted_on": asserted_on,
        "source": source,
    }


# --------------------------------------------------------------------------- #
# Reads.                                                                       #
# --------------------------------------------------------------------------- #

def current_training_phase(db: Session, user_id: int) -> models.TrainingPhase | None:
    """The one open phase (`closed_on IS NULL`), or None = baseline. At most one by the
    exactly-one-open invariant; newest-first is a defence, not a need."""
    return (
        db.query(models.TrainingPhase)
        .filter_by(user_id=user_id, closed_on=None)
        .order_by(models.TrainingPhase.entered_on.desc(), models.TrainingPhase.id.desc())
        .first()
    )


def phase_at(db: Session, user_id: int, d: date) -> models.TrainingPhase | None:
    """The phase in force on day `d`, over the HALF-OPEN interval `entered_on <= d <
    closed_on` (`closed_on NULL` = open, no upper bound). On a same-day close/open boundary
    the successor wins: the predecessor's `closed_on == d` fails `d < closed_on`, while the
    successor's `entered_on == d` passes. `None` before the first phase."""
    rows = (
        db.query(models.TrainingPhase)
        .filter(
            models.TrainingPhase.user_id == user_id,
            models.TrainingPhase.entered_on <= d,
        )
        .order_by(models.TrainingPhase.entered_on.desc(), models.TrainingPhase.id.desc())
        .all()
    )
    for row in rows:
        if row.closed_on is None or d < row.closed_on:
            return row
    return None


def review_due(phase: models.TrainingPhase | None, *, on: date | None = None) -> bool:
    """Is the phase's `review_on` prompt due on the operator-local day? A prompt, never a
    transition (#228) — the operator opens the next phase or does nothing."""
    if phase is None or phase.review_on is None:
        return False
    return phase.review_on <= (on or _local_day())


def phase_to_dict(phase: models.TrainingPhase | None, *, on: date | None = None) -> dict[str, Any] | None:
    if phase is None:
        return None
    return {
        "id": phase.id,
        "label": phase.label,
        "intent": phase.intent,
        "probe_posture": phase.probe_posture,
        "capacities": phase.capacities,          # verbatim
        "microcycle": phase.microcycle,          # verbatim
        "entered_on": str(phase.entered_on),
        "review_on": str(phase.review_on) if phase.review_on else None,
        "closed_on": str(phase.closed_on) if phase.closed_on else None,
        "close_reason": phase.close_reason,
        "asserted_by": phase.asserted_by,
        "asserted_on": str(phase.asserted_on),
        "source": phase.source,
        "review_due": review_due(phase, on=on),
    }


# --------------------------------------------------------------------------- #
# Write path — INSERT never upsert; the one permitted UPDATE is closure.      #
# --------------------------------------------------------------------------- #

def open_phase(db: Session, user_id: int, payload: dict[str, Any]) -> models.TrainingPhase:
    """Open a phase in one transaction: close the current open row (if any), then INSERT the
    new one. Validate BEFORE touching the session (mirror `upsert_profile`) so a refused open
    strands nothing.

    `close_prior_reason` (optional, on the payload) is the closing note for the superseded
    row; default `"opened <label>"`. The prior row closes at `closed_on = new.entered_on`
    (half-open handoff), the ONLY UPDATE this ledger ever performs.
    """
    body = dict(payload)
    close_prior_reason = body.pop("close_prior_reason", None)

    fields = validate_training_phase(body)

    current = current_training_phase(db, user_id)
    if current is not None and fields["entered_on"] < current.entered_on:
        raise ValueError(
            f"entered_on {fields['entered_on']} precedes the open phase's entered_on "
            f"{current.entered_on} — history is monotonic; a phase cannot open before the "
            f"one it supersedes"
        )

    # Mutations only after every check has passed.
    if current is not None:
        current.closed_on = fields["entered_on"]
        current.close_reason = (
            close_prior_reason if (isinstance(close_prior_reason, str) and close_prior_reason.strip())
            else f"opened {fields['label']}"
        )

    phase = models.TrainingPhase(user_id=user_id, **fields)
    db.add(phase)
    db.commit()
    db.refresh(phase)
    return phase


def close_phase(db: Session, user_id: int, close_reason: str) -> models.TrainingPhase:
    """Close the current open phase to zero-open baseline as of the operator-local day.
    `NoOpenPhase` (→ 404) if none is open — closing nothing is an error, not a no-op."""
    if not isinstance(close_reason, str) or not close_reason.strip():
        raise ValueError("close_reason is required — a closure states its grounds")
    current = current_training_phase(db, user_id)
    if current is None:
        raise NoOpenPhase("no open training phase to close")
    current.closed_on = _local_day()
    current.close_reason = close_reason
    db.commit()
    db.refresh(current)
    return current
