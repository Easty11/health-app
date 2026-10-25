"""Garmin per-activity self-evaluation (perceived effort, feel), adapter #1 of the source-neutral sRPE store.

This module READS Garmin and writes through the contract (`srpe_store.record_observation`) into
`session_rpe_observations`; it owns no table and no write of its own. Which counted session a rating belongs
to is not decided here: the read door (`reads.srpe_reads`) places it by overlap of its window, so this
adapter keeps no link to a Health Connect row, no relink pass, and no twin carry-over. (Rows written before
the store was source-neutral were copied by the migration; `garmin_activity_selfevals` is read-only.)

The store is INSERT-ONLY: a row is what Garmin said at `captured_at`. A row is inserted when

  * the activity has no row yet (first sighting; an UNRATED sighting is a row too, rpe/feel NULL, so
    it is not re-fetched daily),
  * the observed (rpe, feel) differs from the latest row, or
  * an UNRATED activity inside its re-check window is checked again and is still unrated (the daily
    marker: insert-only forbids a last-checked update, so the check IS the row).

Reads (two GETs per new activity, plus one list GET per user per run) go through the #361 no-refresh
seam: `ProbeSource` is `garmin_identity.LibrarySource` (the client's `_refresh_session` raises) plus
a generic GET, so this can never refresh a Garmin token, and it never writes to Garmin or reads HR.
It runs inside `scripts.garmin_sync.sweep_garmin_hrv`, right after that sweep's own refresh-and-
writeback, so the token it sees is fresh without this module adding a refresh. A token that still
needs one is reported as `skipped_needs_refresh`, never refreshed. The sweep runs once a night (02:00
Brisbane, `load_sweep`), so a rating given in Garmin reaches the store after that night's close-out.

Scale (probe, 4 Oct 2026, activity 24564069469): `summaryDTO.directWorkoutRpe` 0-100 in steps of 10
(CR-10 x 10), declared to the contract as `garmin_0_100`; `summaryDTO.directWorkoutFeel` 0/25/50/75/100 ->
`feel`. Both live on the activity DETAIL, not the list. A negative is narrow (FEEDBACK section 17): absent or
null keys mean unrated, but a detail with no `summaryDTO` at all is a shape change, reported as an error and
never recorded as "unrated".
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

import models
import srpe_store
from encryption import decrypt
from scripts.garmin_identity import RefreshWouldBeNeeded
from scripts.garmin_selfeval_probe import ACTIVITY_LIST_PATH, ACTIVITY_PATH, ProbeSource

logger = logging.getLogger(__name__)

SOURCE = "garmin"                       # the adapter's name in the contract and in SOURCE_HIERARCHY
RAW_SCALE = srpe_store.GARMIN_0_100.name
RPE_KEY = "directWorkoutRpe"
FEEL_KEY = "directWorkoutFeel"

LIST_WINDOW_DAYS = 14        # how far back a first run (or a gap) lists
LIST_LIMIT = 50              # one bounded page; a fuller page converges over the next runs
RECHECK_DAYS = 7             # an unrated activity is re-checked for this long after its start, then left
RECHECK_MIN_GAP = timedelta(hours=20)   # at most about one re-check a day per activity

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
    """`(rpe_raw, feel)` from one activity DETAIL payload, `(None, None)` when unrated, or None when the
    payload has no `summaryDTO` object (a shape change: not a rating, not recorded). `rpe_raw` is Garmin's
    0-100 as sent; the contract converts it to CR-10 on the declared `garmin_0_100` scale."""
    summary = detail.get("summaryDTO") if isinstance(detail, dict) else None
    if not isinstance(summary, dict):
        return None
    rpe = _scale(summary.get(RPE_KEY), field=RPE_KEY, activity_id=activity_id)
    feel = _scale(summary.get(FEEL_KEY), field=FEEL_KEY, activity_id=activity_id)
    return rpe, (None if feel is None else int(round(feel)))


def _latest_by_activity(db, user_id: int) -> dict[int, models.SessionRpeObservation]:
    """The latest row (greatest `captured_at`, then id) per Garmin activity: the CURRENT value of each."""
    return {int(ref): r for (_, ref), r in srpe_store.latest_by_activity(db, user_id, SOURCE).items()}


def _insert(db, user_id: int, *, activity_id: int, rpe_raw: float | None, feel: int | None, garmin_type: str | None,
            start: datetime, stop: datetime | None, now: datetime,
            transport: str = "di") -> models.SessionRpeObservation:
    """THE Garmin write: one call to the contract, which converts on the declared scale, inserts, commits,
    and places the row strictly later than the activity's prior one. `source` stays 'garmin' whichever
    transport read it; the transport ('personal_api' | 'di') is audit detail in `provenance`."""
    return srpe_store.record_observation(
        db, user_id, source=SOURCE, source_activity_ref=activity_id, start=start, stop=stop, rpe_raw=rpe_raw,
        raw_scale=RAW_SCALE, feel=feel, provenance={"garmin_type": garmin_type, "transport": transport}, now=now)


def _is_rated(r: models.SessionRpeObservation) -> bool:
    return r.rpe_cr10 is not None or r.feel is not None


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
              window_days: int = LIST_WINDOW_DAYS, source: Any = None,
              transport: str = "di") -> dict[str, Any]:
    """One user's self-evaluation capture. Never refreshes a token, never writes to Garmin, never reads HR.

    ONE list GET since the last captured start (bounded by `window_days`), then ONE detail GET per
    activity that has no row yet, and per unrated activity due a re-check (start within `RECHECK_DAYS`,
    last observed over `RECHECK_MIN_GAP` ago). The list is processed oldest-first and the read STOPS at the
    first failure, so the last captured start never passes an unfetched activity.

    Returns `{fetched, rated, unrated, skipped_needs_refresh, errors}` (counts; `skipped_needs_refresh` is
    0/1). `fetched` counts detail records read; `rated` and `unrated` the observations inserted from them.

    `source` (a prebuilt object with `.get(path, params=None)`) bypasses the DI row lookup: the Personal
    API lane passes its `PersonalClient` with `transport='personal_api'`. Everything after the read is the
    same code, so the contract, the scale and the re-check rules are shared between the two lanes.
    """
    now = _utc(now) or datetime.now(timezone.utc)
    out = {"fetched": 0, "rated": 0, "unrated": 0, "skipped_needs_refresh": 0, "errors": 0}

    own_source = source is None
    row = None
    if own_source:
        row = db.query(models.UserIntegration).filter_by(user_id=user_id, provider="garmin").first()
        if row is None:
            return out
    try:
        if own_source:
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
        todo: list[tuple[int, datetime, datetime | None, str | None, models.SessionRpeObservation | None]] = []
        for aid, start, stop, tkey in items:
            if aid not in latest:                                   # never seen: rated or not, it gets a row
                todo.append((aid, start, stop, tkey, None))
        for aid, r in latest.items():                               # unrated and due a re-check (from the store)
            if (not _is_rated(r) and now - _utc(r.start_time) < timedelta(days=RECHECK_DAYS)
                    and now - _utc(r.captured_at) >= RECHECK_MIN_GAP):
                todo.append((aid, _utc(r.start_time), _utc(r.stop_time), (r.provenance or {}).get("garmin_type"), r))
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
            if prior is not None and (rpe, feel) == (prior.rpe_raw, prior.feel) and rated:
                continue                    # re-read of a rated value that did not change: no row
            _insert(db, user_id, activity_id=aid, rpe_raw=rpe, feel=feel, garmin_type=tkey, start=start, stop=stop,
                    now=now, transport=transport)
            out["rated" if rated else "unrated"] += 1
    except RefreshWouldBeNeeded:
        db.rollback()
        out["skipped_needs_refresh"] = 1
    except Exception as exc:  # noqa: BLE001 -- the error CLASS is the whole report; a Garmin hiccup never costs the sweep
        db.rollback()
        out["errors"] += 1
        logger.warning("garmin selfeval: user %s read stopped: %s", user_id, type(exc).__name__)
    return out
