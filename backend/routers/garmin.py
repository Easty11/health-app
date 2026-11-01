"""
Garmin integration — server-side HRV pull through the Personal API (the metrics Garmin withholds from
Health Connect). See `connectors/garmin.py` for the DI token's remaining job and `garmin_personal_lanes.py`
for the credential model (DECISIONS_LOG #449).

Endpoints (all authenticated, self-scoped):
  POST   /integrations/garmin/token        → verify + store the out-of-band DI login token blob, which now
                                             serves the epoch-SpO2 lane only (#450); refuses an account
                                             already linked to another user
  POST   /integrations/garmin/sync?from&to → pull + upsert HRV for a date range (Personal API key required)
  GET    /integrations/garmin/status       → {connected: bool, personal_api: bool}
  DELETE /integrations/garmin              → disconnect (drop the DI token)

The DI token is minted by `scripts/garmin_login.py` (interactive, out-of-band); the platform never sees the
Garmin password. `sync_hrv_for_user` is the reusable core: the endpoint and the `scripts/garmin_sync.py`
cron/ops runner both call it, and it serves a user from the Personal API only. A user with no personal key
raises `NoPersonalKey` (404 on the endpoint); there is no DI fallback (PR-B).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from auth import get_current_user
import garmin_personal_lanes as gpl
import garmin_raw
import wake_day_capture
from connectors import garmin_personal as gp
from connectors.garmin import (
    GarminClient,
    GarminPersonalKeyError,
    GarminProfileUnresolvable,
    GarminReconnectError,
    account_fingerprint,
    normalize_hrv_day,
)
from database import get_db
from encryption import encrypt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/garmin", tags=["garmin"])

# Default pull window when the caller names neither bound — a week of nights.
_DEFAULT_WINDOW_DAYS = 7

# On-read refresh (#299): a caller whose freshest Garmin ingest is younger than this skips the
# pull (unless forced). Mirrors `load.LOAD_REFRESH_STALE_AFTER`, shorter because the Garmin sync
# is a single narrow HRV pull, not a multi-hundred-day chain.
RECOVERY_REFRESH_STALE_AFTER = timedelta(minutes=30)   # = wake_day_capture.THROTTLE (kept for importers)
# On-read window — the last few nights only (the freshness path, not a backfill). Narrower than
# `_DEFAULT_WINDOW_DAYS` so a card-open pull is a couple of API calls, not a week.
_ON_READ_WINDOW_DAYS = 3


def garmin_wake_day() -> date:
    """The Brisbane-local wake-day — the date Garmin files a night under (`hrvSummary.calendarDate`,
    stored as `hrv_readings.captured_at`). Every Garmin pull window ENDS here, never on the UTC
    date: before 10:00 AEST the UTC date is still yesterday, so a UTC-bounded morning pull never
    requests the night just slept and the card/check-in show yesterday or "–" (#327 follow-up)."""
    import pytz

    return datetime.now(pytz.timezone("Australia/Brisbane")).date()


class GarminTokenIn(BaseModel):
    token: str


# Attach-guard responses. Neither names another user: the caller learns only that the ACCOUNT is
# taken, never by whom.
_ATTACH_CONFLICT = "This Garmin account is already connected to a different user."
_ATTACH_UNVERIFIED = (
    "Could not verify which Garmin account this token belongs to, so it was not saved. "
    "Please retry in a few minutes."
)


# ── token storage helpers (mirror the Hevy/Polar UserIntegration pattern) ──────

def _get_garmin_row(user_id: int, db: Session) -> models.UserIntegration | None:
    return (
        db.query(models.UserIntegration)
        .filter_by(user_id=user_id, provider="garmin")
        .first()
    )


def _store_token(db: Session, row: models.UserIntegration, token_json: str) -> None:
    """Persist a (possibly refreshed) token blob. The refresh token IS persistent
    account access — encrypted at rest, never logged."""
    row.api_key_encrypted = encrypt(token_json)


# ── core sync service (reused by the endpoint and the CLI runner) ──────────────

def _upsert_hrv_day(db: Session, user_id: int, source: str, day: dict, *, transport: str | None = None,
                    keep_existing: bool = False) -> int:
    """Idempotent upsert of one normalised night + its samples. Returns #samples.

    Upserts the parent on (user_id, captured_at, source); children replace-on-reingest
    (delete this night's samples, re-add). Portable across Postgres and the SQLite test
    substrate — a manual read-modify-write, not a dialect-specific ON CONFLICT.

    `transport` ('personal_api' | 'di') records how the night arrived; `source` stays 'garmin'.
    `keep_existing` is the Personal API lane's guard: a night first written by the other transport is
    overwritten field by field, but a field the new payload lacks (None) never nulls a stored value, and
    a payload with no samples never deletes the stored series."""
    existing = (
        db.query(models.HrvReading)
        .filter_by(user_id=user_id, captured_at=day["captured_at"], source=source)
        .first()
    )
    if existing is not None:
        for field, value in day["reading"].items():
            if keep_existing and value is None and getattr(existing, field) is not None:
                continue
            setattr(existing, field, value)
        if transport is not None:
            existing.transport = transport
        if not (keep_existing and not day["samples"]):
            db.query(models.HrvSample).filter_by(hrv_reading_id=existing.id).delete()
        reading = existing
    else:
        reading = models.HrvReading(
            user_id=user_id,
            source=source,
            captured_at=day["captured_at"],
            transport=transport,
            **day["reading"],
        )
        db.add(reading)
        db.flush()  # assign reading.id for the child rows

    for s in day["samples"]:
        db.add(models.HrvSample(hrv_reading_id=reading.id, **s))
    return len(day["samples"])


def sync_hrv_for_user(db: Session, user_id: int, start: date, end: date, *, client=None) -> dict:
    """Pull Garmin HRV for one user over [start, end] through the Personal API and upsert it. Commits.

    The Personal API is the only HRV lane (DECISIONS_LOG #449, PR-B): the DI lane's HRV pull is gone and its
    token serves epoch SpO2 only (#450). A user with no `garmin_personal` key raises `NoPersonalKey`; a refused
    key raises `GarminPersonalKeyError` (a reconnect state, 424 upstream). `client` lets a caller that already
    holds a `PersonalClient` (the wake-day capture) share its token and pacing instead of opening a second one.
    """
    if gpl.get_row(db, user_id) is None:
        raise gpl.NoPersonalKey(f"user {user_id} has no garmin_personal key")
    return _sync_hrv_personal(db, user_id, start, end, client=client)


def _sync_hrv_personal(db: Session, user_id: int, start: date, end: date, *, client=None) -> dict:
    """The Personal API HRV pull for one user over [start, end].

    Per night: fetch `hrv-service/hrv/{date}`, LAND the raw payload (identity keys scrubbed), map it with
    the same `normalize_hrv_day` the DI lane uses, and upsert on (user, night, 'garmin') with transport
    'personal_api' and `keep_existing` (a field the payload lacks never nulls a stored one). A refused key
    is a `GarminPersonalKeyError` (a reconnect state, 424 upstream); every other Personal API failure
    propagates as a `PersonalApiError`. The lane status is recorded either way."""
    readings = samples = days_with_data = 0

    def _pull(c) -> None:
        nonlocal readings, samples, days_with_data
        cur = start
        while cur <= end:
            cdate = cur.isoformat()
            raw = c.hrv_day(cdate)
            if raw:
                landed = garmin_raw.land(db, user_id, "hrv", cdate, raw)
                day = normalize_hrv_day(landed.payload, cdate)
                if day is not None:
                    samples += _upsert_hrv_day(db, user_id, "garmin", day, transport="personal_api",
                                               keep_existing=True)
                    readings += 1
                    days_with_data += 1
                db.commit()
            cur += timedelta(days=1)

    try:
        if client is not None:
            _pull(client)
        else:
            with gpl.personal_client(db, user_id) as owned:
                if owned is None:                 # the key was removed between the check and the pull
                    raise gpl.NoPersonalKey(f"user {user_id} has no garmin_personal key")
                _pull(owned)
    except gp.PersonalApiError as exc:
        db.rollback()
        gpl.record_failure(db, user_id, garmin_raw.LANE_PERSONAL_HRV, exc)
        if isinstance(exc, gp.PersonalAuthError):
            raise GarminPersonalKeyError(f"Garmin Personal API key refused or expired: {exc}") from None
        raise
    gpl.record_success(db, user_id, garmin_raw.LANE_PERSONAL_HRV, empty=days_with_data == 0)
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "days_with_data": days_with_data,
        "readings_upserted": readings,
        "samples_upserted": samples,
    }


def _latest_garmin_ingest_at(db: Session, user_id: int) -> datetime | None:
    """The caller's freshest `hrv_readings.created_at` for source='garmin', made UTC-aware — i.e.
    when we last INGESTED a Garmin row. NULL when the user has no Garmin HRV yet (never pulled).

    This is a DATA-recency marker, not an attempt-recency one: there is no per-user "last Garmin
    sync attempt" timestamp (UserIntegration.updated_at is bumped by connect/disconnect and the
    token writeback, so it reads 'fresh' right after connecting — the very Q155 failure). Cost of
    data-recency, accepted (#299): a night Garmin genuinely has nothing creates no row, so this
    does not advance and the on-read gate re-fires on each card open until data arrives. SQLite
    round-trips TIMESTAMPTZ as naive; a naive value is read as UTC (mirrors `load.
    _latest_computed_at`)."""
    latest = db.scalar(
        select(func.max(models.HrvReading.created_at)).where(
            models.HrvReading.user_id == user_id,
            models.HrvReading.source == "garmin",
        )
    )
    if latest is not None and latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)
    return latest


def _reconnect_http(exc: GarminReconnectError) -> HTTPException:
    # Connector-auth failure is NOT session-auth failure — 424 so the frontend
    # interceptor never logs the user out; the body says to reconnect Garmin.
    if isinstance(exc, GarminPersonalKeyError):
        return HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail=f"Garmin Personal API key needs replacing — re-run garmin_personal_attach.py: {exc}",
        )
    return HTTPException(
        status_code=status.HTTP_424_FAILED_DEPENDENCY,
        detail=f"Garmin reconnect required — re-run garmin_login.py: {exc}",
    )


# ── endpoints ──────────────────────────────────────────────────────────────────

def _fingerprint_linked_elsewhere(db: Session, fingerprint: str, user_id: int) -> bool:
    return (
        db.query(models.UserIntegration.id)
        .filter(
            models.UserIntegration.provider.in_(("garmin", gpl.PROVIDER)),   # one Garmin account, one user
            models.UserIntegration.account_fingerprint == fingerprint,
            models.UserIntegration.user_id != user_id,
        )
        .first()
        is not None
    )


@router.post("/token", status_code=status.HTTP_201_CREATED)
def connect_garmin_token(
    body: GarminTokenIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Verify and store the token blob minted out-of-band by `scripts/garmin_login.py`.

    The platform never receives the Garmin password: only this garminconnect token blob, stored
    Fernet-encrypted in UserIntegration(provider="garmin"), upserted on uq_user_provider.

    The root-cause guard for the Garmin account mix-up: the token is used ONCE to resolve which
    Garmin account it belongs to, and the attach is refused when that account is already
    connected to a DIFFERENT user (409; the message names no user). Re-attaching the same account
    to the same user, or a different account to this user, is allowed. FAILS CLOSED: when the
    account cannot be resolved (Garmin unreachable, or its profile response changed shape) the
    token is NOT stored and the caller gets 503 to retry; a shape change also logs an ERROR (the
    alert), so attaches stop loudly instead of silently bypassing the guard. A token that cannot
    authenticate is 424 (reconnect), as on the sync path.

    The blob stored is the client's own dump after login, which may be newer than the one
    submitted (a refresh during login), the same writeback contract as the sync path.
    """
    token = body.token.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="token must not be empty",
        )

    try:
        client = GarminClient.from_token(token)
        profile_id = client.profile_id()
    except GarminReconnectError as exc:
        raise _reconnect_http(exc)
    except GarminProfileUnresolvable:
        # ERROR already logged by the connector (key names only).
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_ATTACH_UNVERIFIED)
    except Exception:  # noqa: BLE001 -- fail closed on ANY inability to verify the account
        logger.exception(
            "garmin attach BLOCKED for user %s: could not verify the Garmin account", current_user.id
        )
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=_ATTACH_UNVERIFIED)

    fingerprint = account_fingerprint(profile_id)
    if _fingerprint_linked_elsewhere(db, fingerprint, current_user.id):
        logger.warning("garmin attach REFUSED for user %s: account already connected to another user",
                       current_user.id)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_ATTACH_CONFLICT)

    blob = client.dump_token()
    row = _get_garmin_row(current_user.id, db)
    if row:
        _store_token(db, row, blob)
        row.account_fingerprint = fingerprint
    else:
        db.add(models.UserIntegration(
            user_id=current_user.id,
            provider="garmin",
            api_key_encrypted=encrypt(blob),
            account_fingerprint=fingerprint,
        ))
    try:
        db.commit()
    except IntegrityError:  # a concurrent attach won the unique index between the check and the commit
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_ATTACH_CONFLICT)
    return {"detail": "Garmin integration saved"}


@router.get("/status")
def garmin_status(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Connected when the user has EITHER lane: a personal-only user is served and must not read as "not connected".
    di = _get_garmin_row(current_user.id, db) is not None
    personal = gpl.get_row(db, current_user.id) is not None
    return {"connected": di or personal, "personal_api": personal}


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_garmin(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_garmin_row(current_user.id, db)
    if row:
        db.delete(row)
        db.commit()


@router.post("/sync")
def sync_garmin_hrv(
    from_: str | None = None,
    to: str | None = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pull this user's Garmin HRV over [from, to] (ISO dates) and upsert it.

    Defaults to the last `_DEFAULT_WINDOW_DAYS` nights ending today when a bound is
    omitted. `from_` binds the `from` query param (a Python reserved word).
    """
    today = garmin_wake_day()
    try:
        end = date.fromisoformat(to) if to else today
        start = date.fromisoformat(from_) if from_ else end - timedelta(days=_DEFAULT_WINDOW_DAYS)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="from/to must be ISO dates (YYYY-MM-DD)",
        )
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="from must not be after to",
        )

    try:
        return sync_hrv_for_user(db, current_user.id, start, end)
    except gpl.NoPersonalKey:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="garmin personal key not connected")
    except GarminPersonalKeyError as exc:
        raise _reconnect_http(exc)
    except gp.PersonalApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Garmin Personal API: {exc}")


@router.post("/refresh")
def refresh_garmin_hrv(
    force: bool = Query(False, description="explicit Refresh: bypass the 30-min throttle (60 s floor remains)"),
    via: str | None = Query(None, description="which surface fired this: checkin | recovery (default recovery)"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """On-read wake-day capture for the calling user (#299 trigger, widened). Opening the AM check-in or the
    Recovery page, or pressing Refresh, fetches THIS wake-day's overnight data (Personal API sleep, heart rate,
    hourly SpO2 and HRV, plus the DI epoch-SpO2 night) via `wake_day_capture.run`; the 02:00 sweep alone could
    only ever land it a day late. SERVER-AUTHORITATIVE gates: the wake-day already complete, the capture window
    closed (10:00 Brisbane), the 30-minute per-user throttle, one fetch in flight. `force=true` is the explicit
    Refresh: it bypasses the throttle and the window.

    Returns `{"skipped": true, "reason": ..., "last_ingested_at": ..., "status": ...}` when nothing was fetched,
    else the run summary (`wake_day`, `outcome`, `via`, `requests`, `status`). Every response carries the
    post-run slot `status`. NEVER errors the card: a refused key, a missing key or any failure is returned as a
    skipped-shaped payload. Sync `def`: the Garmin client is blocking network I/O, run in FastAPI's threadpool."""
    trigger = "refresh" if force else (via if via in ("checkin", "recovery") else "recovery")
    try:
        return wake_day_capture.run(db, current_user.id, trigger=trigger, force=bool(force))
    except Exception:  # noqa: BLE001 -- a card refresh must never error the card; return last-good
        logger.exception("garmin refresh: wake-day capture failed for user %s", current_user.id)
        db.rollback()
        last = _latest_garmin_ingest_at(db, current_user.id)
        return {"skipped": True, "reason": "error", "last_ingested_at": last.isoformat() if last else None}


@router.get("/wake-day")
def wake_day_status(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The current wake-day's slot states (filled / pending / not_synced / missing-with-reason). Read-only."""
    return wake_day_capture.status(db, current_user.id)


@router.get("/lanes")
def garmin_lanes(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Per-lane last success (age and outcome) and the Personal API key's days to expiry, for Settings ->
    Integrations. Read-only; thresholds are the alerts' own (`reads.freshness_reads.garmin_lane_view`)."""
    from reads.freshness_reads import garmin_lane_view

    return garmin_lane_view(db, current_user.id)
