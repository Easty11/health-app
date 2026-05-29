from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Any
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from connectors.hevy import HevyAuthError, HevyClient, HevyForbiddenError
from database import get_db
from encryption import decrypt, encrypt

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ---------- schemas ----------

class HevyKeyIn(BaseModel):
    api_key: str


class IntegrationOut(BaseModel):
    provider: str
    connected: bool


class RoutineSetIn(BaseModel):
    type: str = "normal"          # normal | warmup | dropset | failure
    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: int | None = None
    duration_seconds: int | None = None
    custom_metric: Any = None


class RoutineExerciseIn(BaseModel):
    exercise_template_id: str     # uppercase hex ID, e.g. "0222DB42"
    notes: str = ""
    rest_seconds: int = 90
    superset_id: int | None = None
    sets: list[RoutineSetIn]


class RoutineCreateIn(BaseModel):
    title: str
    folder_id: int | None = None
    exercises: list[RoutineExerciseIn]


# ---------- helpers ----------

def _get_integration(user_id: int, provider: str, db: Session) -> models.UserIntegration | None:
    return (
        db.query(models.UserIntegration)
        .filter_by(user_id=user_id, provider=provider)
        .first()
    )


def _require_integration(user_id: int, provider: str, db: Session) -> models.UserIntegration:
    row = _get_integration(user_id, provider, db)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{provider} integration not connected",
        )
    return row


def _hevy_client(user: models.User, db: Session) -> HevyClient:
    row = _require_integration(user.id, "hevy", db)
    return HevyClient(decrypt(row.api_key_encrypted))


def _hevy_error_to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, HevyAuthError):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    if isinstance(exc, HevyForbiddenError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Hevy API error")


# ---------- endpoints ----------

@router.get("", response_model=list[IntegrationOut])
def list_integrations(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(models.UserIntegration).filter_by(user_id=current_user.id).all()
    connected = {r.provider for r in rows}
    return [IntegrationOut(provider="hevy", connected="hevy" in connected)]


@router.post("/hevy", status_code=status.HTTP_201_CREATED)
def connect_hevy(
    body: HevyKeyIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_integration(current_user.id, "hevy", db)
    if row:
        row.api_key_encrypted = encrypt(body.api_key)
    else:
        row = models.UserIntegration(
            user_id=current_user.id,
            provider="hevy",
            api_key_encrypted=encrypt(body.api_key),
        )
        db.add(row)
    db.commit()
    return {"detail": "Hevy integration saved"}


@router.delete("/hevy", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_hevy(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _require_integration(current_user.id, "hevy", db)
    db.delete(row)
    db.commit()


@router.get("/hevy/workout-count")
async def hevy_workout_count(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client = _hevy_client(current_user, db)
    try:
        return await client.get_workout_count()
    except (HevyAuthError, HevyForbiddenError) as exc:
        raise _hevy_error_to_http(exc)


@router.get("/hevy/workouts")
async def hevy_workouts(
    page: int = 1,
    page_size: int = 10,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client = _hevy_client(current_user, db)
    try:
        return await client.get_workouts(page=page, page_size=page_size)
    except (HevyAuthError, HevyForbiddenError) as exc:
        raise _hevy_error_to_http(exc)


@router.get("/hevy/routines")
async def hevy_get_routines(
    page: int = 1,
    page_size: int = 10,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client = _hevy_client(current_user, db)
    try:
        return await client.get_routines(page=page, page_size=page_size)
    except (HevyAuthError, HevyForbiddenError) as exc:
        raise _hevy_error_to_http(exc)


@router.post("/hevy/routines", status_code=status.HTTP_201_CREATED)
async def hevy_create_routine(
    body: RoutineCreateIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client = _hevy_client(current_user, db)
    exercises = [ex.model_dump() for ex in body.exercises]
    try:
        return await client.create_routine(
            title=body.title,
            exercises=exercises,
            folder_id=body.folder_id,
        )
    except (HevyAuthError, HevyForbiddenError) as exc:
        raise _hevy_error_to_http(exc)
