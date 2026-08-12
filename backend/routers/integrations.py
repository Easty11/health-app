import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator, model_validator
from typing import Any, Literal
from sqlalchemy.orm import Session
import httpx

import models
from auth import get_current_user
from connectors.hevy import HevyAuthError, HevyClient, HevyForbiddenError
from database import get_db
from encryption import decrypt, encrypt
from hevy_templates import refresh_catalogue_if_stale, sync_exercise_templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ---------- schemas ----------

class HevyKeyIn(BaseModel):
    api_key: str


class IntegrationOut(BaseModel):
    provider: str
    connected: bool


# Matches 8-char uppercase hex (built-in) or full UUID (custom) exercise template IDs.
_TEMPLATE_ID_RE = re.compile(
    r"^(?:[0-9A-F]{8}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
)

# Valid (weight_kg, reps, distance_meters, duration_seconds) non-null combinations per exercise type.
_VALID_SET_COMBOS = {
    (False, True,  False, False),  # bodyweight_reps
    (True,  True,  False, False),  # weight_reps / bodyweight_weighted
    (False, False, False, True),   # duration
    (True,  False, True,  False),  # weight_distance
    (False, False, True,  True),   # distance_duration
}


class RoutineSetIn(BaseModel):
    type: Literal["normal", "warmup", "dropset", "failure"] = "normal"
    weight_kg: float | None = None
    reps: int | None = None
    distance_meters: int | None = None
    duration_seconds: int | None = None
    rpe: float | None = None
    custom_metric: Any = None

    @model_validator(mode="after")
    def check_field_combination(self) -> "RoutineSetIn":
        combo = (
            self.weight_kg is not None,
            self.reps is not None,
            self.distance_meters is not None,
            self.duration_seconds is not None,
        )
        if combo not in _VALID_SET_COMBOS:
            raise ValueError(
                "set fields don't match any valid exercise type; "
                "valid combinations: reps; weight_kg+reps; duration_seconds; "
                "weight_kg+distance_meters; distance_meters+duration_seconds"
            )
        if self.rpe is not None and self.reps is None:
            raise ValueError("rpe is only valid for reps-based exercise types")
        return self


class RoutineExerciseIn(BaseModel):
    exercise_template_id: str
    notes: str = ""
    rest_seconds: int = 90
    superset_id: int | None = None
    sets: list[RoutineSetIn]

    @field_validator("exercise_template_id")
    @classmethod
    def validate_template_id(cls, v: str) -> str:
        if not _TEMPLATE_ID_RE.match(v):
            raise ValueError(
                "exercise_template_id must be an 8-char uppercase hex (e.g. C6C9B8A0) "
                "or a full UUID (e.g. a4f88801-6440-40b3-b862-728a3d2b1636)"
            )
        return v


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
        # Connector-auth failure (revoked/invalid Hevy key) is NOT a session-auth
        # failure — return 424 so the frontend interceptor never logs the user out.
        return HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY, detail=str(exc))
    if isinstance(exc, HevyForbiddenError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Hevy API error: {exc}")


# `sync_exercise_templates` consumes the exception inside its per-user isolation
# wrapper and records it as a STRING (`"HevyAuthError: Invalid Hevy API key: 401"`).
# Rehydrate the two types whose mapping is not the 502 default, so a revoked key
# still reaches `_hevy_error_to_http`'s 424 branch instead of being flattened to a
# bad-gateway — the 401->424 decoupling of #66 must survive the round-trip through
# the summary. Every other type maps to 502 either way, so the registry stops here.
_SYNC_ERROR_TYPES: dict[str, type[Exception]] = {
    "HevyAuthError": HevyAuthError,
    "HevyForbiddenError": HevyForbiddenError,
}


def _sync_error_to_http(error: str | None) -> HTTPException:
    """Route a recorded per-user sync error through `_hevy_error_to_http`."""
    text = error or "Hevy template sync failed"
    type_name, _, message = text.partition(": ")
    cls = _SYNC_ERROR_TYPES.get(type_name)
    if cls is None:
        return _hevy_error_to_http(Exception(text))
    return _hevy_error_to_http(cls(message or text))


def _sync_failure(summary: dict) -> HTTPException | None:
    """The summary's failure signal mapped to HTTP — None when the sync is clean.

    `hevy_templates` documents `users_synced == 0` as a first-class failure signal, and
    with `only_user_id` set there is exactly one user in scope, so a zero here is THIS
    user's failure and never a family-wide partial. Two distinguishable shapes:

      * `users_attempted == 0` — no stored key at all. Returns the same 404 body
        `_require_integration` gives, so a keyless caller reads identically whichever
        Hevy route it hits.
      * `users_failed >= 1` — the key exists and the run failed. The recorded error
        decides the code (revoked key -> 424, Hevy HTTP -> 502).

    Returning a 200 with a silent zero is the one thing this must not do: an
    unpopulated catalogue reading as success is the exact FEEDBACK §8 blind spot.
    """
    if summary.get("users_attempted", 0) == 0:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="hevy integration not connected",
        )
    if summary.get("users_failed", 0) >= 1:
        failed = [r for r in summary.get("per_user") or [] if r.get("status") == "failed"]
        return _sync_error_to_http(failed[0].get("error") if failed else None)
    return None


# ---------- endpoints ----------

@router.get("", response_model=list[IntegrationOut])
def list_integrations(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(models.UserIntegration).filter_by(user_id=current_user.id).all()
    connected = {r.provider for r in rows}
    return [
        IntegrationOut(provider="hevy", connected="hevy" in connected),
        IntegrationOut(provider="polar", connected="polar" in connected),
    ]


@router.post("/hevy", status_code=status.HTTP_201_CREATED)
async def connect_hevy(
    body: HevyKeyIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store the user's Hevy key, then seed the exercise-template catalogue.

    Ordering is load-bearing: the seed runs AFTER `db.commit()` because the committed
    `UserIntegration` row is what makes the key visible to `users_with_hevy_key`, which
    the sync reads. It calls the SAME path as `POST /hevy/sync` — one sync code path to
    reason about, not two.

    A seed failure never fails the key store: storing the key is the request's contract
    and still returns 201. But it is not swallowed either — `sync` carries the summary
    (whose own `users_failed` / `rows_processed` expose a partial run) or, if the call
    raised outright, a failure shape. An empty catalogue is visible in the response
    rather than a silent zero; swallowing it recreates the FEEDBACK §8 blind spot the
    wiring exists to close.
    """
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

    try:
        sync: dict = await sync_exercise_templates(db, only_user_id=current_user.id)
    except Exception as exc:  # noqa: BLE001 — the stored key must survive a bad seed
        db.rollback()  # the key commit is already durable; discard the seed's partial
        err = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "Hevy connect-time template seed FAILED for user %d — %s (key stored)",
            current_user.id, err,
        )
        sync = {"users_synced": 0, "status": "failed", "error": err}

    return {"detail": "Hevy integration saved", "sync": sync}


@router.delete("/hevy", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_hevy(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _require_integration(current_user.id, "hevy", db)
    db.delete(row)
    db.commit()


@router.post("/hevy/sync")
async def hevy_sync_templates(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Sync THIS user's Hevy exercise-template catalogue into `hevy_exercise_templates`.

    The operator trigger for the substrate every resolver reads (`resolve_exercise`,
    `catalogue_titles_by_id`, `suggest_candidates`, `resolve_custom_exercise`). Scoped to
    the caller via `only_user_id` — a user-facing route never runs a family-wide sync,
    which would expose one user's request to another user's stale key.

    Returns the summary verbatim, so `rows_processed` / `defaults_seen` / `customs_seen`
    / `collision_count` are readable at the call site rather than only in the log. The
    summary's failure signal is mapped to HTTP by `_sync_failure`; a failed run is never
    a 200.
    """
    summary = await sync_exercise_templates(db, only_user_id=current_user.id)
    failure = _sync_failure(summary)
    if failure is not None:
        raise failure
    return summary


@router.get("/hevy/workout-count")
async def hevy_workout_count(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    client = _hevy_client(current_user, db)
    try:
        return await client.get_workout_count()
    except (HevyAuthError, HevyForbiddenError, httpx.HTTPStatusError) as exc:
        raise _hevy_error_to_http(exc)


@router.get("/hevy/workouts")
async def hevy_workouts(
    page: int = 1,
    page_size: int = 10,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Q75(c): piggyback a staleness-gated template refresh on the fetch. Self-throttling
    # (per-user marker) and non-blocking on failure — never fails the workout fetch.
    await refresh_catalogue_if_stale(db, current_user.id)
    client = _hevy_client(current_user, db)
    try:
        return await client.get_workouts(page=page, page_size=page_size)
    except (HevyAuthError, HevyForbiddenError, httpx.HTTPStatusError) as exc:
        raise _hevy_error_to_http(exc)


@router.get("/hevy/workouts/all")
async def hevy_workouts_all(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Every workout, aggregated across Hevy's paginated /workouts endpoint.

    Backs the "See all" control — Hevy caps a single /workouts page at 10, so true
    "all" requires this server-side page loop. Errors route through the same choke
    point as the other read handlers (connector-auth -> 424, Hevy HTTP -> 502).
    """
    # Q75(c): same staleness-gated refresh as the paged fetch (idempotent — once one
    # path refreshes and stamps the marker, the other sees fresh).
    await refresh_catalogue_if_stale(db, current_user.id)
    client = _hevy_client(current_user, db)
    try:
        return await client.get_all_workouts()
    except (HevyAuthError, HevyForbiddenError, httpx.HTTPStatusError) as exc:
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
    except (HevyAuthError, HevyForbiddenError, httpx.HTTPStatusError) as exc:
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
    except (HevyAuthError, HevyForbiddenError, httpx.HTTPStatusError) as exc:
        raise _hevy_error_to_http(exc)
