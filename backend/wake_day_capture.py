"""Wake-day capture: land the CURRENT wake-day's overnight vitals the morning they happen.

Why this exists. The 02:00 Brisbane sweep reads the wake-day while the night is still in progress (no
`sleepTimeSeconds`, no resting rate) and the on-read refresh used to pull HRV only, so SpO2, respiratory rate,
resting HR and efficiency reached the store ~20 h late, via the NEXT night's sweep. This module is the
morning fetch:

  * ONE fetch per user per wake-day: Personal API `dailySleep`, `dailyHeartRate`, `spo2acclimation` and `hrv`
    (4 data requests, plus 1 if the token is re-exchanged) and the DI `dailySleepData` night (2 requests: the
    social profile, then the night). Mappers and stored values are unchanged; this only decides WHEN to read.
  * TRIGGERS: opening the AM check-in (`checkin`), opening the Recovery page (`recovery`), its Refresh button
    (`refresh`, forced), and the 10:00 Brisbane backstop (`backstop`) for any user whose wake-day is still
    incomplete. The capture window CLOSES at 10:00: after it, an unforced open does not fetch (a forced
    Refresh still does, and the next 02:00 sweep still re-reads the last days).
  * GATES, all server-side: skip when the wake-day is already complete (a finished night, `sleep_time_s`
    present, and the DI epoch night landed for a user with a DI connection); a 30-minute per-user throttle on
    the last attempt; an explicit Refresh bypasses the throttle but keeps a 60 s floor (the host answers 429
    to a burst); one fetch in flight per user (a second caller is told `in_progress`).
  * SLOT STATES for the current wake-day, per figure: `filled`; `pending` (missing, before 10:00);
    `not_synced` (the last fetch found no finished night: Garmin has not received the watch's data);
    `missing` with a reason (missing, after 10:00). A slot never carries an earlier night's value: the
    candidates are read for the wake-day only.

Read-side plus fetch triggering. The attempt is recorded as the `wake_day_fetch` lane (a status row, upserted;
its `last_attempt_at` is the throttle clock and its reason is "<wake-day> <code> via=<trigger>").
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import httpx
import pytz

import garmin_personal_lanes as gpl
import garmin_raw
import garmin_wellness
import models
from connectors import garmin_personal as gp
from connectors.garmin import GarminPersonalKeyError
from reads.recovery_night import load_candidates, resolve_night

logger = logging.getLogger(__name__)

_BRISBANE = pytz.timezone("Australia/Brisbane")          # fixed UTC+10, no DST
CAPTURE_CLOSES_HOUR = 10                                  # the capture window for a wake-day closes at 10:00 local
THROTTLE = timedelta(minutes=30)                          # per-user, on the last attempt
FORCE_FLOOR = timedelta(seconds=60)                       # an explicit Refresh still may not burst the host

TRIGGERS = ("checkin", "recovery", "refresh", "backstop")
WAKE_DAY_ENDPOINTS = (garmin_wellness.EP_SLEEP, garmin_wellness.EP_HEART_RATE, garmin_wellness.EP_SPO2_HOURLY)

SLOTS = ("sleep", "efficiency", "awake", "spo2", "rr", "rhr")
NOT_SYNCED_MESSAGE = "Garmin not synced yet — open Garmin Connect, then Refresh"

# fetch-outcome codes written into the lane reason
COMPLETE, NOT_SYNCED, SPO2_MISSING = "complete", "not_synced", "spo2_missing"
AUTH_FAILED, RATE_LIMITED, FETCH_ERROR = "auth_failed", "rate_limited", "error"

_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


# -- time -----------------------------------------------------------------------------------------------

def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def local(now: datetime) -> datetime:
    return _utc(now).astimezone(_BRISBANE)


def wake_day(now: datetime) -> date:
    """The Brisbane-local date: the date Garmin files the night just slept under."""
    return local(now).date()


def window_open(now: datetime) -> bool:
    return local(now).hour < CAPTURE_CLOSES_HOUR


# -- state ----------------------------------------------------------------------------------------------

@dataclass
class WakeDayState:
    day: date
    personal: bool                    # a Personal API key is attached
    di: bool                          # a DI token is attached (the epoch-SpO2 lane)
    sleep_done: bool                  # a Garmin sleep night for the wake-day carrying sleep_time_s
    spo2_done: bool                   # a DI epoch night for the wake-day
    slots: dict[str, bool] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        """The completeness skip: a finished night and, for a user with a DI connection, the epoch SpO2 night."""
        return self.personal and self.sleep_done and (self.spo2_done or not self.di)

    @property
    def gaps(self) -> list[str]:
        return [s for s in SLOTS if not self.slots.get(s)]


def read_state(db, user_id: int, day: date) -> WakeDayState:
    personal = gpl.get_row(db, user_id) is not None
    di = db.query(models.UserIntegration.id).filter_by(user_id=user_id, provider="garmin").first() is not None
    night = db.query(models.SleepNight).filter_by(user_id=user_id, captured_at=day, source="garmin").first()
    spo2 = db.query(models.Spo2Night.id).filter_by(user_id=user_id, captured_at=day, source="garmin").first()
    r = resolve_night(day, load_candidates(db, user_id, day).get(day, {}))
    stages = (r["stages"] or {}).get("value") or {}
    slots = {
        "sleep": r["tst"] is not None,
        "efficiency": r["efficiency"] is not None,
        "awake": stages.get("awake") is not None,
        "spo2": r["spo2"] is not None,
        "rr": r["rr"] is not None,
        "rhr": r["daily_rhr"] is not None,
    }
    return WakeDayState(day=day, personal=personal, di=di,
                        sleep_done=night is not None and night.sleep_time_s is not None,
                        spo2_done=spo2 is not None, slots=slots)


def _lane(db, user_id: int) -> Optional[models.IntegrationLaneStatus]:
    return db.query(models.IntegrationLaneStatus).filter_by(user_id=user_id, lane=garmin_raw.LANE_WAKE_DAY).first()


def _attempt(lane: Optional[models.IntegrationLaneStatus], day: date) -> Optional[dict[str, Any]]:
    """The last attempt IF it was for this wake-day: {code, via, outcome, at}. The reason is
    '<wake-day> <code> via=<trigger>'; an attempt for another day is no attempt for this one."""
    if lane is None or not lane.reason:
        return None
    parts = lane.reason.split()
    if len(parts) < 2 or parts[0] != day.isoformat():
        return None
    via = parts[2].split("=", 1)[1] if len(parts) > 2 and parts[2].startswith("via=") else None
    return {"code": parts[1], "via": via, "outcome": lane.outcome, "at": _utc(lane.last_attempt_at)}


_FAILURE_TEXT = {
    AUTH_FAILED: "the Garmin key was refused",
    RATE_LIMITED: "Garmin rate-limited the fetch",
    FETCH_ERROR: "the fetch failed",
    NOT_SYNCED: "Garmin had no finished night to return",
}


def _missing_reason(attempt: Optional[dict[str, Any]], state: WakeDayState) -> str:
    if attempt is None:
        return "no fetch ran before 10:00 (no check-in or Recovery open)"
    code = attempt["code"]
    if code in _FAILURE_TEXT:
        return _FAILURE_TEXT[code]
    if code == SPO2_MISSING:
        return "Garmin returned the night without the epoch SpO2"
    return "Garmin returned the night without it"


def status(db, user_id: int, *, now: Optional[datetime] = None) -> dict[str, Any]:
    """The current wake-day's slot states for one user. Read-only; the shape the Recovery page, the Dashboard tile
    and the Settings card read. `connected` is False for a user with no Garmin connection (no slots are claimed)."""
    now = _utc(now or datetime.now(timezone.utc))
    day = wake_day(now)
    state = read_state(db, user_id, day)
    if not (state.personal or state.di):
        return {"connected": False, "wake_day": day.isoformat()}
    open_ = window_open(now)
    lane = _lane(db, user_id)
    att = _attempt(lane, day)
    slots: dict[str, dict[str, str]] = {}
    for name in SLOTS:
        if state.slots.get(name):
            slots[name] = {"state": "filled"}
        elif open_:
            if att is not None and att["code"] == NOT_SYNCED:
                slots[name] = {"state": "not_synced", "message": NOT_SYNCED_MESSAGE}
            else:
                suffix = f" — last fetch: {_FAILURE_TEXT[att['code']]}" if att and att["code"] in _FAILURE_TEXT else ""
                slots[name] = {"state": "pending", "message": "pending" + suffix}
        else:
            slots[name] = {"state": "missing", "message": f"missing — {_missing_reason(att, state)}"}
    gaps = [n for n in SLOTS if slots[n]["state"] != "filled"]
    if not gaps:
        message = None
    elif open_:
        message = (NOT_SYNCED_MESSAGE if att is not None and att["code"] == NOT_SYNCED
                   else f"Overnight data for {day.isoformat()} is still arriving: {', '.join(gaps)} pending")
    else:
        message = (f"Capture for {day.isoformat()} closed at {CAPTURE_CLOSES_HOUR}:00 without: {', '.join(gaps)} "
                   f"({_missing_reason(att, state)})")
    return {
        "connected": True,
        "wake_day": day.isoformat(),
        "window_open": open_,
        "closes_at": f"{CAPTURE_CLOSES_HOUR:02d}:00",
        "complete": state.complete,
        "slots": slots,
        "gaps": gaps,
        "message": message,
        "last_attempt_at": att["at"].isoformat() if att else None,
        "last_outcome": att["code"] if att else None,
        "last_via": att["via"] if att else None,
    }


# -- the fetch ------------------------------------------------------------------------------------------

def _user_lock(user_id: int) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(user_id, threading.Lock())


def _skipped(db, user_id: int, reason: str, now: datetime) -> dict[str, Any]:
    from routers.garmin import _latest_garmin_ingest_at

    last = _latest_garmin_ingest_at(db, user_id)
    return {"skipped": True, "reason": reason, "last_ingested_at": last.isoformat() if last else None,
            "status": status(db, user_id, now=now)}


def _fetch(db, user_id: int, day: date, *, transport, spo2_factory) -> tuple[Optional[str], dict[str, int]]:
    """Run the fetch. Returns (failure_code or None, request counts). Never raises; lane statuses are recorded
    for the Personal API lanes exactly as the sweep records them."""
    from routers.garmin import sync_hrv_for_user

    requests = {"personal": 0, "di": 0}
    failure: Optional[str] = None
    if gpl.get_row(db, user_id) is not None:
        try:
            with gpl.personal_client(db, user_id, transport=transport) as client:
                if client is None:
                    raise gpl.NoPersonalKey(f"user {user_id} has no garmin_personal key")
                lane = garmin_raw.LANE_PERSONAL_HRV           # the lane a PersonalApiError below belongs to
                try:
                    try:
                        sync_hrv_for_user(db, user_id, day, day, client=client)   # records its own lane
                    except GarminPersonalKeyError:
                        failure = AUTH_FAILED
                    if failure is None:
                        lane = garmin_raw.LANE_PERSONAL_WELLNESS
                        counts = garmin_wellness.sync_user(db, user_id, client, start=day, end=day,
                                                           with_zones=False, endpoints=WAKE_DAY_ENDPOINTS)
                        gpl.record_success(db, user_id, lane,
                                           empty=not any(v for k, v in counts.items() if k not in ("days", "empty")))
                except gp.PersonalApiError as exc:
                    db.rollback()
                    if lane != garmin_raw.LANE_PERSONAL_HRV:      # the HRV pull already recorded its own failure
                        gpl.record_failure(db, user_id, lane, exc)
                    failure = {garmin_raw.AUTH_FAILED: AUTH_FAILED,
                               garmin_raw.RATE_LIMITED: RATE_LIMITED}.get(gpl.failure_outcome(exc), FETCH_ERROR)
                finally:
                    requests["personal"] = client.requests
        except gpl.NoPersonalKey:
            failure = FETCH_ERROR
        except Exception as exc:  # noqa: BLE001 -- a fetch must never raise into a card
            db.rollback()
            logger.warning("wake-day capture: user %s personal fetch crashed: %s", user_id, type(exc).__name__)
            failure = failure or FETCH_ERROR

    if db.query(models.UserIntegration.id).filter_by(user_id=user_id, provider="garmin").first() is not None:
        from scripts.garmin_sync import _di_spo2_lane

        import garmin_spo2
        res = _di_spo2_lane(db, user_id, spo2_factory or garmin_spo2.ProbeSource, day, day, keepalive=True)
        # the social-profile GET, plus the night(s) read; the token keepalive is not counted (not a data request)
        requests["di"] = (0 if res.get("keepalive") == "reconnect_required" else 1) + res.get("nights_fetched", 0)
    return failure, requests


def run(db, user_id: int, *, trigger: str, force: bool = False, now: Optional[datetime] = None,
        transport: Optional[httpx.BaseTransport] = None, spo2_factory=None) -> dict[str, Any]:
    """Capture the current wake-day for one user, if the gates allow. Never raises.

    Returns `{"skipped": True, "reason": ..., "last_ingested_at": ..., "status": ...}` when nothing was fetched
    (`no_personal_key`, `complete`, `window_closed`, `throttled`, `in_progress`, `backstop_done`), else
    `{"wake_day", "outcome", "via", "requests", "status"}`. Both carry the post-run slot `status`."""
    if trigger not in TRIGGERS:
        raise ValueError(f"unknown trigger {trigger!r}")
    now = _utc(now or datetime.now(timezone.utc))
    day = wake_day(now)

    if gpl.get_row(db, user_id) is None:
        return _skipped(db, user_id, "no_personal_key", now)
    state = read_state(db, user_id, day)
    lane = _lane(db, user_id)

    if trigger == "backstop":
        if not state.gaps and state.complete:
            return _skipped(db, user_id, "complete", now)
        att = _attempt(lane, day)
        if att is not None and att["via"] == "backstop":
            return _skipped(db, user_id, "backstop_done", now)
    elif not force:
        if not window_open(now):
            return _skipped(db, user_id, "window_closed", now)
        if state.complete:
            return _skipped(db, user_id, "complete", now)

    if lane is not None and trigger != "backstop":
        age = now - _utc(lane.last_attempt_at)
        if age < (FORCE_FLOOR if force else THROTTLE):
            return _skipped(db, user_id, "throttled", now)

    lock = _user_lock(user_id)
    if not lock.acquire(blocking=False):
        return _skipped(db, user_id, "in_progress", now)
    try:
        failure, requests = _fetch(db, user_id, day, transport=transport, spo2_factory=spo2_factory)
        after = read_state(db, user_id, day)
        if failure is not None:
            code, outcome = failure, {AUTH_FAILED: garmin_raw.AUTH_FAILED,
                                      RATE_LIMITED: garmin_raw.RATE_LIMITED}.get(failure, garmin_raw.ERROR)
        elif not after.sleep_done:
            code, outcome = NOT_SYNCED, garmin_raw.EMPTY
        elif after.di and not after.spo2_done:
            code, outcome = SPO2_MISSING, garmin_raw.OK
        else:
            code, outcome = COMPLETE, garmin_raw.OK
        garmin_raw.record_lane(db, user_id, garmin_raw.LANE_WAKE_DAY, outcome, f"{day.isoformat()} {code} via={trigger}",
                               now=now)
        logger.info("wake-day capture: user=%s wake_day=%s via=%s outcome=%s requests=%s",
                    user_id, day.isoformat(), trigger, code, requests)
        return {"wake_day": day.isoformat(), "outcome": code, "via": trigger, "requests": requests,
                "status": status(db, user_id, now=now)}
    finally:
        lock.release()


def run_backstop(db, *, now: Optional[datetime] = None, transport=None, spo2_factory=None) -> dict[str, Any]:
    """The 10:00 Brisbane backstop: one capture per Garmin-connected user whose wake-day is still incomplete.
    Per-user isolation: one user's failure never aborts the rest. Returns {user_id: outcome-or-skip-reason}."""
    ids = sorted({uid for (uid,) in db.query(models.UserIntegration.user_id).filter(
        models.UserIntegration.provider.in_(("garmin", gpl.PROVIDER))).all()})
    out: dict[int, str] = {}
    for uid in ids:
        try:
            res = run(db, uid, trigger="backstop", now=now, transport=transport, spo2_factory=spo2_factory)
            out[uid] = res.get("reason") or res["outcome"]
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("wake-day backstop: user %s failed", uid)
            out[uid] = f"crashed:{type(exc).__name__}"
    return out
