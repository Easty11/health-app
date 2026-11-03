"""An injury's legacy `restrictions[]` → advisory constraint PROPOSALS, one injury at a time
(DECISIONS_LOG "Restrictions become constraint proposals from the injury card"; PR-B of the
injury-lifecycle-in-app brief).

This is the S6 seed script's planning logic (`scripts/seed_constraints.py`, #342, retired by this
module) as a pure planner plus a writer, called by `POST /knowledge/injuries/{id}/propose-constraints`.
One change from S6: the rows are written as PROPOSALS — `status: "proposed"`, `asserted_by: null`,
`review_by` = today + 28 days — and the operator confirms them on the Injuries card, which is the act
the script's `--confirm` flag stood in for. Nothing here confirms anything.

Per restriction string of ONE active injury:

    scope      {"tier": "advisory", "text": <the restriction, verbatim>}
    kind       "block"
    parent_key the injury's key;  exit {"with_parent": true}   (it ends when the injury resolves)
    review_by  <given>;  status "proposed";  asserted_by null

ENGINE-TIER ROWS ARE NEVER PLANNED. A restriction string is prose; an engine constraint comes only
from an explicit operator write or the engine-defaults planner. `injury.restrictions[]` is READ,
never modified (the injury shape, #493, keeps it byte-identical on a rewrite).

IDEMPOTENT on (parent_key, scope.text) across ALL of the user's constraint rows, active or not: an
existing match is reported under `existing` with its state (proposed / confirmed / declined) and
never re-created — a declined proposal (a resolved row) stays declined (the #340 seed-resurrection
lesson). Also reported, never written: the literal `ra_flare` token (an engine signal on the injury,
not an instruction) and a planned key already held by an active row of another shape.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

import models

ENGINE_TOKENS = ("ra_flare",)
# Operator ruling (#487, carried over): a proposal is due for review four weeks after it is written.
REVIEW_DAYS = 28
NOTE = "proposed from {parent}.restrictions by POST /knowledge/injuries/{{id}}/propose-constraints"


def slug(text: str) -> str:
    return "_".join(re.findall(r"[a-z0-9]+", text.lower()))[:60].rstrip("_") or "restriction"


def proposal_value(parent_key: str, text: str, review_by: date) -> dict[str, Any]:
    """The constraint value for one restriction. Passes `validate_constraint` unchanged."""
    return {
        "scope": {"tier": "advisory", "text": text},
        "kind": "block",
        "parent_key": parent_key,
        "exit": {"with_parent": True},
        "review_by": review_by.isoformat(),
        "status": "proposed",
        "asserted_by": None,
    }


def row_state(row: models.UserKnowledgeEntry) -> str:
    """How an existing cover reads on the card: a live proposal, a confirmed row, or a retired one
    (declined, ended, or superseded) — three states, never a fourth."""
    if not row.active:
        return "declined"
    return "confirmed" if (row.value or {}).get("status") == "confirmed" else "proposed"


def plan_restriction_proposals(
    db: Session, user_id: int, injury: models.UserKnowledgeEntry, review_by: date,
) -> dict[str, Any]:
    """Resolve one ACTIVE injury's restrictions into a plan. Writes nothing.

        planned   — [{key, text, value}]                     would be written, in restriction order
        existing  — [{text, key, id, state, status, active}] already covered (any state); never re-created
        skipped   — [{text, why}]                            the `ra_flare` token, or a key held by an
                                                             active row of another shape (never written)
    An inactive injury (resolved or superseded) plans nothing: its restrictions died with it.
    """
    out: dict[str, Any] = {"planned": [], "existing": [], "skipped": []}
    if injury.type != "injury" or not injury.active:
        return out
    restrictions = [str(r) for r in (injury.value or {}).get("restrictions") or []]
    if not restrictions:
        return out

    covers: dict[tuple[str | None, str | None], models.UserKnowledgeEntry] = {}
    for e in db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id, type="constraint").all():
        v = e.value or {}
        pair = (v.get("parent_key"), (v.get("scope") or {}).get("text"))
        prev = covers.get(pair)
        if prev is None or (e.active and not prev.active):   # the ACTIVE cover explains the skip
            covers[pair] = e
    active_keys = {
        e.key: e.id
        for e in db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id, active=True).all()
    }

    used: set[str] = set()
    for text in restrictions:
        if text.strip() in ENGINE_TOKENS:
            out["skipped"].append({"text": text, "why": "engine token, not an instruction"})
            continue
        hit = covers.get((injury.key, text))
        if hit is not None:
            out["existing"].append({
                "text": text, "key": hit.key, "id": hit.id, "state": row_state(hit),
                "status": (hit.value or {}).get("status"), "active": bool(hit.active),
            })
            continue
        base = f"constraint_{injury.key}_{slug(text)}"
        key, n = base, 2
        while key in used:
            key, n = f"{base}_{n}", n + 1
        if key in active_keys:
            out["skipped"].append({
                "text": text, "why": f"key {key} is held by active row #{active_keys[key]} of another shape",
            })
            continue
        used.add(key)
        out["planned"].append({"key": key, "text": text, "value": proposal_value(injury.key, text, review_by)})
    return out


def write_restriction_proposals(db: Session, user_id: int, injury_key: str, plan: dict[str, Any]) -> list[int]:
    """STAGE every planned row through the validated write path; the caller commits (one transaction)
    or rolls back. Returns the new ids in plan order."""
    from routers.knowledge import KnowledgeEntryIn, _stage_upsert_entry   # engine ↔ knowledge: function-local

    ids: list[int] = []
    for p in plan["planned"]:
        row = _stage_upsert_entry(user_id, KnowledgeEntryIn(
            type="constraint", key=p["key"], value=p["value"], source="system",
            notes=NOTE.format(parent=injury_key),
        ), db)
        ids.append(row.id)
    return ids


__all__ = [
    "ENGINE_TOKENS", "REVIEW_DAYS", "plan_restriction_proposals", "proposal_value", "row_state", "slug",
    "write_restriction_proposals",
]
