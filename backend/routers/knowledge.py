import re
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

import models
import hevy_routine_cache
import injury_sweep
import typed_entries
from auth import get_current_user
from connectors.hevy import HevyClient
from database import get_db
from load_metrics import _local_day  # operator-local (AEST) day — Q42 single source
# `satisfies` (#312) validates against the SAME vocabularies the microcycle slot validator
# uses — imported, one definition, never re-literaled. Both are acyclic from here:
# `engine.taxonomy` imports only stdlib; `load_events_metabolic` imports only models+stdlib.
# `engine.training_phase` (which owns `_SLOT_LOAD_WINDOWS`) imports `routers.knowledge`, so
# importing IT back would cycle — hence the token `WINDOW_METABOLIC` at its own source.
from engine.taxonomy import (
    SIDE_BILATERAL, SIDE_LEFT, SIDE_RIGHT, all_regions, by_key as region_by_key, capacity_tokens,
    resolve_capacity,
)
# The authority vocabulary (#227) — imported from its one definition. `engine.profile` imports
# only `models` + `engine.taxonomy`, so this is acyclic from here too.
from engine.profile import ASSERTED_BY_VALUES
from load_events_metabolic import WINDOW_METABOLIC

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

VALID_CATEGORIES = {
    "Injury History",
    "Training Background",
    "Goals",
    "Constraints",
    "Nutrition",
    "Recovery",
    "Other",
}


# ---------- schemas ----------

class KnowledgeIn(BaseModel):
    category: str
    content: str


class KnowledgeOut(BaseModel):
    id: int
    category: str
    content: str

    model_config = {"from_attributes": True}


# Through which CHANNEL did this entry arrive. A closed, declared set validated at
# write, not a comment on the column that anything could contradict.
#
# `source` answers HOW, never WHO. Authority is a separate axis and lives in
# `asserted_by` (#227, `user | engine | clinician`) and `resolved_by` (#222) --
# which is why `api` names the channel of a direct operator write rather than
# `operator` naming the writer. Adding an authority word here would make this a
# mixed axis and duplicate a field that already exists.
SOURCE_VALUES = ("onboarding", "chat", "system", "api")


# ---------- schedule_item shape (#233) ----------
#
# `schedule_item` was unvalidated free JSON, and every fault in the live data traced
# to that: prose in a documented-boolean field, quota values smuggled into `days[]`
# ("flexible", "flexible_third_day"), a `minimum_days` key invented to work around a
# missing one, and duplicate rows for one commitment because the writer minted a new
# key instead of reusing the old one.
#
# Closed set, validated at write, non-member refused -- the `validate_weekly_template`
# pattern (#221). The value is never canonicalised: what is written is what is stored.
WEEKDAYS = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)
EXPECTED_LOAD_VALUES = ("light", "moderate", "heavy", "none")  # "none" = zero-load item (#315)
TIME_OF_DAY_VALUES = ("morning", "afternoon", "evening", "unknown")

MAX_SESSIONS_PER_WEEK = 14

# Stored fields. Anything outside this set is REFUSED rather than carried -- an
# unknown key is how `minimum_days` came to exist.
SCHEDULE_ITEM_FIELDS = (
    "activity", "days", "sessions_per_week", "hard", "expected_load",
    "time_of_day", "time_range", "same_day_training", "same_day_note",
    "duration_weeks", "season_end", "supersedes", "satisfies",
    "event_date", "event_end",   # #317/Q165 — a dated one-off hard item (exclusive with `days`)
)

# Accepted at write, NEVER stored. `distinct_from` acknowledges an overlap for one
# write; it is not a relationship, so persisting it would invent a link the store
# does not model (and would then read back as an unknown key).
SCHEDULE_ITEM_WRITE_ONLY_FIELDS = ("distinct_from",)

# Required keys. `expected_load` is required ON WRITE and non-null: a caller that
# does not know the load must ask rather than guess, because a fabricated load
# entering a load model is worse than a visible gap. Null remains legal IN STORE for
# rows written before this validator existed -- validation is at write, so those are
# untouched and read back unchanged.
SCHEDULE_ITEM_REQUIRED = (
    "activity", "hard", "expected_load", "time_of_day",
    "same_day_training", "duration_weeks", "season_end",
)


# `satisfies` (#312) declares which quota slot a schedule_item fills, so the plan/schedule/
# quota disagreement can be STATED on read rather than resolved by the coach guessing. EXACTLY
# ONE key, validated against the SAME vocabularies `validate_microcycle` uses — a movement
# `capacity` token or the `load_window` metabolic token. `satisfies` is OPTIONAL: absent (or
# null) = unlinked, exactly as today, and an item without it validates byte-identically.
def _validate_satisfies_capacity(v: Any) -> None:
    if resolve_capacity(v) is None:
        raise ValueError(
            f"schedule_item.satisfies.capacity: unknown capacity {v!r} -- one of {capacity_tokens()}"
        )


def _validate_satisfies_load_window(v: Any) -> None:
    if v not in (WINDOW_METABOLIC,):
        raise ValueError(
            f"schedule_item.satisfies.load_window: unknown load_window {v!r} -- one of "
            f"{[WINDOW_METABOLIC]}"
        )


def _validate_satisfies_activity(v: Any) -> None:
    # An `activity` slot's key is a declared, OPEN-vocabulary name (#315) — not a closed set like
    # capacity/load_window — so this checks only a non-empty string; the resolver matches it to a
    # declared activity slot's name at read time.
    if not isinstance(v, str) or not v.strip():
        raise ValueError("schedule_item.satisfies.activity must be a non-empty activity name")


# key -> value-validator. `activity` (#315) is the third kind, mirroring the microcycle slot kinds.
_SATISFIES_VALIDATORS = {
    "capacity": _validate_satisfies_capacity,
    "load_window": _validate_satisfies_load_window,
    "activity": _validate_satisfies_activity,
}


# Coarse time-of-day bands, minutes past local midnight, half-open [start, end).
# A schedule_item resolves to ONE occupancy interval: an explicit `time_range` wins,
# else the `time_of_day` band, else unresolvable. These bands are the data-meaning
# default the day-overlap refinement rests on (#281) -- they exist only to decide
# whether two same-day commitments share clock time, never to move a commitment.
_TIME_OF_DAY_BANDS = {
    "morning": (5 * 60, 12 * 60),      # 05:00–12:00
    "afternoon": (12 * 60, 17 * 60),   # 12:00–17:00
    "evening": (17 * 60, 22 * 60),     # 17:00–22:00
}

_HHMM_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")


def _parse_hhmm(token: str) -> int | None:
    m = _HHMM_RE.match(token)
    if not m:
        return None
    h, mm = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mm <= 59):
        return None
    return h * 60 + mm


def _time_interval(value: dict[str, Any]) -> tuple[int, int] | None:
    """Resolve a schedule_item's occupancy interval, minutes past local midnight,
    half-open [start, end). A parseable `time_range` wins ("HH:MM-HH:MM", or a lone
    "HH:MM" as the point [t, t]); otherwise the `time_of_day` band.

    Returns None when the time cannot be resolved -- `time_of_day` is "unknown" or
    absent and no parseable `time_range` is present, OR a `time_range` is present but
    does not parse. A present-but-unparseable range is deliberately NOT downgraded to
    the band: it was written to say something specific, so treating it as unknown keeps
    the acknowledgement rather than guessing a wider window. The caller reads None as
    "cannot prove disjoint" and keeps the overlap requirement -- never a silent
    double-book.
    """
    tr = value.get("time_range")
    if isinstance(tr, str) and tr.strip():
        parts = re.split(r"\s*[-–—]\s*", tr.strip(), maxsplit=1)
        if len(parts) == 2:
            a, b = _parse_hhmm(parts[0]), _parse_hhmm(parts[1])
            if a is not None and b is not None and a <= b:
                return (a, b)
        else:
            a = _parse_hhmm(parts[0])
            if a is not None:
                return (a, a)
        return None
    tod = value.get("time_of_day")
    if tod in _TIME_OF_DAY_BANDS:
        return _TIME_OF_DAY_BANDS[tod]
    return None


def _intervals_overlap(i1: tuple[int, int], i2: tuple[int, int]) -> bool:
    """Half-open interval intersection, with degenerate (point) intervals compared
    inclusively so a lone-time item ([t, t]) overlaps a band iff t falls inside it and
    two identical times still collide."""
    s1, e1 = i1
    s2, e2 = i2
    if s1 == e1 or s2 == e2:
        return max(s1, s2) <= min(e1, e2)
    return max(s1, s2) < min(e1, e2)


def _times_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """True when two same-day items may occupy the same clock time -- the refined
    occupancy trigger (#281, supersedes #233's day-alone trigger). Non-overlapping
    times (work-morning vs gym-16:30) no longer clash and save with no manual
    disambiguation. When either side's time is unresolvable the pair cannot be proven
    disjoint, so this returns True and the visible acknowledgement is kept."""
    ia, ib = _time_interval(a), _time_interval(b)
    if ia is None or ib is None:
        return True
    return _intervals_overlap(ia, ib)


class ScheduleItemOverlap(Exception):
    """A schedule_item write overlaps an active row on `days` AND on clock time,
    unacknowledged (#281 refines #233: day membership alone no longer triggers).

    Carries the overlapping rows so every caller -- HTTP, chat, a future surface --
    can render the same structured refusal instead of each inventing one.
    """

    # Machine-checkable outcome code for the write-result contract (#283). A caller
    # that flattens this to a string keeps a stable, type-derived code rather than
    # parsing the prose.
    code = "day_time_clash"

    def __init__(self, overlapping: list[dict[str, Any]]):
        self.overlapping = overlapping
        super().__init__(
            "schedule_item overlaps an active row on days; retry with "
            "`supersedes: <id>` or `distinct_from: [<id>, ...]`"
        )


class ScheduleItemInvalid(ValueError):
    """A schedule_item value fails validation. Subclasses ValueError so every existing
    `except ValueError` handler (HTTP `create_entry` -> 422, the chat channel) keeps
    catching it unchanged; it additionally carries a stable `code` so a caller can
    report WHY without parsing the message (#283). `unknown_field` is set at the
    unknown-key raise; every other shape failure defaults to `invalid_shape`.
    """

    def __init__(self, message: str, code: str = "invalid_shape"):
        self.code = code
        super().__init__(message)


def _strict_bool(value: dict[str, Any], field: str) -> None:
    # `isinstance(True, int)` is True in Python, and a truthy STRING is what the live
    # data actually carried -- ids 1 and 2 held constraint prose in `same_day_training`.
    # Both are refused here.
    if not isinstance(value[field], bool):
        raise ValueError(
            f"schedule_item.{field} must be a strict boolean, got "
            f"{type(value[field]).__name__} {value[field]!r}"
        )


def validate_schedule_item(value: Any) -> dict[str, Any]:
    """Validate a `schedule_item` value, raising ValueError with a field-located message.

    Returned UNCHANGED apart from stripping the write-only acknowledgement token, so a
    write-then-read is byte-identical for every stored field.
    """
    if not isinstance(value, dict):
        raise ValueError("schedule_item must be an object")

    known = set(SCHEDULE_ITEM_FIELDS) | set(SCHEDULE_ITEM_WRITE_ONLY_FIELDS)
    extra = sorted(set(value) - known)
    if extra:
        # `active` is the single most likely wrong guess: it is a top-level column that
        # renders on read, so a writer retiring a commitment reaches for it -- but INSIDE
        # `value`, where it is not a field. Redirect to the real deactivation lever rather
        # than only listing what `value` accepts (the observed `unknown field(s)
        # ['active']` failure, WS2 / #281).
        hint = ""
        if "active" in extra:
            hint = (
                " -- to retire a commitment do NOT put `active` in `value`; emit the "
                "block with a TOP-LEVEL `\"active\": false` beside `type`/`key`"
            )
        # The overlap refusal advises `distinct_from`, so the accepted-value list must
        # name it too (WS1#4): advertising only the stored fields told a writer a field
        # the same surface elsewhere tells it to use is unknown.
        raise ScheduleItemInvalid(
            f"schedule_item: unknown field(s) {extra} -- one of "
            f"{list(SCHEDULE_ITEM_FIELDS)} "
            f"(plus write-only {list(SCHEDULE_ITEM_WRITE_ONLY_FIELDS)}){hint}",
            code="unknown_field",
        )

    missing = [f for f in SCHEDULE_ITEM_REQUIRED if f not in value]
    if missing:
        raise ValueError(f"schedule_item: missing required field(s) {missing}")

    if not isinstance(value["activity"], str) or not value["activity"].strip():
        raise ValueError("schedule_item.activity must be a non-empty string")

    # WHEN it happens: a day list, a weekly count, or both — OR a dated one-off (`event_date`,
    # #317/Q165). A dated one-off names specific CALENDAR dates, so it is mutually exclusive with
    # weekday recurrence (`days`/`sessions_per_week`): a commitment is one or the other.
    has_days = "days" in value and value["days"] is not None
    has_count = "sessions_per_week" in value and value["sessions_per_week"] is not None
    has_event = value.get("event_date") is not None
    if has_event and (has_days or has_count):
        raise ValueError(
            "schedule_item: `event_date` (a dated one-off) is mutually exclusive with `days` / "
            "`sessions_per_week` (weekday recurrence) — a commitment is one or the other"
        )
    if not has_days and not has_count and not has_event:
        raise ValueError(
            "schedule_item: at least one of `days`, `sessions_per_week`, or `event_date` is required"
        )

    if has_days:
        days = value["days"]
        if not isinstance(days, list) or not days:
            raise ValueError("schedule_item.days must be a non-empty list")
        seen: set[str] = set()
        for i, d in enumerate(days):
            if not isinstance(d, str):
                raise ValueError(f"schedule_item.days[{i}] must be a string")
            if d not in WEEKDAYS:
                # `flexible` and `flexible_third_day` landed here in live data; they
                # are a COUNT, not a day, and `sessions_per_week` is where they belong.
                raise ValueError(
                    f"schedule_item.days[{i}]: unknown weekday {d!r} -- "
                    f"one of {list(WEEKDAYS)} (a frequency belongs in "
                    f"`sessions_per_week`)"
                )
            if d in seen:
                raise ValueError(f"schedule_item.days[{i}]: duplicate weekday {d!r}")
            seen.add(d)

    if has_count:
        spw = value["sessions_per_week"]
        if not isinstance(spw, int) or isinstance(spw, bool):
            raise ValueError("schedule_item.sessions_per_week must be an integer")
        if not 1 <= spw <= MAX_SESSIONS_PER_WEEK:
            raise ValueError(
                f"schedule_item.sessions_per_week must be between 1 and "
                f"{MAX_SESSIONS_PER_WEEK}, got {spw}"
            )

    _strict_bool(value, "hard")
    _strict_bool(value, "same_day_training")

    # `hard` is a SCHEDULING fact (immovable in the calendar); `expected_load` is a
    # COST fact. Saturday rugby and Thursday set piece are both hard, and only one
    # wants the day before scaled back -- which is why these are two axes, not one.
    if value["expected_load"] not in EXPECTED_LOAD_VALUES:
        raise ValueError(
            f"schedule_item.expected_load: {value['expected_load']!r} is not one of "
            f"{list(EXPECTED_LOAD_VALUES)} -- required on write, so ask rather than "
            f"guess (null is legal only for rows predating this validator)"
        )

    if value["time_of_day"] not in TIME_OF_DAY_VALUES:
        raise ValueError(
            f"schedule_item.time_of_day: {value['time_of_day']!r} is not one of "
            f"{list(TIME_OF_DAY_VALUES)}"
        )

    if "time_range" in value and value["time_range"] is not None:
        if not isinstance(value["time_range"], str):
            raise ValueError("schedule_item.time_range must be a string or null")

    if "same_day_note" in value and value["same_day_note"] is not None:
        if not isinstance(value["same_day_note"], str):
            raise ValueError("schedule_item.same_day_note must be a string or null")

    if value["duration_weeks"] is not None:
        dw = value["duration_weeks"]
        if not isinstance(dw, int) or isinstance(dw, bool) or dw < 1:
            raise ValueError(
                "schedule_item.duration_weeks must be a positive integer or null"
            )

    if value["season_end"] is not None:
        try:
            date.fromisoformat(str(value["season_end"]))
        except ValueError:
            raise ValueError(
                f"schedule_item.season_end must be an ISO date (YYYY-MM-DD) or null, "
                f"got {value['season_end']!r}"
            ) from None

    # Dated one-off (#317/Q165): `event_date` ISO; optional `event_end` ISO on or after it.
    # `event_end` without `event_date` is meaningless.
    if has_event:
        try:
            ed = date.fromisoformat(str(value["event_date"]))
        except ValueError:
            raise ValueError(
                f"schedule_item.event_date must be an ISO date (YYYY-MM-DD), "
                f"got {value['event_date']!r}"
            ) from None
        if value.get("event_end") is not None:
            try:
                ee = date.fromisoformat(str(value["event_end"]))
            except ValueError:
                raise ValueError(
                    f"schedule_item.event_end must be an ISO date (YYYY-MM-DD) or null, "
                    f"got {value['event_end']!r}"
                ) from None
            if ee < ed:
                raise ValueError("schedule_item.event_end must be on or after event_date")
    elif value.get("event_end") is not None:
        raise ValueError("schedule_item.event_end requires event_date")

    if value.get("supersedes") is not None:
        if not isinstance(value["supersedes"], int) or isinstance(value["supersedes"], bool):
            raise ValueError("schedule_item.supersedes must be an integer id or null")

    if value.get("distinct_from") is not None:
        df = value["distinct_from"]
        if not isinstance(df, list) or not df:
            raise ValueError("schedule_item.distinct_from must be a non-empty list of ids")
        for i, rid in enumerate(df):
            if not isinstance(rid, int) or isinstance(rid, bool):
                raise ValueError(f"schedule_item.distinct_from[{i}] must be an integer id")

    if value.get("satisfies") is not None:
        sat = value["satisfies"]
        if not isinstance(sat, dict) or len(sat) != 1:
            raise ValueError(
                "schedule_item.satisfies must be an object with exactly one key -- one of "
                f"{list(_SATISFIES_VALIDATORS)}"
            )
        (key, val), = sat.items()
        validator = _SATISFIES_VALIDATORS.get(key)
        if validator is None:
            raise ValueError(
                f"schedule_item.satisfies: unknown key {key!r} -- one of {list(_SATISFIES_VALIDATORS)}"
            )
        validator(val)

    return value


# ---------- training_plan shape (#312) ----------
#
# The plan of record — the macro plan the coach reads every turn. Supersedes ROADMAP as the
# coach-readable home for the forward plan (#270 relocated to a store the coach can read;
# reverses nothing). EXACTLY ONE current row per user, keyed on the fixed `TRAINING_PLAN_KEY`
# so a rewrite supersedes it by key (the schedule_item same-key pattern) and predecessors are
# retained as history. The CURRENT week is NOT stored here — that is `schedule_item` +
# `load_context` + the quota window; a prose copy would be a fifth store going stale.
TRAINING_PLAN_KEY = "training_plan"
TRAINING_PLAN_FIELDS = ("macro", "revised_on", "revised_by")
REVISED_BY_VALUES = ("operator", "coach")
# Bound on the rendered-every-turn macro (~1000 tokens/turn at 4 chars/token, operator-accepted).
# The operator's reconciled core measures 3,822 chars; 2000 would cut the buffer rule, the
# sacrifice order and the knee-gate fallback — which are the point (G0 ruling 1).
MACRO_MAX_CHARS = 4000


def validate_training_plan(value: Any) -> dict[str, Any]:
    """Validate a `training_plan` value — the closed macro-plan shape. Returned UNCHANGED
    (byte-identical write→read), mirroring `validate_schedule_item` / `validate_microcycle`.

    `macro` is bounded markdown; a rejection states the MEASURED length so a caller knows how
    far over it is. `revised_on` is an ISO date; `revised_by` is `operator | coach`. The
    current week is deliberately NOT a field — see the type comment above.
    """
    if not isinstance(value, dict):
        raise ValueError("training_plan must be an object")
    extra = sorted(set(value) - set(TRAINING_PLAN_FIELDS))
    if extra:
        raise ValueError(
            f"training_plan: unknown field(s) {extra} -- one of {list(TRAINING_PLAN_FIELDS)}"
        )
    missing = [f for f in TRAINING_PLAN_FIELDS if f not in value]
    if missing:
        raise ValueError(f"training_plan: missing required field(s) {missing}")

    macro = value["macro"]
    if not isinstance(macro, str) or not macro.strip():
        raise ValueError("training_plan.macro must be a non-empty string")
    if len(macro) > MACRO_MAX_CHARS:
        raise ValueError(
            f"training_plan.macro is {len(macro)} chars, over the {MACRO_MAX_CHARS}-char bound "
            f"-- tighten the plan (the current week is not stored here)"
        )

    try:
        date.fromisoformat(str(value["revised_on"]))
    except ValueError:
        raise ValueError(
            f"training_plan.revised_on must be an ISO date (YYYY-MM-DD), got {value['revised_on']!r}"
        ) from None

    if value["revised_by"] not in REVISED_BY_VALUES:
        raise ValueError(
            f"training_plan.revised_by: {value['revised_by']!r} is not one of "
            f"{list(REVISED_BY_VALUES)}"
        )
    return value


# ---------- typed entries: constraint (#342) ----------
#
# An instruction to the engine or the coach is a `type="constraint"` row, never free text: free
# text cannot be retired or enforced. Closed shape, unknown keys refused (the #233 discipline),
# the value stored exactly as written. Two tiers make "enforced" vs "advisory" explicit:
#   * `engine`   — scoped to taxonomy `Region.key`s; `selection.is_contraindicated` reads it.
#                  Region keys are the ONLY engine vocabulary in v1 (G0 ruling D1): there is no
#                  pattern layer distinct from region keys, and the only template ids are Hevy's,
#                  which the engine never gates on. `pattern_keys` / `exercise_template_ids` are
#                  therefore refused as unknown until a pattern layer exists.
#   * `advisory` — `text`, rendered to the coach verbatim and labelled advisory; no engine effect.
# Every constraint carries an exit (≥1 of on_date / on_condition / with_parent) AND a
# `review_by` — the pawl on the add-easy/remove-hard ratchet. Nothing lifts one automatically
# (#223): an exit is surfaced for the operator, who retires the row via its resolve route.
#
# `status` proposed → confirmed is ONE path only: `POST /knowledge/constraints/{id}/confirm`.
# A chat write is always `proposed` with `asserted_by: null` (G0 R5). Only `active=True AND
# status="confirmed"` rows are read by anything.
TYPED_ENTRY_TYPES = ("constraint", "finding")

CONSTRAINT_FIELDS = (
    "scope", "kind", "parent_key", "exit", "review_by", "status", "asserted_by", "detail",
)
# `parent_key` and `detail` are optional (absent == null). `asserted_by` is REQUIRED as a key but
# may be null while `proposed` — the writer states "no authority yet" rather than omitting it.
CONSTRAINT_REQUIRED = ("scope", "kind", "exit", "review_by", "status", "asserted_by")
CONSTRAINT_SCOPE_FIELDS = ("tier", "region_keys", "side", "text")
# `side` (G2 ruling 1): engine tier only, optional, absent == bilateral; matched by the engine's own
# `selection._side_conflict`. A right-shoulder constraint must not block the clean left shoulder.
CONSTRAINT_SIDES = (SIDE_LEFT, SIDE_RIGHT, SIDE_BILATERAL)
CONSTRAINT_TIERS = ("engine", "advisory")
CONSTRAINT_KINDS = ("block", "cap", "caution")
# G2 ruling 2: the engine tier is `block` ONLY in v1. `cap` is a load ceiling and the engine has no
# dose seam to enforce one (Q106 / the Banister dosing wire is unbuilt) — an engine cap would
# silently become a block. `caution` through a boolean `is_contraindicated` (#72: it stays boolean)
# is a block with a softer name. Both remain advisory-tier kinds.
CONSTRAINT_ENGINE_KINDS = ("block",)
CONSTRAINT_EXIT_FIELDS = ("on_date", "on_condition", "with_parent")
CONSTRAINT_STATUS_VALUES = ("proposed", "confirmed")

# Stamped by a route, never written (G1 ruling 2): `confirmed_on` by `/confirm`, `resolution` (the
# #223 block — `resolved_on` / `basis` / `resolved_by`, the field names injuries already carry) by
# `/resolve` and `/retract`. A writer supplying one would be forging the route's record.
TYPED_STAMPED_FIELDS = ("confirmed_on", "resolution")
# Stamped by the CHAT CHANNEL when absent (the #342 chat-channel rule, #230 pattern): a chat write is
# a proposal with no authority. One definition for the stamping (`routers.chat`) and the coach's
# write-shape docs (`context_builder`), so the prompt can never tell the model to send them.
TYPED_CHAT_DEFAULTS = {"status": "proposed", "asserted_by": None}
TYPED_CHAT_OMITTED_FIELDS = tuple(TYPED_CHAT_DEFAULTS)


def _iso_date(value: Any, where: str) -> None:
    try:
        date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"{where} must be an ISO date (YYYY-MM-DD), got {value!r}") from None
    if not isinstance(value, str):
        raise ValueError(f"{where} must be an ISO date string (YYYY-MM-DD), got {value!r}")


def _nonempty_str(value: Any, where: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where} must be a non-empty string")


def _closed_keys(obj: Any, fields: tuple[str, ...], where: str) -> None:
    if not isinstance(obj, dict):
        raise ValueError(f"{where} must be an object")
    extra = sorted(set(obj) - set(fields))
    if extra:
        raise ValueError(f"{where}: unknown field(s) {extra} -- one of {list(fields)}")


def _validate_asserted_by(value: dict[str, Any], label: str, confirmed_statuses: tuple[str, ...]) -> None:
    """`asserted_by` is the #227 authority tier. Null is legal only while the row is not yet
    confirmed (a chat proposal carries no authority until the operator stamps one)."""
    ab = value["asserted_by"]
    if ab is None:
        if value["status"] in confirmed_statuses:
            raise ValueError(
                f"{label}.asserted_by is required once status is {value['status']!r} -- one of "
                f"{list(ASSERTED_BY_VALUES)}"
            )
        return
    if ab not in ASSERTED_BY_VALUES:
        raise ValueError(
            f"{label}.asserted_by: {ab!r} is not one of {list(ASSERTED_BY_VALUES)} (or null while proposed)"
        )


def _refuse_stamped(value: Any, label: str) -> None:
    if isinstance(value, dict):
        stamped = sorted(set(value) & set(TYPED_STAMPED_FIELDS))
        if stamped:
            raise ValueError(
                f"{label}: {stamped} is stamped by its route (/confirm, /resolve, /retract), "
                f"never written"
            )


def validate_constraint(value: Any) -> dict[str, Any]:
    """Validate a `constraint` value — shape only, no DB (the parent / chat / transition rules
    are `_validate_typed_write`'s). Returned UNCHANGED (byte-identical write→read)."""
    _refuse_stamped(value, "constraint")
    _closed_keys(value, CONSTRAINT_FIELDS, "constraint")
    missing = [f for f in CONSTRAINT_REQUIRED if f not in value]
    if missing:
        raise ValueError(f"constraint: missing required field(s) {missing}")

    scope = value["scope"]
    _closed_keys(scope, CONSTRAINT_SCOPE_FIELDS, "constraint.scope")
    tier = scope.get("tier")
    if tier not in CONSTRAINT_TIERS:
        raise ValueError(f"constraint.scope.tier: {tier!r} is not one of {list(CONSTRAINT_TIERS)}")
    if tier == "engine":
        keys = scope.get("region_keys")
        if not isinstance(keys, list) or not keys:
            raise ValueError(
                "constraint.scope: an engine-tier constraint needs >=1 scoping key "
                "(`region_keys`, a non-empty list of taxonomy region keys)"
            )
        unknown = [k for k in keys if not isinstance(k, str) or region_by_key(k) is None]
        if unknown:
            # Names the VALID set: the coach's prompt carries no region list (Q185 ruling), so this
            # message — handed back verbatim by the bounded in-turn retry — is where it learns them.
            valid = [r.key for r in all_regions()]
            raise ValueError(
                f"constraint.scope.region_keys: unknown region key(s) {unknown} -- valid keys: {valid}"
            )
        if len(set(keys)) != len(keys):
            raise ValueError("constraint.scope.region_keys must not repeat a key")
        if "side" in scope and scope["side"] not in CONSTRAINT_SIDES:
            raise ValueError(
                f"constraint.scope.side: {scope['side']!r} is not one of {list(CONSTRAINT_SIDES)} "
                f"(absent = bilateral)"
            )
        if "text" in scope and scope["text"] is not None:
            _nonempty_str(scope["text"], "constraint.scope.text")
    else:
        # Advisory: the instruction itself, rendered verbatim. No scoping keys — an advisory row
        # carrying region keys would read as enforced when nothing enforces it.
        for k in ("region_keys", "side"):
            if k in scope:
                raise ValueError(
                    f"constraint.scope.{k} is engine-tier only -- an advisory constraint has no "
                    f"engine effect, so it carries no scoping keys (state the side in its text)"
                )
        if "text" not in scope:
            raise ValueError("constraint.scope.text is required for an advisory constraint")
        _nonempty_str(scope["text"], "constraint.scope.text")

    if value["kind"] not in CONSTRAINT_KINDS:
        raise ValueError(f"constraint.kind: {value['kind']!r} is not one of {list(CONSTRAINT_KINDS)}")
    if tier == "engine" and value["kind"] not in CONSTRAINT_ENGINE_KINDS:
        raise ValueError(
            f"constraint.kind {value['kind']!r} is advisory-tier only -- the engine enforces "
            f"{list(CONSTRAINT_ENGINE_KINDS)} in v1 (no dose seam for a cap; a boolean gate cannot "
            f"express a caution)"
        )

    parent_key = value.get("parent_key")
    if parent_key is not None:
        _nonempty_str(parent_key, "constraint.parent_key")

    exit_ = value["exit"]
    _closed_keys(exit_, CONSTRAINT_EXIT_FIELDS, "constraint.exit")
    if exit_.get("on_date") is not None:
        _iso_date(exit_["on_date"], "constraint.exit.on_date")
    if exit_.get("on_condition") is not None:
        _nonempty_str(exit_["on_condition"], "constraint.exit.on_condition")
    with_parent = exit_.get("with_parent")
    if with_parent is not None and not isinstance(with_parent, bool):
        raise ValueError(f"constraint.exit.with_parent must be a strict boolean, got {with_parent!r}")
    if exit_.get("on_date") is None and exit_.get("on_condition") is None and with_parent is not True:
        raise ValueError(
            "constraint.exit: at least one exit is required -- on_date, on_condition, or "
            "with_parent: true. A constraint that cannot end is the ratchet this type exists to stop"
        )
    if with_parent is True and parent_key is None:
        raise ValueError("constraint.exit.with_parent: true requires a parent_key")

    _iso_date(value["review_by"], "constraint.review_by")

    if value["status"] not in CONSTRAINT_STATUS_VALUES:
        raise ValueError(
            f"constraint.status: {value['status']!r} is not one of {list(CONSTRAINT_STATUS_VALUES)}"
        )
    _validate_asserted_by(value, "constraint", ("confirmed",))

    if value.get("detail") is not None and not isinstance(value["detail"], str):
        raise ValueError("constraint.detail must be a string or null")
    return value


# ---------- typed entries: finding (#343) ----------
#
# An interpretation is a `type="finding"` row: a statement with an `as_of`, a basis and a status,
# optionally parented to any entry (G0 R1 — separate rows, not nested in the injury value). Evidence
# cites READ DOORS and canonical ids only (Q22): never a Hevy template id or a source-native id.
# `derived_from_labs: true` marks an interpretation of lab results; it is held behind the #60
# firewall wherever it would render (the coach never interprets a lab result — G0 D2).
#
# Status (G1 ruling 3): a write may carry `proposed | open | confirmed`. `confirmed` is reached
# from a proposal only via `/confirm`; `retracted` only via `/retract`; `superseded` only by a
# same-key rewrite, which stamps it on the replaced row alongside `superseded_by`. Chat writes are
# `proposed` and chat may never promote one (proposed → open is an operator write). Readers render
# `open` and `confirmed`; `proposed` never.
FINDING_FIELDS = (
    "statement", "domain", "status", "parent_key", "as_of", "basis",
    "marker_status", "derived_from_labs", "review_by", "asserted_by",
)
FINDING_REQUIRED = ("statement", "domain", "status", "as_of", "basis", "derived_from_labs", "asserted_by")
FINDING_DOMAINS = ("injury", "clinical", "training", "analysis")
FINDING_STATUS_VALUES = ("proposed", "open", "confirmed", "retracted", "superseded")
FINDING_WRITE_STATUSES = ("proposed", "open", "confirmed")
FINDING_BASIS_FIELDS = ("text", "evidence")
FINDING_EVIDENCE_FIELDS = ("door", "ref")
# The canonical read doors (Q22) an evidence ref may cite. A source-native store is not a door.
FINDING_EVIDENCE_DOORS = ("counted_workouts", "arbitrated_sessions", "lab_results", "document")
MARKER_STATUS_VALUES = ("provocative", "clear", "untested")   # Q20's three-valued status


def validate_finding(value: Any) -> dict[str, Any]:
    """Validate a `finding` value — shape only, no DB. Returned UNCHANGED."""
    _refuse_stamped(value, "finding")
    _closed_keys(value, FINDING_FIELDS, "finding")
    missing = [f for f in FINDING_REQUIRED if f not in value]
    if missing:
        raise ValueError(f"finding: missing required field(s) {missing}")

    _nonempty_str(value["statement"], "finding.statement")
    if value["domain"] not in FINDING_DOMAINS:
        raise ValueError(f"finding.domain: {value['domain']!r} is not one of {list(FINDING_DOMAINS)}")

    st = value["status"]
    if st not in FINDING_STATUS_VALUES:
        raise ValueError(f"finding.status: {st!r} is not one of {list(FINDING_STATUS_VALUES)}")
    if st not in FINDING_WRITE_STATUSES:
        raise ValueError(
            f"finding.status {st!r} is never written -- 'retracted' is POST /knowledge/findings/"
            f"{{id}}/retract; 'superseded' is stamped when a same-key rewrite replaces the row"
        )

    if value.get("parent_key") is not None:
        _nonempty_str(value["parent_key"], "finding.parent_key")
    _iso_date(value["as_of"], "finding.as_of")

    basis = value["basis"]
    _closed_keys(basis, FINDING_BASIS_FIELDS, "finding.basis")
    if basis.get("text") is not None:
        _nonempty_str(basis["text"], "finding.basis.text")
    evidence = basis.get("evidence")
    if evidence is not None:
        if not isinstance(evidence, list):
            raise ValueError("finding.basis.evidence must be a list")
        for i, ev in enumerate(evidence):
            _closed_keys(ev, FINDING_EVIDENCE_FIELDS, f"finding.basis.evidence[{i}]")
            if ev.get("door") not in FINDING_EVIDENCE_DOORS:
                raise ValueError(
                    f"finding.basis.evidence[{i}].door: {ev.get('door')!r} is not a canonical read "
                    f"door -- one of {list(FINDING_EVIDENCE_DOORS)} (Q22)"
                )
            _nonempty_str(ev.get("ref"), f"finding.basis.evidence[{i}].ref")
    if basis.get("text") is None and not evidence:
        raise ValueError("finding.basis needs text or >=1 evidence ref -- a finding states its grounds")

    ms = value.get("marker_status")
    if ms is not None and ms not in MARKER_STATUS_VALUES:
        raise ValueError(f"finding.marker_status: {ms!r} is not one of {list(MARKER_STATUS_VALUES)}")
    if not isinstance(value["derived_from_labs"], bool):
        raise ValueError(
            f"finding.derived_from_labs must be a strict boolean, got {value['derived_from_labs']!r}"
        )
    if value.get("review_by") is not None:
        _iso_date(value["review_by"], "finding.review_by")
    # `open` is an operator's standing hypothesis, so it carries an authority like `confirmed` does.
    _validate_asserted_by(value, "finding", ("open", "confirmed"))
    return value


# ---------- appointment (#345 — appointment brief v1) ----------
#
# A `type="appointment"` row is the OPERATOR'S PLANNING DATA for one clinical appointment — who, when,
# which injuries it is about, and the asks to leave with. It is not a bodily assertion, so it has no
# proposed/confirm gate and no `asserted_by`: the operator (or chat) writes it as it is. The brief
# (`appointment_brief.build_appointment_brief`) is DERIVED from it plus the ledger on every read and
# is never stored.
#
# `kind` picks the brief's default section list and audience (Amendment 1): the row may add or drop
# sections; assembly builds each one from the same module set. `status` planned → attended → closed;
# chat writes `planned` only and may not rewrite or retire a row past it (`attended` / `closed` are
# operator writes — `POST /knowledge/entry` with `source: "api"`).
APPOINTMENT_FIELDS = (
    "clinician", "practice", "at", "kind", "audience", "since", "scope", "asks", "logistics",
    "sections", "request", "status", "detail",
)
APPOINTMENT_REQUIRED = ("clinician", "at", "kind", "scope", "status")
APPOINTMENT_KINDS = ("intro", "follow_up", "request")
APPOINTMENT_AUDIENCES = ("operator", "clinician")
APPOINTMENT_STATUS_VALUES = ("planned", "attended", "closed")
APPOINTMENT_SCOPE_FIELDS = ("parent_keys",)
APPOINTMENT_ASK_FIELDS = ("id", "text", "priority", "resolves", "options")
APPOINTMENT_ASK_REQUIRED = ("id", "text", "priority")
APPOINTMENT_RESOLVES_FIELDS = ("entry_key", "note")
APPOINTMENT_OPTION_FIELDS = ("option", "implication")
APPOINTMENT_SECTIONS_FIELDS = ("add", "drop")
APPOINTMENT_REQUEST_FIELDS = ("ask", "justification", "evidence", "alternatives")
APPOINTMENT_REQUEST_REQUIRED = ("ask", "justification")
# The section modules, in no particular order — a kind's list (below) is the order.
APPOINTMENT_MODULES = (
    "header", "leave_with", "asks", "options_prep", "since", "changes_vs_history",
    "current_constraints", "background", "imaging_timeline", "request", "logistics",
)
APPOINTMENT_DEFAULT_SECTIONS = {
    "follow_up": ("header", "leave_with", "since", "changes_vs_history", "asks", "options_prep",
                  "current_constraints", "logistics"),
    "intro": ("header", "background", "imaging_timeline", "current_constraints", "asks", "logistics"),
    "request": ("header", "request", "leave_with", "asks", "options_prep", "logistics"),
}
APPOINTMENT_DEFAULT_AUDIENCE = {"follow_up": "operator", "intro": "clinician", "request": "operator"}
# `since` bounds "since last visit"; required where the kind's point is what changed.
APPOINTMENT_SINCE_REQUIRED_KINDS = ("follow_up",)
# Brisbane has no DST: an offset, when given, can only be this one.
APPOINTMENT_AT_OFFSET = "+10:00"
# Stamped by the chat channel when absent (the #342 pattern): a chat write is a plan, never a record
# that the appointment happened.
APPOINTMENT_CHAT_DEFAULTS = {"status": "planned"}


def _str_or_null(value: Any, where: str) -> None:
    if value is not None:
        _nonempty_str(value, where)


def _str_list(value: Any, where: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{where} must be a list of strings")
    for i, s in enumerate(value):
        _nonempty_str(s, f"{where}[{i}]")


def _validate_appointment_at(value: Any) -> None:
    if not isinstance(value, str):
        raise ValueError(f"appointment.at must be an ISO datetime string, got {value!r}")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(
            f"appointment.at must be an ISO datetime (YYYY-MM-DDTHH:MM, Brisbane local), got {value!r}"
        ) from None
    if "T" not in value:
        raise ValueError(f"appointment.at needs a time (YYYY-MM-DDTHH:MM), got {value!r}")
    if dt.tzinfo is not None and dt.strftime("%z") != APPOINTMENT_AT_OFFSET.replace(":", ""):
        raise ValueError(
            f"appointment.at is Brisbane local time: no offset, or {APPOINTMENT_AT_OFFSET}; got {value!r}"
        )


def validate_appointment(value: Any) -> dict[str, Any]:
    """Validate an `appointment` value — shape only, no DB (the parent / chat / expiry rules are
    `_validate_appointment_write`'s). Returned UNCHANGED (stored verbatim)."""
    _closed_keys(value, APPOINTMENT_FIELDS, "appointment")
    missing = [f for f in APPOINTMENT_REQUIRED if f not in value]
    if missing:
        raise ValueError(f"appointment: missing required field(s) {missing}")

    _nonempty_str(value["clinician"], "appointment.clinician")
    _str_or_null(value.get("practice"), "appointment.practice")
    _validate_appointment_at(value["at"])

    kind = value["kind"]
    if kind not in APPOINTMENT_KINDS:
        raise ValueError(f"appointment.kind: {kind!r} is not one of {list(APPOINTMENT_KINDS)}")
    if value.get("audience") is not None and value["audience"] not in APPOINTMENT_AUDIENCES:
        raise ValueError(
            f"appointment.audience: {value['audience']!r} is not one of {list(APPOINTMENT_AUDIENCES)} "
            f"(absent = the kind's default)"
        )

    if value.get("since") is not None:
        _iso_date(value["since"], "appointment.since")
    elif kind in APPOINTMENT_SINCE_REQUIRED_KINDS:
        raise ValueError(f"appointment.since is required for kind {kind!r} -- the 'since last visit' start")

    scope = value["scope"]
    _closed_keys(scope, APPOINTMENT_SCOPE_FIELDS, "appointment.scope")
    pks = scope.get("parent_keys")
    if not isinstance(pks, list) or not pks:
        raise ValueError(
            "appointment.scope.parent_keys must be a non-empty list of injury keys -- the brief "
            "reads only what these injuries parent"
        )
    for i, pk in enumerate(pks):
        _nonempty_str(pk, f"appointment.scope.parent_keys[{i}]")
    if len(set(pks)) != len(pks):
        raise ValueError("appointment.scope.parent_keys must not repeat a key")

    asks = value.get("asks", [])
    if not isinstance(asks, list):
        raise ValueError("appointment.asks must be a list")
    seen_ids: set[str] = set()
    for i, ask in enumerate(asks):
        where = f"appointment.asks[{i}]"
        _closed_keys(ask, APPOINTMENT_ASK_FIELDS, where)
        miss = [f for f in APPOINTMENT_ASK_REQUIRED if f not in ask]
        if miss:
            raise ValueError(f"{where}: missing required field(s) {miss}")
        _nonempty_str(ask["id"], f"{where}.id")
        if ask["id"] in seen_ids:
            raise ValueError(f"{where}.id {ask['id']!r} repeats -- ask ids are unique per appointment")
        seen_ids.add(ask["id"])
        _nonempty_str(ask["text"], f"{where}.text")
        p = ask["priority"]
        if isinstance(p, bool) or not isinstance(p, int) or not 1 <= p <= len(asks):
            raise ValueError(f"{where}.priority must be an integer 1..{len(asks)} (1 = first), got {p!r}")
        if ask.get("resolves") is not None:
            _closed_keys(ask["resolves"], APPOINTMENT_RESOLVES_FIELDS, f"{where}.resolves")
            _str_or_null(ask["resolves"].get("entry_key"), f"{where}.resolves.entry_key")
            _str_or_null(ask["resolves"].get("note"), f"{where}.resolves.note")
        if ask.get("options") is not None:
            if not isinstance(ask["options"], list):
                raise ValueError(f"{where}.options must be a list")
            for j, opt in enumerate(ask["options"]):
                _closed_keys(opt, APPOINTMENT_OPTION_FIELDS, f"{where}.options[{j}]")
                for f in APPOINTMENT_OPTION_FIELDS:
                    _nonempty_str(opt.get(f), f"{where}.options[{j}].{f}")

    if value.get("logistics") is not None:
        _str_list(value["logistics"], "appointment.logistics")

    if value.get("sections") is not None:
        sec = value["sections"]
        _closed_keys(sec, APPOINTMENT_SECTIONS_FIELDS, "appointment.sections")
        for f in APPOINTMENT_SECTIONS_FIELDS:
            mods = sec.get(f, [])
            if not isinstance(mods, list):
                raise ValueError(f"appointment.sections.{f} must be a list of section modules")
            unknown = [m for m in mods if m not in APPOINTMENT_MODULES]
            if unknown:
                raise ValueError(
                    f"appointment.sections.{f}: unknown module(s) {unknown} -- one of {list(APPOINTMENT_MODULES)}"
                )
        both = sorted(set(sec.get("add", [])) & set(sec.get("drop", [])))
        if both:
            raise ValueError(f"appointment.sections: {both} is both added and dropped")

    req = value.get("request")
    if kind == "request":
        if req is None:
            raise ValueError("appointment.request is required for kind 'request' -- the ask and its justification")
        _closed_keys(req, APPOINTMENT_REQUEST_FIELDS, "appointment.request")
        miss = [f for f in APPOINTMENT_REQUEST_REQUIRED if f not in req]
        if miss:
            raise ValueError(f"appointment.request: missing required field(s) {miss}")
        _nonempty_str(req["ask"], "appointment.request.ask")
        _nonempty_str(req["justification"], "appointment.request.justification")
        for i, ev in enumerate(req.get("evidence") or []):
            _closed_keys(ev, FINDING_EVIDENCE_FIELDS, f"appointment.request.evidence[{i}]")
            if ev.get("door") not in FINDING_EVIDENCE_DOORS:
                raise ValueError(
                    f"appointment.request.evidence[{i}].door: {ev.get('door')!r} is not a canonical read "
                    f"door -- one of {list(FINDING_EVIDENCE_DOORS)} (Q22)"
                )
            _nonempty_str(ev.get("ref"), f"appointment.request.evidence[{i}].ref")
        if req.get("alternatives") is not None:
            _str_list(req["alternatives"], "appointment.request.alternatives")
    elif req is not None:
        raise ValueError(f"appointment.request is only for kind 'request' (this is {kind!r})")

    if value["status"] not in APPOINTMENT_STATUS_VALUES:
        raise ValueError(
            f"appointment.status: {value['status']!r} is not one of {list(APPOINTMENT_STATUS_VALUES)}"
        )
    _str_or_null(value.get("detail"), "appointment.detail")
    return value


# Per-type shape validators for the typed entries. The DB-aware rules shared by both types live
# in `_validate_typed_write`.
_TYPED_VALIDATORS = {
    "constraint": validate_constraint,
    "finding": validate_finding,
}

# The statuses a CHAT write may carry, and the statuses reachable only through an explicit
# operator route (never by a plain upsert). Keyed by type.
_TYPED_CHAT_STATUS = {"constraint": "proposed", "finding": "proposed"}
_TYPED_CONFIRMED = {"constraint": ("confirmed",), "finding": ("confirmed",)}


class TypedEntryRefused(ValueError):
    """A write refused by a typed-entry lifecycle rule (not a shape fault). Subclasses
    ValueError so the HTTP 422 and chat refusal paths catch it unchanged; carries a stable
    `code` for the #283 write-result contract."""

    def __init__(self, message: str, code: str):
        self.code = code
        super().__init__(message)


def _is_resolved_injury(row: models.UserKnowledgeEntry | None) -> bool:
    """An injury row retired by RESOLUTION (Q192): inactive, no successor, a `resolution` block
    with its date, and no non-terminal or rejected status. Reads the row's state, not `active`
    alone — a superseded or proposed row is inactive too, and is not a resolved fact."""
    if row is None or row.type != "injury" or row.active or row.superseded_by is not None:
        return False
    v = row.value or {}
    if v.get("status") in ("proposed", "rejected", "superseded", "retracted"):
        return False
    return typed_entries.parse_date((v.get("resolution") or {}).get("resolved_on")) is not None


def _validate_typed_write(
    user_id: int,
    entry_in: "KnowledgeEntryIn",
    existing: models.UserKnowledgeEntry | None,
    db: Session,
) -> None:
    """The DB-aware rules for a `constraint` / `finding` write, after the shape validator.

    * `expires_at` must be null — the exit is the lifecycle, and `expire-stale` would otherwise
      retire the row silently with no operator in the loop (#223).
    * `parent_key` (optional, ANY entry type — G0 R3) must name one of THIS user's ACTIVE rows,
      and never the row itself. One exception (Q192 ruling): a CONSTRAINT may name an injury
      whose current row is RESOLVED, only when its `exit.with_parent` is not true — that shape
      is `parent_resolved_survives` (G5 ruling 1) written directly. Superseded, proposed or
      missing parents stay refused, and a finding still needs an active parent.
    * A chat write is `proposed` with `asserted_by: null` (G0 R5) — refused otherwise, never
      coerced (the value is stored as written).
    * proposed → confirmed has ONE path, the type's `/confirm` route: an upsert carrying a
      confirmed status over an active not-yet-confirmed row of the same key is refused.
    """
    t = entry_in.type
    value = entry_in.value
    if entry_in.expires_at is not None:
        raise TypedEntryRefused(
            f"{t}.expires_at must be null -- a {t} ends through its own lifecycle, never a silent expiry",
            "expires_at_refused",
        )

    parent_key = value.get("parent_key")
    if parent_key is not None:
        if parent_key == entry_in.key:
            raise TypedEntryRefused(f"{t}.parent_key must not name the entry itself", "invalid_parent")
        rows = (
            db.query(models.UserKnowledgeEntry)
            .filter_by(user_id=user_id, key=parent_key)
            .all()
        )
        if not any(r.active for r in rows):
            current = max(rows, key=lambda r: r.id, default=None)
            if t != "constraint" or not _is_resolved_injury(current):
                raise TypedEntryRefused(
                    f"{t}.parent_key {parent_key!r} names no active entry for this user"
                    + (" (a constraint may also name a resolved injury)" if t == "constraint" else ""),
                    "invalid_parent",
                )
            if (value.get("exit") or {}).get("with_parent") is True:
                raise TypedEntryRefused(
                    f"{t}.parent_key {parent_key!r} names a RESOLVED injury -- exit.with_parent: true "
                    f"would make this constraint born already ended; drop with_parent and end it by "
                    f"on_date / on_condition",
                    "invalid_parent",
                )

    if entry_in.source == "chat":
        if value.get("status") != _TYPED_CHAT_STATUS[t] or value.get("asserted_by") is not None:
            raise TypedEntryRefused(
                f"a {t} written from chat is a PROPOSAL: status must be "
                f"{_TYPED_CHAT_STATUS[t]!r} and asserted_by null -- the operator confirms it "
                f"via POST /knowledge/{t}s/{{id}}/confirm",
                "proposal_only",
            )
    elif value.get("status") in _TYPED_CONFIRMED[t] and existing is not None \
            and existing.type == t \
            and (existing.value or {}).get("status") not in _TYPED_CONFIRMED[t]:
        raise TypedEntryRefused(
            f"{t} {entry_in.key!r} is {(existing.value or {}).get('status')!r} -- confirming it is "
            f"POST /knowledge/{t}s/{existing.id}/confirm, never an upsert",
            "confirm_via_route",
        )


def _typed_supersede_guard(entry_in: "KnowledgeEntryIn", existing: models.UserKnowledgeEntry | None) -> None:
    """Same-key supersession rules whenever a typed entry is on EITHER side (G0 D4).

    Supersede-by-key matches on (user, key) alone, so without this a constraint reusing an
    injury's key would silently retire the injury (or the reverse). And a chat write must never
    retire an operator-confirmed row by rewriting its key — R5's proposal gate would otherwise
    be a side door. Rows with no typed entry on either side are untouched (byte-identical)."""
    if existing is None:
        return
    if existing.type != entry_in.type and (
        existing.type in _KEY_GUARDED_TYPES or entry_in.type in _KEY_GUARDED_TYPES
    ):
        raise TypedEntryRefused(
            f"key {entry_in.key!r} is held by an active {existing.type!r} entry -- a "
            f"{entry_in.type!r} write must use its own key",
            "key_collision",
        )
    if entry_in.source == "chat" and chat_may_not_retire(existing) and existing.type == "appointment":
        raise TypedEntryRefused(
            f"appointment {entry_in.key!r} is {(existing.value or {}).get('status')!r} -- chat edits "
            f"only a 'planned' appointment; past that it is the operator's record",
            "operator_only",
        )
    if entry_in.source == "chat" and chat_may_not_retire(existing):
        raise TypedEntryRefused(
            f"{existing.type} {entry_in.key!r} is {(existing.value or {}).get('status')!r} -- chat may "
            f"only rewrite its own proposals; the operator retires it via its resolve route",
            "operator_only",
        )


def chat_may_not_retire(row: models.UserKnowledgeEntry) -> bool:
    """A typed entry past `proposed` is operator territory: chat may neither supersede nor
    deactivate it (G0 D4). Shared by the upsert guard and the chat `active: false` path. An
    appointment past `planned` is the same: it records that the visit happened, which is the
    operator's to write."""
    if row.type == "appointment":
        return (row.value or {}).get("status") != "planned"
    return row.type in TYPED_ENTRY_TYPES and (row.value or {}).get("status") != "proposed"


# Types whose key may not be taken by a row of another type (either direction): same-key supersede
# would otherwise silently retire one with the other.
_KEY_GUARDED_TYPES = TYPED_ENTRY_TYPES + ("appointment",)


def _validate_appointment_write(
    user_id: int,
    entry_in: "KnowledgeEntryIn",
    db: Session,
) -> None:
    """The DB-aware rules for an `appointment` write, after `validate_appointment`.

    * `expires_at` must be null — an appointment ends by its own `status`, never a silent expiry.
    * Every `scope.parent_keys` entry names one of THIS user's injury rows that is ACTIVE, or was
      RESOLVED on/after `since` (a follow-up can be about an injury cleared since the last visit).
    * A chat write is `planned` only (the chat channel stamps it when absent). Chat rewriting or
      retiring a row past `planned` is refused by `_typed_supersede_guard` via `chat_may_not_retire`.
    """
    value = entry_in.value
    if entry_in.expires_at is not None:
        raise TypedEntryRefused(
            "appointment.expires_at must be null -- an appointment ends through its status "
            "(planned → attended → closed), never a silent expiry",
            "expires_at_refused",
        )
    if entry_in.source == "chat" and value.get("status") != "planned":
        raise TypedEntryRefused(
            f"an appointment written from chat is 'planned' -- {value.get('status')!r} records that "
            f"the visit happened, which is the operator's write",
            "operator_only",
        )
    since = typed_entries.parse_date(value.get("since"))
    injuries = (
        db.query(models.UserKnowledgeEntry)
        .filter(
            models.UserKnowledgeEntry.user_id == user_id,
            models.UserKnowledgeEntry.type == "injury",
            models.UserKnowledgeEntry.key.in_(value["scope"]["parent_keys"]),
        )
        .all()
    )
    for pk in value["scope"]["parent_keys"]:
        rows = [r for r in injuries if r.key == pk]
        if any(r.active for r in rows):
            continue
        resolved_on = [
            typed_entries.parse_date(((r.value or {}).get("resolution") or {}).get("resolved_on"))
            for r in rows
        ]
        if since is not None and any(d is not None and d >= since for d in resolved_on):
            continue
        raise TypedEntryRefused(
            f"appointment.scope.parent_keys: {pk!r} names no active injury"
            + (f", nor one resolved on/after since ({since})" if since is not None
               else " (a resolved injury is in scope only with a `since` it was resolved after)"),
            "invalid_parent",
        )


class KnowledgeEntryIn(BaseModel):
    type: str
    key: str
    value: dict[str, Any]
    # No default. The default WAS the defect: four operator writes made from
    # PowerShell against this endpoint persisted as `source: "chat"` because
    # `chat` was both the fallback and the only member that could absorb them.
    # A caller that will not say how a write arrived is refused.
    source: str
    expires_at: date | None = None
    notes: str | None = None

    @field_validator("source")
    @classmethod
    def _known_source(cls, v: str) -> str:
        if v not in SOURCE_VALUES:
            raise ValueError(
                f"unknown source {v!r} -- one of {list(SOURCE_VALUES)}"
            )
        return v


class KnowledgeEntryOut(BaseModel):
    id: int
    type: str
    key: str
    value: dict[str, Any]
    source: str
    added_at: date
    expires_at: date | None
    active: bool
    notes: str | None
    # Exposed so the two terminal states stay distinguishable through the API and
    # not only in the table: a SUPERSEDED row carries the id of the statement that
    # replaced it, a RESOLVED row carries null. Both read `active=False`, so
    # without this field the history surface cannot tell them apart.
    superseded_by: int | None = None

    model_config = {"from_attributes": True}


RESOLVED_BY_VALUES = ("user", "clinician")


class ResolutionIn(BaseModel):
    """The operator's answer to "is this still true?", for any resolvable entry type.
    `basis` is mandatory and free text: a resolution with no stated grounds is the
    thing that later reads as an accident. `resolved_on` defaults to today rather than
    being required, since the common case is resolving something as of now — today is
    the operator-local (AEST) day, not Railway UTC (Q42 local-day; see `_resolve_entry`)."""
    basis: str
    resolved_by: str
    resolved_on: date | None = None


# ---------- helpers ----------

def _validate_category(category: str) -> str:
    if category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid category. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}",
        )
    return category


def _get_entry(entry_id: int, user_id: int, db: Session) -> models.UserKnowledge:
    entry = db.query(models.UserKnowledge).filter_by(id=entry_id, user_id=user_id).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return entry


def expire_stale_entries(user_id: int, db: Session) -> int:
    """Set active=False for all entries where expires_at < today. Returns count expired."""
    today = date.today()
    entries = (
        db.query(models.UserKnowledgeEntry)
        .filter(
            models.UserKnowledgeEntry.user_id == user_id,
            models.UserKnowledgeEntry.expires_at < today,
            models.UserKnowledgeEntry.active == True,
        )
        .all()
    )
    for e in entries:
        e.active = False
    if entries:
        db.commit()
    return len(entries)


def _schedule_overlap_check(
    user_id: int,
    entry_in: KnowledgeEntryIn,
    db: Session,
) -> None:
    """Refuse a schedule_item write that lands on a day AND a clock time an active row
    already holds, unless the write acknowledges every row it collides with.

    THE TRIGGER IS DAY OVERLAP AND TIME OVERLAP (#281, refining #233). #233 triggered
    on day membership ALONE, to make the live duplicate pairs visible -- but it also
    refused every genuinely distinct same-day commitment, so work(morning) and
    gym(16:30) on one weekday could not coexist without manual `supersedes`/
    `distinct_from`. The refinement keeps the anti-duplicate guarantee (a true duplicate
    shares the commitment's time, so it still collides) while letting non-overlapping
    same-day times save automatically. Matching on `activity` stays rejected for #233's
    reason: it is string equality over generated free text and fails OPEN.

    Time is compared via `_times_overlap`. When either side's time is UNRESOLVABLE
    (`time_of_day` "unknown"/absent with no parseable `time_range`) the pair cannot be
    proven disjoint, so it is treated as colliding -- the ambiguous case stays visible,
    never a silent double-book.

    Every colliding row must be accounted for, not just one of them -- acknowledging a
    single row out of three would leave the other two to duplicate silently, which is
    the hole this closes.
    """
    value = entry_in.value
    days = {d for d in (value.get("days") or []) if isinstance(d, str)}
    if not days:
        return

    acknowledged: set[int] = set(value.get("distinct_from") or [])
    if value.get("supersedes") is not None:
        acknowledged.add(value["supersedes"])

    rows = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=user_id, type="schedule_item", active=True)
        .all()
    )

    unacknowledged: list[dict[str, Any]] = []
    for row in rows:
        # A same-key rewrite supersedes its own predecessor by key below; it is not a
        # duplicate and must not be made to acknowledge itself.
        if row.key == entry_in.key or row.id in acknowledged:
            continue
        row_value = row.value or {}
        row_days = {d for d in (row_value.get("days") or []) if isinstance(d, str)}
        if (days & row_days) and _times_overlap(value, row_value):
            unacknowledged.append({
                "id": row.id,
                "activity": row_value.get("activity"),
                "days": sorted(row_days & days),
                "time_of_day": row_value.get("time_of_day"),
            })

    if unacknowledged:
        raise ScheduleItemOverlap(unacknowledged)


def _validate_training_plan_write(user_id: int, entry_in: KnowledgeEntryIn, db: Session) -> None:
    """Guard a `training_plan` write: exactly one current plan of record per user.

    Enforced by a FIXED key (`TRAINING_PLAN_KEY`) so `upsert_knowledge_entry`'s same-key
    supersede gives single-current + retained predecessor for free; a write under any other key
    is refused. Belt-and-braces: a write is also refused if an active `training_plan` already
    exists under a DIFFERENT key — a pre-existing stray would otherwise leave two current plans.
    `expires_at` must be null: the plan supersedes by rewrite and never expires, so the
    `expire-stale` sweep can never silently retire it.
    """
    if entry_in.key != TRAINING_PLAN_KEY:
        raise ValueError(
            f"training_plan.key must be {TRAINING_PLAN_KEY!r} -- exactly one plan of record per "
            f"user, keyed so a rewrite supersedes it; got {entry_in.key!r}"
        )
    if entry_in.expires_at is not None:
        raise ValueError(
            "training_plan.expires_at must be null -- the plan supersedes by rewrite and never expires"
        )
    validate_training_plan(entry_in.value)
    stray = (
        db.query(models.UserKnowledgeEntry)
        .filter(
            models.UserKnowledgeEntry.user_id == user_id,
            models.UserKnowledgeEntry.type == "training_plan",
            models.UserKnowledgeEntry.active == True,
            models.UserKnowledgeEntry.key != TRAINING_PLAN_KEY,
        )
        .first()
    )
    if stray is not None:
        raise ValueError(
            f"an active training_plan already exists under key {stray.key!r} -- resolve it before "
            f"writing a new plan of record (exactly one current plan per user)"
        )


def _stage_upsert_entry(
    user_id: int,
    entry_in: KnowledgeEntryIn,
    db: Session,
) -> models.UserKnowledgeEntry:
    """Validate + STAGE an upsert (supersede-by-key, and an explicit cross-key `supersedes`)
    WITHOUT committing — the shared core of `upsert_knowledge_entry` (which commits) and the
    phase transition (#317, which batches many writes into ONE commit so a later failure rolls the
    whole set back). One definition of the write mechanic; no fork. Returns the flushed new row."""
    stored_value = entry_in.value
    if entry_in.type == "training_plan":
        _validate_training_plan_write(user_id, entry_in, db)
    if entry_in.type == "schedule_item":
        validate_schedule_item(entry_in.value)
        _schedule_overlap_check(user_id, entry_in, db)
        # Strip the write-only acknowledgement token. It satisfied the validator for
        # this write; it is not a relationship and is not stored.
        stored_value = {
            k: v for k, v in entry_in.value.items()
            if k not in SCHEDULE_ITEM_WRITE_ONLY_FIELDS
        }
    if entry_in.type in _TYPED_VALIDATORS:
        _TYPED_VALIDATORS[entry_in.type](entry_in.value)
    if entry_in.type == "appointment":
        validate_appointment(entry_in.value)

    existing = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=user_id, key=entry_in.key, active=True)
        .first()
    )
    # Typed-entry rules run BEFORE `db.add` (#221's ordering): a refusal leaves no pending row.
    _typed_supersede_guard(entry_in, existing)
    if entry_in.type in _TYPED_VALIDATORS:
        _validate_typed_write(user_id, entry_in, existing, db)
    if entry_in.type == "appointment":
        _validate_appointment_write(user_id, entry_in, db)

    new_entry = models.UserKnowledgeEntry(
        user_id=user_id,
        type=entry_in.type,
        key=entry_in.key,
        value=stored_value,
        source=entry_in.source,
        expires_at=entry_in.expires_at,
        notes=entry_in.notes,
        active=True,
    )
    db.add(new_entry)
    db.flush()  # get new_entry.id before committing

    if existing:
        existing.superseded_by = new_entry.id
        existing.active = False
        if existing.type == "finding":
            # G1 ruling 3: the replaced finding reads `superseded` in its own value too, so a history
            # reader of the JSON alone cannot mistake it for a live status. Reassign — plain JSON.
            existing.value = {**(existing.value or {}), "status": "superseded"}

    # An explicit `supersedes` retires a row under a DIFFERENT key -- which is the
    # case the key-based supersede above cannot reach, and precisely how the duplicate
    # pairs formed. Scoped to this user's own rows: a supersedes naming someone else's
    # entry id retires nothing and reports nothing, so a probe learns nothing from it.
    superseded_id = stored_value.get("supersedes") if entry_in.type == "schedule_item" else None
    if superseded_id is not None and (existing is None or superseded_id != existing.id):
        target = (
            db.query(models.UserKnowledgeEntry)
            .filter_by(id=superseded_id, user_id=user_id, active=True)
            .first()
        )
        if target is not None:
            target.superseded_by = new_entry.id
            target.active = False

    return new_entry


def upsert_knowledge_entry(
    user_id: int,
    entry_in: KnowledgeEntryIn,
    db: Session,
) -> models.UserKnowledgeEntry:
    """Create a new entry, superseding any existing active entry with the same key.

    A `schedule_item` is validated BEFORE the session is touched (#221's ordering): a
    refused write must leave no row behind, and `db.add` runs before the commit, so a
    later raise would strand a pending INSERT for a caller sharing the session.

    Validation lives here rather than only on `POST /knowledge/entry` because this
    function is the write path for chat (`routers/chat.py`) and the health router too.
    A rejection that the chat writer never sees is a silently dropped fact, which is
    the failure this replaces -- so the check has to sit where every writer passes.
    Direct ORM construction stays unvalidated by design: that is the backfill's path,
    and validation is at write.
    """
    new_entry = _stage_upsert_entry(user_id, entry_in, db)
    db.commit()
    db.refresh(new_entry)
    return new_entry


# ---------- legacy endpoints (UserKnowledge) ----------

@router.get("", response_model=list[KnowledgeOut])
def list_knowledge(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.UserKnowledge)
        .filter_by(user_id=current_user.id)
        .order_by(models.UserKnowledge.category, models.UserKnowledge.created_at)
        .all()
    )


@router.post("", response_model=KnowledgeOut, status_code=status.HTTP_201_CREATED)
def create_knowledge(
    body: KnowledgeIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_category(body.category)
    entry = models.UserKnowledge(
        user_id=current_user.id,
        category=body.category,
        content=body.content.strip(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=KnowledgeOut)
def update_knowledge(
    entry_id: int,
    body: KnowledgeIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate_category(body.category)
    entry = _get_entry(entry_id, current_user.id, db)
    entry.category = body.category
    entry.content = body.content.strip()
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge(
    entry_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = _get_entry(entry_id, current_user.id, db)
    db.delete(entry)
    db.commit()


# ---------- structured knowledge endpoints ----------

@router.get("/schedule", response_model=list[KnowledgeEntryOut])
def get_schedule(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all active schedule_item entries for the current user."""
    return (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=current_user.id, type="schedule_item", active=True)
        .order_by(models.UserKnowledgeEntry.added_at.desc())
        .all()
    )


@router.get("/injuries", response_model=list[KnowledgeEntryOut])
def list_injuries(
    include_resolved: bool = Query(
        False,
        description=(
            "Also return inactive injury rows (resolved or superseded), so history "
            "is inspectable. Default false — active constraints only."
        ),
    ),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The user's injury entries — the read half of the resolution loop.

    Nothing can be retired that cannot first be seen: `gather_active_injuries` and
    `is_contraindicated` have consumed these rows since #72, but no endpoint listed
    them, so a healed injury kept suppressing regions with nothing to show the user
    what to retire.

    Each row's `value` is returned UNMODIFIED, so an entry's `trajectory` block (#72)
    rides along untouched — this surface reads the ledger, it does not reinterpret it.
    """
    q = db.query(models.UserKnowledgeEntry).filter_by(
        user_id=current_user.id, type="injury",
    )
    if not include_resolved:
        q = q.filter_by(active=True)
    return q.order_by(models.UserKnowledgeEntry.added_at.desc(),
                      models.UserKnowledgeEntry.id.desc()).all()


@router.get("/proposals", response_model=list[KnowledgeEntryOut])
def list_proposals(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Active PROPOSED constraints and findings — the confirm half of the proposal loop (#346).

    Chat writes typed entries as proposals only, and every reader skips `proposed`, so nothing
    showed the operator what was awaiting confirmation. This lists them for the Injuries page's
    Confirm buttons, and nothing else reads it: the readers are unchanged. A finding not
    explicitly `derived_from_labs: false` is left out (the #60 firewall) — a lab interpretation is
    never rendered here either.
    """
    rows = (
        db.query(models.UserKnowledgeEntry)
        .filter(
            models.UserKnowledgeEntry.user_id == current_user.id,
            models.UserKnowledgeEntry.type.in_(TYPED_ENTRY_TYPES),
            models.UserKnowledgeEntry.active == True,
        )
        .order_by(models.UserKnowledgeEntry.added_at.desc(), models.UserKnowledgeEntry.id.desc())
        .all()
    )
    return [
        r for r in rows
        if (r.value or {}).get("status") == "proposed"
        and (r.type != "finding" or (r.value or {}).get("derived_from_labs") is False)
    ]


@router.post("/entry", response_model=KnowledgeEntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(
    body: KnowledgeEntryIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update a structured knowledge entry (supersedes existing entry with same key).

    A refused `schedule_item` is a 422 (shape) or a 409 (unacknowledged day overlap),
    never a 500 and never a silent store. The 409 body names every overlapping row so
    the caller can retry with `supersedes` or `distinct_from` without a second lookup.
    """
    try:
        return upsert_knowledge_entry(current_user.id, body, db)
    except ScheduleItemOverlap as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "schedule_item_overlap",
                "message": str(exc),
                "overlapping": exc.overlapping,
                "resolve_with": ["supersedes", "distinct_from"],
            },
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None


@router.post("/expire-stale", status_code=status.HTTP_200_OK)
def expire_stale(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Expire all entries whose expires_at is in the past."""
    count = expire_stale_entries(current_user.id, db)
    return {"expired": count}


# Human label per resolvable type, used to build the 404/409 details. The type
# scope is the deliberate cross-type 404-leak defence (see `_resolve_entry`); the
# label keeps each route's refusals named for its own type.
_RESOLVE_LABELS = {
    "injury": "Injury entry",
    "schedule_item": "schedule_item entry",
    "constraint": "Constraint entry",
    "finding": "Finding entry",
}


def _resolve_entry(
    entry_id: int,
    body: ResolutionIn,
    entry_type: str,
    user_id: int,
    db: Session,
    terminal_status: str | None = None,
) -> models.UserKnowledgeEntry:
    """Retire one entry of `entry_type`: it is no longer true. The shared body behind
    the per-type resolve routes (injury, schedule_item, constraint) and the finding
    retract route, which also passes `terminal_status="retracted"` so the value's own
    status is stamped in the same write as the `resolution` block.

    THE TYPE SCOPE IS A DELIBERATE 404-LEAK DEFENCE. The query filters on
    `type=entry_type` as well as the caller, so a resolve route can only ever retire a
    row of its OWN type: an injury id reached through the schedule route (or the
    reverse) is a 404 that reveals nothing about whether that id exists under some
    other type, exactly as another user's id does. This is why the routes stay
    per-type and are NOT generalised into one `/entry/{id}/resolve` — the type in the
    path IS the boundary.

    RESOLUTION IS NOT SUPERSESSION. Both terminal states set `active=False`, but
    supersession names its successor in `superseded_by`; resolution has no successor,
    so `superseded_by` stays untouched (null for a first-time terminal row).

    NEVER DELETES. The row is retained with its `resolution` block — a resolved fact
    is still context for the next decision.
    """
    label = _RESOLVE_LABELS[entry_type]
    if body.resolved_by not in RESOLVED_BY_VALUES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"resolved_by must be one of: {', '.join(RESOLVED_BY_VALUES)}",
        )
    if not body.basis.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="basis is required — a resolution must state its grounds",
        )

    entry = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(id=entry_id, user_id=user_id, type=entry_type)
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
    if not entry.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{label} is already inactive — resolving twice is an error, not a no-op",
        )

    # REASSIGN, never mutate in place: the column is a plain `JSON`, not a
    # `MutableDict`, so an in-place `entry.value["resolution"] = ...` is not seen by
    # the unit of work and is silently dropped at commit. Tested by reading the row
    # back from a fresh query rather than from the in-session identity map.
    entry.value = {
        **(entry.value or {}),
        "resolution": {
            # Operator-local (AEST) day, not Railway UTC (Q42): a resolution stamped
            # late on an AEST evening must not read as the following UTC day. Mirrors
            # the training-phase ledger's `entered_on` default.
            "resolved_on": str(body.resolved_on or _local_day()),
            "basis": body.basis,
            "resolved_by": body.resolved_by,
        },
        **({"status": terminal_status} if terminal_status is not None else {}),
    }
    entry.active = False
    # `superseded_by` is deliberately left untouched — resolution has no successor.
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/injuries/{entry_id}/resolve", response_model=KnowledgeEntryOut)
def resolve_injury(
    entry_id: int,
    body: ResolutionIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retire one injury entry: it is no longer true.

    RESOLUTION IS NOT SUPERSESSION. Both terminal states set `active=False`, but
    supersession means "replaced by a newer statement about the same thing" and
    names its successor in `superseded_by`; resolution means "no longer true" and
    has no successor, so `superseded_by` stays null. Collapsing the two would read
    as a simplification later and would destroy the only signal distinguishing a
    healed injury from a re-worded one.

    ALWAYS AN EXPLICIT OPERATOR WRITE. Nothing auto-resolves — not a passing
    `resolve_by` date, not a soreness series at its exit condition, not a live
    `review` flag from `injury_trajectory.evaluate()`. That module stays
    surfacing-only (#72): it identifies candidates, this endpoint is where the
    operator puts the answer. A constraint that lifted itself would invert #72 with
    no operator in the loop. Nor is this the app clearing anyone (#133) — the app
    interprets nothing here; it records an assertion and stamps who made it.

    NEVER DELETES. The row is retained with its `resolution` block; a resolved
    hamstring tear is still a fact about the user and still context for the next one.
    """
    return _resolve_entry(entry_id, body, "injury", current_user.id, db)


class SweepOtherInjury(BaseModel):
    entry_id: int
    key: str
    active: bool                # true = the line is still in use by a live injury
    matched_terms: list[str]


class SweepHit(BaseModel):
    store: str                  # user_knowledge | user_knowledge_entries | hevy_routines
    row_id: Any                 # int for app stores; Hevy routine id (str) for hevy_routines
    line_index: int
    location: str
    snippet: str
    matched_terms: list[str]    # primary terms found (why this line is a hit)
    restriction_terms: list[str]  # restriction words also on the line — the stale-order signal
    sides_mentioned: list[str]
    opposite_side: bool         # names only the opposite side — flagged, never dropped
    marked_resolved: bool       # the line says "resolved"/"historical" — history, not an order
    other_injuries: list[SweepOtherInjury]  # other ledger rows the line also names
    reaches_context: str        # yes | no | conditional | unverified
    action: str                 # edit | resolve | none  (none → the UI shows "manual")
    action_route: str | None


class SweepStore(BaseModel):
    store: str
    status: str                 # searched | not_connected | unavailable | stale
    hits: int


class RadicularWarning(BaseModel):
    signal_type: str
    fires: list[str]
    message: str


class RehomedTo(BaseModel):
    entry_id: int
    key: str
    body_part: str | None
    signal_type: str
    radicular_warning: RadicularWarning | None


class ConstraintRef(BaseModel):
    entry_id: int
    key: str
    kind: str | None
    tier: str | None
    parent_key: str | None


class RestrictionAudit(BaseModel):
    restriction: str
    match_stems: list[str]
    covered_by_basis: bool
    rehomed_to: list[RehomedTo]
    # S5: a confirmed constraint that outlives this row re-homes it; one parented to THIS row is
    # listed under `dies_with_parent` and re-homes nothing (the restriction stays an orphan).
    rehomed_to_constraints: list[ConstraintRef] = []
    dies_with_parent: list[ConstraintRef] = []
    # Parented to THIS row without a with_parent exit: outlives it and keeps enforcing (G5 ruling 1).
    parent_resolved_survives: list[ConstraintRef] = []
    status: str                 # covered | rehomed | orphan
    suggested_action: str | None = None   # "propose as constraint" on an orphan; never performed


class SweepChecklistItem(BaseModel):
    store: str
    where: str
    why: str


class InjurySweepOut(BaseModel):
    entry_id: int
    key: str
    body_part: str | None
    side: str | None
    active: bool
    terms: list[str]              # PRIMARY: names the injury; a hit needs >= 1
    restriction_terms: list[str]  # SECONDARY: annotates a hit, never creates one
    # Restrictions that would drop out of chat context with this row (orphan), are
    # addressed by its resolution basis (covered), or live on another active row (rehomed).
    restriction_audit: list[RestrictionAudit]
    restrictions_note: str
    stores: list[SweepStore]
    hits: list[SweepHit]
    manual_checklist: list[SweepChecklistItem]   # always present, always last


@router.get("/injuries/{entry_id}/sweep", response_model=InjurySweepOut)
async def sweep_injury(
    entry_id: int,
    terms: str | None = Query(
        None, description="Extra comma-separated match terms, case-insensitive."),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Find every copy of one injury outside the ledger — SURFACING-ONLY, never edits.

    The ledger is the only authority on injury state; every other store holding the injury
    is a copy the operator clears by hand. A line is a hit only if it names the injury — a
    PRIMARY term: body_part, its `BODY_PART_ALIASES`, key tokens, or `?terms=`. Restriction
    words are SECONDARY: they annotate a hit (`restriction_terms`, the stale-order signal) and
    never create one. Searched: the free-text `user_knowledge` rows (per line), non-injury
    structured entries (`value` leaves and `notes`), and Hevy routine/exercise notes via the
    routine cache. Each hit carries the store's EXISTING action, or `none`. The response
    always ends with a fixed checklist of stores the app cannot search.

    Also audits the entry's `restrictions`: each is `covered` by the resolution basis,
    `rehomed` onto another active injury row, or an `orphan` about to leave chat context
    (restriction strings are chat-rendered only; the engine gates on body_part +
    signal_type). A re-homed destination typed neural/radicular on a spinal part carries a
    `_RADICULAR_BLOCKS` warning. The resolve route's contract is untouched: the frontend
    calls this straight after a resolve.

    Works for resolved entries — the point is sweeping after a resolve. Scoped to
    `type='injury'` like the resolve route: any other id, or another user's, is a 404.
    """
    # Local: `encryption` builds its Fernet at import, which this router has never required.
    from encryption import decrypt

    entry = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(id=entry_id, user_id=current_user.id, type="injury")
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Injury entry not found")

    value = entry.value or {}
    own_side = (str(value.get("side") or "").lower() or None)
    extra = (terms or "").split(",")
    primary_terms, restriction_terms = injury_sweep.derive_terms(entry, extra)
    rx = injury_sweep.term_regex(primary_terms)

    all_injuries = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=current_user.id, type="injury")
        .order_by(models.UserKnowledgeEntry.id)
        .all()
    )
    # Confirmed constraints re-home a restriction when they outlive this row (S5). One query of the
    # user's active entries, lifted through the shared `typed_entries` definition.
    live_entries = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=current_user.id, active=True)
        .all()
    )
    audit = injury_sweep.audit_restrictions(
        entry, [i for i in all_injuries if i.active],
        constraints=typed_entries.lift_constraints(live_entries),
        live_keys=typed_entries.active_keys(live_entries),
    )
    ctx = injury_sweep.line_context(entry, all_injuries, restriction_terms)

    stores: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    if rx is not None:
        uk_rows = (
            db.query(models.UserKnowledge)
            .filter_by(user_id=current_user.id)
            .order_by(models.UserKnowledge.category, models.UserKnowledge.id)
            .all()
        )
        uk_hits = injury_sweep.sweep_user_knowledge(uk_rows, rx, ctx)
        stores.append({"store": "user_knowledge", "status": "searched", "hits": len(uk_hits)})

        entries = (
            db.query(models.UserKnowledgeEntry)
            .filter(models.UserKnowledgeEntry.user_id == current_user.id,
                    models.UserKnowledgeEntry.type != "injury")
            .order_by(models.UserKnowledgeEntry.id)
            .all()
        )
        e_hits = injury_sweep.sweep_entries(entries, rx, ctx)
        stores.append({"store": "user_knowledge_entries", "status": "searched", "hits": len(e_hits)})

        integration = (
            db.query(models.UserIntegration)
            .filter_by(user_id=current_user.id, provider="hevy")
            .first()
        )
        h_hits: list[dict[str, Any]] = []
        if integration is None:
            h_status = "not_connected"
        else:
            # The chat turn's own cache + 3s budget — never waits on Hevy, never raises.
            cached = await hevy_routine_cache.get_routines_cached(
                HevyClient(decrypt(integration.api_key_encrypted)), current_user.id)
            if cached.get("unavailable"):
                h_status = "unavailable"
            else:
                h_status = "stale" if cached.get("stale") else "searched"
                h_hits = injury_sweep.sweep_hevy_routines(cached.get("routines"), rx, ctx)
        stores.append({"store": "hevy_routines", "status": h_status, "hits": len(h_hits)})
        hits = uk_hits + e_hits + h_hits

    return {
        "entry_id": entry.id,
        "key": entry.key,
        "body_part": value.get("body_part"),
        "side": own_side,
        "active": entry.active,
        "terms": primary_terms,
        "restriction_terms": restriction_terms,
        "restriction_audit": audit,
        "restrictions_note": injury_sweep.RESTRICTIONS_NOTE,
        "stores": stores,
        "hits": hits,
        "manual_checklist": list(injury_sweep.MANUAL_CHECKLIST),
    }


@router.post("/schedule/{entry_id}/resolve", response_model=KnowledgeEntryOut)
def resolve_schedule_item(
    entry_id: int,
    body: ResolutionIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retire one schedule_item: the commitment is no longer true — the season ended,
    the user left the team, the job changed — recorded with provenance and no
    successor.

    RESOLUTION IS NOT SUPERSESSION AND IS NOT EXPIRY. Supersession replaces a row
    with a newer statement about the same commitment and names it in `superseded_by`
    (the `supersedes` / day-overlap path in `upsert_knowledge_entry`). `expire-stale`
    is the overlay sweep — it flips rows whose predicted `expires_at` has passed and
    writes no `resolution` block. This is the third, distinct act: an explicit
    operator assertion that the commitment is retired, stamped with who made it,
    keeping the row and leaving `superseded_by` untouched.

    PER-TYPE BY DESIGN. Scoped to `type='schedule_item'`, so an injury id here is a
    404 — the same cross-type 404-leak defence the injury route carries. Do not
    generalise the two into a shared `/entry/{id}/resolve`; the type in the path is
    the boundary.

    NEVER DELETES. The retired commitment stays in history with its `resolution`
    block; `GET /knowledge/schedule` (active-only) simply stops returning it.
    """
    return _resolve_entry(entry_id, body, "schedule_item", current_user.id, db)


# ---------- typed entries: confirm + resolve (#342/#343) ----------

class ConfirmIn(BaseModel):
    """The operator's confirmation of a proposed typed entry. `asserted_by` is the #227 authority
    tier stamped on the row — who stands behind the claim, which is not necessarily who typed it
    (`source` stays the channel). No default: an unattributed confirmation is refused."""
    asserted_by: str


def _confirm_entry(
    entry_id: int,
    body: ConfirmIn,
    entry_type: str,
    user_id: int,
    db: Session,
) -> models.UserKnowledgeEntry:
    """Move one typed entry to its confirmed status — the ONLY such path (a confirmed status on
    a plain upsert over a proposal is refused in `_validate_typed_write`). A finding may be
    confirmed from `proposed` or `open`. Stamps `confirmed_on` (G1 ruling 2).

    Type-scoped exactly as `_resolve_entry` is: an id of another type is a 404 that reveals
    nothing (the cross-type 404-leak defence). Confirming twice is a 409, not a no-op. A
    `with_parent` constraint whose parent is no longer active is a 409 — confirming it would mint
    a rule whose own exit has already fired.
    """
    label = _RESOLVE_LABELS[entry_type]
    if body.asserted_by not in ASSERTED_BY_VALUES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"asserted_by must be one of: {', '.join(ASSERTED_BY_VALUES)}",
        )
    entry = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(id=entry_id, user_id=user_id, type=entry_type)
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
    if not entry.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{label} is inactive — only an active entry can be confirmed",
        )
    value = entry.value or {}
    current = value.get("status")
    if current in _TYPED_CONFIRMED[entry_type]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{label} is already {current!r} — confirming twice is an error, not a no-op",
        )
    parent_key = value.get("parent_key")
    if parent_key is not None and (value.get("exit") or {}).get("with_parent") is True:
        parent = (
            db.query(models.UserKnowledgeEntry)
            .filter_by(user_id=user_id, key=parent_key, active=True)
            .first()
        )
        if parent is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{label}'s parent {parent_key!r} is no longer active — its with_parent exit "
                       f"has already fired; resolve the entry instead",
            )
    # REASSIGN, never mutate in place (plain JSON column — see `_resolve_entry`). `confirmed_on` is
    # the operator-local (AEST) day, like `resolved_on` (Q42); stamped here and nowhere else.
    entry.value = {
        **value,
        "status": _TYPED_CONFIRMED[entry_type][0],
        "asserted_by": body.asserted_by,
        "confirmed_on": str(_local_day()),
    }
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/constraints/{entry_id}/confirm", response_model=KnowledgeEntryOut)
def confirm_constraint(
    entry_id: int,
    body: ConfirmIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirm one proposed constraint: the explicit operator write (#223 pattern) that makes it
    readable by the engine and the coach, stamped with its authority (`asserted_by`, #227).

    THE ONLY PROPOSED → CONFIRMED PATH. A chat write is always `proposed`; an upsert carrying
    `status: "confirmed"` over a proposal is refused. Nothing confirms itself.
    """
    return _confirm_entry(entry_id, body, "constraint", current_user.id, db)


@router.post("/constraints/{entry_id}/resolve", response_model=KnowledgeEntryOut)
def resolve_constraint(
    entry_id: int,
    body: ResolutionIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retire one constraint: its exit has fired, or it is withdrawn (a proposal the operator
    declines is resolved the same way, with its basis). The operator's act, never automatic —
    a passed `exit.on_date` or `review_by` SURFACES the row; it does not lift it (#223).

    Per-type (the 404-leak defence), never deletes, `superseded_by` untouched — exactly the
    injury / schedule_item resolve contract (#222).
    """
    return _resolve_entry(entry_id, body, "constraint", current_user.id, db)


@router.post("/findings/{entry_id}/confirm", response_model=KnowledgeEntryOut)
def confirm_finding(
    entry_id: int,
    body: ConfirmIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Confirm one finding (from `proposed` or `open`): the explicit operator write that stands
    behind an interpretation, stamped with its authority (`asserted_by`, #227). The only path to
    `confirmed` from a proposal; nothing confirms itself.
    """
    return _confirm_entry(entry_id, body, "finding", current_user.id, db)


@router.post("/findings/{entry_id}/retract", response_model=KnowledgeEntryOut)
def retract_finding(
    entry_id: int,
    body: ResolutionIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retract one finding: it is no longer held to be true. `basis` is mandatory (#223's
    resolve contract — a retraction with no stated grounds is the thing that later reads as an
    accident). Stamps `status: "retracted"` with the `resolution` block and sets `active=False`.

    NEVER DELETES. A retracted interpretation stays in the table: that it was once held, and why
    it was dropped, is itself context. Per-type route (the 404-leak defence).
    """
    return _resolve_entry(entry_id, body, "finding", current_user.id, db, terminal_status="retracted")
