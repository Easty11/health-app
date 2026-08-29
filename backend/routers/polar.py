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
  POST /integrations/polar/import-export    → upload a Flow-export ZIP → AerobicSession (source='polar_flow_export')
  GET  /integrations/polar/aerobic-sessions → all AerobicSession records (ZIP + v4)
  GET  /integrations/polar/v4-raw           → raw first session JSON (schema debug)

Every aerobic ingest (sync + import-export) fires the per-user metabolic cascade
(recompute-on-ingest is automatic). ZIP-export history can also be loaded from the
command line via import_polar.py (ops / backfill; same shared import core).
"""
import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
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
from import_polar import import_flow_export
from metabolic_cascade import run_metabolic_cascade
from reads.aerobic_reads import arbitrated_sessions, coverage_notice, zone_coverage

router = APIRouter(prefix="/integrations/polar", tags=["polar"])

FRONTEND_URL = "https://health-app-production-e0ff.up.railway.app"

# ── Flow-export upload hygiene caps (fail-closed; reported in the PR body) ────────
# The archive is untrusted input, so bound it before any decompression. Members
# other than `training-session_*.json` are ignored and never decompressed, so a
# zip-bomb can only hide in members we don't read; caps therefore bind the parsed
# set. A generous Flow export is a few hundred small JSON members, so these caps
# sit far above any real export while still refusing a pathological archive.
MAX_ZIP_MEMBERS = 10_000                              # total entries in the archive
MAX_TRAINING_SESSION_MEMBERS = 5_000                 # session members we will parse
MAX_MEMBER_UNCOMPRESSED_BYTES = 10 * 1024 * 1024     # 10 MiB per session member
MAX_TOTAL_UNCOMPRESSED_BYTES = 200 * 1024 * 1024     # 200 MiB across parsed members


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
            # Token-refresh failure is a connector failure, not session death — 424,
            # not 401, so the frontend interceptor never logs the user out.
            raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY, detail=f"Polar token refresh failed: {exc}")

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
    """Pull v4 training sessions over the last `days` and upsert into aerobic_sessions,
    then fire the per-user metabolic cascade (transform + rollup).

    Aerobic ingest is recompute-triggering: every ingest cascades automatically, no
    manual recompute step. The cascade on a v4 sync is harmless today — v4 list rows
    carry no HR-zone split, so they fail-closed skip the metabolic transform (INV-7)
    and contribute nothing — and becomes correct unchanged after Phase 2 enriches v4
    sessions with per-exercise zones.
    """
    client = _valid_client(current_user.id, db)
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days)
    end = today + timedelta(days=1)

    try:
        raw_sessions = client.list_training_sessions_chunked(start, end)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Polar v4 API error: {exc}")

    stored = 0
    for raw in raw_sessions:
        fields = PolarV4Client.parse_session(raw)
        if not fields or not fields.get("source_session_id"):
            continue
        # Dedup across sources: a session already imported from the ZIP
        # (polar_flow_export, which carries cardio_load + zones) takes precedence,
        # so v4 only adds sessions not already present.
        exists = (
            db.query(models.AerobicSession)
            .filter(
                models.AerobicSession.user_id == current_user.id,
                models.AerobicSession.source_session_id == fields["source_session_id"],
                models.AerobicSession.source.in_(["polar_flow_export", "polar_v4"]),
            )
            .first()
        )
        if exists:
            continue
        db.add(models.AerobicSession(user_id=current_user.id, **fields))
        stored += 1

    db.commit()

    cascade = run_metabolic_cascade(db, current_user.id)
    coverage = zone_coverage(current_user.id, db)
    return {
        "synced": stored,
        "available": len(raw_sessions),
        "cascade": cascade,
        "coverage": coverage,
        "notice": coverage_notice(coverage),
    }


@router.post("/import-export")
async def import_polar_flow_export(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a Polar Flow data-export ZIP and ingest its training sessions.

    Collapses the operator's local `import_polar.py` runbook into one in-app action
    for the AUTHENTICATED user (never an email parameter): parse the ZIP's
    `training-session_*.json` members into `aerobic_sessions` (source
    `polar_flow_export`, skipping ids already imported), then fire the per-user
    metabolic cascade (transform + `load_metrics` rollup) — recompute-on-ingest is
    automatic, not a button.

    Fail-closed input hygiene: a non-ZIP upload, or an archive breaching the member-
    count / per-member / total-size caps, is rejected 4xx before anything is parsed.
    Only `training-session_*.json` members are read; all other members are ignored.
    """
    raw = await file.read()

    # Reject a non-ZIP outright (fail-closed on the archive magic, not content-type).
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is not a valid ZIP archive",
        )

    # Bound the archive before decompressing anything.
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_MEMBERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ZIP has too many entries (limit {MAX_ZIP_MEMBERS})",
            )
        session_infos = [
            i for i in infos
            if i.filename.startswith("training-session_") and i.filename.endswith(".json")
        ]
        if len(session_infos) > MAX_TRAINING_SESSION_MEMBERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"ZIP has too many training-session members "
                    f"(limit {MAX_TRAINING_SESSION_MEMBERS})"
                ),
            )
        total = 0
        for i in session_infos:
            if i.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"A training-session member exceeds the per-file size cap "
                        f"({MAX_MEMBER_UNCOMPRESSED_BYTES} bytes)"
                    ),
                )
            total += i.file_size
        if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Training-session members exceed the total size cap "
                    f"({MAX_TOTAL_UNCOMPRESSED_BYTES} bytes)"
                ),
            )

    summary = import_flow_export(db, current_user.id, raw)
    cascade = run_metabolic_cascade(db, current_user.id)
    coverage = zone_coverage(current_user.id, db)
    return {
        "import": {
            "found": summary["found"],
            "inserted": summary["inserted"],
            "skipped": summary["skipped"],
            "errors": summary["errors"],
            "pre_existing": summary["pre_existing"],
        },
        "cascade": cascade,
        "coverage": coverage,
        "notice": coverage_notice(coverage),
    }


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
    from_dt = f"{(today - timedelta(days=days)).isoformat()}T00:00:00"
    to_dt = f"{(today + timedelta(days=1)).isoformat()}T00:00:00"
    try:
        raw = client.list_training_sessions(from_dt, to_dt)
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
    # Derived at read time (reads.aerobic_reads), never a stored column: false
    # when a higher-fidelity session from another source describes the same bout.
    canonical: bool = True

    model_config = {"from_attributes": True}


@router.get("/aerobic-sessions", response_model=list[AerobicSessionOut])
def get_aerobic_sessions(
    limit: int = 100,
    since: Optional[date] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """All aerobic sessions — ZIP export history + v4 live sync, one table.

    Each row carries a derived `canonical` flag from read-time cross-source
    arbitration (Polar outranks Health Connect for the same bout). The flag is
    computed over the full window before `limit` so a bout's counterpart is
    never truncated out of the comparison.
    """
    return arbitrated_sessions(current_user.id, db, since=since, limit=limit)
