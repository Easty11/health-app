"""Short-TTL, in-process cache for a user's Hevy routines + folders (#314, G0 ruling 4).

The coach reads routines every turn; a live `get_all_routines()` is ceil(N/10) serial GETs
with no server-side all-in-one read. So the fetch is cached per process for `TTL_SECONDS`,
behind a hard `BUDGET_SECONDS` so the chat turn never waits on Hevy: on timeout or error the
last cached copy is served marked with its age, else the caller renders "unavailable". The
cache is INVALIDATED immediately whenever the coach creates or updates a routine, so a write is
reflected on the next turn rather than after the TTL.

No table (ruling 4): a module-level dict, process-local. A multi-worker deployment simply has a
per-worker cache — acceptable for a 5-minute TTL over read-only display data.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

TTL_SECONDS = 300.0      # 5 minutes (ruling 4)
BUDGET_SECONDS = 3.0     # hard fetch budget inside the chat turn (ruling 4)

# user_id -> (fetched_at_monotonic, {"routines": [...], "folders": [...]})
_CACHE: dict[int, tuple[float, dict[str, Any]]] = {}


def invalidate(user_id: int) -> None:
    """Drop a user's cached routines — called immediately after the coach creates/updates a
    routine, so the change shows next turn instead of waiting out the TTL."""
    _CACHE.pop(user_id, None)


def _served(data: dict[str, Any], *, age_seconds: int | None, stale: bool, unavailable: bool) -> dict[str, Any]:
    return {
        "routines": data.get("routines", []),
        "folders": data.get("folders", []),
        "age_seconds": age_seconds,
        "stale": stale,
        "unavailable": unavailable,
    }


async def get_routines_cached(
    client: Any,
    user_id: int,
    *,
    ttl: float = TTL_SECONDS,
    budget: float = BUDGET_SECONDS,
    now: float | None = None,
) -> dict[str, Any]:
    """Return `{routines, folders, age_seconds, stale, unavailable}` for the user.

    Fresh cache (age < ttl) is served directly. Otherwise fetch under `budget`; on success
    refresh + serve; on timeout/error serve the last cached copy marked `stale` with its age,
    or `unavailable` when there is nothing cached. Never raises — the chat turn never goes down
    for Hevy.
    """
    now = time.monotonic() if now is None else now
    cached = _CACHE.get(user_id)
    if cached is not None and (now - cached[0]) < ttl:
        return _served(cached[1], age_seconds=int(now - cached[0]), stale=False, unavailable=False)

    async def _fetch() -> dict[str, Any]:
        routines = await client.get_all_routines()
        folders = await client.get_routine_folders()
        return {"routines": routines, "folders": folders}

    try:
        data = await asyncio.wait_for(_fetch(), timeout=budget)
    except Exception as exc:  # noqa: BLE001 — timeout OR any Hevy error → serve stale/unavailable
        logger.warning("hevy routine fetch failed/timed out for user %s: %s", user_id, exc)
        if cached is not None:
            return _served(cached[1], age_seconds=int(now - cached[0]), stale=True, unavailable=False)
        return _served({}, age_seconds=None, stale=False, unavailable=True)

    _CACHE[user_id] = (now, data)
    return _served(data, age_seconds=0, stale=False, unavailable=False)
