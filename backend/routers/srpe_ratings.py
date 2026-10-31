"""Per-session sRPE for the close-out, the AM catch-up and the backfill.

  GET  /checkin-v2/srpe/sessions?since=&until=   each counted session in a range (default today), with its label and
                                                 its current rating and source if any (the read door's answer)
  GET  /checkin-v2/srpe/earlier?before=          the backfill: earlier sessions no source has rated, within the bound
  POST /checkin-v2/srpe/ratings                  one CR-10 per counted session, written as source `in_app`

Both are bounded by `srpe_in_app.rating_window`. The read is `reads.srpe_reads.session_ratings` (the one door,
so the card shows exactly what the MCP lines and the residual read); the write is `srpe_in_app.rate_sessions`
(the contract: a key must be a counted session of this user, and the window written is the server's own).
Insert-only: re-rating a session is a new row and the door's latest-wins resolves it.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

import pytz
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
import srpe_in_app
import srpe_store
from auth import get_current_user
from database import get_db
from reads.srpe_reads import session_ratings
from routers import checkin_v2
from routers.checkin_v2 import SessionRatingOut, session_rating_out

router = APIRouter(prefix="/checkin-v2/srpe", tags=["checkin-v2", "srpe"])

AEST = pytz.timezone("Australia/Brisbane")


class SessionsOut(BaseModel):
    since: date
    until: date
    sessions: list[SessionRatingOut]


class RatingBody(BaseModel):
    kind: Literal["aerobic", "hevy"]
    id: str = Field(..., min_length=1, max_length=64)
    rpe: float = Field(..., ge=0, le=10)


class RatingsIn(BaseModel):
    ratings: list[RatingBody] = Field(..., min_length=1, max_length=60)


class RatingsOut(BaseModel):
    written: int
    sessions: list[SessionRatingOut]


def _local_day_of(dt) -> date:
    """The operator-local day of a stored instant (a naive value, as SQLite hands back, is UTC)."""
    return (dt.replace(tzinfo=pytz.utc) if dt.tzinfo is None else dt).astimezone(AEST).date()


@router.get("/sessions", response_model=SessionsOut)
def get_sessions(
    since: Optional[date] = Query(None),
    until: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Each counted session in `[since, until]` (both default to today) with its current rating and source."""
    today = checkin_v2._today_aest()
    since = since or until or today
    until = until or since
    earliest, latest = srpe_in_app.rating_window(today)
    if since > until:
        raise HTTPException(status_code=422, detail="since must not be after until.")
    if since < earliest or until > latest:
        raise HTTPException(status_code=422, detail=f"sessions can be read from {earliest} to {latest}.")
    rated = session_ratings(db, current_user.id, since=since, until=until)
    return SessionsOut(since=since, until=until, sessions=[session_rating_out(rs) for rs in rated])


@router.get("/earlier", response_model=SessionsOut)
def get_earlier(
    before: Optional[date] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The backfill: sessions earlier than `before` (default today) that NO source has rated, oldest first.

    The bound is `srpe_in_app.earlier_range`: the 14 days before `before`, never before the store's release
    (18 Oct 2026). A session with no usable window is left out (nothing could be placed on it). Empty is a
    normal answer: nothing to offer."""
    today = checkin_v2._today_aest()
    before = before or today
    if before > today:
        raise HTTPException(status_code=422, detail="before must not be in the future.")
    window = srpe_in_app.earlier_range(before, today)
    if window is None:
        return SessionsOut(since=before, until=before, sessions=[])
    since, until = window
    unrated = [session_rating_out(rs) for rs in session_ratings(db, current_user.id, since=since, until=until)
               if rs.rating is None]
    return SessionsOut(since=since, until=until, sessions=[s for s in unrated if s.rateable])


@router.post("/ratings", response_model=RatingsOut)
def post_ratings(
    body: RatingsIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        rows = srpe_in_app.rate_sessions(
            db, current_user.id,
            [srpe_in_app.RatingIn(kind=r.kind, id=r.id, rpe=r.rpe) for r in body.ratings],
            today=checkin_v2._today_aest())
    except srpe_store.SRPEContractError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))
    written = {tuple(r.source_activity_ref.split(":", 1)) for r in rows}
    days = [_local_day_of(r.start_time) for r in rows]
    refreshed = session_ratings(db, current_user.id, since=min(days), until=max(days))
    return RatingsOut(
        written=len(rows),
        sessions=[session_rating_out(rs) for rs in refreshed if (rs.bout.kind, str(rs.bout.key[1])) in written])
