from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pytz
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db
from encryption import decrypt
from connectors.hevy import HevyClient, HevyAuthError

router = APIRouter(prefix="/checkin", tags=["checkin"])

AEST = pytz.timezone("Australia/Brisbane")

RUGBY_KEYWORDS = {"rugby", "conditioning", "match", "game", "scrimmage"}


def _today_aest() -> date:
    return datetime.now(AEST).date()


def _calc_readiness(sleep: int, fatigue: int, shoulder: int, motivation: int) -> int:
    """
    Weighted readiness score (1-10):
      sleep_quality    × 0.30
      (10 - fatigue)   × 0.30
      (10 - shoulder)  × 0.20
      motivation       × 0.20
    """
    raw = (
        sleep * 0.30
        + (10 - fatigue) * 0.30
        + (10 - shoulder) * 0.20
        + motivation * 0.20
    )
    return max(1, min(10, round(raw)))


# ---------- schemas ----------

class CheckInIn(BaseModel):
    sleep_quality: int = Field(..., ge=1, le=10)
    fatigue: int = Field(..., ge=1, le=10)
    shoulder_pain: int = Field(..., ge=0, le=10)
    motivation: int = Field(..., ge=1, le=10)
    rugby_session_yesterday: bool = False
    notes: Optional[str] = None


class CheckInOut(BaseModel):
    id: int
    date: date
    sleep_quality: int
    fatigue: int
    shoulder_pain: int
    motivation: int
    rugby_session_yesterday: bool
    notes: Optional[str]
    readiness_score: int

    model_config = {"from_attributes": True}


class CheckInPrefill(BaseModel):
    """Pre-populated values and metadata for the confirm-and-adjust screen."""
    rugby_session_yesterday: bool
    rugby_session_title: Optional[str]       # title of the Hevy session if found
    last_session_title: Optional[str]        # most recent Hevy workout title
    last_session_date: Optional[str]         # ISO date of most recent workout
    # Manual fields — defaults only, no auto-fill yet
    sleep_quality: int = 7
    fatigue: int = 4
    shoulder_pain: int = 2
    motivation: int = 7


# ---------- helpers ----------

async def _get_hevy_prefill(user_id: int, db: Session) -> dict:
    """Fetch yesterday's Hevy data to pre-populate rugby toggle and last session."""
    result = {
        "rugby_session_yesterday": False,
        "rugby_session_title": None,
        "last_session_title": None,
        "last_session_date": None,
    }

    integration = db.query(models.UserIntegration).filter_by(user_id=user_id, provider="hevy").first()
    if not integration:
        return result

    try:
        client = HevyClient(decrypt(integration.api_key_encrypted))
        data = await client.get_workouts(page=1, page_size=5)
        workouts = data.get("workouts", [])

        if not workouts:
            return result

        # Most recent workout
        latest = workouts[0]
        result["last_session_title"] = latest.get("title") or latest.get("name")
        start = latest.get("start_time") or latest.get("created_at") or ""
        result["last_session_date"] = start[:10] if start else None

        # Check last 24h for rugby/conditioning session
        yesterday_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        for w in workouts:
            start_str = w.get("start_time") or w.get("created_at") or ""
            if not start_str:
                continue
            try:
                w_dt = datetime.fromisoformat(start_str[:19]).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if w_dt < yesterday_cutoff:
                break  # sorted newest first; stop once outside window
            title = (w.get("title") or w.get("name") or "").lower()
            if any(kw in title for kw in RUGBY_KEYWORDS):
                result["rugby_session_yesterday"] = True
                result["rugby_session_title"] = w.get("title") or w.get("name")
                break
    except HevyAuthError:
        pass

    return result


# ---------- endpoints ----------

@router.get("/prefill", response_model=CheckInPrefill)
async def get_prefill(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return auto-populated values for the check-in form."""
    hevy = await _get_hevy_prefill(current_user.id, db)
    return CheckInPrefill(**hevy)


@router.post("", response_model=CheckInOut, status_code=status.HTTP_201_CREATED)
def submit_checkin(
    body: CheckInIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = _today_aest()
    readiness = _calc_readiness(
        body.sleep_quality, body.fatigue, body.shoulder_pain, body.motivation
    )

    existing = (
        db.query(models.DailyCheckIn)
        .filter_by(user_id=current_user.id, date=today)
        .first()
    )
    if existing:
        for field, value in body.model_dump().items():
            setattr(existing, field, value)
        existing.readiness_score = readiness
        db.commit()
        db.refresh(existing)
        return existing

    checkin = models.DailyCheckIn(
        user_id=current_user.id,
        date=today,
        readiness_score=readiness,
        **body.model_dump(),
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)
    return checkin


@router.get("/today", response_model=Optional[CheckInOut])
def get_today_checkin(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = _today_aest()
    return (
        db.query(models.DailyCheckIn)
        .filter_by(user_id=current_user.id, date=today)
        .first()
    )


@router.get("/history", response_model=list[CheckInOut])
def get_checkin_history(
    days: int = 14,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = _today_aest()
    since = today - timedelta(days=days)
    return (
        db.query(models.DailyCheckIn)
        .filter(
            models.DailyCheckIn.user_id == current_user.id,
            models.DailyCheckIn.date >= since,
        )
        .order_by(models.DailyCheckIn.date.desc())
        .all()
    )
