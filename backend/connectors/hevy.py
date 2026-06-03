import httpx
import logging
from typing import Any

logger = logging.getLogger(__name__)

HEVY_BASE = "https://api.hevyapp.com/v1"


class HevyAuthError(Exception):
    pass


class HevyForbiddenError(Exception):
    pass


class HevyClient:
    def __init__(self, api_key: str) -> None:
        self._headers = {"api-key": api_key}

    def _check(self, response: httpx.Response) -> httpx.Response:
        if response.status_code == 401:
            raise HevyAuthError("Invalid Hevy API key")
        if response.status_code == 403:
            raise HevyForbiddenError("Access forbidden — check Hevy plan or permissions")
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
                set_data = {
                    "index": set_idx,
                    "type": s.get("type", "normal"),
                    "weight_kg": s.get("weight_kg"),
                    "reps": s.get("reps"),
                    "distance_meters": s.get("distance_meters"),
                    "duration_seconds": s.get("duration_seconds"),
                    "custom_metric": s.get("custom_metric"),
                }
                built_sets.append(set_data)

            built_exercises.append({
                "index": ex_idx,
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
