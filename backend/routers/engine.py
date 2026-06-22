"""
Adaptive Exposure Engine API (Decision Support module).

Endpoints:
  GET  /engine/taxonomy         — the versioned axis list (read-only reference)
  GET  /engine/profile          — this user's fortification-target profile (§9)
  PUT  /engine/profile          — upsert the profile
  GET  /engine/capability-state — the map contents + coverage summary (§3, §2.1)
  GET  /engine/probe-queue      — the computed probe queue (§4)
  GET  /engine/next             — one Fortify rec + one Probe suggestion (§2)
  POST /engine/response         — apply an adaptation-loop response tag (§7)

Avoidance (§4) is read from Hevy load history — what the user does NOT load is the
candidate deficiency set. Probe-queue / next fetch that best-effort; if Hevy is
absent the loaded set is empty and every region reads as "avoided", which is a
safe over-inclusion bounded by the one-probe-per-session cadence.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from connectors.hevy import HevyAuthError, HevyClient
from database import get_db
from encryption import decrypt
from engine import adaptation, profile as profile_mod, selection, taxonomy

router = APIRouter(prefix="/engine", tags=["engine"])


# --------------------------------------------------------------------------- #
# Schemas                                                                      #
# --------------------------------------------------------------------------- #

class ProfileIn(BaseModel):
    floor: dict[str, Any] | None = None
    ceiling: str | None = None
    horizon: str | None = None
    horizon_date: str | None = None
    primary_target: str | None = None
    primary_target_note: str | None = None
    live_signals: list[dict[str, Any]] | None = None
    hard_stops: list[dict[str, Any]] | None = None
    vehicle_bias: list[str] | None = None
    probe_budget: float | None = None
    notes: str | None = None


class ResponseIn(BaseModel):
    region_key: str
    side: str = taxonomy.SIDE_BILATERAL
    tag: str                       # absorbed_clean | symptom_carryover | flare | capability_revealed
    probe_result: str | None = None  # pass | deficient (required for capability_revealed)
    signal_text: str | None = None   # the user's education-idiom report
    source: str = "probe"


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

async def _loaded_regions(db: Session, user_id: int) -> set[str]:
    """Region keys the user has loaded recently (Hevy), best-effort."""
    integ = (
        db.query(models.UserIntegration)
        .filter_by(user_id=user_id, provider="hevy")
        .first()
    )
    if integ is None:
        return set()
    try:
        client = HevyClient(decrypt(integ.api_key_encrypted))
        data = await client.get_workouts(page=1, page_size=10)
    except (HevyAuthError, Exception):
        return set()
    return selection.infer_loaded_regions(data.get("workouts", []))


def _readiness_hint(db: Session, user_id: int) -> int | None:
    """Subjective readiness on a 1–10 scale, or None. Used only to re-rank
    vehicles — never to gate (DECISIONS_LOG #8)."""
    import pytz
    from datetime import datetime as _dt

    today = _dt.now(pytz.timezone("Australia/Brisbane")).date()
    rec = db.query(models.DailyRecord).filter_by(user_id=user_id, date=today).first()
    if rec is not None and rec.morning_readiness is not None:
        return int(rec.morning_readiness) * 2  # 1–5 → 1–10
    chk = db.query(models.DailyCheckIn).filter_by(user_id=user_id, date=today).first()
    if chk is not None and chk.readiness_score is not None:
        return int(chk.readiness_score)
    return None


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #

@router.get("/taxonomy")
def get_taxonomy():
    return {
        "version": taxonomy.TAXONOMY_VERSION,
        "regions": [taxonomy.as_dict(r) for r in taxonomy.all_regions()],
    }


@router.get("/profile")
def get_profile(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = profile_mod.get_profile(db, current_user.id)
    return {"profile": profile_mod.profile_to_dict(p)}


@router.put("/profile")
def put_profile(
    body: ProfileIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from datetime import date as _date

    data = body.model_dump(exclude_unset=True)
    if data.get("horizon_date"):
        try:
            data["horizon_date"] = _date.fromisoformat(data["horizon_date"])
        except ValueError:
            raise HTTPException(status_code=422, detail="horizon_date must be ISO YYYY-MM-DD")
    p = profile_mod.upsert_profile(db, current_user.id, data)
    return {"profile": profile_mod.profile_to_dict(p)}


@router.get("/capability-state")
def get_capability_state(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.CapabilityState)
        .filter_by(user_id=current_user.id)
        .order_by(models.CapabilityState.region_key, models.CapabilityState.side)
        .all()
    )
    return {
        "states": [
            {
                "region_key": r.region_key,
                "label": (taxonomy.by_key(r.region_key).label
                          if taxonomy.by_key(r.region_key) else r.region_key),
                "side": r.side,
                "status": r.status,
                "source": r.source,
                "detail": r.detail,
                "last_probed_at": str(r.last_probed_at) if r.last_probed_at else None,
            }
            for r in rows
        ],
        "coverage": adaptation.coverage_summary(db, current_user.id),
    }


@router.get("/probe-queue")
async def get_probe_queue(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = profile_mod.get_profile(db, current_user.id)
    loaded = await _loaded_regions(db, current_user.id)
    queue = selection.compute_probe_queue(
        db, current_user.id, profile=p, loaded_region_keys=loaded,
    )
    return {"probe_queue": queue, "loaded_regions": sorted(loaded)}


@router.get("/next")
async def get_next(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = profile_mod.get_profile(db, current_user.id)
    loaded = await _loaded_regions(db, current_user.id)
    queue = selection.compute_probe_queue(
        db, current_user.id, profile=p, loaded_region_keys=loaded,
    )
    return selection.select_next(
        db, current_user.id, profile=p, probe_queue=queue,
        readiness_hint=_readiness_hint(db, current_user.id),
    )


@router.post("/response")
def post_response(
    body: ResponseIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row = adaptation.apply_response(
            db, current_user.id,
            region_key=body.region_key, side=body.side, tag=body.tag,
            probe_result=body.probe_result, signal_text=body.signal_text,
            source=body.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return {
        "region_key": row.region_key,
        "side": row.side,
        "status": row.status,
        "source": row.source,
        "detail": row.detail,
        "last_probed_at": str(row.last_probed_at) if row.last_probed_at else None,
    }
