"""
Garmin integration — server-side HRV pull (the metrics Garmin withholds from Health
Connect). See `connectors/garmin.py` for the why and the credential model.

Endpoints (all authenticated, self-scoped):
  POST   /integrations/garmin/token        → store the out-of-band login token blob
  POST   /integrations/garmin/sync?from&to → pull + upsert HRV for a date range
  GET    /integrations/garmin/status       → {connected: bool}
  DELETE /integrations/garmin              → disconnect (drop the token)

The token is minted by `scripts/garmin_login.py` (interactive, out-of-band); the
platform never sees the Garmin password. `sync_hrv_for_user` is the reusable core —
the endpoint and the `scripts/garmin_sync.py` cron/ops runner both call it.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from connectors.garmin import GarminClient, GarminReconnectError
from database import get_db
from encryption import decrypt, encrypt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/garmin", tags=["garmin"])

# Default pull window when the caller names neither bound — a week of nights.
_DEFAULT_WINDOW_DAYS = 7

# On-read refresh (#299): a caller whose freshest Garmin ingest is younger than this skips the
# pull (unless forced). Mirrors `load.LOAD_REFRESH_STALE_AFTER`, shorter because the Garmin sync
# is a single narrow HRV pull, not a multi-hundred-day chain.
RECOVERY_REFRESH_STALE_AFTER = timedelta(minutes=30)
# On-read window — the last few nights only (the freshness path, not a backfill). Narrower than
# `_DEFAULT_WINDOW_DAYS` so a card-open pull is a couple of API calls, not a week.
_ON_READ_WINDOW_DAYS = 3


class GarminTokenIn(BaseModel):
    token: str


# ── token storage helpers (mirror the Hevy/Polar UserIntegration pattern) ──────

def _get_garmin_row(user_id: int, db: Session) -> models.UserIntegration | None:
    return (
        db.query(models.UserIntegration)
        .filter_by(user_id=user_id, provider="garmin")
        .first()
    )


def _require_garmin_row(user_id: int, db: Session) -> models.UserIntegration:
    row = _get_garmin_row(user_id, db)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="garmin integration not connected",
        )
    return row


def _store_token(db: Session, row: models.UserIntegration, token_json: str) -> None:
    """Persist a (possibly refreshed) token blob. The refresh token IS persistent
    account access — encrypted at rest, never logged."""
    row.api_key_encrypted = encrypt(token_json)


# ── core sync service (reused by the endpoint and the CLI runner) ──────────────

def _upsert_hrv_day(db: Session, user_id: int, source: str, day: dict) -> int:
    """Idempotent upsert of one normalised night + its samples. Returns #samples.

    Upserts the parent on (user_id, captured_at, source); children replace-on-reingest
    (delete this night's samples, re-add). Portable across Postgres and the SQLite test
    substrate — a manual read-modify-write, not a dialect-specific ON CONFLICT."""
    existing = (
        db.query(models.HrvReading)
        .filter_by(user_id=user_id, captured_at=day["captured_at"], source=source)
        .first()
    )
    if existing is not None:
        for field, value in day["reading"].items():
            setattr(existing, field, value)
        db.query(models.HrvSample).filter_by(hrv_reading_id=existing.id).delete()
        reading = existing
    else:
        reading = models.HrvReading(
            user_id=user_id,
            source=source,
            captured_at=day["captured_at"],
            **day["reading"],
        )
        db.add(reading)
        db.flush()  # assign reading.id for the child rows

    for s in day["samples"]:
        db.add(models.HrvSample(hrv_reading_id=reading.id, **s))
    return len(day["samples"])


def sync_hrv_for_user(db: Session, user_id: int, start: date, end: date) -> dict:
    """Pull Garmin HRV for one user over [start, end] and upsert it. Commits.

    Auth-from-token only (no password). The token blob is re-encrypted and committed
    immediately after a successful login so a refresh performed during login survives
    even if the subsequent pull fails. A dead/MFA-needed token raises
    GarminReconnectError (mapped to 424 upstream), never a 500.
    """
    row = _require_garmin_row(user_id, db)
    client = GarminClient.from_token(decrypt(row.api_key_encrypted))

    # Refresh-token writeback: persist the (possibly refreshed) blob right after login,
    # before the pull, so the refresh is never lost to a later pull failure.
    _store_token(db, row, client.dump_token())
    db.commit()

    days = client.get_hrv_range(start, end)

    readings = samples = 0
    for day in days:
        samples += _upsert_hrv_day(db, user_id, "garmin", day)
        readings += 1
    db.commit()

    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "days_with_data": len(days),
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
    return HTTPException(
        status_code=status.HTTP_424_FAILED_DEPENDENCY,
        detail=f"Garmin reconnect required — re-run garmin_login.py: {exc}",
    )


# ── endpoints ──────────────────────────────────────────────────────────────────

@router.post("/token", status_code=status.HTTP_201_CREATED)
def connect_garmin_token(
    body: GarminTokenIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store the token blob minted out-of-band by `scripts/garmin_login.py`.

    The platform never receives the Garmin password — only this garminconnect token blob,
    stored Fernet-encrypted in UserIntegration(provider="garmin"), upserted on
    uq_user_provider. Mirrors the Hevy register path; no migration.
    """
    token = body.token.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="token must not be empty",
        )

    row = _get_garmin_row(current_user.id, db)
    if row:
        row.api_key_encrypted = encrypt(token)
    else:
        row = models.UserIntegration(
            user_id=current_user.id,
            provider="garmin",
            api_key_encrypted=encrypt(token),
        )
        db.add(row)
    db.commit()
    return {"detail": "Garmin integration saved"}


@router.get("/status")
def garmin_status(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"connected": _get_garmin_row(current_user.id, db) is not None}


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
    today = datetime.now(timezone.utc).date()
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
    except GarminReconnectError as exc:
        raise _reconnect_http(exc)


@router.post("/refresh")
def refresh_garmin_hrv(
    force: bool = Query(False, description="bypass the staleness gate (pull-to-refresh)"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """On-read freshness trigger for the recovery card (#299) — the FRESHNESS leg that resolves
    Q155. Runs a narrow Garmin HRV pull for the CALLING USER, staleness-gated at
    `RECOVERY_REFRESH_STALE_AFTER`; `force=true` bypasses (pull-to-refresh). Fired on
    recovery-card open, after Garmin's ~6am overnight sync, so the card shows THIS morning's HRV.
    The nightly 02:00 sweep (`load_sweep`, #299) is the guarantee for mornings the card is never
    opened.

    SERVER-AUTHORITATIVE gate: the client always calls, the server decides. Returns
    `{"skipped": true, "reason": ..., "last_ingested_at": ...}` when fresh, and the sync summary
    on a real run.

    NEVER errors the card. A dead/MFA-needed token (`GarminReconnectError`) or any other sync
    failure is logged and returns last-good (a skipped-shaped payload), so a background refresh
    can never break a card that is already showing its cached data. Sync `def` (not `async`): the
    Garmin client is blocking network I/O, which FastAPI runs in its threadpool off the event
    loop."""
    last = _latest_garmin_ingest_at(db, current_user.id)
    if (
        not force
        and last is not None
        and datetime.now(timezone.utc) - last < RECOVERY_REFRESH_STALE_AFTER
    ):
        return {"skipped": True, "reason": "fresh", "last_ingested_at": last.isoformat()}

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=_ON_READ_WINDOW_DAYS)
    last_iso = last.isoformat() if last is not None else None
    try:
        return sync_hrv_for_user(db, current_user.id, start, today)
    except GarminReconnectError as exc:
        logger.warning("garmin refresh: reconnect needed for user %s — %s", current_user.id, exc)
        return {"skipped": True, "reason": "reconnect_required", "last_ingested_at": last_iso}
    except Exception:  # noqa: BLE001 — a card refresh must never error the card; return last-good
        logger.exception("garmin refresh: sync failed for user %s", current_user.id)
        return {"skipped": True, "reason": "error", "last_ingested_at": last_iso}
