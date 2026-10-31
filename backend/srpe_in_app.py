"""The app's own per-session RPE capture: the close-out, the AM catch-up and the backfill write through here.

One CR-10 per counted session, written as source `in_app` into the source-neutral store (`srpe_store`). The
client names WHICH session (`kind`, `id`) and HOW HARD (`rpe`); it never names a window. The session must be a
counted session of this user (`reads.srpe_reads.counted_sessions`, the one definition of what counts), inside
the rateable window below, and the window written is the server's own for that session (`srpe_store.bout_window`).

Insert-only: re-rating a session is a new row, and the read door's latest-wins resolves it
(`reads.srpe_reads.observed_ratings`). `in_app` is the top rung of `srpe_hierarchy.SOURCE_HIERARCHY`, so a
rating made here outranks the device's own (a Garmin one) for the same session.

The rateable window is bounded on both sides: no earlier than `RATING_FLOOR` (the day the store was released,
so nothing predates the surface that could have been asked), and no more than `BACKFILL_DAYS` before the day
being viewed (the backfill is a catch-up, not an archive). `rating_window` is the one place that says so, and
both the read route and the write route use it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

import models
import srpe_store
from reads.srpe_reads import Bout, counted_sessions

# The store's release day (18 Oct 2026): the earliest day a session can be rated in the app, and the start of
# the backfill. Sessions before it were never asked about at per-session grain and are left as they are.
RATING_FLOOR = date(2026, 10, 18)
# How far back a card's backfill reaches from the day it is on: 14 local days. State of the bound: a session
# older than this (and older than the floor allows) can no longer be rated in the app.
BACKFILL_DAYS = 14


class NotARateableSession(srpe_store.SRPEContractError):
    """The key is not a counted session of this user inside the rateable window. Nothing is inserted."""


@dataclass(frozen=True)
class RatingIn:
    """One rating asked for: `kind` is `aerobic` or `hevy`, `id` the row's id, `rpe` on CR-10 (0-10)."""
    kind: str
    id: str
    rpe: float


def rating_window(today: date) -> tuple[date, date]:
    """`(earliest, latest)` local day a session can be rated on, seen from `today`: `latest` is today (a future
    day has no sessions), `earliest` is `BACKFILL_DAYS + 1` days back (the backfill of the day before today
    reaches `BACKFILL_DAYS` further), never earlier than the store's release."""
    return max(RATING_FLOOR, today - timedelta(days=BACKFILL_DAYS + 1)), today


def _key(kind: str, ref: object) -> tuple[str, str]:
    return (str(kind), str(ref))


def rate_sessions(
    db: Session, user_id: int, ratings: Iterable[RatingIn], *, today: date, now: Optional[datetime] = None
) -> list[models.SessionRpeObservation]:
    """Write one `in_app` observation per rating, in order. ALL are checked before ANY is written: one key that
    is not a counted session of this user in the window (or has no usable window) refuses the lot and inserts
    nothing. A key given twice is written twice (the later one wins at read time)."""
    asked = list(ratings)
    if not asked:
        return []
    since, until = rating_window(today)
    by_key: dict[tuple[str, str], Bout] = {
        _key(b.key[0], b.key[1]): b for b in counted_sessions(db, user_id, since=since, until=until)}
    resolved: list[tuple[Bout, RatingIn]] = []
    for r in asked:
        bout = by_key.get(_key(r.kind, r.id))
        if bout is None:
            raise NotARateableSession(f"{r.kind}:{r.id} is not a counted session of yours between {since} and {until}")
        srpe_store.bout_window(bout)              # refuses an unplaceable session before anything is written
        resolved.append((bout, r))
    out: list[models.SessionRpeObservation] = []
    for bout, r in resolved:
        out.append(srpe_store.record_observation(
            db, user_id, source=srpe_store.IN_APP, source_activity_ref=f"{bout.key[0]}:{bout.key[1]}",
            bout=bout, rpe_raw=r.rpe, raw_scale=srpe_store.CR10.name, now=now,
            provenance={"kind": bout.key[0], "id": str(bout.key[1])}))
    return out
