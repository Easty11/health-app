"""The one read door for per-session RPE: `{counted session -> (rpe_cr10, source, rung)}`.

Two questions, answered once, for every reader (the psychological residual, the close-out's "is there a session
to rate", the MCP session lines, and Q231's imputed-load fit, which imports this door and builds no lookup of
its own):

  1. WHICH SESSIONS COUNT. `counted_sessions` is the bout set a felt-load metric counts, exactly as
     `psychological_reads._duration_min_by_day` has always defined it (#309, #322 S3): canonical aerobic rows
     through read-time arbitration, minus `NON_TRAINING_SPORTS`, minus an aerobic row that is the same bout as
     a COUNTED Hevy workout (`overlaps_workout`), plus the counted Hevy workouts (`counted_workouts`).
  2. WHAT EACH ONE WAS RATED. A rating from a source is placed on a counted session by OVERLAP of its window
     with the session, never by a stored link. Aerobic rows: at least `OVERLAP_THRESHOLD` of the shorter of
     the two. Counted Hevy workouts: the same `overlaps_workout` predicate every other reader of "the same bout
     as a Hevy workout" uses. An observation lands on the ONE session it overlaps most. When several sources
     rated a session the declared hierarchy (`srpe_hierarchy.SOURCE_HIERARCHY`) picks the highest rung; within
     one source the latest `captured_at` wins; ratings are never averaged. A session no source rated has NO
     rating: it never borrows the day's value (the day fill was retired, so `daily_records.session_rpe` is read
     by nothing).

Everything here is derived at READ time from stored observations and the session stores, so the answer for a
past day changes only when an observation is read that was not before: never because of capture-time UI or
the order adapters wrote in (series invariance).

FAIL OPEN TO ASKING. A rating that cannot be placed (no window, no overlapping counted session, a source not
in the hierarchy, or one that has not synced yet) leaves its session unrated, so `srpe_needed` is true and
the close-out asks about that session. A later observation overrides per session; nothing re-prompts.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

import models
from load_metrics import _local_day  # identical AEST day-bucketing as the Banister rollup
from reads.aerobic_reads import OVERLAP_THRESHOLD, arbitrated_sessions, overlaps_workout
from reads.hevy_reads import counted_workouts
from sport_classes import is_non_training
from srpe_hierarchy import rung_of
from srpe_store import latest_by_activity

AEROBIC = "aerobic"
HEVY = "hevy"


@dataclass(frozen=True)
class Bout:
    """One counted session. `key` is `(kind, id)`: `("aerobic", aerobic_sessions.id)` or
    `("hevy", hevy_workouts.hevy_id)`. `day` is the local (AEST) day it is counted on. `minutes` is its usable
    duration or None. `start`/`stop` are aware UTC, None when the session is untimed (it can then only be
    day-filled). `ref` is the underlying row, kept so the Hevy predicate can run on the real object."""
    key: tuple[str, Any]
    day: date
    start: Optional[datetime]
    stop: Optional[datetime]
    minutes: Optional[float]
    ref: Any = None

    @property
    def kind(self) -> str:
        return self.key[0]


@dataclass(frozen=True)
class Rating:
    """A counted session's effort rating on the CR-10 axis, where it came from, and its rung in the
    hierarchy (0 highest). `feel` is the source's passthrough."""
    rpe_cr10: float
    source: str
    rung: int
    feel: Optional[int] = None


@dataclass(frozen=True)
class RatedSession:
    bout: Bout
    rating: Optional[Rating]       # None: no source rated it


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def session_label(bout: Bout) -> str:
    """What a counted session is called wherever it is listed: the Hevy workout's title, else the device row's
    sport name, else a plain noun. One rule, so the cards, the MCP lines and the chat all name a session alike."""
    ref = bout.ref
    if bout.kind == HEVY:
        return (getattr(ref, "title", None) or "").strip() or "Workout"
    return (getattr(ref, "sport_name", None) or "").strip() or "Session"


def aerobic_bout(s) -> Bout:
    """A `Bout` for an aerobic row (for callers that rate sessions the counted set excludes, e.g. the MCP
    session lines, which show a Pilates rating though Pilates is not counted)."""
    mins = float(s.duration_minutes) if s.duration_minutes is not None and s.duration_minutes > 0 else None
    return Bout((AEROBIC, s.id), s.session_date, _utc(s.start_time), _utc(s.stop_time), mins, s)


def hevy_bout(w) -> Bout:
    """A `Bout` for a Hevy workout (for callers that rate workouts, e.g. the MCP session lines)."""
    mins = None
    if w.end_time is not None and w.start_time is not None:
        m = (w.end_time - w.start_time).total_seconds() / 60.0
        mins = m if m > 0 else None
    return Bout((HEVY, w.hevy_id), _local_day(w.start_time), _utc(w.start_time), _utc(w.end_time), mins, w)


# ---------------------------------------------------------------------------
# 1. Which sessions count
# ---------------------------------------------------------------------------

def counted_sessions(
    db: Session, user_id: int, *, since: Optional[date] = None, until: Optional[date] = None
) -> list[Bout]:
    """Every counted session of the user, optionally limited to local days in `[since, until]`.

    One physical bout contributes AT MOST once (#309): aerobic rows are read CANONICAL only through
    `arbitrated_sessions`; a canonical aerobic row that is the same bout as a counted Hevy workout
    (`overlaps_workout`) is that workout and contributes nothing; Hevy workouts count through
    `counted_workouts` (excluded rows out; an unadjudicated duplicate counts for nothing). Non-training
    sports (`sport_classes.NON_TRAINING_SPORTS`, #322 S3, all sources) are not counted. A Hevy workout with
    no start time cannot be placed on a day and is skipped. A session with no usable duration is still a
    counted session (it can be rated; it just adds no minutes).

    The windowed arbitration reads one day before `since` so a same-bout twin on the previous local date
    is not cut out of the comparison."""
    arb_since = None if since is None else since - timedelta(days=1)
    hevy_q = select(models.HevyWorkout).where(
        models.HevyWorkout.user_id == user_id, models.HevyWorkout.excluded_at.is_(None))
    if arb_since is not None:
        hevy_q = hevy_q.where(models.HevyWorkout.start_time >= datetime.combine(
            arb_since - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
    hevy, _unadjudicated = counted_workouts(db, user_id, db.execute(hevy_q).scalars().all())

    out: list[Bout] = []
    for s in arbitrated_sessions(user_id, db, since=arb_since):
        if not getattr(s, "canonical", True):
            continue
        if is_non_training(s.sport_name):
            continue                              # #322 S3: non-training minutes are not felt load
        if overlaps_workout(s, hevy):
            continue                              # same bout as a counted Hevy workout
        out.append(aerobic_bout(s))
    for w in hevy:
        if w.start_time is None:
            continue
        out.append(hevy_bout(w))

    return [b for b in out if (since is None or b.day >= since) and (until is None or b.day <= until)]


# ---------------------------------------------------------------------------
# 2. What each one was rated
# ---------------------------------------------------------------------------

def _overlap_s(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> float:
    return max(0.0, (min(a1, b1) - max(a0, b0)).total_seconds())


def _place(obs, bouts: list[Bout]) -> Optional[Bout]:
    """The counted session an observation belongs to: the one it overlaps most, among those it is the
    same bout as; None when it overlaps none. Ties break by start, kind, id so the answer never depends on
    the order sessions were listed in."""
    o0, o1 = _utc(obs.start_time), _utc(obs.stop_time)
    if o0 is None or o1 is None or o1 <= o0:
        return None
    o_dur = (o1 - o0).total_seconds()
    best: Optional[tuple[tuple, Bout]] = None
    for b in bouts:
        if b.start is None or b.stop is None or b.stop <= b.start:
            continue
        ov = _overlap_s(o0, o1, b.start, b.stop)
        if ov <= 0:
            continue
        if b.kind == HEVY:
            same = overlaps_workout(obs, [b.ref])        # the shared "same bout as a Hevy workout" predicate
        else:
            same = ov >= OVERLAP_THRESHOLD * min(o_dur, (b.stop - b.start).total_seconds())
        if not same:
            continue
        rank = (-ov, b.start, b.kind, str(b.key[1]))
        if best is None or rank < best[0]:
            best = (rank, b)
    return None if best is None else best[1]


def observed_ratings(db: Session, user_id: int, bouts: list[Bout]) -> dict[tuple, Rating]:
    """`{bout key: Rating}` from per-session observations ONLY (no day fill), for the given sessions.

    Each activity's CURRENT observation (its latest row) is placed on one session. Only rated observations
    of a source in the declared hierarchy with a full window take part; anything else leaves its session
    unrated. On a session, the highest rung wins, then the latest `captured_at`, then the highest row id."""
    candidates: dict[tuple, list] = defaultdict(list)
    for obs in latest_by_activity(db, user_id).values():
        if obs.rpe_cr10 is None or rung_of(obs.source) is None:
            continue
        b = _place(obs, bouts)
        if b is not None:
            candidates[b.key].append(obs)
    out: dict[tuple, Rating] = {}
    for key, obs_list in candidates.items():
        win = min(obs_list, key=lambda o: (rung_of(o.source), -_utc(o.captured_at).timestamp(), -o.id))
        out[key] = Rating(float(win.rpe_cr10), win.source, rung_of(win.source), win.feel)
    return out


def session_ratings(
    db: Session, user_id: int, *, since: Optional[date] = None, until: Optional[date] = None
) -> list[RatedSession]:
    """THE door: every counted session in `[since, until]` with its rating or None.

    Per-session observations by the declared hierarchy; a session no source rated is `None`. There is no day
    fill: the whole-day value never stands in for a session."""
    # Placement is decided against the window's whole neighbourhood (a day either side), so cutting the
    # window cannot move a rating onto a different session than the full history would.
    pad = timedelta(days=1)
    around = counted_sessions(db, user_id, since=None if since is None else since - pad,
                              until=None if until is None else until + pad)
    observed = observed_ratings(db, user_id, around)
    bouts = [b for b in around if (since is None or b.day >= since) and (until is None or b.day <= until)]
    far = datetime.max.replace(tzinfo=timezone.utc)
    return [RatedSession(b, observed.get(b.key))
            for b in sorted(bouts, key=lambda b: (b.day, b.start or far, b.kind, str(b.key[1])))]


def srpe_needed(db: Session, user_id: int, day: date) -> bool:
    """Whether the close-out has a session to ask about: at least one counted session that day has no rating
    from any source. Fails open to asking: a day with no counted session at all returns True too (an
    unrecorded session, which only the athlete can rate), and an unsynced source leaves its session unrated."""
    rated = session_ratings(db, user_id, since=day, until=day)
    if not rated:
        return True
    return any(r.rating is None for r in rated)
