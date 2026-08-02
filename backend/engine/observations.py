"""
Capability observations (DECISIONS_LOG #NEXT) — the measured half of the map.

`capability_state` says what the user's response to load revealed: a verdict, in
four ordinal levels, overwritten in place. This module records what was MEASURED:
a quantity, on a declared unit, on the date it was taken. Different signal,
different provenance, both real.

WRITES ARE APPEND-ONLY AND FAIL-CLOSED. There is no update path — a correction is
a new row, and `latest()` resolves supersession by `observed_on` then `created_at`.
Region, measure, and side are each validated against `taxonomy.py` before anything
is written, mirroring the unknown-`region_key` guard in `adaptation.py`: an orphan
key is refused, never stored.

THE BOUNDARY (mirrors `injury_probes.py`, enforced in
`tests/test_capability_observations.py`, not by this docstring):

  legal    — store a measured quantity; derive symmetry, trend, or dose-response
             slope for display.
  ILLEGAL  — turn any of that into a clearance, a "safe to return", a severity
             grade, or a return-to-sport verdict.

`symmetry()` is the sharpest edge here. The return-to-sport literature attaches a
>=90% Limb Symmetry Index threshold to exactly this ratio, and the taxonomy's own
note on `single_leg_hop` records that the threshold is "rarely met even uninjured,
so treat as direction-of-travel". So this module returns the ratio and which side
is lower, and never compares either to a threshold. The number is the output; the
verdict is not ours to emit.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pytz
from sqlalchemy.orm import Session

import models
from . import taxonomy
from .taxonomy import SIDE_BILATERAL, SIDE_LEFT, SIDE_RIGHT, TAXONOMY_VERSION

AEST = pytz.timezone("Australia/Brisbane")

# How the measurement was produced — the protocol, not the device.
METHODS = frozenset({"baseline_battery", "probe", "session", "manual"})
# Where the value came from — the device-agnostic source tag (CLAUDE.md).
SOURCES = frozenset({"self_report", "catapult", "hevy", "polar", "manual"})
# Mirrors taxonomy.Confidence.
CONFIDENCES = frozenset({"certain", "likely", "guessing"})


def _today() -> date:
    return datetime.now(AEST).date()


def _validate(region_key: str, measure_key: str, side: str) -> taxonomy.Measure:
    """Resolve and validate (region, measure, side). Raises ValueError so the
    caller can 4xx — the same contract `adaptation.apply_response` offers."""
    region = taxonomy.by_key(region_key)
    if region is None:
        raise ValueError(f"unknown region_key: {region_key!r}")

    measure = region.measure(measure_key)
    if measure is None:
        declared = [m.key for m in region.measures]
        if not declared:
            # Not a typo — an axis nobody has chosen an instrument for. Saying so
            # is more useful than listing an empty set of alternatives.
            raise ValueError(
                f"region {region_key!r} declares no measures and is not observable"
            )
        raise ValueError(
            f"unknown measure_key {measure_key!r} for region {region_key!r} "
            f"(declared: {', '.join(sorted(declared))})"
        )

    # A measure's sidedness is the instrument's, bounded by the region's ceiling.
    allowed = [s for s in measure.sides() if s in region.sides() or s == SIDE_BILATERAL]
    if side not in allowed:
        raise ValueError(
            f"side {side!r} is not valid for {region_key}/{measure_key} "
            f"(allowed: {', '.join(allowed)})"
        )
    return measure


def record_observation(
    db: Session,
    user_id: int,
    *,
    region_key: str,
    measure_key: str,
    value: float,
    side: str = SIDE_BILATERAL,
    observed_on: date | None = None,
    method: str = "manual",
    source: str = "self_report",
    confidence: str = "likely",
    context: dict[str, Any] | None = None,
    unit: str | None = None,
) -> models.CapabilityObservation:
    """Append one measurement. Never updates an existing row.

    `unit` is taken from the declared measure rather than the caller: two callers
    disagreeing about whether a hop is cm or m would silently corrupt the series,
    and the taxonomy already holds the answer. A caller MAY pass `unit` to assert
    what it thinks it is sending — a mismatch raises rather than converting,
    because a unit conversion we invented is a value we made up.
    """
    measure = _validate(region_key, measure_key, side)

    if unit is not None and unit != measure.unit:
        raise ValueError(
            f"unit {unit!r} does not match the declared unit {measure.unit!r} "
            f"for {region_key}/{measure_key} — no conversion is performed"
        )
    if method not in METHODS:
        raise ValueError(f"unknown method: {method!r}")
    if source not in SOURCES:
        raise ValueError(f"unknown source: {source!r}")
    if confidence not in CONFIDENCES:
        raise ValueError(f"unknown confidence: {confidence!r}")

    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"value must be numeric, got {value!r}")

    observed = observed_on or _today()
    if observed > _today():
        # A measurement dated in the future is a data-entry fault, and it would
        # sort ahead of every real row in `latest()`.
        raise ValueError(f"observed_on {observed} is in the future")

    row = models.CapabilityObservation(
        user_id=user_id,
        region_key=region_key,
        side=side,
        observed_on=observed,
        measure_key=measure_key,
        value=value,
        unit=measure.unit,
        method=method,
        source=source,
        confidence=confidence,
        context=context,
        taxonomy_version=TAXONOMY_VERSION,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def series(
    db: Session,
    user_id: int,
    *,
    region_key: str,
    measure_key: str,
    side: str | None = None,
    since: date | None = None,
) -> list[models.CapabilityObservation]:
    """Every observation for one (region, measure), oldest first.

    Corrections are NOT collapsed — a superseded row stays in the series, because
    the fact that a value was corrected is itself part of the record. Callers
    wanting one value per date use `latest()`.
    """
    q = db.query(models.CapabilityObservation).filter_by(
        user_id=user_id, region_key=region_key, measure_key=measure_key,
    )
    if side is not None:
        q = q.filter(models.CapabilityObservation.side == side)
    if since is not None:
        q = q.filter(models.CapabilityObservation.observed_on >= since)
    return q.order_by(
        models.CapabilityObservation.observed_on.asc(),
        models.CapabilityObservation.created_at.asc(),
        models.CapabilityObservation.id.asc(),
    ).all()


def latest(
    db: Session,
    user_id: int,
    *,
    region_key: str,
    measure_key: str,
    side: str = SIDE_BILATERAL,
) -> models.CapabilityObservation | None:
    """The current value for one (region, measure, side).

    Supersession order is `observed_on`, then `created_at`, then `id` — so a
    correction entered today for a measurement taken last week supersedes the
    original for last week, and does NOT displace a measurement actually taken
    since. `id` breaks the tie when two rows share a timestamp, which SQLite's
    second-resolution `now()` makes reachable in tests.
    """
    return (
        db.query(models.CapabilityObservation)
        .filter_by(user_id=user_id, region_key=region_key,
                   measure_key=measure_key, side=side)
        .order_by(
            models.CapabilityObservation.observed_on.desc(),
            models.CapabilityObservation.created_at.desc(),
            models.CapabilityObservation.id.desc(),
        )
        .first()
    )


def symmetry(
    db: Session,
    user_id: int,
    *,
    region_key: str,
    measure_key: str,
) -> dict[str, Any] | None:
    """Left/right ratio for a per-side measure, or None if it is not per-side or
    a side is missing.

    Returns the ratio and which side is lower. It does NOT compare that ratio to
    the >=90% return-to-sport threshold, and must not be extended to: the
    threshold is a clearance criterion, and the taxonomy's own note records that
    it is rarely met even uninjured. Direction of travel across repeated
    observations is the usable signal; a single ratio against a cutoff is not.

    `index_pct` is lower/higher regardless of `higher_is_better`, so it is always
    in (0, 100]. `lower_side` names the side with the smaller VALUE — for a
    measure where lower is better, that is the better side, which is why the
    direction flag is returned alongside rather than baked into the number.
    """
    measure = taxonomy.measure_for(region_key, measure_key)
    if measure is None or not measure.per_side:
        return None

    left = latest(db, user_id, region_key=region_key, measure_key=measure_key, side=SIDE_LEFT)
    right = latest(db, user_id, region_key=region_key, measure_key=measure_key, side=SIDE_RIGHT)
    if left is None or right is None:
        return None

    lo, hi = sorted((left.value, right.value))
    index_pct = round(lo / hi * 100, 1) if hi else None

    return {
        "region_key": region_key,
        "measure_key": measure_key,
        "unit": measure.unit,
        "higher_is_better": measure.higher_is_better,
        "left": left.value,
        "right": right.value,
        "left_observed_on": str(left.observed_on),
        "right_observed_on": str(right.observed_on),
        # Both sides carry their own date: a "symmetry" built from a left measured
        # in March and a right measured in July is a comparison across time, and
        # the reader needs to see that rather than be handed one number.
        "as_of": str(max(left.observed_on, right.observed_on)),
        "index_pct": index_pct,
        "lower_side": SIDE_LEFT if left.value < right.value else (
            SIDE_RIGHT if right.value < left.value else None
        ),
    }


def observation_to_dict(row: models.CapabilityObservation) -> dict[str, Any]:
    return {
        "id": row.id,
        "region_key": row.region_key,
        "side": row.side,
        "observed_on": str(row.observed_on),
        "measure_key": row.measure_key,
        "value": row.value,
        "unit": row.unit,
        "method": row.method,
        "source": row.source,
        "confidence": row.confidence,
        "context": row.context,
        "taxonomy_version": row.taxonomy_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
