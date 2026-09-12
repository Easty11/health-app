import httpx
import json
import logging
import math
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


class RoutineAlreadyExists(Exception):
    """A create_routine call collides with an existing routine on title AND folder.

    Hevy has NO delete endpoint and its update REPLACES a routine's contents, so
    silently POSTing past a duplicate leaves an unremovable second copy, and
    auto-updating on a false match destroys the original irrecoverably. The guard
    therefore refuses the create before the POST and hands the collision back
    typed, so every caller renders the SAME choice (rename, or explicitly update)
    rather than each inventing one — the chat lane flattens it to a WriteResult,
    the REST lane to a 409.

    Match is case-insensitive on title AND equal on folder_id (None == None): the
    same title in a different folder is a distinct routine, not a collision. The
    colliding rows are carried so a caller can name the existing id(s).
    """

    # Machine-checkable outcome code for the write-result contract, mirroring
    # ScheduleItemOverlap.code — a caller flattening this to a string keeps a
    # stable, type-derived code rather than parsing the prose (#283).
    code = "already_exists"

    def __init__(self, title: str, folder_id: int | None, existing: list[dict[str, Any]]):
        self.title = title
        self.folder_id = folder_id
        self.existing = existing
        ids = ", ".join(str(r.get("id")) for r in existing) or "?"
        super().__init__(
            f"a Hevy routine titled {title!r} already exists in this folder "
            f"(id: {ids}); Hevy has no delete and an update REPLACES its contents, "
            f"so rename the new routine or explicitly update the existing one"
        )


class RoutineNumericError(ValueError):
    """A routine-create payload carries a non-number where Hevy expects a number.

    The concrete incident was `Expected number, received nan`: the model emitted a
    literal `NaN` token, `json.loads` accepts it (parse_constant default), the builder
    passed it through (`NaN is not None`), and httpx serialized it (`allow_nan=True`
    default) straight to the wire. This is the whole CLASS — NaN, ±Infinity, a string
    or bool in a numeric slot — caught deterministically BEFORE any POST, naming the
    field and the exercise so the failure is nameable, not a bare Hevy 400.

    Subclasses ValueError so a REST caller's existing `except ValueError` still catches
    it; carries a stable `code` for the write-result contract (mirrors ScheduleItemInvalid).
    """

    code = "invalid_number"

    def __init__(self, message: str):
        super().__init__(message)


def _is_finite_number(value: Any) -> bool:
    """True only for a real, finite int/float — never a bool, never NaN/±Infinity.

    bool is a subclass of int, so `True`/`False` in a numeric slot is rejected too
    (a boolean weight is as wrong as a NaN one)."""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


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

    async def get_routine(self, routine_id: str) -> dict[str, Any]:
        """Fetch a single routine by its Hevy id — GET /v1/routines/{id}.

        The list endpoint (`get_routines`) returns compact rows; this is the
        full-config read the by-id inspect tool needs. The response is returned
        raw (`.json()`), like every GET here — Hevy wraps it as
        `{"routine": {...}}`, but callers tolerate both a wrapper and a bare
        object rather than asserting one shape (the connector parses nothing).

        A missing/invalid id surfaces as the connector's normal error mapping:
        `_check` raises `httpx.HTTPStatusError` on the 404, which the calling
        tool catches to render a clean not-found message rather than a crash.
        """
        async with httpx.AsyncClient(headers=self._headers) as client:
            r = await client.get(f"{HEVY_BASE}/routines/{routine_id}")
            return self._check(r).json()

    async def get_all_routines(self, page_size: int = 10) -> list[dict[str, Any]]:
        """Every routine across Hevy's paginated /routines endpoint — a flat list.

        Hevy caps a /routines page at 10 and offers no all-in-one read, so the
        idempotency guard (and any caller needing the full set) walks page
        1..page_count here. Mirrors get_all_workouts' terminate-on-page_count-or-
        empty-batch loop, so a missing/short page_count can't hang it. Returns the
        rows, not the paged envelope — every caller wants the routines themselves.
        """
        routines: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self.get_routines(page=page, page_size=page_size)
            batch = data.get("routines", []) or []
            routines.extend(batch)
            page_count = data.get("page_count", page)
            if page >= page_count or not batch:
                break
            page += 1
        return routines

    async def get_routine_folders(self, page_size: int = 10) -> list[dict[str, Any]]:
        """Every routine folder across Hevy's paginated /routine_folders endpoint.

        Backs name→id resolution for routine creation: the model names a folder, the
        chat lane matches it here. Returns a flat list of folder dicts (each carrying at
        least `id` and `title`). Defensive about the envelope — Hevy wraps the page as
        `{"routine_folders": [...], "page_count": N}`, but a caller asserts nothing:
        both a `routine_folders` key and a bare list are tolerated, mirroring how
        `get_routine` tolerates its wrapper (the connector parses nothing rigid).
        """
        folders: list[dict[str, Any]] = []
        page = 1
        while True:
            async with httpx.AsyncClient(headers=self._headers) as client:
                r = await client.get(
                    f"{HEVY_BASE}/routine_folders",
                    params={"page": page, "pageSize": page_size},
                )
                data = self._check(r).json()
            batch = data.get("routine_folders", []) if isinstance(data, dict) else (data or [])
            folders.extend(batch)
            page_count = data.get("page_count", page) if isinstance(data, dict) else page
            if page >= page_count or not batch:
                break
            page += 1
        return folders

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
        # Canonical Hevy path is /v1/exercise_history/{id}, where {id} is the
        # exercise TEMPLATE id (not a separate history id). The old
        # /exercise_templates/{id}/history shape 404'd since ship. Verified against
        # official docs + 3 independent current clients (hevy-api-wrapper 1.0.0,
        # chrisdoc/hevy-mcp, OpenClaw enumeration). See DECISIONS_LOG Q16.
        async with httpx.AsyncClient(headers=self._headers) as client:
            r = await client.get(f"{HEVY_BASE}/exercise_history/{template_id}")
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

        Idempotency (safe, Q144(a)): Hevy has NO delete and its update REPLACES a
        routine's contents, so a duplicate is unremovable and an auto-update on a
        false match is unrecoverable. Before the POST this refuses a create whose
        (title, folder_id) already exists — case-insensitive title, equal folder
        (None == None) — raising RoutineAlreadyExists. Both entry points inherit
        this floor. Cost accepted: one paginated /routines read per create.

        `rpe` is stripped from every set (Q144(b)): Hevy ignores rpe on a planned
        routine set, so emitting it is noise. The strip is deterministic here, not
        just prompt guidance — the model may emit it anyway. RPE is a logged-set
        fact consumed on the workout READ path (load_events); there is no
        workout-CREATE path, so this strip cannot touch load logging.

        Numeric floor (Q144 follow-up — the `Expected number, received nan` class):
        every value bound for a numeric field is checked for finiteness FIRST, before
        any network call, and a non-number (NaN, ±Infinity, a string/bool in a numeric
        slot) raises `RoutineNumericError` naming the field and exercise. Nothing
        non-finite is ever built or sent. `folder_id` name→id resolution is the caller's
        job (chat lane); here folder_id must already be an int or None.
        """
        def _ref(ex_idx: int, ex: dict[str, Any]) -> str:
            tid = ex.get("exercise_template_id") or ex.get("title") or "?"
            return f"exercise {ex_idx + 1} ({tid})"

        for ex_idx, ex in enumerate(exercises):
            for field in ("rest_seconds", "superset_id"):
                val = ex.get(field)
                if val is not None and not _is_finite_number(val):
                    raise RoutineNumericError(
                        f"{field} on {_ref(ex_idx, ex)} is not a valid number ({val!r})"
                    )
            for set_idx, s in enumerate(ex.get("sets", [])):
                for field in ("weight_kg", "reps", "distance_meters", "duration_seconds"):
                    val = s.get(field)
                    if val is not None and not _is_finite_number(val):
                        raise RoutineNumericError(
                            f"{field} on set {set_idx + 1} of {_ref(ex_idx, ex)} "
                            f"is not a valid number ({val!r})"
                        )
        if folder_id is not None and not _is_finite_number(folder_id):
            raise RoutineNumericError(f"folder_id is not a valid number ({folder_id!r})")

        existing = await self.get_all_routines()
        wanted = (title or "").strip().casefold()
        collisions = [
            r for r in existing
            if (r.get("title") or "").strip().casefold() == wanted
            and r.get("folder_id") == folder_id
        ]
        if collisions:
            raise RoutineAlreadyExists(title, folder_id, collisions)

        built_exercises = []
        for ex_idx, ex in enumerate(exercises):
            built_sets = []
            for set_idx, s in enumerate(ex.get("sets", [])):
                set_data: dict[str, Any] = {
                    "type": s.get("type", "normal"),
                }
                # `rpe` intentionally ABSENT — Hevy ignores it on a routine set and
                # the strip is the hard floor, not prompt guidance (Q144(b)).
                for field in ("weight_kg", "reps", "distance_meters", "duration_seconds", "custom_metric"):
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

        # Hard serialize backstop: allow_nan=False makes any non-finite that slipped
        # past the numeric floor above raise locally (ValueError) instead of emitting
        # an invalid `NaN`/`Infinity` token to the wire. The numeric floor should have
        # caught it already; this guarantees "never sent" even if a field was missed.
        body = json.dumps(payload, allow_nan=False).encode()
        async with httpx.AsyncClient(headers=self._headers) as client:
            r = await client.post(
                f"{HEVY_BASE}/routines",
                content=body,
                headers={"Content-Type": "application/json"},
            )
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
        must not trust it as the store key; resolve by list-back instead (#65).

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
        checked = self._check(r)
        # The create-response BODY IS NOT LOAD-BEARING. `create_and_resolve` discards
        # this return value entirely and reads the canonical id by list-back (#65), so
        # nothing downstream can be harmed by an unparseable body — but RAISING here is
        # actively destructive.
        #
        # By this line the status is 2xx (401/403/4xx die in `_check`, and the 400/403
        # branches above pre-empt it), so Hevy has ALREADY created the template. A throw
        # unwinds past `create_and_resolve`'s sync + list-back, leaving the new template
        # live in Hevy and absent from `hevy_exercise_templates` — an orphan the app then
        # reports as "Failed to create". A user who believes that message and retries
        # mints a permanent duplicate against an API with no delete.
        #
        # Observed in prod: the live create returned 2xx with a body that raised
        # `json.JSONDecodeError: Extra data: line 1 column 4 (char 3)` — the spec's
        # promised `{"id": <int>}` is not what the endpoint actually sends. So on a 2xx,
        # a bad parse is logged loudly and swallowed. This changes ONLY the success path;
        # the typed-error pre-checks above are untouched.
        #
        # Deliberately NOT generalised to the other `.json()` call sites: for the GETs the
        # body IS the payload, and tolerating a bad parse there would turn a real failure
        # into silent empty data.
        try:
            return checked.json()
        except json.JSONDecodeError:
            logger.warning(
                "Hevy create_exercise_template: 2xx with an unparseable body — the "
                "template WAS created. status=%s body=%r. Returning {} so the caller "
                "proceeds to sync + list-back rather than orphaning it.",
                checked.status_code, checked.text,
            )
            return {}
