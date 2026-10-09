"""`GET /freshness` — the data-freshness read for the UI (home load card).

Read-only and computed on read (`reads/freshness_reads.py`): per (stream, writer) newest record
and staleness, plus the last delivery of each pipe into the platform. Nothing is written."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db
from reads.freshness_reads import freshness

router = APIRouter(prefix="/freshness", tags=["freshness"])


@router.get("")
def get_freshness(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return freshness(db, current_user.id)
