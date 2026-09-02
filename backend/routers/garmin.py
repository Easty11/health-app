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

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
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
