"""Training-phase ledger API (Q112, #270) — the exposure engine's DOING-NOW axis.

Endpoints (mounted at /engine/phase):
  POST /engine/phase/transition — the ONE way a phase is entered (#378): close the outgoing phase,
                                  open the new one, write the schedule and folder, atomically
  POST /engine/phase/close    — close the current open phase to zero-open baseline
  GET  /engine/phase          — the current open phase | null, with review_due
  GET  /engine/phase/history  — every phase for the user, newest first, each with `zero_length`

Write paths are fail-closed (422 on shape, 404 on close-with-nothing-open). The ledger is
append-only: the only mutation any of these performs is setting `closed_on` / `close_reason`
at closure. Selection reads the open phase in `/engine/next` (see `routers/engine.py`); this
router owns authorship and history.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from connectors.hevy import HevyAuthError, HevyClient
from database import get_db
from encryption import decrypt
from engine import resolver as resolver_mod
from engine import training_phase as phase_mod
from engine import week_plan as week_plan_mod
from load_metrics import _local_day
from reads.aerobic_reads import sport_names_seen
from routers.knowledge import (
    KnowledgeEntryIn,
    ScheduleItemInvalid,
    ScheduleItemOverlap,
    _stage_upsert_entry,
)

router = APIRouter(prefix="/engine/phase", tags=["engine"])

# The phase→Hevy-folder declaration (#314) is a `preference` entry under this fixed key; the
# transition merges {label: folder_id} into it. Same key `current_state`/chat read.
_PHASE_FOLDERS_KEY = "phase_folders"


class PhaseIn(BaseModel):
    """The STORE fields minus id/closed_on/close_reason/created_at/updated_at, plus the
    optional `close_prior_reason` control. `source` and `asserted_by` are mandatory with no
    defaults (#227/#230); `entered_on` defaults to the operator-local day when omitted."""
    label: str
    intent: str | None = None
    probe_posture: str
    capacities: list[str] | None = None
    microcycle: dict[str, Any] | None = None
    entered_on: str | None = None
    review_on: str | None = None
    asserted_by: str
    asserted_on: str
    source: str
    # Closing note for the phase this open supersedes; default "opened <label>".
    close_prior_reason: str | None = None


class CloseIn(BaseModel):
    close_reason: str


@router.post("/close")
def close_phase(
    body: CloseIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        phase = phase_mod.close_phase(db, current_user.id, body.close_reason)
    except phase_mod.NoOpenPhase as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return {"training_phase": phase_mod.phase_to_dict(phase)}


@router.get("")
def get_current_phase(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    phase = phase_mod.current_training_phase(db, current_user.id)
    return {"training_phase": phase_mod.phase_to_dict(phase)}


@router.get("/history")
def get_phase_history(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(models.TrainingPhase)
        .filter_by(user_id=current_user.id)
        .order_by(
            models.TrainingPhase.entered_on.desc(),
            models.TrainingPhase.id.desc(),
        )
        .all()
    )
    # `zero_length` is DERIVED here and only here (#379): a same-day correction closes the row it
    # replaces on the day that row was entered, so it never covered a day. The row stays in the
    # ledger (append-only); the flag lets the card label it. Not on `phase_to_dict`, so the current
    # phase read is unchanged.
    return {"history": [
        {**phase_mod.phase_to_dict(r), "zero_length": r.closed_on is not None and r.closed_on == r.entered_on}
        for r in rows
    ]}


# --------------------------------------------------------------------------- #
# Phase transition (#317) — the single atomic write behind the phase-change form.
# --------------------------------------------------------------------------- #

class ScheduleOpIn(BaseModel):
    """One schedule-item op in a transition. `upsert` supersedes-by-key with `value` (a full
    `schedule_item` value, validated by the existing validator); `retire` deactivates the active
    row for `key`. Unchanged items are simply not listed (ruling 2 — left untouched)."""
    action: str            # "upsert" | "retire"
    key: str
    value: dict[str, Any] | None = None


class PhaseTransitionIn(BaseModel):
    """The form's single confirm. `phase` opens the new phase (and closes the outgoing one, via the
    shared `_apply_open_phase`); `schedule_items` are the ops; a folder is either an existing
    `folder_id` or a `new_folder_name` to create (outside the transaction, only AFTER a validate-only pass, the 4 Oct 2026 ruling)."""
    phase: PhaseIn
    schedule_items: list[ScheduleOpIn] = []
    folder_id: str | None = None
    new_folder_name: str | None = None


def _resolve_entered_on(phase_payload: dict[str, Any]) -> date:
    raw = phase_payload.get("entered_on")
    return _local_day() if raw is None else date.fromisoformat(str(raw))


def _matching_open_phase(db: Session, user_id: int, phase_payload: dict[str, Any]):
    """Natural-state idempotency (ruling 3): the user's OPEN phase, if it already deep-equals the
    submitted label + entered_on + microcycle. Cross-worker and non-schema — a re-submit of an
    identical transition matches here and writes NOTHING (not even a second folder create)."""
    current = phase_mod.current_training_phase(db, user_id)
    if current is None:
        return None
    try:
        entered = _resolve_entered_on(phase_payload)
    except (ValueError, TypeError):
        return None
    if (current.label == phase_payload.get("label")
            and current.entered_on == entered
            and current.microcycle == phase_payload.get("microcycle")):
        return current
    return None


# A stand-in folder id for the validate-only pass: the `phase_folders` preference is staged (and so
# validated) with it, then the whole pass is rolled back. Never stored; never sent to Hevy.
_DRY_RUN_FOLDER_ID = "dry-run"


def _apply_phase_transition(
    db: Session, user_id: int, *,
    phase_payload: dict[str, Any],
    schedule_ops: list[ScheduleOpIn],
    folder_id: str | None,
    commit: bool = True,
) -> models.TrainingPhase:
    """ONE transaction (G1): stage the close-outgoing + open-new (shared `_apply_open_phase`), the
    schedule retires (first, flushed) then upserts, and the `phase_folders` merge — then a single
    commit. Any ValueError / overlap rolls the WHOLE set back (the caller does `db.rollback()`), so
    a rejected part writes nothing. Retires precede upserts so a replacement item does not collide
    on the overlap check with the row it replaces.

    `commit=False` is the VALIDATE-ONLY pass (the route runs it before any external call): every
    validator and overlap check runs exactly as in the real write, the rows are staged and flushed,
    and the caller rolls the session back. One code path, so "validated" cannot drift from "writable"."""
    phase = phase_mod._apply_open_phase(db, user_id, phase_payload)   # stages close+open; may raise

    for op in schedule_ops:
        if op.action == "retire":
            row = (
                db.query(models.UserKnowledgeEntry)
                .filter_by(user_id=user_id, key=op.key, active=True)
                .first()
            )
            if row is not None:
                row.active = False
        elif op.action != "upsert":
            raise ValueError(
                f"schedule item {op.key!r}: unknown action {op.action!r} (one of 'upsert', 'retire')"
            )
    db.flush()

    for op in schedule_ops:
        if op.action == "upsert":
            if not isinstance(op.value, dict):
                raise ValueError(f"schedule item {op.key!r}: 'upsert' requires a value object")
            try:
                _stage_upsert_entry(
                    user_id,
                    KnowledgeEntryIn(type="schedule_item", key=op.key, value=op.value, source="api"),
                    db,
                )
            except ScheduleItemOverlap as exc:
                # Name the offending op so the form can render F17 (the clash) and offer to
                # resubmit that specific row with `distinct_from`. The rows the write collides
                # with already ride on `exc.overlapping`.
                exc.key = op.key
                raise

    if folder_id is not None:
        existing = (
            db.query(models.UserKnowledgeEntry)
            .filter_by(user_id=user_id, type="preference", key=_PHASE_FOLDERS_KEY, active=True)
            .first()
        )
        mapping = dict(existing.value) if (existing and isinstance(existing.value, dict)) else {}
        mapping[phase_payload.get("label")] = folder_id
        _stage_upsert_entry(
            user_id,
            KnowledgeEntryIn(type="preference", key=_PHASE_FOLDERS_KEY, value=mapping, source="api"),
            db,
        )

    if not commit:
        db.flush()
        return phase
    db.commit()
    db.refresh(phase)
    return phase


def _transition_error(exc: Exception, *, orphan_folder: str | None) -> HTTPException:
    """The 422 for a rejected transition. `orphan_folder` is passed ONLY when a Hevy folder was
    actually created before the failure, so a validation refusal never talks about an orphan."""
    if isinstance(exc, ScheduleItemOverlap):
        # STRUCTURED 422 (F17): a day+time clash carries the colliding rows (id / activity /
        # days / time_of_day) and the offending schedule key, so the form can name the clash
        # and offer "these are separate sessions" -> a `distinct_from` resubmit. `error` keeps a
        # readable string for any caller that does not special-case the structure.
        detail: dict[str, Any] = {
            "code": exc.code,
            "error": str(exc),
            "key": getattr(exc, "key", None),
            "overlapping": exc.overlapping,
            "resolve_with": ["distinct_from"],
        }
        if orphan_folder:
            detail["orphan_folder"] = orphan_folder
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    detail_str = str(exc)
    if orphan_folder:
        detail_str += (f" — NOTHING was written, but the Hevy folder "
                       f"'{orphan_folder}' was already created (orphan; reuse or delete it)")
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail_str)


@router.post("/transition")
async def phase_transition(
    body: PhaseTransitionIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The phase-change form's single confirm. ONE atomic write closes the outgoing phase, opens the
    new one, writes the schedule items and the `phase_folders` entry. Order of operations (the 4 Oct 2026
    ruling, superseding #317's folder-first order): (1) natural-state idempotency; (2) when a NEW folder is
    asked for, a VALIDATE-ONLY pass of the whole transaction (rolled back), so a refused form never
    reaches Hevy; (3) the Hevy folder create, the ONLY external call, so its failure writes nothing;
    (4) the real transaction. A failure at (4) can now only be a database fault or a race, and names
    the created folder as an orphan (the Hevy API has no folder delete, so it cannot be undone from
    here). A re-submit identical to the open phase returns it 200 and writes nothing (no second
    folder)."""
    phase_payload = body.phase.model_dump(exclude_unset=True)

    # (1) Idempotency FIRST — before any folder create (ruling 3).
    match = _matching_open_phase(db, current_user.id, phase_payload)
    if match is not None:
        return {"training_phase": phase_mod.phase_to_dict(match), "no_op": True}

    folder_id = body.folder_id
    if body.new_folder_name:
        integ = (
            db.query(models.UserIntegration)
            .filter_by(user_id=current_user.id, provider="hevy")
            .first()
        )
        if integ is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="cannot create a Hevy folder — Hevy is not connected")

        # (2) Validate the WHOLE write before the only external call. Same code path as the real
        # write, rolled back: nothing is kept, and nothing has left the building if it refuses.
        try:
            _apply_phase_transition(
                db, current_user.id,
                phase_payload=phase_payload,
                schedule_ops=body.schedule_items,
                folder_id=_DRY_RUN_FOLDER_ID,
                commit=False,
            )
        except (ScheduleItemOverlap, ValueError) as exc:
            db.rollback()
            raise _transition_error(exc, orphan_folder=None)
        db.rollback()   # the validate-only pass never keeps a row

        # (3) Hevy folder create (the only external call); abort clean on failure.
        try:
            client = HevyClient(decrypt(integ.api_key_encrypted))
            created = await client.create_routine_folder(body.new_folder_name)
        except (HevyAuthError, Exception) as exc:  # abort clean — nothing written yet
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                                detail=f"Hevy folder create failed — nothing written: {exc}")
        folder_id = str((created.get("routine_folder") or created).get("id"))

    # (4) The single transaction. On failure, roll back; if a folder was created, name the orphan.
    try:
        phase = _apply_phase_transition(
            db, current_user.id,
            phase_payload=phase_payload,
            schedule_ops=body.schedule_items,
            folder_id=folder_id,
        )
    except (ScheduleItemOverlap, ValueError) as exc:
        db.rollback()
        raise _transition_error(exc, orphan_folder=body.new_folder_name or None)
    return {"training_phase": phase_mod.phase_to_dict(phase), "no_op": False}


def _outgoing_review(db: Session, user_id: int, phase: models.TrainingPhase, today: date) -> list[dict]:
    """Per-leg done/quota for the OUTGOING phase, replaying `resolve()` over the legs since
    `entered_on`. BOUNDED (GUARD/G4): `resolve()` is NEVER asked about a day before `entered_on` —
    the resolver clamps a pre-entry day to leg A and would report a phantom window for a time the
    phase did not exist. Windows dedup by start_date; one entry per elapsed leg."""
    entered = phase.entered_on
    scd = None
    if isinstance(phase.microcycle, dict):
        s = phase.microcycle.get("sub_cycle_days")
        if isinstance(s, int) and s > 0:
            scd = s
    step = scd or 7

    probe_days: list[date] = []
    d = entered
    while d <= today:
        probe_days.append(d)
        d += timedelta(days=step)
    if not probe_days or probe_days[-1] != today:
        probe_days.append(today)   # the current partial leg

    out: list[dict] = []
    seen: set[str] = set()
    for pd in probe_days:
        if pd < entered:           # the bound, restated — never resolve before entered_on
            continue
        pos = resolver_mod.resolve(db, user_id, today=pd)
        w = pos.get("window")
        if not w or w["start_date"] in seen:
            continue
        seen.add(w["start_date"])
        out.append({
            "window": w,
            "slots": [
                {"kind": s.get("kind"), "key": s.get(s.get("kind")),
                 "quota": s.get("quota"), "done": s.get("done")}
                for s in pos.get("slots", [])
            ],
            "uncounted": pos.get("uncounted", []),
        })
    return out


@router.get("/transition/draft")
async def phase_transition_draft(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Prefill for the phase-change form (S3) — pure read, no state. Outgoing per-leg review
    (bounded to ≥ entered_on), the active hard/soft schedule items, the user's `sport_names_seen`
    pick-list, device-ingest freshness, and (best-effort) the Hevy routine folders."""
    today = _local_day()
    phase = phase_mod.current_training_phase(db, current_user.id)

    entries = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=current_user.id, active=True)
        .all()
    )
    # `id` (F8) so the form can render each active item for keep / relink / retire and, on an
    # overlap, acknowledge the colliding row by id via `distinct_from`. `value` already carries
    # `satisfies` and `hard`, so the form splits hard-first without a second field.
    schedule_items = [
        {"id": e.id, "key": e.key, "value": e.value}
        for e in entries if e.type == "schedule_item"
    ]

    folders: list[dict[str, Any]] | None = None
    integ = (
        db.query(models.UserIntegration)
        .filter_by(user_id=current_user.id, provider="hevy")
        .first()
    )
    if integ is not None:
        try:
            client = HevyClient(decrypt(integ.api_key_encrypted))
            data = await client.get_routine_folders()   # returns a LIST (connector normalises)
            folders = [
                {"id": str(f.get("id")), "title": f.get("title")}
                for f in (data or []) if isinstance(f, dict)
            ]
        except (HevyAuthError, Exception):
            folders = None   # best-effort; the form offers "new folder" regardless

    return {
        "current_phase": phase_mod.phase_to_dict(phase, on=today),
        "outgoing_review": _outgoing_review(db, current_user.id, phase, today) if phase else [],
        "schedule_items": schedule_items,
        "sport_names_seen": sport_names_seen(current_user.id, db),
        "routine_folders": folders,
        # The closed vocabularies the step-4 slot pickers offer, from the validator's own source, so
        # the form never keeps a copy that can drift (a free-text key was the 4 Oct refusal).
        "slot_options": phase_mod.slot_options(),
        "freshness": week_plan_mod._freshness(db, current_user.id, today),
        # The outgoing window's per-day availability + `caution: day after heavy` (F12), so
        # step 5 can show which days a hard commitment blocks. `None` at baseline (no window).
        "week_plan": week_plan_mod.plan_week(db, current_user.id, today, entries=entries),
    }


class TransitionPreviewIn(BaseModel):
    """The step-5 counter's live inputs (F9): the PROPOSED quota slots and the schedule-item
    values that would be active after this transition (kept-and-linked existing items + the new
    rows). The server computes `consistency_rows` — the ONE definition `plan_week` and the chat
    consistency line already share — so the form never re-derives "scheduled" client-side (the B3
    fault). `done` is 0: a not-yet-opened phase has recorded nothing, and placement parity (F9/G4)
    turns on scheduled-vs-quota only."""
    slots: list[dict[str, Any]] = []            # {kind, key, quota}
    schedule_item_values: list[dict[str, Any]] = []


@router.post("/transition/preview")
def phase_transition_preview(
    body: TransitionPreviewIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pure derivation, no state (F9). Normalises the form's `{kind, key, quota}` slots into the
    `consistency_rows` slot shape and returns the per-slot scheduled/quota/excess/unplaced for the
    kept+proposed set. Same definition the backend uses everywhere, so the counter cannot drift
    from what the phase will actually read (B3)."""
    norm = [
        {"kind": s.get("kind"), s.get("kind"): s.get("key"),
         "quota": s.get("quota") or 0, "done": 0}
        for s in body.slots if s.get("kind")
    ]
    return {"consistency_rows": week_plan_mod.consistency_rows(norm, body.schedule_item_values)}
