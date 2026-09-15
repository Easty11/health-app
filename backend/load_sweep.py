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
    user has never been computed), run one sweep immediately. This covers a restart that crossed
    02:00 while the process was down — the exact rot #297 exists to end.

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
from database import SessionLocal
from scripts.refresh_load import refresh_load

logger = logging.getLogger(__name__)

# 02:00 Australia/Brisbane, fixed UTC+10 no DST — the same zone load buckets into
# (`load_metrics._AEST`). The sweep fires just after the AEST day boundary.
_BRISBANE = pytz.timezone("Australia/Brisbane")
SWEEP_LOCAL_HOUR = 2
# Startup self-heal threshold: freshest per-user metric older than this (or any keyed user with
# none) means the load table has rotted while the process was down — run one sweep on boot.
STARTUP_STALE_AFTER = timedelta(hours=24)


def next_sweep_fire_utc(now_utc: datetime) -> datetime:
    """The next 02:00 Australia/Brisbane instant strictly after `now_utc`, returned in UTC.

    Brisbane is fixed UTC+10 with no DST, so 02:00 local is 16:00 UTC of the prior calendar day;
    computing in the Brisbane zone (not a bare UTC-16 literal) keeps this self-documenting and
    tied to the same zone the rollup uses."""
    now_local = now_utc.astimezone(_BRISBANE)
    target = now_local.replace(hour=SWEEP_LOCAL_HOUR, minute=0, second=0, microsecond=0)
    if target <= now_local:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc)


def all_users_stale(
    db: Session,
    *,
    threshold: timedelta = STARTUP_STALE_AFTER,
    now_utc: datetime | None = None,
) -> bool:
    """True when the all-users load freshness is stale: ANY Hevy-keyed user has never been
    computed, or the OLDEST per-user `max(computed_at)` is older than `threshold`. False when
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
            return True  # a keyed user with no metrics at all
        if latest.tzinfo is None:  # SQLite round-trips TIMESTAMPTZ as naive; assume UTC
            latest = latest.replace(tzinfo=timezone.utc)
        if now_utc - latest > threshold:
            return True
    return False


def _sweep() -> dict[str, Any]:
    """Run the all-users load chain in a FRESH session. Called via `asyncio.to_thread` so the
    orchestrator's `asyncio.run(...)` has no running loop to collide with."""
    db = SessionLocal()
    try:
        return refresh_load(db, only_user_id=None)
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
    """The log-worthy head of a sweep summary — never the full per-user tree."""
    return {
        k: summary.get(k)
        for k in ("users_attempted", "users_succeeded", "users_failed", "days")
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
