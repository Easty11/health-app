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

The v4 pull also runs without a Sync press: the load chain's `polar_sync` step
(`scripts/refresh_load.py`, on Training-page open and in the nightly sweep) calls the
same core, `polar_ingest.sync_user`, with the cascade off — the chain's own metabolic
steps recompute after it.
"""
import io
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
import polar_ingest
from auth import get_current_user
from connectors.polar import (
    PolarV4Client,
    build_auth_url,
    exchange_code_for_token,
)
from database import get_db
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
# The token store and refresh live in `polar_ingest` (Q154), so the load chain can read
# and refresh a user's token outside a request; the router maps the core's plain
# exceptions to HTTP statuses.

_get_polar_row = polar_ingest.get_polar_row
_store_tokens = polar_ingest.store_tokens


def _http_from_ingest(exc: polar_ingest.PolarIngestError) -> HTTPException:
    """Map a `polar_ingest` exception to the status this router has always returned:
    not connected → 404, token refresh → 424 (never 401, so the frontend interceptor
    never logs the user out), v4 API / zone fetch → 502. `detail` carries the core's
    message verbatim."""
    if isinstance(exc, polar_ingest.NotConnected):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, polar_ingest.TokenRefreshFailed):
        return HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


def _valid_client(user_id: int, db: Session) -> PolarV4Client:
    """`polar_ingest.valid_client` with its exceptions mapped to HTTP statuses."""
    try:
        return polar_ingest.valid_client(user_id, db)
    except polar_ingest.PolarIngestError as exc:
        raise _http_from_ingest(exc)


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
    """Pull v4 training sessions over the last `days`, upsert into aerobic_sessions,
    ENRICH the zoneless v4 rows in the window with per-exercise HR zones, then fire the
    per-user metabolic cascade (transform + rollup).

    The two-pass ingest (summary upsert → v4 zone enrichment → cascade) lives in
    `polar_ingest.sync_user` (Q154), shared with the load chain's `polar_sync` step;
    this route is the manual trigger and keeps its contract: default window 365 days,
    response `{synced, enriched, available, cascade, coverage, notice}`, and the core's
    failures mapped to 404 (not connected) / 424 (token refresh) / 502 (v4 API).
    """
    try:
        result = polar_ingest.sync_user(db, current_user.id, days=days, run_cascade=True)
    except polar_ingest.PolarIngestError as exc:
        raise _http_from_ingest(exc)
    coverage = zone_coverage(current_user.id, db)
    return {
        "synced": result["synced"],
        "enriched": result["enriched"],
        "available": result["available"],
        "cascade": result["cascade"],
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
    # Derived at read time: this Health Connect row is a Hevy workout that Garmin / Strava wrote
    # back into Health Connect (>= HEVY_MIRROR_OVERLAP_FRACTION of its own duration inside a
    # Hevy bout, excluded or not). Always non-canonical; the stored row is kept as evidence.
    hevy_mirror: bool = False

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
