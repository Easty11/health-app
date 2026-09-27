"""Typed entries — the read half of `constraint` / `finding` (#NEXT).

Pure lifts over an ALREADY-LOADED list of `user_knowledge_entries` rows — the
`declared_state.lift_declared_state` pattern: zero queries of their own, so `current_state`
(the chat), the MCP tools and the engine can all read the same rows through one definition
(G0 ruling D3) without a second query path.

WHAT IS READ. Only `active=True` rows ever reach a lift (the caller loads active rows; a lift
re-checks rather than trusting it). Within those:
  * constraints — `status == "confirmed"` only. A proposal changes nothing anywhere.
  * findings    — `status in ("open", "confirmed")`. `proposed` never renders (G1 ruling 3);
                  `retracted` / `superseded` rows are inactive and never arrive.

THE #60 FIREWALL. A finding with `derived_from_labs: true` is an interpretation of a lab result,
which the coach must never state (`context_builder._section_labs`: "Never interpret a lab
result … direct the user to the Labs page"). Such findings are WITHHELD from the lift's visible
list and only counted, so a renderer can say that they exist and where to look without carrying
their statement (G0 ruling D2). There is deliberately no flag to include them. A finding is visible
only when `derived_from_labs` is explicitly `False`; absent or malformed degrades to withheld.
"""
from __future__ import annotations

from typing import Any

import models

CONSTRAINT_READ_STATUSES = ("confirmed",)
FINDING_READ_STATUSES = ("open", "confirmed")


def _active(entry: models.UserKnowledgeEntry) -> bool:
    return bool(getattr(entry, "active", True))


def _row(entry: models.UserKnowledgeEntry) -> dict[str, Any]:
    """The lifted shape: the stored value, verbatim, plus the row identity a reader cites."""
    return {"id": entry.id, "key": entry.key, "added_at": entry.added_at, **(entry.value or {})}


def lift_constraints(entries: list[models.UserKnowledgeEntry]) -> list[dict[str, Any]]:
    """Active, CONFIRMED constraints, in the order given (the caller's newest-first)."""
    return [
        _row(e) for e in entries
        if e.type == "constraint" and _active(e)
        and (e.value or {}).get("status") in CONSTRAINT_READ_STATUSES
    ]


def lift_findings(entries: list[models.UserKnowledgeEntry]) -> dict[str, Any]:
    """Active `open` / `confirmed` findings, newest `as_of` first (ties: newest row first), split
    into what may render and a COUNT of what the #60 firewall withholds.

    Always returns both keys, so a consumer never branches on presence.
    """
    readable = [
        e for e in entries
        if e.type == "finding" and _active(e)
        and (e.value or {}).get("status") in FINDING_READ_STATUSES
    ]
    readable.sort(key=lambda e: (str((e.value or {}).get("as_of") or ""), e.id or 0), reverse=True)
    # Visible only when EXPLICITLY not lab-derived: an absent or malformed flag (a row written
    # around the validator) degrades to withheld, never to rendered.
    visible = [_row(e) for e in readable if (e.value or {}).get("derived_from_labs") is False]
    return {"visible": visible, "withheld_labs": len(readable) - len(visible)}
