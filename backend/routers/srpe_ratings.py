"""Per-session sRPE for the close-out, the AM catch-up and the backfill.

  GET  /checkin-v2/srpe/sessions?since=&until=   each counted session in a range, with its label and its current
                                                 rating and source if any (the read door's answer, nothing else)
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
from reads.srpe_reads import HEVY, RatedSession, session_ratings
from routers import checkin_v2

router = APIRouter(prefix="/checkin-v2/srpe", tags=["checkin-v2", "srpe"])

AEST = pytz.timezone("Australia/Brisbane")


class SessionRatingOut(BaseModel):
    """A counted session as the cards show it. `rpe`/`source` are the current rating (None, None when unrated).
    `rateable` is False for a session with no usable window, which no rating could be placed on."""
    kind: Literal["aerobic", "hevy"]
    id: str
    day: date
    label: str
    minutes: Optional[float] = None
    start_local: Optional[str] = None          # "HH:MM" in the operator's local day (Brisbane)
    rpe: Optional[float] = None
    source: Optional[str] = None
    rateable: bool = True


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


def _label(rs: RatedSession) -> str:
    ref = rs.bout.ref
    if rs.bout.kind == HEVY:
        return (getattr(ref, "title", None) or "").strip() or "Workout"
    return (getattr(ref, "sport_name", None) or "").strip() or "Session"


def _out(rs: RatedSession) -> SessionRatingOut:
    b = rs.bout
    try:
        srpe_store.bout_window(b)
        rateable = True
    except srpe_store.UnplaceableBout:
        rateable = False
    return SessionRatingOut(
        kind=b.kind, id=str(b.key[1]), day=b.day, label=_label(rs),
        minutes=None if b.minutes is None else round(b.minutes, 1),
        start_local=None if b.start is None else b.start.astimezone(AEST).strftime("%H:%M"),
        rpe=None if rs.rating is None else rs.rating.rpe_cr10,
        source=None if rs.rating is None else rs.rating.source,
        rateable=rateable)


@router.get("/sessions", response_model=SessionsOut)
def get_sessions(
    since: date = Query(...),
    until: date = Query(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    earliest, latest = srpe_in_app.rating_window(checkin_v2._today_aest())
    if since > until:
        raise HTTPException(status_code=422, detail="since must not be after until.")
    if since < earliest or until > latest:
        raise HTTPException(status_code=422, detail=f"sessions can be read from {earliest} to {latest}.")
    rated = session_ratings(db, current_user.id, since=since, until=until)
    return SessionsOut(since=since, until=until, sessions=[_out(rs) for rs in rated])


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
        sessions=[_out(rs) for rs in refreshed if (rs.bout.kind, str(rs.bout.key[1])) in written])
