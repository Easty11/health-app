"""
arbitrated_sessions(user_id, db, *, since, limit) -> list[AerobicSession]
arbitrate(sessions) -> list  (pure; sets `.canonical` on each row)

Read-time cross-source arbitration over `aerobic_sessions`. Polar and Health
Connect can each capture the SAME physical bout from different sensors; this
module marks exactly one row per bout `canonical` at READ time. The flag is
DERIVED and never persisted — there is no `canonical` column (a persisted flag
is a separate decision).

Why read-time, not write-time: Polar sync and HC sync arrive in unpredictable
order. Write-time suppression makes the winner depend on arrival order and forces
retro-suppression when the higher-fidelity source lands second. Computing it at
read is order-independent and reversible.

This is a DISTINCT concern from the #35/#36/#37/#175 admission dedup, which
governs one writer re-posting another writer's record (a mirror carrying no new
signal). Here two independent sensors each captured one event and BOTH carry
signal (Polar carries cardio_load + HR-zone seconds; HC carries duration + type);
the question is which row is richer, not whether one is a copy. Do not fold them.

Follows the labs_reads.py shape: a query-only helper plus a pure core, no schema.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

import models


# Two cross-source sessions describe the same physical bout when their intervals
# overlap by at least this fraction of the SHORTER session's duration. One place
# to tune; empirical calibration against real Polar/HC pairs is an open question.
OVERLAP_THRESHOLD = 0.50


# Fidelity rank — higher wins when two sources describe the same bout.
# polar_v4 == polar_flow_export (both Polar, one sensor via two transports;
# each carries cardio_load + zone seconds) > health_connect (duration + type
# only). An unknown source ranks below all known ones rather than above.
_SOURCE_RANK = {
    "polar_v4": 2,
    "polar_flow_export": 2,
    "health_connect": 1,
}
_UNKNOWN_RANK = 0


def _rank(source: Optional[str]) -> int:
    return _SOURCE_RANK.get(source or "", _UNKNOWN_RANK)


def _ts(dt: Optional[datetime]) -> Optional[float]:
    """Epoch seconds, treating a naive datetime as UTC. Comparing epoch floats
    (not datetime objects) sidesteps aware/naive subtraction errors when rows
    from different sources carry different tzinfo shapes."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _win_key(session, dur: float, start_ts: float) -> tuple:
    """Ordering key for 'which row of a same-bout pair is canonical'. LARGER
    wins: higher rank, then longer duration, then earlier start, then lower id.
    The id is a final deterministic discriminator so a fully-tied cross-source
    pair still yields exactly ONE canonical (never zero — which would drop the
    bout entirely). The brief's stated tie chain is rank -> duration -> start;
    id only breaks a residual exact tie."""
    return (
        _rank(session.source),
        dur,
        -start_ts,
        -(session.id if session.id is not None else 0),
    )


def arbitrate(sessions: list) -> list:
    """Set `.canonical` (bool) on every session in `sessions`, in place.

    A session is canonical unless some OTHER session from a DIFFERENT source
    describes the same bout (interval overlap >= OVERLAP_THRESHOLD of the shorter
    duration) and outranks it by `_win_key`. Same-source pairs are never compared
    — same-source duplication is out of scope (the unique key prevents it). A
    session with no usable [start_time, stop_time] interval cannot be paired and
    is canonical by default.

    O(n^2) over the passed set; fine at personal/family scale (same assumption as
    _capture_record_sources). Returns the same list for convenience.
    """
    # Precompute interval + duration once per session.
    intervals: dict[int, tuple[float, float, float]] = {}
    for s in sessions:
        start_ts = _ts(s.start_time)
        stop_ts = _ts(s.stop_time)
        if start_ts is not None and stop_ts is not None and stop_ts > start_ts:
            intervals[id(s)] = (start_ts, stop_ts, stop_ts - start_ts)

    for x in sessions:
        xi = intervals.get(id(x))
        canonical = True
        if xi is not None:
            x_start, x_stop, x_dur = xi
            x_key = _win_key(x, x_dur, x_start)
            for y in sessions:
                if y is x or y.source == x.source:
                    continue
                yi = intervals.get(id(y))
                if yi is None:
                    continue
                y_start, y_stop, y_dur = yi
                overlap = min(x_stop, y_stop) - max(x_start, y_start)
                if overlap < OVERLAP_THRESHOLD * min(x_dur, y_dur):
                    continue  # not the same bout
                if _win_key(y, y_dur, y_start) > x_key:
                    canonical = False
                    break
        x.canonical = canonical
    return sessions


def arbitrated_sessions(
    user_id: int,
    db: Session,
    *,
    since: Optional[date] = None,
    limit: Optional[int] = None,
) -> list:
    """Aerobic sessions for a user, each carrying a derived `.canonical` flag.

    Arbitration runs over the whole `since`-windowed set BEFORE `limit` is
    applied, so a bout's counterpart is never truncated out of the comparison.
    """
    q = (
        db.query(models.AerobicSession)
        .filter(models.AerobicSession.user_id == user_id)
        .order_by(models.AerobicSession.session_date.desc())
    )
    if since is not None:
        q = q.filter(models.AerobicSession.session_date >= since)
    rows = q.all()
    arbitrate(rows)
    if limit is not None:
        rows = rows[:limit]
    return rows
