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

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

import models
from load_events_metabolic import compute_metabolic_load


# Two cross-source sessions describe the same physical bout when their intervals
# overlap by at least this fraction of the SHORTER session's duration. One place
# to tune; empirical calibration against real Polar/HC pairs is an open question.
OVERLAP_THRESHOLD = 0.50


# Fidelity rank — higher wins when two sources describe the same bout.
# polar_flow_export > polar_v4 > health_connect. Both Polar rows come off the
# same sensor, but the two transports do NOT carry the same payload: the v4
# *list* endpoint omits trainingLoadReport/zones (cardio_load, muscle_load and
# z*_seconds come back null — see connectors/polar.PolarV4Client.parse_session),
# while the Flow-export ZIP carries them. So for a same-bout v4/flow_export twin
# the export row is STRICTLY richer and must be the canonical one — otherwise the
# id-order tie-break can leave the zoneless v4 row canonical, which the metabolic
# transform then skips fail-closed (INV-7), dropping the bout entirely (#260/Q127).
# health_connect carries duration + type only. An unknown source ranks below all
# known ones rather than above.
_SOURCE_RANK = {
    "polar_flow_export": 3,
    "polar_v4": 2,
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


# ── zone coverage (the "transport-starved sessions are visible, not silent" flag) ──

# A zoneless `polar_v4` session older than this many days is STALE: the v4 list
# endpoint never carries the HR-zone split, so its zones only ever arrive via a
# fresh Flow-export re-download — past this horizon that refresh is overdue. A
# reasoned prior (constant, tunable); the failure mode it surfaces is the 17
# zoneless v4 sessions that sat silent for two months.
ZONELESS_STALE_DAYS = 7


def _has_usable_zones(session) -> bool:
    """True iff the session carries zone data the metabolic transform can score.

    Uses the SAME qualifying predicate as the transform's INV-7 fail-closed rule
    (`load_events_metabolic.compute_metabolic_load`): at least one `z*_seconds`
    non-NULL AND a positive zone-sum. A session that fails this emits no metabolic
    `load_events` row — which is exactly the silence this flag makes visible."""
    return compute_metabolic_load({
        1: session.z1_seconds, 2: session.z2_seconds, 3: session.z3_seconds,
        4: session.z4_seconds, 5: session.z5_seconds,
    }).qualifying


def zone_coverage(
    user_id: int,
    db: Session,
    *,
    now: Optional[datetime] = None,
) -> dict:
    """Per-user HR-zone coverage over `aerobic_sessions`.

    Counts zone-carrying vs zoneless sessions overall and by source, plus
    `stale_zoneless` — zoneless `polar_v4` sessions older than `ZONELESS_STALE_DAYS`
    (the ones a fresh Flow-export would backfill; `polar_flow_export` rows already
    carry zones and `health_connect` never does via this path). A read-only helper
    (no schema), following the module's query-helper shape.
    """
    now = now or datetime.now(timezone.utc)
    stale_before = now.date() - timedelta(days=ZONELESS_STALE_DAYS)

    rows = (
        db.query(models.AerobicSession)
        .filter(models.AerobicSession.user_id == user_id)
        .all()
    )

    with_zones = zoneless = stale_zoneless = 0
    by_source: dict[str, dict[str, int]] = {}
    for s in rows:
        bucket = by_source.setdefault(s.source, {"with_zones": 0, "zoneless": 0})
        if _has_usable_zones(s):
            with_zones += 1
            bucket["with_zones"] += 1
        else:
            zoneless += 1
            bucket["zoneless"] += 1
            if s.source == "polar_v4" and s.session_date < stale_before:
                stale_zoneless += 1

    return {
        "total": len(rows),
        "with_zones": with_zones,
        "zoneless": zoneless,
        "stale_zoneless": stale_zoneless,
        "stale_zoneless_days": ZONELESS_STALE_DAYS,
        "by_source": by_source,
    }


def coverage_notice(coverage: dict) -> Optional[str]:
    """A user-facing nudge when zoneless `polar_v4` sessions have gone stale, else
    None. Surfaced verbatim in the Polar ingest responses."""
    n = coverage["stale_zoneless"]
    if n > 0:
        return f"{n} sessions awaiting zone data — refresh export"
    return None
