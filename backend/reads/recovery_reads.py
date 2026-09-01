"""
canonical_hrv(user_id, db, *, since, limit) -> list[HrvReading]
arbitrate(readings) -> list  (pure; sets `.canonical` on each row)

Read-time cross-source arbitration over `hrv_readings`. Two sources (Garmin,
later Samsung) can each report an HRV summary for the SAME night; this module marks
exactly one row per night `canonical` at READ time. The flag is DERIVED and never
persisted — there is no `canonical` column (same principle as `reads/aerobic_reads.py`).

Why read-time, not write-time: sources sync in unpredictable order, so a write-time
winner depends on arrival order and forces retro-suppression when the richer source
lands second. Computing it at read is order-independent and reversible.

Simpler than aerobic arbitration: HRV groups by the NIGHT `(user_id, captured_at)`,
not by interval overlap — a night is a night, no same-bout overlap test needed.

Follows the aerobic_reads.py shape: a query-only helper plus a pure core, no schema.
Consumption (rewiring recovery.py's HRV read to this helper, migrating Samsung HRV
into hrv_readings) is the DEFERRED follow-on — this module is ready-but-single-source
now, exactly as aerobic arbitration predated all its sources landing.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

import models


# Fidelity rank — higher wins when two sources report the same night. Garmin's pull
# carries the richer summary (status band + baseline + weekly avg + 5-min series);
# Samsung is nightly-only. An unknown source ranks below all known ones.
#
# NOTE (OPEN_QUESTIONS — HRV _SOURCE_RANK unexercised): per-user overlap is nil today
# (one household member on Garmin, one on Samsung), so no night is actually contested.
# The rank only bites once a single user acquires both sources; revisit it then.
_SOURCE_RANK = {
    "garmin": 2,
    "samsung": 1,
}
_UNKNOWN_RANK = 0


def _rank(source: Optional[str]) -> int:
    return _SOURCE_RANK.get(source or "", _UNKNOWN_RANK)


def _win_key(reading) -> tuple:
    """Ordering key for 'which row of a same-night group is canonical'. LARGER wins:
    higher source rank, then higher id (a deterministic final discriminator so a group
    always yields exactly ONE canonical — never zero, which would drop the night)."""
    return (_rank(reading.source), reading.id if reading.id is not None else 0)


def arbitrate(readings: list) -> list:
    """Set `.canonical` (bool) on every reading in `readings`, in place.

    Group by `(user_id, captured_at)`; within a group the row with the max `_win_key`
    is canonical, all others False. A night with a single source is canonical by
    default. Returns the same list for convenience.
    """
    groups: dict[tuple, list] = {}
    for r in readings:
        groups.setdefault((r.user_id, r.captured_at), []).append(r)

    for group in groups.values():
        winner = max(group, key=_win_key)
        for r in group:
            r.canonical = r is winner
    return readings


def canonical_hrv(
    user_id: int,
    db: Session,
    *,
    since: Optional[date] = None,
    limit: Optional[int] = None,
) -> list:
    """HRV readings for a user, each carrying a derived `.canonical` flag.

    Arbitration runs over the whole `since`-windowed set BEFORE `limit` is applied, so
    a night's counterpart from another source is never truncated out of the group.
    Reads `hrv_readings` only (source-agnostic); Samsung rows are absent until the
    deferred unification migration.
    """
    q = (
        db.query(models.HrvReading)
        .filter(models.HrvReading.user_id == user_id)
        .order_by(models.HrvReading.captured_at.desc())
    )
    if since is not None:
        q = q.filter(models.HrvReading.captured_at >= since)
    rows = q.all()
    arbitrate(rows)
    if limit is not None:
        rows = rows[:limit]
    return rows
