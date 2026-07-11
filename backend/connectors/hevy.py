import httpx
import logging
from typing import Any

logger = logging.getLogger(__name__)

HEVY_BASE = "https://api.hevyapp.com/v1"


class HevyAuthError(Exception):
    pass


class HevyForbiddenError(Exception):
    pass


class HevyCustomExerciseLimitError(Exception):
    """403 exceeds-custom-exercise-limit on POST /v1/exercise_templates."""
    pass


class HevyBadRequestError(Exception):
    """400 Invalid request body on POST /v1/exercise_templates."""
    pass


class HevyClient:
    def __init__(self, api_key: str) -> None:
        self._headers = {"api-key": api_key}

    def _check(self, response: httpx.Response) -> httpx.Response:
        if response.status_code == 401:
            raise HevyAuthError(f"Invalid Hevy API key: {response.text}")
        if response.status_code == 403:
            raise HevyForbiddenError(f"Access forbidden — check Hevy plan or permissions: {response.text}")
        if response.is_error:
            raise httpx.HTTPStatusError(
                f"Hevy API error {response.status_code}: {response.text}",
                request=response.request,
                response=response,
            )
        return response

    async def get_workout_count(self) -> dict[str, Any]:
        async with httpx.AsyncClient(headers=self._headers) as client:
            r = await client.get(f"{HEVY_BASE}/workouts/count")
            return self._check(r).json()

    async def get_workouts(self, page: int = 1, page_size: int = 10) -> dict[str, Any]:
        async with httpx.AsyncClient(headers=self._headers) as client:
            r = await client.get(
                f"{HEVY_BASE}/workouts",
                params={"page": page, "pageSize": page_size},
            )
            return self._check(r).json()

    async def get_all_workouts(self, page_size: int = 10) -> dict[str, Any]:
        """Loop every /workouts page and concatenate — genuine "all workouts".

        Hevy caps /workouts pageSize at 10, so a single call can never return the
        full history; this walks page 1..page_count. Terminates on page_count and,
        defensively, on an empty batch (so a missing/short page_count can't hang it).
        Returns the same envelope shape as get_workouts: {"workouts": [...], "page_count": N}.
        """
        all_workouts: list[dict[str, Any]] = []
        page = 1
        page_count = 1
        while True:
            data = await self.get_workouts(page=page, page_size=page_size)
            batch = data.get("workouts", [])
            all_workouts.extend(batch)
            page_count = data.get("page_count", page)
            if page >= page_count or not batch:
                break
            page += 1
        return {"workouts": all_workouts, "page_count": page_count}

    async def get_routines(self, page: int = 1, page_size: int = 10) -> dict[str, Any]:
        async with httpx.AsyncClient(headers=self._headers) as client:
            r = await client.get(
                f"{HEVY_BASE}/routines",
                params={"page": page, "pageSize": page_size},
            )
            return self._check(r).json()

    async def get_exercise_templates(
        self,
        page: int = 1,
        page_size: int = 100,
        search: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"page": page, "pageSize": page_size}
        if search:
            params["search"] = search
        async with httpx.AsyncClient(headers=self._headers) as client:
            r = await client.get(f"{HEVY_BASE}/exercise_templates", params=params)
            return self._check(r).json()

    async def get_exercise_history(self, template_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(headers=self._headers) as client:
            r = await client.get(f"{HEVY_BASE}/exercise_templates/{template_id}/history")
            return self._check(r).json()

    async def create_routine(
        self,
        title: str,
        exercises: list[dict[str, Any]],
        folder_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Create a routine in Hevy.

        Each exercise in `exercises` should be a dict with keys:
            exercise_template_id  str      required  — uppercase hex ID, e.g. "0222DB42"
            notes                 str      optional
            rest_seconds          int      optional  — default 90
            superset_id           int|None optional
            sets                  list     required  — list of set dicts:
                type              str      required  — "normal"|"warmup"|"dropset"|"failure"
                weight_kg         float|None
                reps              int|None
                distance_meters   int|None
                duration_seconds  int|None
                custom_metric     any|None

        index fields on exercises and sets are assigned automatically (0-based).
        """
        built_exercises = []
        for ex_idx, ex in enumerate(exercises):
            built_sets = []
            for set_idx, s in enumerate(ex.get("sets", [])):
                set_data: dict[str, Any] = {
                    "type": s.get("type", "normal"),
                }
                for field in ("weight_kg", "reps", "distance_meters", "duration_seconds", "rpe", "custom_metric"):
                    val = s.get(field)
                    if val is not None:
                        set_data[field] = val
                built_sets.append(set_data)

            built_exercises.append({
                "exercise_template_id": ex["exercise_template_id"],
                "superset_id": ex.get("superset_id"),
                "notes": ex.get("notes", ""),
                "rest_seconds": ex.get("rest_seconds", 90),
                "sets": built_sets,
            })

        payload = {
            "routine": {
                "title": title,
                "folder_id": folder_id,
                "exercises": built_exercises,
            }
        }

        logger.info("Hevy create_routine payload: %s", payload)

        async with httpx.AsyncClient(headers=self._headers) as client:
            r = await client.post(f"{HEVY_BASE}/routines", json=payload)
            return self._check(r).json()

    async def create_exercise_template(
        self,
        title: str,
        exercise_type: str,
        equipment_category: str,
        muscle_group: str,
        other_muscles: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a custom exercise template in Hevy.

        POST /v1/exercise_templates. Body is WRAPPED: {"exercise": {...}} —
        confirmed against the live OpenAPI spec's CreateCustomExerciseRequestBody
        (mirrors create_routine's {"routine": {...}}, NOT flat fields). Fields:
            title               str        required
            exercise_type       str        CustomExerciseType enum
                                           (weight_reps, reps_only, bodyweight_reps, …)
            equipment_category  str        EquipmentCategory enum (barbell, dumbbell, …)
            muscle_group        str        MuscleGroup enum — the PRIMARY muscle
            other_muscles       list[str]  optional — secondary MuscleGroup enums

        Returns the raw response, e.g. {"id": 123}. The spec types this `id` as an
        INTEGER, distinct from the canonical string-UUID returned by GET — callers
        must not trust it as the store key; resolve by list-back instead (#NEXT).

        Raises HevyCustomExerciseLimitError on 403 (exceeds-custom-exercise-limit)
        and HevyBadRequestError on 400 (invalid body), so callers see typed errors
        rather than a raw httpx.HTTPStatusError.
        """
        exercise: dict[str, Any] = {
            "title": title,
            "exercise_type": exercise_type,
            "equipment_category": equipment_category,
            "muscle_group": muscle_group,
        }
        if other_muscles is not None:
            exercise["other_muscles"] = other_muscles
        payload = {"exercise": exercise}

        logger.info("Hevy create_exercise_template payload: %s", payload)

        async with httpx.AsyncClient(headers=self._headers) as client:
            r = await client.post(f"{HEVY_BASE}/exercise_templates", json=payload)
        # Map the endpoint-specific statuses before the generic _check, which
        # would mis-label this 403 as a plan/permission error.
        if r.status_code == 403:
            raise HevyCustomExerciseLimitError(
                f"Hevy custom-exercise limit reached: {r.text}"
            )
        if r.status_code == 400:
            raise HevyBadRequestError(
                f"Hevy rejected the exercise-template body: {r.text}"
            )
        return self._check(r).json()
