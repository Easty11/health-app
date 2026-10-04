"""Garmin per-activity self-evaluation (perceived effort, feel) into an immutable, capture-timed store (Q209 path a).

`garmin_activity_selfevals` is INSERT-ONLY: a row is what Garmin said at `captured_at`, and the only
writer is `_insert` here, which never updates. The current value of an activity is its latest row;
older rows are the history a later revision must not rewrite. A row is inserted when

  * the activity has no row yet (first sighting; an UNRATED sighting is a row too, rpe/feel NULL, so
    it is not re-fetched daily),
  * the observed (rpe, feel) differs from the latest row,
  * an UNRATED activity inside its re-check window is checked again and is still unrated (the daily
    marker: insert-only forbids a last-checked update, so the check IS the row), or
  * the DB-only relink pass finds the Health Connect row a rated activity's latest row lacks (a
    linked row with the same values).

Reads (two GETs per new activity, plus one list GET per user per run) go through the #361 no-refresh
seam: `ProbeSource` is `garmin_identity.LibrarySource` (the client's `_refresh_session` raises) plus
a generic GET, so this can never refresh a Garmin token, and it never writes to Garmin or reads HR.
It runs inside `scripts.garmin_sync.sweep_garmin_hrv`, right after that sweep's own refresh-and-
writeback, so the token it sees is fresh without this module adding a refresh. A token that still
needs one is reported as `skipped_needs_refresh`, never refreshed.

Scale (probe, 4 Oct 2026, activity 24564069469): `summaryDTO.directWorkoutRpe` 0-100 in steps of 10
(CR-10 x 10) -> `rpe_cr10` = value / 10; `summaryDTO.directWorkoutFeel` 0/25/50/75/100 -> `feel`. Both
live on the activity DETAIL, not the list. A negative is narrow (FEEDBACK section 17): absent or null
keys mean unrated, but a detail with no `summaryDTO` at all is a shape change, reported as an error and
never recorded as "unrated".
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import models
from encryption import decrypt
from reads.aerobic_reads import HEALTH_CONNECT, OVERLAP_THRESHOLD, arbitrated_sessions
from scripts.garmin_identity import RefreshWouldBeNeeded
from scripts.garmin_selfeval_probe import ACTIVITY_LIST_PATH, ACTIVITY_PATH, ProbeSource

logger = logging.getLogger(__name__)

GARMIN_HC_PACKAGE = "com.garmin.android.apps.connectmobile"   # in reads.aerobic_reads.WEARABLE_NATIVE
RPE_KEY = "directWorkoutRpe"
FEEL_KEY = "directWorkoutFeel"

LIST_WINDOW_DAYS = 14        # how far back a first run (or a gap) lists
LIST_LIMIT = 50              # one bounded page; a fuller page converges over the next runs
RECHECK_DAYS = 7             # an unrated activity is re-checked for this long after its start, then left
RECHECK_MIN_GAP = timedelta(hours=20)   # at most about one re-check a day per activity
RELINK_DAYS = 14             # the DB-only relink pass only looks at activities this recent

SourceFactory = Callable[[str], Any]


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _parse_gmt(s: Any) -> datetime | None:
    """Garmin's `startTimeGMT` ('2026-10-04 01:30:00', no offset: it IS GMT) as an aware UTC datetime."""
    if not isinstance(s, str) or not s:
        return None
    try:
        return _utc(datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T")))
    except ValueError:
        return None


def _scale(raw: Any, *, field: str, activity_id: int) -> float | None:
    """A Garmin 0-100 self-evaluation value as a float, or None when absent, non-numeric or out of range
    (the last two logged: corrupt at source is not a rating, and the row is not lost over it)."""
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not 0 <= raw <= 100:
        logger.warning("garmin selfeval: activity %s has unusable %s (%r); treated as unrated", activity_id, field, raw)
        return None
    return float(raw)


def parse_selfeval(detail: Any, activity_id: int) -> tuple[float | None, int | None] | None:
    """`(rpe_cr10, feel)` from one activity DETAIL payload, `(None, None)` when unrated, or None when the
    payload has no `summaryDTO` object (a shape change: not a rating, not recorded)."""
    summary = detail.get("summaryDTO") if isinstance(detail, dict) else None
    if not isinstance(summary, dict):
        return None
    rpe = _scale(summary.get(RPE_KEY), field=RPE_KEY, activity_id=activity_id)
    feel = _scale(summary.get(FEEL_KEY), field=FEEL_KEY, activity_id=activity_id)
    return (None if rpe is None else rpe / 10.0), (None if feel is None else int(round(feel)))


def find_link(db, user_id: int, start: datetime, stop: datetime | None) -> int | None:
    """The `aerobic_sessions` Health Connect row of the same bout: a Garmin-package row whose interval
    overlaps this activity's by at least `OVERLAP_THRESHOLD` (50%) of the SHORTER of the two. Greatest
    overlap wins, then the lowest id. None when there is none (a Garmin-only type that never reaches
    Health Connect, e.g. breathwork, or an HC row that has not arrived yet) or this activity has no
    interval."""
    start, stop = _utc(start), _utc(stop)
    if start is None or stop is None or stop <= start:
        return None
    # Through THE read-door (`arbitrated_sessions`, #Q161): it returns every row, canonical or not, which is
    # what a link needs (the Garmin HC row may have lost to a same-bout twin; the readout carries the value
    # to the winner). Narrowed here, in Python, to this user's timed Garmin-package Health Connect rows.
    rows = [r for r in arbitrated_sessions(user_id, db, since=(start - timedelta(days=1)).date())
            if r.source == HEALTH_CONNECT and r.source_package == GARMIN_HC_PACKAGE
            and r.start_time is not None and r.stop_time is not None
            and r.session_date <= (stop + timedelta(days=1)).date()]
    best: tuple[float, int] | None = None
    for r in rows:
        r_start, r_stop = _utc(r.start_time), _utc(r.stop_time)
        r_dur = (r_stop - r_start).total_seconds()
        if r_dur <= 0:
            continue
        overlap = (min(stop, r_stop) - max(start, r_start)).total_seconds()
        if overlap < OVERLAP_THRESHOLD * min((stop - start).total_seconds(), r_dur):
            continue
        if best is None or overlap > best[0] or (overlap == best[0] and r.id < best[1]):
            best = (overlap, r.id)
    return None if best is None else best[1]


def _latest_by_activity(db, user_id: int, activity_ids: set[int] | None = None) -> dict[int, models.GarminActivitySelfEval]:
    """The latest row (greatest `captured_at`, then id) per activity: the CURRENT value of each."""
    q = db.query(models.GarminActivitySelfEval).filter(models.GarminActivitySelfEval.user_id == user_id)
    if activity_ids is not None:
        q = q.filter(models.GarminActivitySelfEval.garmin_activity_id.in_(activity_ids))
    out: dict[int, models.GarminActivitySelfEval] = {}
    for r in q.order_by(models.GarminActivitySelfEval.captured_at, models.GarminActivitySelfEval.id):
        out[r.garmin_activity_id] = r        # ascending, so the last write per activity is the latest
    return out


def _insert(db, user_id: int, *, activity_id: int, rpe: float | None, feel: int | None, garmin_type: str | None,
            start: datetime, stop: datetime | None, link: int | None, now: datetime,
            prior: models.GarminActivitySelfEval | None) -> models.GarminActivitySelfEval:
    """THE write: one INSERT, committed. Strictly later than the activity's prior row, so the unique key
    (user, activity, captured_at) cannot collide and "latest" is unambiguous."""
    captured = now
    if prior is not None and _utc(prior.captured_at) >= captured:
        captured = _utc(prior.captured_at) + timedelta(microseconds=1)
    row = models.GarminActivitySelfEval(
        user_id=user_id, garmin_activity_id=activity_id, captured_at=captured, rpe_cr10=rpe, feel=feel,
        garmin_type=garmin_type, start_time=start, stop_time=stop, aerobic_session_id=link)
    db.add(row)
    db.commit()
    return row


def _is_rated(r: models.GarminActivitySelfEval) -> bool:
    return r.rpe_cr10 is not None or r.feel is not None


def _relink(db, user_id: int, now: datetime) -> int:
    """DB-only: a rated activity whose latest row has no link, and whose Health Connect row has since
    arrived, gets a NEW row (same values, linked). No Garmin call. Returns the number linked."""
    cutoff = now - timedelta(days=RELINK_DAYS)
    linked = 0
    for r in _latest_by_activity(db, user_id).values():
        if r.aerobic_session_id is not None or not _is_rated(r) or _utc(r.start_time) < cutoff:
            continue
        link = find_link(db, user_id, r.start_time, r.stop_time)
        if link is None:
            continue
        _insert(db, user_id, activity_id=r.garmin_activity_id, rpe=r.rpe_cr10, feel=r.feel,
                garmin_type=r.garmin_type, start=r.start_time, stop=r.stop_time, link=link, now=now, prior=r)
        linked += 1
    return linked


def _list_item_fields(item: Any) -> tuple[int, datetime, datetime | None, str | None] | None:
    """`(activity_id, start_utc, stop_utc, type_key)` from one activity-list item, or None if unusable."""
    if not isinstance(item, dict):
        return None
    aid = item.get("activityId")
    start = _parse_gmt(item.get("startTimeGMT"))
    if isinstance(aid, bool) or not isinstance(aid, int) or start is None:
        return None
    dur = item.get("duration")
    stop = start + timedelta(seconds=float(dur)) if isinstance(dur, (int, float)) and not isinstance(dur, bool) and dur > 0 else None
    atype = item.get("activityType")
    type_key = atype.get("typeKey") if isinstance(atype, dict) else None
    return aid, start, stop, (str(type_key)[:100] if type_key else None)


def sync_user(db, user_id: int, *, factory: SourceFactory = ProbeSource, now: datetime | None = None,
              window_days: int = LIST_WINDOW_DAYS) -> dict[str, Any]:
    """One user's self-evaluation capture. Never refreshes a token, never writes to Garmin, never reads HR.

    Order: (1) the DB-only relink pass, which always runs; (2) the read: ONE list GET since the last
    captured start (bounded by `window_days`), then ONE detail GET per activity that has no row yet, and
    per unrated activity due a re-check (start within `RECHECK_DAYS`, last observed over
    `RECHECK_MIN_GAP` ago). The list is processed oldest-first and the read STOPS at the first failure, so
    the last captured start never passes an unfetched activity.

    Returns `{fetched, rated, unrated, linked, relinked, skipped_needs_refresh, errors}` (counts; the
    last two are 0/1 and a number). `fetched` counts detail records read; `rated` and `unrated` the
    observations inserted from them; `linked` those inserted with a link (relinks included in `linked`).
    """
    now = _utc(now) or datetime.now(timezone.utc)
    out = {"fetched": 0, "rated": 0, "unrated": 0, "linked": 0, "relinked": 0,
           "skipped_needs_refresh": 0, "errors": 0}

    out["relinked"] = _relink(db, user_id, now)
    out["linked"] += out["relinked"]

    row = db.query(models.UserIntegration).filter_by(user_id=user_id, provider="garmin").first()
    if row is None:
        return out
    try:
        source = factory(decrypt(row.api_key_encrypted))
        latest = _latest_by_activity(db, user_id)
        floor = (now - timedelta(days=window_days)).date()
        last_start = max((_utc(r.start_time) for r in latest.values()), default=None)
        since: date = max(floor, (last_start - timedelta(days=1)).date()) if last_start else floor
        listed = source.get(ACTIVITY_LIST_PATH, {"startDate": since.isoformat(), "start": "0",
                                                  "limit": str(LIST_LIMIT), "sortOrder": "asc"})
        items = [f for f in (_list_item_fields(i) for i in (listed if isinstance(listed, list) else [])) if f]
        items.sort(key=lambda f: f[1])
        # Work list, oldest first: (activity, start, stop, type, prior row or None).
        todo: list[tuple[int, datetime, datetime | None, str | None, models.GarminActivitySelfEval | None]] = []
        for aid, start, stop, tkey in items:
            if aid not in latest:                                   # never seen: rated or not, it gets a row
                todo.append((aid, start, stop, tkey, None))
        for aid, r in latest.items():                               # unrated and due a re-check (from the store)
            if (not _is_rated(r) and now - _utc(r.start_time) < timedelta(days=RECHECK_DAYS)
                    and now - _utc(r.captured_at) >= RECHECK_MIN_GAP):
                todo.append((aid, _utc(r.start_time), _utc(r.stop_time), r.garmin_type, r))
        todo.sort(key=lambda t: t[1])
        for aid, start, stop, tkey, prior in todo:
            detail = source.get(f"{ACTIVITY_PATH}/{aid}")
            out["fetched"] += 1
            parsed = parse_selfeval(detail, aid)
            if parsed is None:
                logger.error("garmin selfeval: activity %s detail has no summaryDTO object (shape changed?)", aid)
                out["errors"] += 1
                break
            rpe, feel = parsed
            rated = rpe is not None or feel is not None
            if prior is not None and (rpe, feel) == (prior.rpe_cr10, prior.feel) and rated:
                continue                    # re-read of a rated value that did not change: no row
            link = find_link(db, user_id, start, stop) if rated else None
            _insert(db, user_id, activity_id=aid, rpe=rpe, feel=feel, garmin_type=tkey, start=start, stop=stop,
                    link=link, now=now, prior=prior)
            out["rated" if rated else "unrated"] += 1
            if link is not None:
                out["linked"] += 1
    except RefreshWouldBeNeeded:
        db.rollback()
        out["skipped_needs_refresh"] = 1
    except Exception as exc:  # noqa: BLE001 -- the error CLASS is the whole report; a Garmin hiccup never costs the sweep
        db.rollback()
        out["errors"] += 1
        logger.warning("garmin selfeval: user %s read stopped: %s", user_id, type(exc).__name__)
    return out


def selfeval_by_session(db, user_id: int, sessions: list) -> dict[int, models.GarminActivitySelfEval]:
    """`{aerobic_session.id: latest selfeval row}` for the given arbitrated sessions (rated rows only).

    A row attaches to its linked session; and when that linked Health Connect row LOST arbitration to a
    same-bout twin (a Polar row, say), it attaches to the canonical twin instead, so the value is not
    dropped from the readout. Twin = overlap of at least `OVERLAP_THRESHOLD` of the shorter."""
    by_link = {r.aerobic_session_id: r for r in _latest_by_activity(db, user_id).values()
               if r.aerobic_session_id is not None and _is_rated(r)}
    if not by_link:
        return {}
    out: dict[int, models.GarminActivitySelfEval] = {}
    canonical = [s for s in sessions if getattr(s, "canonical", True)]
    for s in sessions:
        r = by_link.get(s.id)
        if r is None:
            continue
        if getattr(s, "canonical", True):
            out[s.id] = r
            continue
        s_start, s_stop = _utc(s.start_time), _utc(s.stop_time)
        if s_start is None or s_stop is None or s_stop <= s_start:
            continue
        for c in canonical:
            c_start, c_stop = _utc(c.start_time), _utc(c.stop_time)
            if c_start is None or c_stop is None or c_stop <= c_start:
                continue
            overlap = (min(s_stop, c_stop) - max(s_start, c_start)).total_seconds()
            if overlap >= OVERLAP_THRESHOLD * min((s_stop - s_start).total_seconds(), (c_stop - c_start).total_seconds()):
                out.setdefault(c.id, r)
                break
    return out
