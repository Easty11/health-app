"""Counted Hevy workouts — the single "which workouts feed a metric" door (#309).

`counted_workouts(db, user_id, candidates)` partitions a set of `hevy_workouts` into the
workouts a load/quota/duration metric should count and the ones it must not, WITHOUT
silently dropping a real performed session.

The subtlety (#309, correcting the round-1 "honour excluded_at + dedup_flag" instruction):
`dedup_flag` is set on BOTH members of a suspected duplicate pair
(`hevy_workouts._recompute_dedup_flags`); `dedup_partner_ids` lists the partner hevy_ids.
`excluded_at` is the operator's ADJUDICATION of which member is the artifact. So filtering
`dedup_flag IS NOT TRUE` drops the RETAINED performed log as well as the artifact — the
error this door exists to prevent. The load transform (`load_events`, `excluded_at` only)
had it right; the resolver (#276) and the round-1 psychological fix did not.

    counted(w)  := w.excluded_at IS NULL
                   AND ( NOT w.dedup_flag
                         OR every id in w.dedup_partner_ids is excluded )

A flagged, non-excluded workout whose pair has NOT been adjudicated (no excluded member) is
`unadjudicated`: it counts for nothing and is SURFACED by the caller (never counted twice,
never silently dropped). Partner exclusion is resolved against ALL of the user's excluded
workouts, so a partner outside `candidates` — a re-log hours later, beyond a resolver
window — is still seen (the 89b8f0c8/a0f298a4 pair is ~11h apart).

A reads helper: query-light, no schema, one definition for every caller (the follow-up
read-door PR makes this THE door with a drift-guard; here it serves the two callers this PR
already touches).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

import models


def counted_workouts(db: Session, user_id: int, candidates) -> tuple[list, list]:
    """Return (counted, unadjudicated) over `candidates` (hevy_workouts of `user_id`).

    See the module docstring for `counted(w)`. `candidates` may already exclude
    `excluded_at IS NOT NULL` rows (a caller often pre-filters); the excluded-partner set is
    loaded here regardless, so the classification is correct either way."""
    excluded_ids = {
        hid
        for (hid,) in db.query(models.HevyWorkout.hevy_id).filter(
            models.HevyWorkout.user_id == user_id,
            models.HevyWorkout.excluded_at.isnot(None),
        )
    }
    counted: list = []
    unadjudicated: list = []
    for w in candidates:
        if w.excluded_at is not None:
            continue                                  # adjudicated out (artifact / deleted)
        if not w.dedup_flag:
            counted.append(w)                         # not a duplicate
        elif all(pid in excluded_ids for pid in (w.dedup_partner_ids or [])):
            counted.append(w)                         # retained survivor of an adjudicated pair
        else:
            unadjudicated.append(w)                   # pair not yet adjudicated — surface, never count
    return counted, unadjudicated
