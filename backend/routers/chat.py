from typing import Any
import json
import logging
import os
import re

import anthropic
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from connectors.hevy import (
    HevyAuthError,
    HevyBadRequestError,
    HevyClient,
    HevyCustomExerciseLimitError,
    RoutineAlreadyExists,
    RoutineNumericError,
)
from context_builder import build_system_prompt, render_asked_lab_value
from current_state import current_state as compute_current_state
from database import get_db
from encryption import decrypt
from hevy_templates import (
    HevyCreateUnresolvedError,
    HevyKeyMissingError,
    catalogue_titles,
    catalogue_titles_by_id,
    create_and_resolve,
    refresh_catalogue_if_stale,
    resolve_exercise,
    suggest_candidates,
    user_hevy_key,
)
from engine import adaptation, selection
from reads.labs_reads import find_marker
from routers.knowledge import (
    KnowledgeEntryIn,
    ScheduleItemInvalid,
    ScheduleItemOverlap,
    expire_stale_entries,
    upsert_knowledge_entry,
)

load_dotenv()

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

router = APIRouter(prefix="/chat", tags=["chat"])

# Regex to find <hevy_create_routine>...</hevy_create_routine> blocks
_ROUTINE_BLOCK_RE = re.compile(
    r"<hevy_create_routine>\s*(.*?)\s*</hevy_create_routine>",
    re.DOTALL,
)

# Regex to find <hevy_create_exercise>...</hevy_create_exercise> blocks — the
# app-originated custom-exercise idiom. Separate from the routine block ON PURPOSE:
# creation is permanent (Hevy has no delete/edit-template API), so it stays an
# explicit, separately-confirmed act rather than a side effect of a resolve miss.
_EXERCISE_BLOCK_RE = re.compile(
    r"<hevy_create_exercise>\s*(.*?)\s*</hevy_create_exercise>",
    re.DOTALL,
)

# Regex to find <knowledge_update>...</knowledge_update> blocks
_KNOWLEDGE_BLOCK_RE = re.compile(
    r"<knowledge_update>\s*(.*?)\s*</knowledge_update>",
    re.DOTALL,
)

# Regex to find <capability_update>...</capability_update> blocks — the adaptation
# loop's education-idiom capture (spec §7). The user reports how a probe/fortify
# felt; Claude records the response tag against the taxonomy region.
_CAPABILITY_BLOCK_RE = re.compile(
    r"<capability_update>\s*(.*?)\s*</capability_update>",
    re.DOTALL,
)


# ---------- schemas ----------

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_history: list[ChatMessage] = []


class WriteResult(BaseModel):
    """Machine-checkable outcome of ONE knowledge/schedule write block (#283, Q143a).

    The gloss the origin transcript showed — narrating "saved" while `actions_taken`
    carried `✗` strings — was possible because success was only inferable from prose.
    This is the additive, hard-gateable substrate: a client (or a later turn) checks
    `saved` rather than trusting the reply's narration. `actions_taken` is preserved
    verbatim as `reason`, so nothing regresses for a reader.

    ONE result per `<knowledge_update>` block, never a batch roll-up: the failure mode
    was several blocks where some saved and some did not, narrated as all-saved, so a
    single top-level flag would reintroduce exactly that gloss.
    """
    saved: bool
    # Stable, type-derived (never message-parsed): saved | deactivated | not_found |
    # day_time_clash | unknown_field | invalid_shape | invalid_json | error.
    reason_code: str
    reason: str             # the human string, identical to the `actions_taken` entry
    key: str | None = None  # the schedule_item / knowledge key, when the block named one


class ChatResponse(BaseModel):
    response: str
    actions_taken: list[str] = []   # e.g. ["✓ Routine 'Push Day' created in Hevy"]
    # Per-block structured outcomes for the write lanes. Additive to `actions_taken`; empty
    # when the turn wrote no mapped blocks. Covers every write lane: knowledge/schedule
    # (#283), Hevy routine (#286), and Hevy exercise (Q144). No string-only write lane remains.
    write_results: list[WriteResult] = []


# ---------- context gathering ----------

async def _gather_hevy_context(api_key: str) -> dict[str, Any]:
    client = HevyClient(api_key)
    try:
        count_data = await client.get_workout_count()
        workouts_data = await client.get_workouts(page=1, page_size=10)
        return {
            "workout_count": count_data.get("workout_count", 0),
            "recent_workouts": workouts_data.get("workouts", []),
        }
    except HevyAuthError:
        return {"workout_count": 0, "recent_workouts": [], "error": "invalid_key"}


def _annotate_canonical_titles(hevy_data: dict[str, Any], db: Session) -> dict[str, Any]:
    """Annotate each logged exercise with its CURRENT catalogue title (#81).

    Done HERE, upstream, and not in `context_builder`: the context builder is a
    pure formatter (the invariant the #43 parity guard exists to protect), so it
    gets no Session and performs no queries. It renders `canonical_title` if we
    put one there.

    Hevy's logged `title` is a snapshot from when the workout was logged, and
    Hevy renames its default templates, so the two title-spaces drift (#79).
    Handing the model a logged title while telling it to emit titles that
    `resolve_exercise` byte-matches against the CATALOGUE would guarantee a miss
    on exactly the drifted movements. Ids with no catalogue row are left
    un-annotated — the renderer marks them rather than passing a logged title off
    as canonical.

    Mutates in place and returns `hevy_data` for convenience.
    """
    workouts = hevy_data.get("recent_workouts") or []
    exercises = [ex for w in workouts for ex in (w.get("exercises") or [])]
    template_ids = {tid for ex in exercises if (tid := ex.get("exercise_template_id"))}
    if not template_ids:
        return hevy_data

    titles = catalogue_titles_by_id(db, template_ids)
    drifted = 0
    for ex in exercises:
        tid = ex.get("exercise_template_id")
        canonical = titles.get(tid) if tid else None
        if not canonical:
            continue
        ex["canonical_title"] = canonical
        if ex.get("title") and ex["title"] != canonical:
            drifted += 1

    missing = len(template_ids - set(titles))
    if drifted or missing:
        logger.info(
            "chat context: %d logged exercise(s) renamed to the catalogue title, "
            "%d template id(s) absent from the catalogue (rendered as logged, marked)",
            drifted, missing,
        )
    return hevy_data


# ---------- custom-exercise action parsing ----------

# The CREATE enums, captured from Hevy's live OpenAPI spec
# (api.hevyapp.com/docs/swagger-ui-init.js, embedded `swaggerDoc`,
# `CreateCustomExerciseRequestBody`). Held here only to make a 400 CORRECTABLE — the
# request itself passes the model's strings straight through, so this copy never gates
# a create and cannot fail closed if Hevy adds a member (Q76 takes round-trip-and-
# correct over a validating table).
_CREATE_EXERCISE_TYPES = (
    "weight_reps", "reps_only", "bodyweight_reps", "bodyweight_assisted_reps",
    "duration", "weight_duration", "distance_duration", "short_distance_weight",
)
_CREATE_EQUIPMENT = (
    "none", "barbell", "dumbbell", "kettlebell", "machine", "plate",
    "resistance_band", "suspension", "other",
)
_CREATE_MUSCLE_GROUPS = (
    "abdominals", "shoulders", "biceps", "triceps", "forearms", "quadriceps",
    "hamstrings", "calves", "glutes", "abductors", "adductors", "lats",
    "upper_back", "traps", "lower_back", "chest", "cardio", "neck", "full_body",
    "other",
)

_CREATE_ENUM_BY_FIELD = {
    "exercise_type": _CREATE_EXERCISE_TYPES,
    "equipment_category": _CREATE_EQUIPMENT,
    "muscle_group": _CREATE_MUSCLE_GROUPS,
    "other_muscles": _CREATE_MUSCLE_GROUPS,
}


def _format_schedule_overlap(key: str, overlapping: list[dict]) -> str:
    """Render an unacknowledged day overlap as an instruction the next turn can act on.

    Names every overlapping row rather than reporting a count, for the same reason
    `_format_exercise_rejection` echoes valid values: a bare "that clashes" leaves the
    model guessing which row it clashed with, and guessing is what produced the
    duplicate pairs in the first place.

    The model must NOT resolve the ambiguity itself. Whether a second commitment on a
    shared day replaces the first or sits beside it is the operator's call; inventing
    an answer is the failure this refusal exists to make visible.
    """
    rows = "; ".join(
        f"id {o['id']} — {o.get('activity') or '?'} on "
        f"{', '.join(o.get('days') or [])}"
        + (f" ({o['time_of_day']})" if o.get("time_of_day") else "")
        for o in overlapping
    )
    return (
        f"✗ Schedule entry NOT saved: {key} — it lands on a day already held by: {rows}. "
        f"Ask the user whether this REPLACES those rows or is a separate commitment on "
        f"the same day, then retry with `supersedes: <id>` or `distinct_from: [<id>, ...]`. "
        f"Do not choose for them."
    )


def _format_exercise_rejection(title: str, detail: str) -> str:
    """Render a Hevy 400 as a message the next turn can act on (#83's pattern).

    A bare "Hevy rejected the body" leaves the model re-guessing the same wrong string.
    Hevy's 400 text names the offending field, so echo the VALID values for that field
    back — the same reason `_format_unresolved` names candidate titles rather than just
    reporting a miss.

    The field is matched against the create-schema field names rather than parsed out of
    Hevy's prose, so an unrecognised message degrades to listing every enum instead of
    guessing wrong about which one is at fault.
    """
    named = [f for f in _CREATE_ENUM_BY_FIELD if f in detail.lower()]
    fields = named or ["exercise_type", "equipment_category", "muscle_group"]
    parts = [
        f"{f} must be one of: " + ", ".join(_CREATE_ENUM_BY_FIELD[f])
        for f in fields
    ]
    return (
        f"⚠️ Custom exercise '{title}' not created — Hevy rejected the request. "
        + " | ".join(parts)
        + f" (Hevy said: {detail})"
    )


async def _process_exercise_actions(
    reply: str,
    user_id: int,
    db: Session,
) -> tuple[str, list[str], list[WriteResult]]:
    """Scan `reply` for <hevy_create_exercise> blocks and mint each one.

    Mirrors `_process_routine_actions`: parse, act, strip the raw block, record a
    confirmation AND a machine-checkable WriteResult. Delegates to `create_and_resolve`
    (#65), which owns the create -> sync -> list-back-in-the-custom-subset loop and
    returns the canonical string id — never the integer id the POST response carries.

    MUST run before `_process_routine_actions`. The model cannot know a server-minted
    UUID, so a same-turn routine references the new exercise by TITLE, and
    `_resolve_missing_ids` finds it only if the create and its sync have already run.
    Reverse the order and the routine fails an unresolved-title miss on an exercise that
    was created moments earlier in the same reply.

    Idempotency is re-checked HERE, not just inside `create_and_resolve`, so the
    confirmation can tell the truth. The orchestrator short-circuits an existing title by
    returning its id — indistinguishable at this layer from a fresh create — and
    reporting "created" for something that already existed would be a false confirmation
    about an irreversible act.

    Freshness gate (#212 / follow-up to Q75 #211). Both idempotency reads — the honest-
    confirmation pre-check below AND `create_and_resolve`'s own — resolve against the LOCAL
    template store. A chat-initiated create with no recent workout fetch (the path #211
    guards) can therefore race a stale catalogue: an upstream custom minted since the last
    sync is invisible to both reads, and the create mints a permanent duplicate against a
    delete-less API — the 2026-08-05 incident's mint offer. So refresh-if-stale HERE, before
    the pre-check, not inside `create_and_resolve`: the confirmation's honesty depends on the
    pre-check below reading a fresh store, and a fresh read here leaves `create_and_resolve`'s
    read fresh too — one refresh closes both. Staleness-gated (`_CATALOGUE_STALE_AFTER`) and
    run once per turn, so a recent fetch/create skips the Hevy call; non-blocking on failure,
    so a Hevy outage degrades to the stale-store behaviour rather than dropping the reply.

    Returns (cleaned_reply, actions_taken, write_results) — this is the LAST un-wrapped
    Hevy write surface folded onto the #283 substrate (Q144), one WriteResult per block
    paired 1:1 with its action string so a failed/unconfirmed/already-present create can't
    be narrated as a fresh success. WRAP-ONLY, no collision guard: unlike routines (#286),
    this lane is already idempotent — the `resolve_exercise` pre-check below, plus
    `create_and_resolve`'s own #65 pre-check and the freshness gate above, structurally
    prevent a duplicate mint. Reason_code vocab reuses #286 where the outcome matches, with
    new codes for the genuinely distinct exercise outcomes: created | already_present |
    invalid_json | invalid_shape | limit_reached | invalid_exercise_field |
    created_unconfirmed | create_failed.
    """
    actions_taken: list[str] = []
    write_results: list[WriteResult] = []

    def record(saved: bool, reason_code: str, message: str, *, key: str | None = None):
        actions_taken.append(message)
        write_results.append(
            WriteResult(saved=saved, reason_code=reason_code, reason=message, key=key)
        )

    matches = list(_EXERCISE_BLOCK_RE.finditer(reply))

    if not matches:
        return reply, actions_taken, write_results

    # Not connected — strip every block with one message, as routines do, rather than
    # emitting an identical warning per block. The `HevyKeyMissingError` branch below is
    # the defensive twin: it catches a key deleted between this check and the create.
    if user_hevy_key(db, user_id) is None:
        cleaned = _EXERCISE_BLOCK_RE.sub("", reply).strip()
        record(False, "create_failed", "⚠️ Custom exercise not created — Hevy is not connected.")
        return cleaned, actions_taken, write_results

    # Close the stale-catalogue mint window (see docstring): refresh before either
    # idempotency read, staleness-gated so the common (fresh) path skips the Hevy call.
    await refresh_catalogue_if_stale(db, user_id)

    cleaned = reply
    for match in matches:
        raw_json = match.group(1)
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            record(False, "invalid_json", f"⚠️ Could not parse custom-exercise JSON: {exc}")
            cleaned = cleaned.replace(match.group(0), "")
            continue

        if not isinstance(data, dict):
            record(False, "invalid_shape", "⚠️ Custom-exercise block is not a JSON object.")
            cleaned = cleaned.replace(match.group(0), "")
            continue

        title = (data.get("title") or "").strip()
        if not title:
            record(False, "invalid_shape", "⚠️ Custom exercise not created — no title given.")
            cleaned = cleaned.replace(match.group(0), "")
            continue

        # Honest-confirmation pre-check (see docstring). Default-wins, same predicate the
        # routine path resolves against, so "already there" means "the routine block will
        # resolve it". saved=False: nothing was minted, so a pre-write "created!" is
        # CORRECTED to "already in your catalogue" rather than left standing as a fresh
        # create — the exact gloss this fold closes. Informational, not a fault.
        existing = resolve_exercise(db, title, user_id)
        if existing is not None:
            record(False, "already_present",
                   f"ℹ️ '{title}' is already in the exercise catalogue — nothing created",
                   key=title)
            cleaned = cleaned.replace(match.group(0), "")
            continue

        try:
            await create_and_resolve(
                db,
                user_id,
                title=title,
                exercise_type=data.get("exercise_type"),
                equipment_category=data.get("equipment_category"),
                muscle_group=data.get("muscle_group"),
                other_muscles=data.get("other_muscles"),
            )
            record(True, "created", f"✓ Custom exercise '{title}' created in Hevy", key=title)
        except HevyCustomExerciseLimitError:
            record(False, "limit_reached",
                   "⚠️ Custom exercise not created — Hevy's custom-exercise limit reached.",
                   key=title)
        except HevyBadRequestError as exc:
            record(False, "invalid_exercise_field", _format_exercise_rejection(title, str(exc)), key=title)
        except HevyCreateUnresolvedError as exc:
            # The POST may well have SUCCEEDED — only the list-back failed. Say so, and
            # say not to retry: a second create against a delete-less API is how you get
            # two permanent templates with the same name. saved=False so a confident
            # "created!" is discarded, but the verbatim no-retry guidance rides in the
            # action string regardless of how pass-2 renders it.
            record(False, "created_unconfirmed",
                   f"⚠️ Custom exercise '{title}' — created in Hevy but it did not surface "
                   f"in the catalogue after the sync retries. Do NOT create it again; it "
                   f"likely exists. ({exc})",
                   key=title)
        except HevyKeyMissingError:
            record(False, "create_failed",
                   "⚠️ Custom exercise not created — Hevy is not connected.", key=title)
        except Exception as exc:  # noqa: BLE001 — mirror the routine path's catch-all
            record(False, "create_failed", f"⚠️ Failed to create custom exercise '{title}': {exc}", key=title)

        cleaned = cleaned.replace(match.group(0), "")

    return cleaned.strip(), actions_taken, write_results


# ---------- routine action parsing ----------

def _resolve_missing_ids(
    exercises: list[dict],
    user_id: int,
    db: Session,
) -> tuple[list[dict], list[tuple[str, list[tuple[str, str]]]]]:
    """Opt-in title->id resolution (DECISIONS_LOG #60), with candidates on a miss (#83).

    The provisioning block already carries `exercise_template_id`s, so this is a
    fallback, not a mandatory hop: only exercises MISSING a non-empty id but
    carrying a `title` are resolved (exact canonical-title match, default-wins).
    Exercises that already have an id are passed through untouched.

    Returns the exercises with ids filled where possible, plus `unresolved` as
    (title, candidates) pairs — candidates being ranked catalogue suggestions for
    that miss, possibly empty. Resolution stays EXACT: a candidate is never
    silently adopted, not even when it is the only one (#83). The caller decides
    what to do; it still provisions nothing.
    """
    unresolved: list[tuple[str, list[tuple[str, str]]]] = []
    for ex in exercises:
        if ex.get("exercise_template_id"):
            continue
        title = ex.get("title") or ex.get("exercise_name")
        if not title:
            continue
        resolved = resolve_exercise(db, title, user_id)
        if resolved:
            ex["exercise_template_id"] = resolved
            ex.pop("title", None)
            ex.pop("exercise_name", None)
        else:
            unresolved.append((title, suggest_candidates(db, title, user_id)))
    return exercises, unresolved


def _format_unresolved(unresolved: list[tuple[str, list[tuple[str, str]]]]) -> str:
    """Render a miss as a correctable message (#83).

    The model sees this on the next turn (the reply, actions appended, is echoed
    back as conversation history), so it names the exact catalogue titles it must
    copy. A bare "could not resolve" left it guessing the same wrong string
    again — measured at a 25% hit-rate on out-of-history titles.
    """
    parts = []
    for title, candidates in unresolved:
        if candidates:
            named = ", ".join(f"'{t}'" for _, t in candidates)
            parts.append(f"'{title}' (did you mean: {named}?)")
        else:
            parts.append(f"'{title}' (no similar exercise found in the catalogue)")
    return ", ".join(parts)


async def _resolve_folder_id(
    hevy_client: HevyClient,
    folder_name: str | None,
    explicit_id: int | None,
) -> tuple[int | None, str | None]:
    """Resolve a routine's target folder to an int id (Q144 follow-up — FIX #1).

    The model names a folder (`"folder": "2026 Post Season Decompression"`); the connector
    needs `folder_id` (int). Before this, the name was silently dropped and the routine
    landed unfoldered. Now: an explicit `folder_id` wins; otherwise the name is matched
    case-insensitively against the live folder list. Returns `(folder_id, unresolved_name)`
    — a miss yields `(None, name)` so the caller creates the routine UNFOLDERED (never a
    NaN, never a hard failure) and surfaces the miss, mirroring the exercise-title resolver.
    A folder-list read that raises is treated as a miss (unfoldered), never blocking the create.
    """
    if explicit_id is not None:
        return explicit_id, None
    if not folder_name:
        return None, None
    try:
        folders = await hevy_client.get_routine_folders()
    except Exception as exc:  # noqa: BLE001 — a folder-lookup failure must not block the create
        logger.warning("routine folder lookup failed; creating unfoldered: %s", exc)
        return None, folder_name
    wanted = folder_name.strip().casefold()
    for f in folders:
        if (f.get("title") or "").strip().casefold() == wanted:
            return f.get("id"), None
    return None, folder_name


async def _process_routine_actions(
    reply: str,
    hevy_client: HevyClient | None,
    user_id: int,
    db: Session,
) -> tuple[str, list[str], list[WriteResult]]:
    """
    Scan `reply` for <hevy_create_routine> blocks.
    For each one found:
      - Parse the JSON payload
      - Resolve any title-only exercises to ids (opt-in fallback, #60)
      - Call hevy_client.create_routine()
      - Strip the raw block from the displayed text
      - Record a confirmation message AND a machine-checkable WriteResult

    Returns (cleaned_reply, actions_taken, write_results). Each block yields ONE
    `WriteResult` (the #283 shape, Hevy codes), paired 1:1 with its `actions_taken`
    string via `record()` so a failed or collided create can never be narrated as
    success (Q144(c)) — the same discipline the knowledge lane already holds.

    Hevy reason_code vocab (type-derived, never message-parsed):
      created            — routine POSTed (saved=True)
      created_unfoldered — routine POSTed, but the named folder didn't resolve; created
                           unfoldered (saved=True — don't retry, it exists)
      already_exists     — (title, folder) collision; the connector refused (saved=False)
      unresolved_exercise— a title did not match the catalogue; nothing created (saved=False)
      invalid_number     — a non-finite/non-number reached a numeric field; caught before
                           the POST, named by field+exercise (saved=False)
      invalid_json       — the block was not parseable JSON (saved=False)
      invalid_shape      — the block parsed but was not a JSON object (saved=False)
      create_failed      — Hevy not connected, or the create raised (saved=False)
    """
    actions_taken: list[str] = []
    write_results: list[WriteResult] = []

    def record(saved: bool, reason_code: str, message: str, *, key: str | None = None):
        actions_taken.append(message)
        write_results.append(
            WriteResult(saved=saved, reason_code=reason_code, reason=message, key=key)
        )

    matches = list(_ROUTINE_BLOCK_RE.finditer(reply))

    if not matches:
        return reply, actions_taken, write_results

    if hevy_client is None:
        # Hevy not connected — strip blocks and explain
        cleaned = _ROUTINE_BLOCK_RE.sub("", reply).strip()
        record(False, "create_failed", "⚠️ Routine not created — Hevy is not connected.")
        return cleaned, actions_taken, write_results

    cleaned = reply
    for match in matches:
        raw_json = match.group(1)
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            record(False, "invalid_json", f"⚠️ Could not parse routine JSON: {exc}")
            cleaned = cleaned.replace(match.group(0), "")
            continue

        if not isinstance(data, dict):
            record(False, "invalid_shape", "⚠️ Routine block is not a JSON object.")
            cleaned = cleaned.replace(match.group(0), "")
            continue

        title = data.get("title", "Untitled Routine")
        exercises = data.get("exercises", [])

        # Folder name→id resolution (FIX #1). The model names a folder; resolve it to an
        # int id, else create unfoldered and surface the miss (never a NaN folder_id).
        folder_id, unresolved_folder = await _resolve_folder_id(
            hevy_client, data.get("folder"), data.get("folder_id"))

        # Opt-in fallback: fill ids for any title-only exercises. Blocks that
        # already carry ids are untouched (#60).
        exercises, unresolved = _resolve_missing_ids(exercises, user_id, db)
        if unresolved:
            record(
                False, "unresolved_exercise",
                f"⚠️ Routine '{title}' not created — could not resolve exercise(s): "
                + _format_unresolved(unresolved),
                key=title,
            )
            cleaned = cleaned.replace(match.group(0), "")
            continue

        try:
            await hevy_client.create_routine(
                title=title,
                exercises=exercises,
                folder_id=folder_id,
            )
            if unresolved_folder:
                # The routine WAS created (saved=True → no retry, no duplicate) but not
                # in the named folder. A distinct code keeps the miss machine-visible;
                # the verbatim reason tells the user, correcting any "filed under X" claim.
                record(True, "created_unfoldered",
                       f"✓ Routine '{title}' created in Hevy — folder "
                       f"'{unresolved_folder}' not found, so it was created unfoldered "
                       f"(create the folder in Hevy or fix the name).",
                       key=title)
            else:
                record(True, "created", f"✓ Routine '{title}' created in Hevy", key=title)
        except RoutineAlreadyExists as exc:
            # The connector refused a (title, folder) duplicate before the POST. Type-
            # derived code drives the user_resolvable affordance (rename vs update),
            # exactly like the schedule lane's day_time_clash.
            record(False, exc.code, f"⚠️ Routine '{title}' not created — {exc}", key=title)
        except RoutineNumericError as exc:
            # A non-finite/non-number reached a numeric field (the `received nan` class).
            # Caught before the POST and named by field+exercise, never sent to Hevy.
            record(False, exc.code, f"⚠️ Routine '{title}' not created — {exc}", key=title)
        except Exception as exc:
            record(False, "create_failed", f"⚠️ Failed to create routine '{title}': {exc}", key=title)

        # Remove the raw block from the visible response
        cleaned = cleaned.replace(match.group(0), "")

    return cleaned.strip(), actions_taken, write_results


# ---------- knowledge update parsing ----------

def _process_knowledge_updates(
    reply: str,
    user_id: int,
    db: Session,
) -> tuple[str, list[str], list[WriteResult]]:
    """
    Scan `reply` for <knowledge_update> blocks.

    Handles two payload formats:
    - Legacy: {category, content} → writes to UserKnowledge (free-text KB)
    - Structured: {type, key, value, ...} → writes to UserKnowledgeEntry
      - If active=false is present, deactivates the existing entry for that key
        without creating a new one.

    Returns (cleaned_reply, actions_taken, write_results). `write_results` carries ONE
    machine-checkable `WriteResult` per block (#283), paired with its `actions_taken`
    string so `saved` never disagrees with the prose a reader sees. `record()` appends
    to both lists together — the pairing is the point (the origin gloss was possible
    because only the prose existed).
    """
    actions_taken: list[str] = []
    write_results: list[WriteResult] = []

    def record(saved: bool, reason_code: str, message: str, *, key: str | None = None):
        actions_taken.append(message)
        write_results.append(
            WriteResult(saved=saved, reason_code=reason_code, reason=message, key=key)
        )

    matches = list(_KNOWLEDGE_BLOCK_RE.finditer(reply))

    if not matches:
        return reply, actions_taken, write_results

    cleaned = reply
    for match in matches:
        raw_json = match.group(1)
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            record(False, "invalid_json", f"⚠️ Could not parse knowledge update: {exc}")
            cleaned = cleaned.replace(match.group(0), "")
            continue

        key = data.get("key") if isinstance(data, dict) else None
        try:
            if "type" in data and "key" in data:
                # Structured format → UserKnowledgeEntry
                key = data["key"]

                # Deactivation: active=false means remove existing entry, no new one
                if data.get("active") is False:
                    existing = (
                        db.query(models.UserKnowledgeEntry)
                        .filter_by(user_id=user_id, key=key, active=True)
                        .first()
                    )
                    if existing:
                        existing.active = False
                        db.commit()
                        record(True, "deactivated", f"✓ Schedule entry removed: {key}", key=key)
                    else:
                        # No row changed — a `not_found` outcome, NOT a success. Narrating
                        # this as "removed" is the same gloss `saved:false` exists to block.
                        record(False, "not_found",
                               f"ℹ️ No active entry found for key: {key}", key=key)
                else:
                    from datetime import date as _date
                    expires_raw = data.get("expires_at")
                    expires_at = None
                    if expires_raw:
                        try:
                            expires_at = _date.fromisoformat(str(expires_raw))
                        except ValueError:
                            pass

                    entry_in = KnowledgeEntryIn(
                        type=data.get("type", "schedule_item"),
                        key=key,
                        value=data.get("value", {}),
                        # Not `data.get("source", ...)`. This block was parsed out
                        # of an assistant turn by `_KNOWLEDGE_BLOCK_RE`, so it arrived
                        # via chat BY CONSTRUCTION OF THIS ROUTER -- there is no case
                        # where the model knows the channel better than the call site.
                        # A model-supplied `source` is ignored, not trusted (#230).
                        source="chat",
                        expires_at=expires_at,
                        notes=data.get("notes"),
                    )
                    # A refused write is REPORTED, never swallowed. The user said the
                    # thing out loud; dropping it silently is worse than the unvalidated
                    # mess this replaces, because nothing downstream can tell the
                    # difference between "not said" and "said and lost".
                    try:
                        upsert_knowledge_entry(user_id, entry_in, db)
                        record(True, "saved", f"✓ Schedule entry saved: {key}", key=key)
                    except ScheduleItemOverlap as exc:
                        db.rollback()
                        record(False, exc.code,
                               _format_schedule_overlap(key, exc.overlapping), key=key)
                    except ValueError as exc:
                        db.rollback()
                        # ScheduleItemInvalid carries a specific `code` (e.g. unknown_field);
                        # any other ValueError is a generic shape failure. Type-derived, never
                        # parsed out of the message.
                        code = getattr(exc, "code", "invalid_shape")
                        record(False, code,
                               f"✗ Schedule entry NOT saved: {key} — {exc}. "
                               f"State this back to the user and retry with a corrected block.",
                               key=key)

            else:
                # Legacy format → UserKnowledge (free-text categories)
                category = data.get("category", "Other").strip()
                new_content = data.get("content", "").strip()

                if not new_content:
                    cleaned = cleaned.replace(match.group(0), "")
                    continue

                existing = (
                    db.query(models.UserKnowledge)
                    .filter_by(user_id=user_id, category=category)
                    .order_by(models.UserKnowledge.created_at)
                    .first()
                )
                if existing:
                    existing.content = existing.content.rstrip() + "\n" + new_content
                    db.commit()
                    record(True, "saved", f"✓ Knowledge updated: {category}", key=category)
                else:
                    entry = models.UserKnowledge(
                        user_id=user_id,
                        category=category,
                        content=new_content,
                    )
                    db.add(entry)
                    db.commit()
                    record(True, "saved", f"✓ Knowledge saved: {category}", key=category)

        except Exception as exc:
            record(False, "error", f"⚠️ Failed to save knowledge: {exc}", key=key)

        cleaned = cleaned.replace(match.group(0), "")

    return cleaned.strip(), actions_taken, write_results


# ---------- capability update parsing (adaptation loop, §7) ----------

def _process_capability_updates(
    reply: str,
    user_id: int,
    db: Session,
) -> tuple[str, list[str]]:
    """
    Scan `reply` for <capability_update> blocks and apply each as a §7 response
    tag against the capability map. Payload:
        {region_key, side?, tag, probe_result?, signal_text?}
    where tag is one of absorbed_clean | symptom_carryover | flare | capability_revealed.
    """
    actions_taken: list[str] = []
    matches = list(_CAPABILITY_BLOCK_RE.finditer(reply))
    if not matches:
        return reply, actions_taken

    cleaned = reply
    for match in matches:
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            actions_taken.append(f"⚠️ Could not parse capability update: {exc}")
            cleaned = cleaned.replace(match.group(0), "")
            continue
        try:
            row = adaptation.apply_response(
                db, user_id,
                region_key=data["region_key"],
                side=data.get("side", "bilateral"),
                tag=data["tag"],
                probe_result=data.get("probe_result"),
                signal_text=data.get("signal_text"),
                source=data.get("source", "probe"),
            )
            actions_taken.append(f"✓ Capability logged: {row.region_key}/{row.side} → {row.status}")
        except (KeyError, ValueError) as exc:
            actions_taken.append(f"⚠️ Could not log capability: {exc}")
        cleaned = cleaned.replace(match.group(0), "")

    return cleaned.strip(), actions_taken


# ---------- narrate-after-write (Q143a / WS4 in-repo gate) ----------

# The conversational reply is produced in ONE pass, BEFORE any write executes (see the
# endpoint). So a "saved" the model writes into that prose PRECEDES the outcome it claims —
# the exact gloss the origin transcript showed: a rugby-retire narrated as done while the
# `active` block was mis-nested and the write was in fact refused. #283 made each write's
# outcome machine-checkable (`WriteResult.saved`); this closes the loop on the NARRATION.
# If any write failed, the pre-write prose is discarded and a bounded second pass
# regenerates a reply that reports the true per-row outcome. A deterministic footer,
# computed from `write_results`, is the hard floor under both passes.

# Affordance is TYPE-DERIVED from the reason_code — never parsed from prose, the same
# discipline as the codes themselves. A user-resolvable clash offers the supersedes/
# distinct_from path; a bug code is a fault on OUR side and must never be handed back to
# the user to fix. `needs_disambiguation` is not emitted today (the current vocab is in
# `WriteResult`); it is carried here so a future code lands in the right bucket by default.
# `already_exists` (Hevy routine collision, Q144) is user_resolvable: the user chooses
# rename vs update, exactly like a schedule day_time_clash. `unresolved_exercise` and
# `create_failed` are neither — they fall to `informational` (stated plainly), the routine
# lane's honest default.
_USER_RESOLVABLE_CODES = frozenset({"day_time_clash", "needs_disambiguation", "already_exists"})
# `invalid_number` (a non-finite/non-number in a routine numeric field, Q144 follow-up) is a
# malformed-payload fault on our side, like invalid_shape/invalid_json — never handed to the
# user to fix.
_SYSTEM_BUG_CODES = frozenset({"unknown_field", "invalid_shape", "invalid_json", "error", "invalid_number"})


def _write_affordance(reason_code: str) -> str:
    if reason_code in _USER_RESOLVABLE_CODES:
        return "user_resolvable"
    if reason_code in _SYSTEM_BUG_CODES:
        return "system_issue"
    return "informational"  # e.g. not_found — nothing matched; state it plainly


# Short, user-facing phrase per code for the deterministic footer. Falls back to the raw
# code so a member added to the vocab upstream still renders (never a KeyError).
_FOOTER_REASON_PHRASE = {
    "day_time_clash": "day/time clash",
    "needs_disambiguation": "needs disambiguation",
    "unknown_field": "unknown field",
    "invalid_shape": "invalid shape",
    "invalid_json": "invalid format",
    "not_found": "no matching entry",
    "error": "system error",
    # Hevy routine lane (Q144)
    "already_exists": "already exists",
    "unresolved_exercise": "unresolved exercise",
    "create_failed": "create failed",
    "invalid_number": "invalid number",
    # Hevy exercise lane (Q144 — the last un-wrapped write surface)
    "already_present": "already present",
    "limit_reached": "limit reached",
    "invalid_exercise_field": "rejected by Hevy",
    "created_unconfirmed": "created (unconfirmed)",
}


def _has_failed_write(write_results: list[WriteResult]) -> bool:
    return any(not r.saved for r in write_results)


def _render_write_footer(write_results: list[WriteResult]) -> str:
    """Deterministic status line for the knowledge/schedule write lane (always-on, Q143a).

    Empty when the turn wrote no `<knowledge_update>` blocks — the footer is a floor for
    write turns, not a banner on every reply. On an all-saved turn it is one terse line
    (`✓ 3 saved`); this is the cost the always-on fork accepts, and it is also what neuters
    the exotic "narrated a save it never emitted" case on a SUCCESS turn — the tally is
    computed from `write_results`, not from the prose. On a mixed/failed turn it names the
    saved/failed counts and the distinct failure reasons, so the floor tells the truth even
    if pass-2 itself misreports.
    """
    if not write_results:
        return ""
    saved = sum(1 for r in write_results if r.saved)
    failed = [r for r in write_results if not r.saved]
    if not failed:
        return f"✓ {saved} saved"
    reasons: list[str] = []
    for r in failed:
        phrase = _FOOTER_REASON_PHRASE.get(r.reason_code, r.reason_code)
        if phrase not in reasons:
            reasons.append(phrase)
    return f"⚠ {saved} saved, {len(failed)} failed — " + ", ".join(reasons)


# Pass-2 is bounded: it reproduces the turn's conversational content and corrects only the
# write claims, so it needs far fewer tokens than the open-ended first pass. Kept well below
# the first pass's 4096 to cap the added cost of the (failed-write only) second call.
_PASS2_MAX_TOKENS = 1024

_PASS2_SYSTEM = (
    "You are correcting your own draft reply in a health app. The draft was written "
    "BEFORE the outcomes were known, and some of the changes it described were NOT saved. "
    "Rewrite the reply so it is TRUE about what was saved.\n"
    "\n"
    "- Keep every piece of conversational and analytical content from the draft — advice, "
    "synthesis, and answers to what the user asked. Only the claims about what was SAVED "
    "may change.\n"
    "- Never state or imply a change was saved unless its outcome below says [SAVED].\n"
    "- For each [NOT SAVED] item, say plainly that it was not saved, in the user's terms.\n"
    "- Act on the affordance tag attached to each item:\n"
    "  - user_resolvable: the user must choose. State the clash and ask whether the new "
    "entry REPLACES the existing one or sits alongside it. Do not decide for them.\n"
    "  - system_issue: a fault on OUR side. Say briefly it wasn't recorded and that you'll "
    "sort it out. NEVER tell the user to fix a format, field, or block — they cannot see "
    "or edit one.\n"
    "  - informational: state the fact plainly (e.g. there was nothing matching to remove).\n"
    "- Do NOT append a tally or a '✓ N saved' line; that is added separately.\n"
)


def _pass2_user_content(
    user_message: str,
    pre_write_reply: str,
    write_results: list[WriteResult],
) -> str:
    """Render the pass-2 user turn: the ask, the draft to preserve, and the PER-ROW outcome.

    One line per result, never a roll-up — the failure mode was several blocks narrated as
    all-saved, so a batch summary here would re-open exactly that gap.
    """
    lines = []
    for r in write_results:
        status = "SAVED" if r.saved else "NOT SAVED"
        tag = "saved" if r.saved else _write_affordance(r.reason_code)
        key = r.key or "(unkeyed)"
        lines.append(f"- [{status} · {tag}] key={key} ({r.reason_code}): {r.reason}")
    outcomes = "\n".join(lines)
    return (
        f"The user said:\n{user_message}\n\n"
        f"Your draft reply (conversational content to preserve):\n{pre_write_reply}\n\n"
        f"The actual outcome of each write you requested:\n{outcomes}\n\n"
        "Rewrite your reply following the rules."
    )


# Fail-closed body if pass-2 itself errors: never re-emit the possibly-false draft prose.
# The truthful per-row action strings and the deterministic footer are appended after this,
# so the user still gets the real outcome.
_PASS2_FALLBACK = (
    "I ran into a problem finishing that — the outcome of each change is listed below."
)


def _narrate_after_write(
    *,
    client: Any,
    model: str,
    user_message: str,
    pre_write_reply: str,
    write_results: list[WriteResult],
) -> tuple[str, bool]:
    """Bounded second generation that reports the true write outcomes (Q143a / WS4).

    Client-injected so it is faked at the TRANSPORT layer in tests (#166 companion rule),
    never the live model. Returns (narration, second_call_fired). On any transport error the
    draft prose is DISCARDED for a fixed safe line — the floor (action strings + footer)
    still carries the truth, and a false "saved" never survives.
    """
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=_PASS2_MAX_TOKENS,
            system=_PASS2_SYSTEM,
            messages=[{
                "role": "user",
                "content": _pass2_user_content(user_message, pre_write_reply, write_results),
            }],
        )
        return resp.content[0].text, True
    except Exception as exc:  # noqa: BLE001 — degrade to the deterministic floor, never the draft
        logger.warning("narrate-after-write pass-2 failed, falling back to floor: %s", exc)
        return _PASS2_FALLBACK, True


def _compose_response(
    *,
    client: Any,
    model: str,
    user_message: str,
    reply: str,
    all_actions: list[str],
    write_results: list[WriteResult],
) -> tuple[str, bool]:
    """Assemble the final `response` text after writes have executed (Q143a / WS4).

    - Every write saved (or none attempted) → keep the pre-write `reply`, no second call.
    - Any write failed → discard the pre-write prose and regenerate it (pass-2).
    Then append the confirmation strings (unchanged from before) and the always-on
    deterministic footer. Returns (response_text, second_call_fired); the flag lets the
    caller and the gates assert the "+1 call on failed-write turns only" cost profile.
    """
    second_call_fired = False
    if _has_failed_write(write_results):
        reply, second_call_fired = _narrate_after_write(
            client=client,
            model=model,
            user_message=user_message,
            pre_write_reply=reply,
            write_results=write_results,
        )

    if all_actions:
        reply = reply + "\n\n" + "\n".join(all_actions)

    footer = _render_write_footer(write_results)
    if footer:
        reply = reply + "\n\n" + footer

    return reply, second_call_fired


# ---------- endpoint ----------

@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY is not configured",
        )

    # Expire stale knowledge entries (piggyback on chat request, no separate cron needed)
    expire_stale_entries(current_user.id, db)

    # Discover which integrations the user has connected
    integrations = db.query(models.UserIntegration).filter_by(user_id=current_user.id).all()
    connected = {row.provider: row for row in integrations}

    hevy_data: dict[str, Any] | None = None
    hevy_client: HevyClient | None = None
    exercise_catalogue: list[tuple[str, bool]] | None = None
    if "hevy" in connected:
        raw_key = decrypt(connected["hevy"].api_key_encrypted)
        hevy_data = await _gather_hevy_context(raw_key)
        _annotate_canonical_titles(hevy_data, db)
        hevy_client = HevyClient(raw_key)
        # Read HERE, not in context_builder — that module is a pure formatter and gets no
        # Session (the #43 parity-guard invariant), same reason _annotate_canonical_titles
        # runs upstream. It renders whatever we hand it.
        exercise_catalogue = catalogue_titles(db, current_user.id)

    knowledge_entries = (
        db.query(models.UserKnowledge)
        .filter_by(user_id=current_user.id)
        .order_by(models.UserKnowledge.category, models.UserKnowledge.created_at)
        .all()
    )

    import pytz
    from datetime import datetime as _dt
    today_aest = _dt.now(pytz.timezone("Australia/Brisbane")).date()
    today_checkin = (
        db.query(models.DailyCheckIn)
        .filter_by(user_id=current_user.id, date=today_aest)
        .first()
    )
    daily_record = (
        db.query(models.DailyRecord)
        .filter_by(user_id=current_user.id, date=today_aest)
        .first()
    )

    from datetime import timedelta as _td
    hc_since = today_aest - _td(days=2)  # today + yesterday
    health_connect_records = (
        db.query(models.HealthConnectSync)
        .filter(
            models.HealthConnectSync.user_id == current_user.id,
            models.HealthConnectSync.date >= hc_since,
        )
        .order_by(models.HealthConnectSync.date.desc())
        .all()
    )

    # Samsung Galaxy Ring scraper readings from the last 7 days (HRV/sleep,
    # extracted on-device). Latest first; used for a rolling HRV baseline.
    samsung_window_start = today_aest - _td(days=7)
    samsung_readings = (
        db.query(models.SamsungHRVReading)
        .filter(
            models.SamsungHRVReading.user_id == current_user.id,
            models.SamsungHRVReading.captured_at >= samsung_window_start,
            models.SamsungHRVReading.context != 'session',
        )
        .order_by(models.SamsungHRVReading.captured_at.desc())
        .all()
    )

    # Compute-on-read current-state (DECISIONS_LOG #43): active structured
    # knowledge entries, fortification profile, capability state, HRV baseline.
    state = compute_current_state(current_user.id, db, today=today_aest)

    # ---- Adaptive Exposure Engine: fortification profile + session selection ----
    # Avoidance signal (§4) reads from what the user loads in Hevy; the rest of the
    # taxonomy is the candidate deficiency set. Readiness only re-ranks vehicles,
    # never gates (DECISIONS_LOG #8).
    fort_profile = state.fortification_profile_orm
    engine_selection = None
    if fort_profile is not None:
        loaded_regions = selection.infer_loaded_regions(
            (hevy_data or {}).get("recent_workouts", []), db=db
        )
        probe_queue = selection.compute_probe_queue(
            db, current_user.id, profile=fort_profile, loaded_region_keys=loaded_regions,
        )
        if daily_record is not None and daily_record.morning_readiness is not None:
            readiness_hint = int(daily_record.morning_readiness) * 2  # 1–5 → 1–10
        elif today_checkin is not None and today_checkin.readiness_score is not None:
            readiness_hint = int(today_checkin.readiness_score)
        else:
            readiness_hint = None
        engine_selection = selection.select_next(
            db, current_user.id, profile=fort_profile,
            probe_queue=probe_queue, readiness_hint=readiness_hint,
        )

    system_prompt = build_system_prompt(
        user=current_user,
        connected_integrations=list(connected.keys()),
        state=state,
        hevy_data=hevy_data,
        knowledge_entries=knowledge_entries,
        today_checkin=today_checkin,
        health_connect_records=health_connect_records,
        samsung_hrv=samsung_readings,
        daily_record=daily_record,
        engine_selection=engine_selection,
        exercise_catalogue=exercise_catalogue,
    )

    # On-ask lab value relay (#60): standing feed above is generality-only.
    # If the user's current message explicitly names a marker they have on
    # file, append the one value for THIS turn only — never merged into the
    # standing render, and it re-triggers per-message rather than persisting.
    asked_marker = find_marker(state.labs, body.message)
    if asked_marker is not None:
        system_prompt += "\n\n" + render_asked_lab_value(asked_marker)

    # Build messages list: history + current user message
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in body.conversation_history
    ]
    messages.append({"role": "user", "content": body.message})

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=messages,
    )

    reply = response.content[0].text

    # Parse and execute any embedded action blocks.
    # Exercise creation runs FIRST and the order is load-bearing: a custom minted this
    # turn must be in the catalogue before the routine block's `_resolve_missing_ids`
    # looks for it by title. The model cannot cite a server-minted UUID it has never
    # seen, so same-turn create-then-use resolves only in this order.
    reply, exercise_actions, exercise_write_results = await _process_exercise_actions(
        reply, current_user.id, db)
    reply, routine_actions, routine_write_results = await _process_routine_actions(
        reply, hevy_client, current_user.id, db)
    reply, knowledge_actions, knowledge_write_results = _process_knowledge_updates(
        reply, current_user.id, db)
    reply, capability_actions = _process_capability_updates(reply, current_user.id, db)

    all_actions = exercise_actions + routine_actions + knowledge_actions + capability_actions
    # Every Hevy write lane (exercise + routine) and the knowledge/schedule lane are now
    # mapped onto WriteResult (Q144 folds the last one, the exercise-action lane); one
    # combined list drives the single narrate-after-write pass and the deterministic footer.
    # The acknowledgement-discipline arc (schedule / /chat / Hevy routine / Hevy exercise)
    # is complete — no string-only write lane remains.
    all_write_results = exercise_write_results + routine_write_results + knowledge_write_results

    # Narrate-after-write (Q143a / WS4). `reply` was generated in the single pass above,
    # BEFORE these writes executed, so any "saved" it claims precedes the outcome. If every
    # write (routine + knowledge/schedule) saved, that prose is already true and is kept
    # unchanged (no second call). If any failed, the prose is discarded and regenerated to
    # report the true per-row outcome. Either way the confirmation strings and the always-on
    # deterministic footer are appended — the footer is the hard floor if pass-2 itself
    # misreports. The SAME `client` is reused for the bounded second call.
    reply, _second_call_fired = _compose_response(
        client=client,
        model=MODEL,
        user_message=body.message,
        reply=reply,
        all_actions=all_actions,
        write_results=all_write_results,
    )

    # `write_results` is the machine-checkable outcome of the write lanes — a client (or a
    # later turn) hard-gates on `saved` rather than trusting the reply's prose. Every write
    # lane is mapped onto this shape now: knowledge/schedule (#283), Hevy routine (#286), and
    # Hevy exercise (Q144, this arc). No string-only write lane remains.
    return ChatResponse(
        response=reply,
        actions_taken=all_actions,
        write_results=all_write_results,
    )
