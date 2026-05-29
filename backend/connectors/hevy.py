import httpx
from typing import Any

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
        response.raise_for_status()
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
