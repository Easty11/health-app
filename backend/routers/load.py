"""On-demand per-user load refresh — `POST /load/refresh` (#297).

The INTERACTION trigger of the load-refresh model that supersedes #296's dedicated Railway
cron service: the Training page calls this on open (and on pull-to-refresh) so a session shows
up in the load table on the next page open, not the next 02:00. The nightly all-users sweep
(`load_sweep.py`, wired in `main.lifespan`) is the GUARANTEE for users who don't open the app.

Why a SYNC `def` route, not `async def`. `refresh_load.run_user_chain` drives the Hevy ingest
with `asyncio.run(hevy_workouts.sync_workouts(...))`; `asyncio.run` raises inside a running event
loop. FastAPI runs an `async def` route ON the loop (collision) but a plain `def` route in its
threadpool, where no loop is running and `asyncio.run` is legal — so the #296 orchestrator is
reused UNCHANGED. Do not make this route async.

Staleness gate (migration-free). Freshness is `max(LoadMetric.computed_at)` for the caller:
NULL (never computed) or older than `LOAD_REFRESH_STALE_AFTER` -> run; otherwise return
`{"skipped": true, ...}` without touching Hevy. `computed_at` is the existing per-row write
marker of `load_metrics.compute_load_metrics` (always set, UTC-aware — verified #297), so no new
column is needed. `?force=true` bypasses the gate (pull-to-refresh). The gate is
SERVER-AUTHORITATIVE: the client always calls, the server decides.

Window. On-demand uses a NARROW `days` (recent sessions only) rather than the orchestrator's
180-day default, so an open-page refresh is not a multi-hundred-day Hevy pull. The nightly sweep
keeps the default window.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db
from scripts.refresh_load import refresh_load as run_refresh_load

router = APIRouter(prefix="/load", tags=["load"])

# A caller whose freshest load metric is younger than this skips the refresh (unless forced).
LOAD_REFRESH_STALE_AFTER = timedelta(minutes=15)
# On-demand Hevy backfill window — recent sessions only, NOT hevy_workouts.DEFAULT_BACKFILL_DAYS.
ON_DEMAND_BACKFILL_DAYS = 30


def _latest_computed_at(db: Session, user_id: int) -> datetime | None:
    """The caller's freshest `load_metrics.computed_at`, made UTC-aware. NULL when the user has
    never had metrics computed. SQLite round-trips TIMESTAMPTZ as naive, so a naive value is
    read as UTC (mirrors `hevy_templates.refresh_catalogue_if_stale`)."""
    latest = db.scalar(
        select(func.max(models.LoadMetric.computed_at)).where(
            models.LoadMetric.user_id == user_id
        )
    )
    if latest is not None and latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    return latest


@router.post("/refresh")
def refresh_current_user_load(
    force: bool = Query(False, description="bypass the staleness gate (pull-to-refresh)"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run the #296 load chain for the CALLING USER ONLY, staleness-gated at
    `LOAD_REFRESH_STALE_AFTER`. Returns the orchestrator summary on a real run, or
    `{"skipped": true, "reason": "fresh", "last_computed_at": ...}` when fresh and not forced.

    Sync `def` on purpose (see module docstring): FastAPI runs it in the threadpool, where the
    orchestrator's `asyncio.run` is legal."""
    latest = _latest_computed_at(db, current_user.id)
    if (
        not force
        and latest is not None
        and datetime.now(timezone.utc) - latest < LOAD_REFRESH_STALE_AFTER
    ):
        return {"skipped": True, "reason": "fresh", "last_computed_at": latest.isoformat()}

    return run_refresh_load(db, only_user_id=current_user.id, days=ON_DEMAND_BACKFILL_DAYS)
