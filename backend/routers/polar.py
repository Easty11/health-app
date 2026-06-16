"""
Polar Accesslink integration router.

Connect flow:
  GET /integrations/polar/auth-url        → returns {url} for frontend to redirect to
  GET /integrations/polar/callback        → OAuth callback (no auth — Polar posts back here)
  GET /integrations/polar/status          → {connected: bool}
  DELETE /integrations/polar              → disconnect

Data (single canonical table: aerobic_sessions):
  POST /integrations/polar/sync             → pull new Accesslink exercises → AerobicSession (source='polar_accesslink')
  GET  /integrations/polar/aerobic-sessions → return all AerobicSession records (ZIP + live sync)

ZIP-export history is loaded via import_polar.py (source='polar_flow_export').
Both sources share the aerobic_sessions table.
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from connectors.polar import (
    PolarClient,
    build_auth_url,
    exchange_code_for_token,
    parse_iso_duration,
)
from database import get_db
from encryption import decrypt, encrypt

router = APIRouter(prefix="/integrations/polar", tags=["polar"])

FRONTEND_URL = "https://health-app-production-e0ff.up.railway.app"


# ── helpers ────────────────────────────────────────────────────────────────────

def _get_polar_row(user_id: int, db: Session) -> models.UserIntegration | None:
    return (
        db.query(models.UserIntegration)
        .filter_by(user_id=user_id, provider="polar")
        .first()
    )


def _require_polar(user_id: int, db: Session) -> dict:
    row = _get_polar_row(user_id, db)
    if not row:
        raise HTTPException(status_code=404, detail="Polar not connected")
    import json
    return json.loads(decrypt(row.api_key_encrypted))


# ── connect ────────────────────────────────────────────────────────────────────

@router.get("/auth-url")
def get_auth_url(current_user: models.User = Depends(get_current_user)):
    """Return the Polar OAuth URL. Frontend fetches this (with bearer token) then
    does window.location.href = url."""
    import os
    if not os.getenv("POLAR_CLIENT_ID"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="POLAR_CLIENT_ID not configured on server",
        )
    return {"url": build_auth_url(current_user.id)}


@router.get("/callback")
def polar_callback(code: str, state: str, db: Session = Depends(get_db)):
    """
    OAuth callback — Polar redirects here after user authorises.
    state = user_id (set in build_auth_url).
    No bearer token here — this is a browser GET from Polar.
    """
    import json

    try:
        user_id = int(state)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    user = db.query(models.User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        token_data = exchange_code_for_token(code)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Token exchange failed: {exc}")

    access_token = token_data["access_token"]
    client = PolarClient(access_token)

    # Register once — 409 is fine (already registered)
    try:
        client.register_user(user_id)
    except Exception:
        pass  # registration errors are non-fatal if already registered

    # Prefer x_user_id from token response; fall back to /users/me
    polar_user_id = token_data.get("x_user_id")
    if not polar_user_id:
        try:
            polar_user_id = client.get_polar_user_id()
        except Exception:
            polar_user_id = None

    payload = json.dumps({
        "access_token": access_token,
        "polar_user_id": polar_user_id,
        "scope": token_data.get("scope"),
        "token_type": token_data.get("token_type"),
    })

    row = _get_polar_row(user_id, db)
    if row:
        row.api_key_encrypted = encrypt(payload)
    else:
        db.add(models.UserIntegration(
            user_id=user_id,
            provider="polar",
            api_key_encrypted=encrypt(payload),
        ))
    db.commit()

    return RedirectResponse(f"{FRONTEND_URL}/settings?polar=connected")


# ── status / disconnect ────────────────────────────────────────────────────────

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


# ── data sync ──────────────────────────────────────────────────────────────────

@router.get("/debug")
def polar_debug(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return raw registration + user info from Polar for troubleshooting."""
    import json as _json
    tokens = _require_polar(current_user.id, db)
    client = PolarClient(tokens["access_token"], polar_user_id=tokens.get("polar_user_id"))
    result = {
        "stored_polar_user_id": tokens.get("polar_user_id"),
        "token_keys": list(tokens.keys()),
        "token_scope": tokens.get("scope"),
        "token_type": tokens.get("token_type"),
    }
    try:
        reg = client.register_user(current_user.id)
        result["register"] = reg
    except Exception as exc:
        result["register_error"] = str(exc)

    # Try creating an exercise transaction and report raw response
    import httpx as _httpx
    try:
        with _httpx.Client() as hc:
            txn_resp = hc.post(
                f"https://www.polaraccesslink.com/v3/users/{tokens.get('polar_user_id')}/exercise-transactions",
                headers=client.headers,
            )
            result["txn_status"] = txn_resp.status_code
            result["txn_body"] = txn_resp.text[:500] if txn_resp.text else None
    except Exception as exc:
        result["txn_error"] = str(exc)

    return result


def _hr_zone_seconds(hr_zones) -> dict[str, int]:
    """Extract per-zone seconds from an Accesslink heart-rate-zones payload."""
    out = {f"z{i}_seconds": 0 for i in range(1, 6)}
    if not hr_zones:
        return out
    zones = hr_zones.get("zone") if isinstance(hr_zones, dict) else hr_zones
    if not isinstance(zones, list):
        return out
    for idx, z in enumerate(zones[:5], start=1):
        secs = parse_iso_duration(z.get("in-zone")) if isinstance(z, dict) else None
        out[f"z{idx}_seconds"] = secs or 0
    return out


@router.post("/sync")
def sync_polar_sessions(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pull new exercise sessions from Polar Accesslink and store as AerobicSession.

    Live increments land in the same aerobic_sessions table as the ZIP-export
    history, tagged source='polar_accesslink'.
    """
    tokens = _require_polar(current_user.id, db)
    client = PolarClient(tokens["access_token"], polar_user_id=tokens.get("polar_user_id"))

    # Ensure user is registered — safe to call again (409 = already registered)
    try:
        client.register_user(current_user.id)
    except Exception:
        pass

    try:
        sessions = client.pull_exercise_sessions()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Polar API error: {exc}")

    stored = 0
    for s in sessions:
        exists = (
            db.query(models.AerobicSession)
            .filter(
                models.AerobicSession.user_id == current_user.id,
                models.AerobicSession.source == "polar_accesslink",
                models.AerobicSession.source_session_id == s["external_id"],
            )
            .first()
        )
        if exists:
            continue

        start = s["start_time"]
        dur_s = s["duration_seconds"]
        zones = _hr_zone_seconds(s["hr_zones"])
        db.add(models.AerobicSession(
            user_id=current_user.id,
            source="polar_accesslink",
            source_session_id=s["external_id"],
            session_date=start.date() if start else None,
            start_time=start,
            stop_time=s["end_time"],
            sport_name=s["sport"],
            duration_minutes=round(dur_s / 60, 2) if dur_s else None,
            hr_avg=s["avg_hr"],
            hr_max=s["max_hr"],
            calories=s["calories"],
            **zones,
        ))
        stored += 1

    db.commit()
    return {"synced": stored, "available": len(sessions)}


# ── aerobic sessions (ZIP import) ──────────────────────────────────────────────

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
    """Return aerobic sessions seeded from the Polar Flow ZIP export."""
    q = (
        db.query(models.AerobicSession)
        .filter(models.AerobicSession.user_id == current_user.id)
        .order_by(models.AerobicSession.session_date.desc())
    )
    if since:
        q = q.filter(models.AerobicSession.session_date >= since)
    return q.limit(limit).all()
