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

HEVY MIRRORS (A3.2). A Hevy bout can reach `aerobic_sessions` under ANOTHER package: hevy2garmin
pushes Hevy workouts to Garmin, and Garmin Connect / Strava then write them into Health Connect
as their own activities (16 `com.strava` Weightlifting rows, Sept-Oct 2026). Admission drops only
`com.hevy` (routers/health_connect.HEVY_PACKAGE), so these rows are stored. They are the Hevy
bout again, not a second session, and are suppressed HERE, at read time, so admission order never
matters and the stored rows stay as evidence: a Health Connect row whose overlap with a counted
Hevy bout is >= HEVY_MIRROR_OVERLAP_FRACTION of its OWN duration is a `hevy_mirror`. It is marked
`canonical=False` and kept out of arbitration (a mirror must not outrank a live row for the same
bout). The rule is package-agnostic; Polar rows are never mirrors (a strap worn in the gym is a
genuine HR trace; the orthogonal-windows design stands for them).
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

# A session is "the same bout as a Hevy workout" when its overlap with ONE Hevy bout is at
# least this fraction of the SESSION'S OWN duration (A3.2, D-a / D-b). One constant, one definition:
# `overlaps_workout` is the only predicate, used by the Hevy-mirror read-door below, the resolver's
# `concurrent_strength` guard and the psychological duration read. Own duration (not the shorter of
# the pair) is what protects an erg or cardio session that merely brushes a sloppily started Hevy
# timer: a 2-minute brush on a 30-minute session is 0.07, not a copy.
# The Hevy side of the MIRROR test is every `hevy_workouts` row, excluded and unadjudicated-duplicate
# rows included (the A3.2 amendment); only readers that COUNT bouts use the `counted_workouts` door.
HEVY_MIRROR_OVERLAP_FRACTION = 0.50


# Fidelity rank — higher wins when two sources describe the same bout.
# polar_flow_export > polar_v4 > health_connect. Both Polar rows come off the
# same sensor, but the two transports do NOT carry the same payload: the v4
# *summary* list omits trainingLoadReport/zones (cardio_load, muscle_load and
# z*_seconds come back null — see connectors/polar.PolarV4Client.parse_session),
# while the Flow-export ZIP carries them. The sync's v4 zone enrichment (#261) later
# fills z*_seconds on zoneless v4 rows in its window, but never cardio_load or
# muscle_load, and a v4 row outside that window (or whose fetch returned no split)
# stays zoneless. So for a same-bout v4/flow_export twin the export row is at least
# as rich and must be the canonical one — otherwise the id-order tie-break can leave
# a zoneless v4 row canonical, which the metabolic transform then skips fail-closed
# (INV-7), dropping the bout entirely (#260/Q127).
# health_connect carries duration + type only. An unknown source ranks below all
# known ones rather than above.
#
# RICHNESS FIRST (Brief A A6): source rank orders rows only WITHIN a data tier (`_data_tier`).
# The rank above is a prior about which source usually carries more; the tier is what the row
# actually carries. The order was source-rank blind to HR/zone presence, so a zoneless
# flow_export row could suppress a same-bout v4 row that had zones — and the metabolic transform,
# which consumes canonical rows only and skips zoneless ones fail-closed (INV-7), then dropped
# the bout. Operator invariant: a row without HR never suppresses a same-bout row with HR.
# This refines #260/#309 (their source-rank / writer-class ladders now decide within a tier).
_SOURCE_RANK = {
    "polar_flow_export": 3,
    "polar_v4": 2,
    "health_connect": 1,
}
_UNKNOWN_RANK = 0


def _rank(source: Optional[str]) -> int:
    return _SOURCE_RANK.get(source or "", _UNKNOWN_RANK)


HEALTH_CONNECT = "health_connect"

# Writer-class table (#309, Ruling 1) — the SINGLE declared table used both here (same-bout
# arbitration between two `health_connect` rows, S3) and at admission (mirror-drop, S1,
# routers/health_connect). Classes rank wearable-native > aggregator/mirror > unknown; WITHIN
# a class rank is EQUAL, so the duration→start→id ladder in `_win_key` decides (Ruling 1: no
# per-device preference — a deliberate recording and an auto-detection are separated by the
# ladder, not by device identity). A package outside the table is `unknown` — the total
# catch-all (Ruling 2), so the table classifies EVERY package. `com.hevy` is deliberately
# absent: Hevy-mirrored bouts are dropped at admission (the Hevy connector owns them), never
# ingested as HC aerobic sessions, so they never reach this arbitration.
WEARABLE_NATIVE = frozenset({
    "com.garmin.android.apps.connectmobile",
    "com.sec.android.app.shealth",
    "fi.polar.polarflow",
})
AGGREGATOR_MIRROR = frozenset({
    "com.withings.wiscale2",
    "nl.appyhapps.healthsync",
})
_WRITER_CLASS_RANK = {"wearable_native": 2, "aggregator_mirror": 1, "unknown": 0}


def writer_class(source_package: Optional[str]) -> str:
    """The declared writer class for an HC recording package. Total over all packages —
    anything outside the table is `unknown` (Ruling 2)."""
    if source_package in WEARABLE_NATIVE:
        return "wearable_native"
    if source_package in AGGREGATOR_MIRROR:
        return "aggregator_mirror"
    return "unknown"


def writer_class_rank(source_package: Optional[str]) -> int:
    """Higher wins when two same-source `health_connect` rows describe one bout. Equal within
    a class (the ladder then decides)."""
    return _WRITER_CLASS_RANK[writer_class(source_package)]


def _ts(dt: Optional[datetime]) -> Optional[float]:
    """Epoch seconds, treating a naive datetime as UTC. Comparing epoch floats
    (not datetime objects) sidesteps aware/naive subtraction errors when rows
    from different sources carry different tzinfo shapes."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _data_tier(session) -> int:
    """How much physiological signal the row carries — the FIRST term of `_win_key` (Brief A A6,
    operator invariant: a row without HR never suppresses a same-bout row with HR).

        2  usable zones (the metabolic transform can score it — `_has_usable_zones`)
        1  avg HR present, no usable zones
        0  neither

    "Usable zones" reuses the transform's own INV-7 predicate, so the tier and the transform can
    never disagree about which row is scoreable. `hr_avg` presence is `is not None`."""
    if _has_usable_zones(session):
        return 2
    if session.hr_avg is not None:
        return 1
    return 0


def _win_key(session, dur: float, start_ts: float, *, by_writer: bool) -> tuple:
    """Ordering key for 'which row of a same-bout pair is canonical'. LARGER
    wins: richer data tier, then higher rank, then longer duration, then earlier
    start, then lower id. The id is a final deterministic discriminator so a
    fully-tied pair still yields exactly ONE canonical (never zero — which would
    drop the bout entirely). Within a tier the chain is rank -> duration -> start;
    id only breaks a residual exact tie.

    RICHNESS FIRST (Brief A A6): the data tier (`_data_tier`) leads, in BOTH regimes below. A row
    carrying HR/zones is never suppressed by a same-bout row that carries less, whatever the
    source or writer class; only among rows of the SAME tier does the ranking that stood before
    (#260/#309) decide. All-tier-0 pairs therefore order exactly as they did.

    Two rank bases, selected by the PAIR being compared (#309): a CROSS-source
    pair ranks by `source` fidelity (`_SOURCE_RANK`, e.g. polar_flow_export >
    polar_v4 > health_connect); a same-source `health_connect` pair ranks by
    WRITER CLASS (`writer_class_rank`, Ruling 1). Both sides of one comparison
    always use the same basis, so the ordering stays a total order."""
    rank = writer_class_rank(session.source_package) if by_writer else _rank(session.source)
    return (
        _data_tier(session),
        rank,
        dur,
        -start_ts,
        -(session.id if session.id is not None else 0),
    )


def arbitrate(sessions: list) -> list:
    """Set `.canonical` (bool) on every session in `sessions`, in place.

    A session is canonical unless some OTHER session describes the same bout
    (interval overlap >= OVERLAP_THRESHOLD of the shorter duration) and outranks
    it by `_win_key`. Two comparison regimes (#309):

    - CROSS-source pairs rank by `source` fidelity (the original behaviour).
    - Same-source `health_connect` pairs ARE compared, ranked by WRITER CLASS
      (Ruling 1) — two health_connect rows can be a same-bout pair: a mirror
      (identical start, lower writer class → dropped) or two independent device
      detections (starts seconds apart, both wearable → the ladder decides). This
      is why the same-source skip is now health_connect-specific, not universal.
    - Other same-source pairs (two polar_* rows) are still never compared —
      same-source duplication is out of scope there (the unique key prevents it).

    A session with no usable [start_time, stop_time] interval cannot be paired and
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
            for y in sessions:
                if y is x:
                    continue
                same_source = (y.source == x.source)
                # Same-source pairs are compared ONLY within health_connect (writer-class
                # arbitration); any other same-source pair is skipped as before.
                if same_source and x.source != HEALTH_CONNECT:
                    continue
                yi = intervals.get(id(y))
                if yi is None:
                    continue
                y_start, y_stop, y_dur = yi
                overlap = min(x_stop, y_stop) - max(x_start, y_start)
                if overlap < OVERLAP_THRESHOLD * min(x_dur, y_dur):
                    continue  # not the same bout
                # `same_source` here implies both rows are health_connect, so rank by
                # writer class; a cross-source pair ranks by source fidelity.
                by_writer = same_source
                x_key = _win_key(x, x_dur, x_start, by_writer=by_writer)
                if _win_key(y, y_dur, y_start, by_writer=by_writer) > x_key:
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
    """Aerobic sessions for a user, each carrying derived `.canonical` and `.hevy_mirror` flags.

    Arbitration runs over the whole `since`-windowed set BEFORE `limit` is
    applied, so a bout's counterpart is never truncated out of the comparison.

    Hevy mirrors (A3.2) are marked FIRST: a Health Connect row that is the same bout as ANY Hevy
    workout (excluded and unadjudicated-duplicate rows included, see `_hevy_near`) gets `hevy_mirror=True, canonical=False` and is kept OUT of the arbitration, so it
    can neither be emitted as a session nor suppress a live row for the same bout (a zoned
    Strava copy would otherwise outrank a zoneless watch row that is the genuine record). Mirrors
    are still RETURNED, like any non-canonical row, for callers that need every row (the Garmin
    self-evaluation link); every reader that lists or counts sessions filters on `.canonical`.
    """
    q = (
        db.query(models.AerobicSession)
        .filter(models.AerobicSession.user_id == user_id)
        .order_by(models.AerobicSession.session_date.desc())
    )
    if since is not None:
        q = q.filter(models.AerobicSession.session_date >= since)
    rows = q.all()
    hevy = _hevy_near(db, user_id, [r for r in rows if r.source == HEALTH_CONNECT])
    for r in rows:
        r.hevy_mirror = bool(hevy) and r.source == HEALTH_CONNECT and overlaps_workout(r, hevy)
    arbitrate([r for r in rows if not r.hevy_mirror])
    for r in rows:
        if r.hevy_mirror:
            r.canonical = False
    if limit is not None:
        rows = rows[:limit]
    return rows


def sport_names_seen(user_id: int, db: Session) -> list[dict[str, str]]:
    """Distinct `sport_name` this user has recorded, with a representative `source` (#317) — the
    pick-list the phase-change form offers for a slot's `device_sports` (plus free entry), so the
    operator scopes a slot by a sport that WILL match a real session rather than a guessed spelling
    (the Q164 mismatch risk). A NULL sport is skipped (it matches nothing — surfaced elsewhere as
    `no_sport`). Newest-first by the most recent session carrying each name."""
    rows = (
        db.query(models.AerobicSession.sport_name, models.AerobicSession.source,
                 models.AerobicSession.session_date)
        .filter(models.AerobicSession.user_id == user_id,
                models.AerobicSession.sport_name.isnot(None))
        .order_by(models.AerobicSession.session_date.desc())
        .all()
    )
    seen: dict[str, str] = {}
    for sport, source, _ in rows:
        s = (sport or "").strip()
        if s and s not in seen:
            seen[s] = source
    return [{"sport_name": k, "source": v} for k, v in seen.items()]


def overlap_fraction(session, workouts) -> float:
    """The largest share of `session`'s OWN duration covered by any ONE workout, 0.0..1.0.

    Own duration is the denominator on purpose (A3.2, D-a): a copy of a Hevy bout is covered by
    it almost completely, while an erg or cardio session that brushes a sloppily started Hevy
    timer is covered for a sliver of itself. A 60-minute watch row around a 25-minute bout is
    0.42, not a copy. One workout at a time (Hevy bouts do not overlap each other); two adjacent
    bouts do not add up to a single "same bout".

    An untimed session (NULL start or stop, or a non-positive span) has no interval, so it can
    never be shown to overlap: 0.0, and the caller counts it rather than dropping real minutes on
    an undecidable pair. A workout with a NULL endpoint is skipped. Instants are compared as epoch
    seconds, so a naive and an aware stamp (SQLite vs Postgres) cannot raise."""
    s_start, s_stop = _ts(session.start_time), _ts(session.stop_time)
    if s_start is None or s_stop is None or s_stop <= s_start:
        return 0.0
    own = s_stop - s_start
    best = 0.0
    for w in workouts:
        w_start, w_end = _ts(w.start_time), _ts(w.end_time)
        if w_start is None or w_end is None:
            continue
        best = max(best, min(s_stop, w_end) - max(s_start, w_start))
    return max(best, 0.0) / own


def overlaps_workout(session, workouts) -> bool:
    """True iff `session` is the same bout as one of `workouts`: its overlap with a single workout
    is at least `HEVY_MIRROR_OVERLAP_FRACTION` of its own duration. The SINGLE predicate (#309,
    A3.2 D-b) — the Hevy-mirror read-door in `arbitrated_sessions`, the resolver's
    `concurrent_strength` guard and the psychological duration read all call this, so "same bout
    as a Hevy workout" means the same thing to every reader. (It was any intersection at all, which
    treated an erg session brushing a Hevy timer as a strength trace.)"""
    return overlap_fraction(session, workouts) >= HEVY_MIRROR_OVERLAP_FRACTION


def _hevy_near(db: Session, user_id: int, rows) -> list:
    """EVERY Hevy workout near the timed rows, for the mirror test: excluded rows and both sides of
    an unadjudicated duplicate pair included. One query, bounded to the rows' span plus a day either
    side (a gym bout is hours long).

    Deliberately NOT the `counted_workouts` door (A3.2 amendment). The mirror test asks "did this
    Health Connect row come from a Hevy workout?", and the answer does not depend on whether Hevy's
    workout still counts. hevy2garmin does not honour a Hevy deletion: row 111 mirrors a bout the
    operator excluded on 18 Sep (`deleted_in_hevy_never_performed`), and the 7 Oct backfill pushed it
    into Garmin and on to Health Connect anyway. A test against only the counted bouts lets that copy
    through as a genuine session. Anything that COUNTS a bout still uses `counted_workouts`."""
    timed = [r for r in rows if _ts(r.start_time) is not None and _ts(r.stop_time) is not None]
    if not timed:
        return []
    lo = datetime.fromtimestamp(min(_ts(r.start_time) for r in timed), tz=timezone.utc) - timedelta(days=1)
    hi = datetime.fromtimestamp(max(_ts(r.stop_time) for r in timed), tz=timezone.utc) + timedelta(days=1)
    return (
        db.query(models.HevyWorkout)
        .filter(models.HevyWorkout.user_id == user_id,
                models.HevyWorkout.start_time >= lo,
                models.HevyWorkout.start_time <= hi)
        .all()
    )


def hevy_mirror_session_ids(user_id: int, db: Session, *, since: Optional[date] = None) -> set[int]:
    """Ids of the user's Health Connect rows that are Hevy mirrors, by the SAME predicate
    `arbitrated_sessions` uses -- for raw readers that cannot take ORM entities.

    Column-explicit on purpose: `cbti.replay` reads production BEFORE a migration deploys, so a
    full-entity load that selects a column the live database does not have yet would break the
    replay. This selects three columns (id, start_time, stop_time) that have existed since the
    table did, and filters on user and source."""
    q = (db.query(models.AerobicSession.id, models.AerobicSession.start_time, models.AerobicSession.stop_time)
         .filter(models.AerobicSession.user_id == user_id,
                 models.AerobicSession.source == HEALTH_CONNECT))
    if since is not None:
        q = q.filter(models.AerobicSession.session_date >= since)
    rows = q.all()
    hevy = _hevy_near(db, user_id, rows)
    return {r.id for r in rows if overlaps_workout(r, hevy)} if hevy else set()


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
