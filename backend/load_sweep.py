"""Nightly in-process all-users load sweep — the GUARANTEE half of the #297 refresh model
that supersedes #296's dedicated Railway cron service.

Why in-process, not a cron service. Railway deprecated config-as-code, so a NEW cron service
(`railway.cron.toml`) can no longer be provisioned; and every hard part of that path
(cross-service `DATABASE_URL`/`FERNET_KEY` references, two-context verification) existed only
because it duplicated the backend env in a second service. A background task in the FastAPI
`lifespan` (see `main.py`) needs none of it: same process, same env.

Two triggers:
  * SCHEDULED — fire the all-users sweep at 02:00 Australia/Brisbane (fixed UTC+10, no DST —
    matches `load_metrics._AEST`) = 16:00 UTC, every day, via a plain `asyncio` sleep-until-fire
    loop (no scheduler dependency; `requirements.txt` has none).
  * STARTUP SELF-HEAL — on boot, if the all-users freshness is stale (>24h, or any Hevy-keyed
    user WITH load events has never been computed), run one sweep immediately. This covers a
    restart that crossed 02:00 while the process was down — the exact rot #297 exists to end.
    A keyed user with no load events has nothing to compute and never will, so it is not stale (#432).

Off the loop. The sweep runs through `asyncio.to_thread(_sweep)`: `refresh_load.run_user_chain`
drives the Hevy ingest with `asyncio.run(...)`, which raises inside a running event loop, so it
must run in a worker thread (no loop) — the same constraint the sync `/load/refresh` route
satisfies via FastAPI's threadpool. `_sweep` opens its OWN `SessionLocal()`; a request/loop
session is never shared across the thread.

Single replica. The chain is delete-then-insert idempotent, so a double fire (e.g. two replicas,
or a startup run landing near 02:00) is WASTEFUL, never wrong. If the backend ever runs multiple
replicas this needs a leader/lock (DECISIONS_LOG #297, "Do not revisit unless").
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pytz
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import models
import wake_day_capture
from database import SessionLocal
from scripts.garmin_sync import sweep_garmin_hrv
from scripts.refresh_load import refresh_load

logger = logging.getLogger(__name__)

# 02:00 Australia/Brisbane, fixed UTC+10 no DST — the same zone load buckets into
# (`load_metrics._AEST`). The sweep fires just after the AEST day boundary.
_BRISBANE = pytz.timezone("Australia/Brisbane")
SWEEP_LOCAL_HOUR = 2
# Startup self-heal threshold: freshest per-user metric older than this (or any keyed user with
# load events but no metrics) means the load table has rotted while the process was down — run
# one sweep on boot.
STARTUP_STALE_AFTER = timedelta(hours=24)


def _next_fire_utc(now_utc: datetime, hour: int) -> datetime:
    now_local = now_utc.astimezone(_BRISBANE)
    target = now_local.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now_local:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc)


def next_sweep_fire_utc(now_utc: datetime) -> datetime:
    """The next 02:00 Australia/Brisbane instant strictly after `now_utc`, returned in UTC.

    Brisbane is fixed UTC+10 with no DST, so 02:00 local is 16:00 UTC of the prior calendar day;
    computing in the Brisbane zone (not a bare UTC-16 literal) keeps this self-documenting and
    tied to the same zone the rollup uses."""
    return _next_fire_utc(now_utc, SWEEP_LOCAL_HOUR)


def next_backstop_fire_utc(now_utc: datetime) -> datetime:
    """The next 10:00 Australia/Brisbane instant strictly after `now_utc` (the wake-day capture window closes)."""
    return _next_fire_utc(now_utc, wake_day_capture.CAPTURE_CLOSES_HOUR)


def all_users_stale(
    db: Session,
    *,
    threshold: timedelta = STARTUP_STALE_AFTER,
    now_utc: datetime | None = None,
) -> bool:
    """True when the all-users load freshness is stale: ANY Hevy-keyed user who HAS load events
    has never been computed, or the OLDEST per-user `max(computed_at)` is older than `threshold`.
    A keyed user with no load events and no metrics (e.g. a Hevy account with no workouts) is
    skipped: the load chain writes no rows for a user with no events, so such a user can never
    become fresh and counting them would re-run the whole sweep on every boot (#432). False when
    there are no keyed users (nothing to sweep). Used for the startup self-heal only."""
    from hevy_templates import users_with_hevy_key

    now_utc = now_utc or datetime.now(timezone.utc)
    user_ids = [uid for uid, _key in users_with_hevy_key(db)]
    if not user_ids:
        return False

    for uid in user_ids:
        latest = db.scalar(
            select(func.max(models.LoadMetric.computed_at)).where(
                models.LoadMetric.user_id == uid
            )
        )
        if latest is None:
            # No metrics at all. Stale only if there is something to compute from: `load_events` is
            # the chain's input, and a user without any writes no metric rows, ever (#432).
            has_events = db.scalar(
                select(models.LoadEvent.id).where(models.LoadEvent.user_id == uid).limit(1)
            ) is not None
            if has_events:
                return True
            continue
        if latest.tzinfo is None:  # SQLite round-trips TIMESTAMPTZ as naive; assume UTC
            latest = latest.replace(tzinfo=timezone.utc)
        if now_utc - latest > threshold:
            return True
    return False


def _sweep() -> dict[str, Any]:
    """Run the all-users load chain AND the Garmin HRV sweep in a FRESH session. Called via
    `asyncio.to_thread` so the load orchestrator's `asyncio.run(...)` has no running loop to
    collide with (the Garmin sweep is plain blocking I/O — no asyncio — but rides the same
    off-loop thread).

    Two jobs on the one rail (#299): the load chain, then `garmin_sync` as the second per-user
    job. At 02:00 Brisbane the Garmin leg can only ever land the PRIOR night — Garmin finalises
    overnight HRV post-wake (~6am), after this sweep — which is accepted: this is the GUARANTEE
    that no night is permanently lost for mornings the card is never opened, not the freshness
    path. `POST /integrations/garmin/refresh` (fired on card open) owns same-morning freshness.
    Per-user isolation lives inside `sweep_garmin_hrv` (one dead token is caught, rolled back and
    skipped, never aborting the batch), so a Garmin failure never touches the load result."""
    db = SessionLocal()
    try:
        load_summary = refresh_load(db, only_user_id=None)
        garmin_summary = sweep_garmin_hrv(db, only_user_id=None)
        return {"load": load_summary, "garmin": garmin_summary}
    finally:
        db.close()


def _startup_is_stale() -> bool:
    """`all_users_stale` in a fresh session, for the startup self-heal check off the loop."""
    db = SessionLocal()
    try:
        return all_users_stale(db)
    finally:
        db.close()


def _summary_brief(summary: dict[str, Any]) -> dict[str, Any]:
    """The log-worthy head of a sweep summary — never the full per-user tree. Both jobs (#299):
    the load chain and the Garmin sweep, each reduced to its user counts."""
    load = summary.get("load", {})
    garmin = summary.get("garmin", {})
    return {
        "load": {
            k: load.get(k)
            for k in ("users_attempted", "users_succeeded", "users_failed", "days")
        },
        "garmin": {
            k: garmin.get(k)
            for k in ("users_attempted", "users_succeeded", "users_failed", "selfeval", "spo2", "wellness")
        },
    }


async def sweep_loop() -> None:
    """Run the all-users sweep once on startup if stale, then at every 02:00 Brisbane, forever.

    Started as an `asyncio` task in `main.lifespan` and cancelled on shutdown. A single sweep
    failure is logged and swallowed so the scheduler survives it; `CancelledError` is re-raised
    so shutdown is clean."""
    # Startup self-heal — cover a restart that crossed 02:00 while the process was down.
    try:
        if await asyncio.to_thread(_startup_is_stale):
            logger.info("load sweep: startup freshness stale (>%s) — running one sweep now",
                        STARTUP_STALE_AFTER)
            summary = await asyncio.to_thread(_sweep)
            logger.info("load sweep (startup) done: %s", _summary_brief(summary))
        else:
            logger.info("load sweep: startup freshness OK — no immediate sweep")
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 — a startup-sweep failure must not kill the scheduler
        logger.exception("load sweep: startup run failed (scheduler continues)")

    while True:
        now = datetime.now(timezone.utc)
        fire = next_sweep_fire_utc(now)
        await asyncio.sleep((fire - now).total_seconds())
        try:
            summary = await asyncio.to_thread(_sweep)
            logger.info("load sweep (02:00 Brisbane) done: %s", _summary_brief(summary))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — a scheduled-sweep failure must not kill the scheduler
            logger.exception("load sweep: scheduled run failed (scheduler continues)")


# -- the 10:00 wake-day backstop ------------------------------------------------------------------------
# The 02:00 sweep can only land the PRIOR night; on-read triggers need someone to open the app. At 10:00
# Brisbane (the wake-day capture window closes) one more capture runs for any user whose wake-day is still
# incomplete. It is idempotent per day (`wake_day_capture.run` records `via=backstop` and skips a repeat),
# so a restart that crossed 10:00 can safely re-run it within a few hours.
BACKSTOP_STARTUP_GRACE_HOURS = 4


def _backstop() -> dict[int, str]:
    db = SessionLocal()
    try:
        return wake_day_capture.run_backstop(db)
    finally:
        db.close()


async def backstop_loop() -> None:
    """Run the wake-day backstop at every 10:00 Brisbane, forever; once on startup when the process came up
    within BACKSTOP_STARTUP_GRACE_HOURS after 10:00 (a restart that crossed it). Failures are logged, never
    fatal; `CancelledError` is re-raised so shutdown is clean."""
    try:
        local = datetime.now(timezone.utc).astimezone(_BRISBANE)
        hour = wake_day_capture.CAPTURE_CLOSES_HOUR
        if hour <= local.hour < hour + BACKSTOP_STARTUP_GRACE_HOURS:
            logger.info("wake-day backstop (startup, after 10:00): %s", await asyncio.to_thread(_backstop))
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("wake-day backstop: startup run failed (scheduler continues)")

    while True:
        now = datetime.now(timezone.utc)
        await asyncio.sleep((next_backstop_fire_utc(now) - now).total_seconds())
        try:
            logger.info("wake-day backstop (10:00 Brisbane): %s", await asyncio.to_thread(_backstop))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("wake-day backstop: scheduled run failed (scheduler continues)")
