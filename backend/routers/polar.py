"""
Polar AccessLink Dynamic API v4 integration router.

v4 (auth.polar.com) replaces v3: v3's exercise-transactions only surfaced
device-recorded sessions, silently excluding Polar Flow app recordings (which is
how this user records H10 sessions). v4's date-range training-sessions/list
returns them.

Connect:
  GET    /integrations/polar/auth-url   → {url} for frontend redirect
  GET    /integrations/polar/callback   → OAuth callback (no bearer; browser GET)
  GET    /integrations/polar/status     → {connected: bool}
  DELETE /integrations/polar            → disconnect

Data (canonical table: aerobic_sessions):
  POST /integrations/polar/sync             → pull training sessions → AerobicSession (source='polar_v4')
  GET  /integrations/polar/aerobic-sessions → all AerobicSession records (ZIP + v4)
  GET  /integrations/polar/v4-raw           → raw first session JSON (schema debug)

ZIP-export history is loaded via import_polar.py (source='polar_flow_export').
"""
import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from connectors.polar import (
    PolarV4Client,
    build_auth_url,
    exchange_code_for_token,
    refresh_access_token,
)
from database import get_db
from encryption import decrypt, encrypt

router = APIRouter(prefix="/integrations/polar", tags=["polar"])

FRONTEND_URL = "https://health-app-production-e0ff.up.railway.app"


# ── token storage helpers ────────────────────────────────────────────────────

def _get_polar_row(user_id: int, db: Session) -> models.UserIntegration | None:
    return (
        db.query(models.UserIntegration)
        .filter_by(user_id=user_id, provider="polar")
        .first()
    )


def _load_tokens(user_id: int, db: Session) -> dict:
    row = _get_polar_row(user_id, db)
    if not row:
        raise HTTPException(status_code=404, detail="Polar not connected")
    return json.loads(decrypt(row.api_key_encrypted))


def _store_tokens(user_id: int, token_data: dict, db: Session) -> None:
    """Persist a token response, computing an absolute expiry."""
    expires_in = token_data.get("expires_in", 43199)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    payload = json.dumps({
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": expires_at,
        "scope": token_data.get("scope"),
        "token_type": token_data.get("token_type"),
    })
    row = _get_polar_row(user_id, db)
    if row:
        row.api_key_encrypted = encrypt(payload)
    else:
        db.add(models.UserIntegration(
            user_id=user_id, provider="polar", api_key_encrypted=encrypt(payload),
        ))
    db.commit()


def _valid_client(user_id: int, db: Session) -> PolarV4Client:
    """Return a client with a non-expired access token, refreshing if needed."""
    tokens = _load_tokens(user_id, db)
    expires_at = tokens.get("expires_at")
    needs_refresh = True
    if expires_at:
        try:
            needs_refresh = datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc) + timedelta(seconds=60)
        except ValueError:
            needs_refresh = True

    if needs_refresh and tokens.get("refresh_token"):
        try:
            new_tokens = refresh_access_token(tokens["refresh_token"])
            # refresh response may omit refresh_token — keep the old one if so
            new_tokens.setdefault("refresh_token", tokens["refresh_token"])
            _store_tokens(user_id, new_tokens, db)
            tokens = _load_tokens(user_id, db)
        except Exception as exc:
            raise HTTPException(status_code=401, detail=f"Polar token refresh failed: {exc}")

    return PolarV4Client(tokens["access_token"])


# ── connect ──────────────────────────────────────────────────────────────────

@router.get("/auth-url")
def get_auth_url(current_user: models.User = Depends(get_current_user)):
    import os
    if not os.getenv("POLAR_CLIENT_ID"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="POLAR_CLIENT_ID not configured on server",
        )
    return {"url": build_auth_url(current_user.id)}


@router.get("/callback")
def polar_callback(code: str, state: str, db: Session = Depends(get_db)):
    """OAuth callback — Polar redirects here (browser GET, no bearer). state=user_id."""
    try:
        user_id = int(state)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    if not db.query(models.User).filter_by(id=user_id).first():
        raise HTTPException(status_code=404, detail="User not found")

    try:
        token_data = exchange_code_for_token(code)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {exc}")

    _store_tokens(user_id, token_data, db)
    return RedirectResponse(f"{FRONTEND_URL}/settings?polar=connected")


@router.get("/status")
def polar_status(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"connected": _get_polar_row(current_user.id, db) is not None}


@router.delete("")
def disconnect_polar(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_polar_row(current_user.id, db)
    if row:
        db.delete(row)
        db.commit()
    return {"disconnected": True}


# ── data sync ────────────────────────────────────────────────────────────────

@router.post("/sync")
def sync_polar_sessions(
    days: int = 365,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pull v4 training sessions over the last `days` and upsert into aerobic_sessions."""
    client = _valid_client(current_user.id, db)
    today = datetime.now(timezone.utc).date()
    from_date = (today - timedelta(days=days)).isoformat()
    to_date = (today + timedelta(days=1)).isoformat()

    try:
        raw_sessions = client.list_training_sessions(from_date, to_date)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Polar v4 API error: {exc}")

    stored = 0
    for raw in raw_sessions:
        s = PolarV4Client.parse_session(raw)
        if not s["external_id"]:
            continue
        exists = (
            db.query(models.AerobicSession)
            .filter(
                models.AerobicSession.user_id == current_user.id,
                models.AerobicSession.source == "polar_v4",
                models.AerobicSession.source_session_id == s["external_id"],
            )
            .first()
        )
        if exists:
            continue
        db.add(models.AerobicSession(
            user_id=current_user.id,
            source="polar_v4",
            source_session_id=s["external_id"],
            session_date=s["session_date"],
            start_time=s["start_time"],
            stop_time=s["stop_time"],
            sport_id=s["sport_id"],
            sport_name=s["sport_name"],
            duration_minutes=s["duration_minutes"],
            hr_avg=s["hr_avg"],
            hr_max=s["hr_max"],
            calories=s["calories"],
            cardio_load=s["cardio_load"],
            muscle_load=s["muscle_load"],
            recovery_hours=s["recovery_hours"],
            z1_seconds=s["z1_seconds"], z2_seconds=s["z2_seconds"],
            z3_seconds=s["z3_seconds"], z4_seconds=s["z4_seconds"],
            z5_seconds=s["z5_seconds"],
        ))
        stored += 1

    db.commit()
    return {"synced": stored, "available": len(raw_sessions)}


@router.get("/v4-raw")
def polar_v4_raw(
    days: int = 30,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the raw first training session JSON so we can verify the v4 schema
    and confirm the field mapping. Safe to remove once mapping is validated."""
    client = _valid_client(current_user.id, db)
    today = datetime.now(timezone.utc).date()
    from_date = (today - timedelta(days=days)).isoformat()
    to_date = (today + timedelta(days=1)).isoformat()
    try:
        raw = client.list_training_sessions(from_date, to_date)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Polar v4 API error: {exc}")
    return {"count": len(raw), "first": raw[0] if raw else None}


# ── aerobic sessions (read) ──────────────────────────────────────────────────

class AerobicSessionOut(BaseModel):
    id: int
    source: str
    source_session_id: Optional[str] = None
    session_date: date
    start_time: Optional[datetime] = None
    stop_time: Optional[datetime] = None
    sport_id: Optional[str] = None
    sport_name: Optional[str] = None
    duration_minutes: Optional[float] = None
    hr_avg: Optional[int] = None
    hr_max: Optional[int] = None
    calories: Optional[int] = None
    cardio_load: Optional[float] = None
    muscle_load: Optional[float] = None
    recovery_hours: Optional[float] = None
    z1_seconds: Optional[int] = None
    z2_seconds: Optional[int] = None
    z3_seconds: Optional[int] = None
    z4_seconds: Optional[int] = None
    z5_seconds: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/aerobic-sessions", response_model=list[AerobicSessionOut])
def get_aerobic_sessions(
    limit: int = 100,
    since: Optional[date] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """All aerobic sessions — ZIP export history + v4 live sync, one table."""
    q = (
        db.query(models.AerobicSession)
        .filter(models.AerobicSession.user_id == current_user.id)
        .order_by(models.AerobicSession.session_date.desc())
    )
    if since:
        q = q.filter(models.AerobicSession.session_date >= since)
    return q.limit(limit).all()
