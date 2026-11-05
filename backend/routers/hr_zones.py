"""Heart-rate zone config — the Settings card's API (design 0010 §6).

  GET  /hr-zones/config            the one read (`reads.zone_reads.zone_config`): classes, bpm bands today, anchors
                                   (in force + every entry), retest flags, the R8 default date, hrmax_prompts,
                                   the Garmin mirror. Read-only.
  POST /hr-zones/anchors/preview   the bpm preview before commit (R6): today's edges per class before and after,
                                   the rows whose spec changes, the row a restatement corrects. Writes nothing.
  POST /hr-zones/anchors           append ONE LTHR / RHR row (dated change or restatement — the forced choice),
                                   append-only; `kind: hrmax` is refused naming `scripts/set_hrmax.py`.

Every refusal is a 400 whose detail says the way out (`hr_anchors.AnchorRefused`). The caller forces the load
chain afterwards (`POST /load/refresh?force=true`), which re-zones every row and recomputes `metab-v2`.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import hr_anchors
import models
from auth import get_current_user
from database import get_db
from load_metrics import _local_day   # the operator-local (AEST) day, the one source
from reads.zone_reads import zone_config

router = APIRouter(prefix="/hr-zones", tags=["hr-zones"])


class AnchorIn(BaseModel):
    kind: str = Field(..., description="'lthr' | 'rhr' ('hrmax' is refused: scripts/set_hrmax.py)")
    bpm: int
    effective_from: date
    provenance: str = Field(..., description="tested | observed | device_estimated | stated")
    note: str = Field(..., description="the evidence")
    change: str = Field(..., description="'dated' (forward only) | 'restate' (corrects the row on this date)")
    rationale: Optional[str] = None


@router.get("/config")
def get_config(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return zone_config(db, current_user.id, today=_local_day())


@router.post("/anchors/preview")
def preview_anchor(body: AnchorIn, current_user: models.User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    try:
        hr_anchors.validate(kind=body.kind, bpm=body.bpm, effective_from=body.effective_from,
                            provenance=body.provenance, note=body.note, change=body.change,
                            rationale=body.rationale)
        return hr_anchors.plan(db, current_user.id, kind=body.kind, bpm=body.bpm,
                               effective_from=body.effective_from, provenance=body.provenance, change=body.change,
                               today=_local_day())
    except hr_anchors.AnchorRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/anchors", status_code=201)
def append_anchor(body: AnchorIn, current_user: models.User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    try:
        return hr_anchors.append(db, current_user.id, kind=body.kind, bpm=body.bpm,
                                 effective_from=body.effective_from, provenance=body.provenance,
                                 note=body.note, change=body.change, rationale=body.rationale,
                                 today=_local_day())
    except hr_anchors.AnchorRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc))
