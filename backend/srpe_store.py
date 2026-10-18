"""The source-neutral per-session RPE store: its contract, its one writer, its scale declarations.

Any app that can say how hard one of its own activities felt writes that rating here, through
`record_observation`, into `session_rpe_observations` (`models.SessionRpeObservation`). Nothing else
writes the table (a test greps for it). What a rating is WORTH when sources disagree, and which counted
session it belongs to, is not decided here: `reads.srpe_reads` resolves that at read time from a declared
hierarchy (`srpe_hierarchy.py`), so a write never depends on which adapter ran first.

The contract an adapter signs:

  * It names its `source` and DECLARES the scales it writes in `SOURCE_SCALES`. A `raw_scale` the adapter
    did not declare is REFUSED (fail closed), as is a source with no declaration: an unknown unit is never
    guessed into CR-10. The writer, not the adapter, converts `rpe_raw` to `rpe_cr10` with the declared scale,
    so the stored number is always on one axis.
  * It gives the bout it rated as a UTC window (`start`, and `stop` when known). A rating with no window
    cannot be placed on a session by the read door and so is never used as a value.
  * It may record an UNRATED sighting (`rpe_raw=None`) so an unrated activity is not re-fetched every day.
  * `feel` is a source-specific passthrough and `provenance` is audit detail; neither carries a value.

Rows are INSERT-ONLY. A row is what the source said at `captured_at`; a changed or later answer is a NEW
row, strictly later than that activity's previous one, so "latest" is unambiguous and the unique key
(user, source, activity, captured_at) cannot collide. The CURRENT value of an activity is its latest row.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import models


class SRPEContractError(ValueError):
    """A write the contract refuses. Nothing is inserted."""


class UnknownSource(SRPEContractError):
    """The source has no declaration in `SOURCE_SCALES` (no adapter has signed the contract)."""


class UnknownScale(SRPEContractError):
    """The scale is not one the source declared."""


@dataclass(frozen=True)
class Scale:
    """A declared rating scale: raw values in `[lo, hi]`, and `rpe_cr10 = raw / divisor`.

    A divisor (not a general linear map) so the conversion is exact for the scales that exist: Garmin's
    0-100 steps of ten are CR-10 times ten, and a CR-10 source needs no conversion."""
    name: str
    lo: float
    hi: float
    divisor: float

    def to_cr10(self, raw: float) -> float:
        return raw / self.divisor


GARMIN_0_100 = Scale("garmin_0_100", lo=0.0, hi=100.0, divisor=10.0)   # `summaryDTO.directWorkoutRpe` (probe, 4 Oct 2026)
CR10 = Scale("cr10", lo=0.0, hi=10.0, divisor=1.0)

# source -> the scales it has declared. Adding an adapter means adding its entry here, after a read-only
# probe has shown the field and its scale (Q209 pattern, FEEDBACK section 17). `in_app` is named in the
# hierarchy (`srpe_hierarchy.py`) but deliberately absent here: it has no writer yet, so a write naming it
# is refused until one signs the contract.
SOURCE_SCALES: dict[str, dict[str, Scale]] = {
    "garmin": {GARMIN_0_100.name: GARMIN_0_100},
}


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _convert(source: str, raw_scale: str, rpe_raw: Any) -> float | None:
    """`rpe_cr10` for a declared (source, scale, raw), or None for an unrated sighting. Refuses anything else."""
    scales = SOURCE_SCALES.get(source)
    if scales is None:
        raise UnknownSource(f"source {source!r} has not declared any scale")
    scale = scales.get(raw_scale)
    if scale is None:
        raise UnknownScale(f"source {source!r} did not declare scale {raw_scale!r} (declared: {sorted(scales)})")
    if rpe_raw is None:
        return None
    if isinstance(rpe_raw, bool) or not isinstance(rpe_raw, (int, float)) or not math.isfinite(rpe_raw):
        raise SRPEContractError(f"rpe_raw {rpe_raw!r} is not a number")
    if not scale.lo <= rpe_raw <= scale.hi:
        raise SRPEContractError(f"rpe_raw {rpe_raw!r} is outside the declared {scale.name} range [{scale.lo:g}, {scale.hi:g}]")
    return float(scale.to_cr10(rpe_raw))


def latest_by_activity(db, user_id: int, source: str | None = None) -> dict[tuple[str, str], models.SessionRpeObservation]:
    """`{(source, source_activity_ref): latest row}`: the CURRENT observation of each activity (greatest
    `captured_at`, then id). An UNRATED latest row is the current value: "no rating". Optionally one source."""
    q = db.query(models.SessionRpeObservation).filter(models.SessionRpeObservation.user_id == user_id)
    if source is not None:
        q = q.filter(models.SessionRpeObservation.source == source)
    out: dict[tuple[str, str], models.SessionRpeObservation] = {}
    for r in q.order_by(models.SessionRpeObservation.captured_at, models.SessionRpeObservation.id):
        out[(r.source, r.source_activity_ref)] = r        # ascending, so the last write per activity is the latest
    return out


def record_observation(
    db,
    user_id: int,
    *,
    source: str,
    source_activity_ref: str | int,
    start: datetime,
    stop: datetime | None,
    rpe_raw: float | None,
    raw_scale: str,
    feel: int | None = None,
    provenance: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> models.SessionRpeObservation:
    """THE write: one INSERT, committed. Refuses an undeclared source or scale and an out-of-range value.

    `now` is the observation time (default: the clock); the row's `captured_at` is that, nudged to be
    strictly later than the activity's previous row when the clock has not moved past it. Returns the row."""
    ref = str(source_activity_ref)
    rpe_cr10 = _convert(source, raw_scale, rpe_raw)
    start_utc, stop_utc = _utc(start), _utc(stop)
    if start_utc is None:
        raise SRPEContractError("an observation needs the start of the bout it rates")
    if stop_utc is not None and stop_utc <= start_utc:
        raise SRPEContractError("stop must be after start")

    captured = _utc(now) or datetime.now(timezone.utc)
    prior = (db.query(models.SessionRpeObservation)
             .filter_by(user_id=user_id, source=source, source_activity_ref=ref)
             .order_by(models.SessionRpeObservation.captured_at.desc(), models.SessionRpeObservation.id.desc())
             .first())
    if prior is not None and _utc(prior.captured_at) >= captured:
        captured = _utc(prior.captured_at) + timedelta(microseconds=1)

    row = models.SessionRpeObservation(
        user_id=user_id, source=source, source_activity_ref=ref, start_time=start_utc, stop_time=stop_utc,
        rpe_raw=None if rpe_raw is None else float(rpe_raw), raw_scale=raw_scale, rpe_cr10=rpe_cr10,
        feel=feel, captured_at=captured, provenance=dict(provenance or {}))
    db.add(row)
    db.commit()
    return row
