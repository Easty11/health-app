from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db

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
EXPECTED_LOAD_VALUES = ("light", "moderate", "heavy")
TIME_OF_DAY_VALUES = ("morning", "afternoon", "evening", "unknown")

MAX_SESSIONS_PER_WEEK = 14

# Stored fields. Anything outside this set is REFUSED rather than carried -- an
# unknown key is how `minimum_days` came to exist.
SCHEDULE_ITEM_FIELDS = (
    "activity", "days", "sessions_per_week", "hard", "expected_load",
    "time_of_day", "time_range", "same_day_training", "same_day_note",
    "duration_weeks", "season_end", "supersedes",
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


class ScheduleItemOverlap(Exception):
    """A schedule_item write overlaps an active row on `days`, unacknowledged.

    Carries the overlapping rows so every caller -- HTTP, chat, a future surface --
    can render the same structured refusal instead of each inventing one.
    """

    def __init__(self, overlapping: list[dict[str, Any]]):
        self.overlapping = overlapping
        super().__init__(
            "schedule_item overlaps an active row on days; retry with "
            "`supersedes: <id>` or `distinct_from: [<id>, ...]`"
        )


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
        raise ValueError(
            f"schedule_item: unknown field(s) {extra} -- "
            f"one of {list(SCHEDULE_ITEM_FIELDS)}"
        )

    missing = [f for f in SCHEDULE_ITEM_REQUIRED if f not in value]
    if missing:
        raise ValueError(f"schedule_item: missing required field(s) {missing}")

    if not isinstance(value["activity"], str) or not value["activity"].strip():
        raise ValueError("schedule_item.activity must be a non-empty string")

    # WHEN it happens: a day list, a weekly count, or both. Neither is not a schedule.
    has_days = "days" in value and value["days"] is not None
    has_count = "sessions_per_week" in value and value["sessions_per_week"] is not None
    if not has_days and not has_count:
        raise ValueError(
            "schedule_item: at least one of `days` or `sessions_per_week` is required"
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

    return value


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


class InjuryResolutionIn(BaseModel):
    """The operator's answer to "is this still true?". `basis` is mandatory and
    free text: a resolution with no stated grounds is the thing that later reads as
    an accident. `resolved_on` defaults to today rather than being required, since
    the common case is resolving something as of now."""
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
    """Refuse a schedule_item write that lands on a day an active row already holds,
    unless the write acknowledges every row it overlaps.

    THE TRIGGER IS DAY OVERLAP ALONE -- deliberately not `days` overlap AND matching
    `activity`. The duplicate pairs in live data exist because the writer minted a new
    key for an existing commitment; matching on `activity` is string equality over
    generated free text, which fails the same way one level down and fails OPEN -- a
    near-miss string produces a silent duplicate exactly as before.

    This refuses more often, including on genuinely distinct same-day commitments.
    That is the point: the failure moves from silent to visible, and the caller states
    which it is. Every overlapping row must be accounted for, not just one of them --
    acknowledging a single row out of three would leave the other two to duplicate
    silently, which is the hole this closes.
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
        if days & row_days:
            unacknowledged.append({
                "id": row.id,
                "activity": row_value.get("activity"),
                "days": sorted(row_days & days),
                "time_of_day": row_value.get("time_of_day"),
            })

    if unacknowledged:
        raise ScheduleItemOverlap(unacknowledged)


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
    stored_value = entry_in.value
    if entry_in.type == "schedule_item":
        validate_schedule_item(entry_in.value)
        _schedule_overlap_check(user_id, entry_in, db)
        # Strip the write-only acknowledgement token. It satisfied the validator for
        # this write; it is not a relationship and is not stored.
        stored_value = {
            k: v for k, v in entry_in.value.items()
            if k not in SCHEDULE_ITEM_WRITE_ONLY_FIELDS
        }

    existing = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=user_id, key=entry_in.key, active=True)
        .first()
    )

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


@router.post("/injuries/{entry_id}/resolve", response_model=KnowledgeEntryOut)
def resolve_injury(
    entry_id: int,
    body: InjuryResolutionIn,
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

    # Scoped to the caller AND to type='injury': another user's row and a
    # non-injury row are both 404 here, so this route cannot retire a
    # schedule_item, and a probe for someone else's entry id learns nothing.
    entry = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(id=entry_id, user_id=current_user.id, type="injury")
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Injury entry not found")
    if not entry.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Injury entry is already inactive — resolving twice is an error, not a no-op",
        )

    # REASSIGN, never mutate in place: the column is a plain `JSON`, not a
    # `MutableDict`, so an in-place `entry.value["resolution"] = ...` is not seen by
    # the unit of work and is silently dropped at commit. Tested by reading the row
    # back from a fresh query rather than from the in-session identity map.
    entry.value = {
        **(entry.value or {}),
        "resolution": {
            "resolved_on": str(body.resolved_on or date.today()),
            "basis": body.basis,
            "resolved_by": body.resolved_by,
        },
    }
    entry.active = False
    # `superseded_by` is deliberately left untouched — see the docstring.
    db.commit()
    db.refresh(entry)
    return entry
