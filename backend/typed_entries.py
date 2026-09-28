"""Typed entries — the read half of `constraint` / `finding` (#342/#343).

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

from datetime import date
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


# ── rendering: one formatter for the chat section and the MCP snapshot ─────────
#
# The chat context and the MCP read the same rows through the lifts above; they also render them
# through the SAME line formatters below, so the two surfaces cannot drift into saying different
# things about one constraint.

AUTHORITY_LABELS = {
    "user": "set by you",
    "clinician": "set by your clinician",
    "engine": "set by the engine",
}

# G3 ruling: the findings section's standing budget, and the per-statement cap inside it (the #314
# routines pattern — overflow is NAMED, never dropped). The full row stays readable via
# `get_findings`. The Constraints section is deliberately UNBUDGETED: a constraint that does not
# render cannot be obeyed.
FINDINGS_CHAR_BUDGET = 2_000
FINDING_STATEMENT_MAX_CHARS = 280


def active_keys(entries: list[models.UserKnowledgeEntry]) -> set[str]:
    return {e.key for e in entries if _active(e)}


def parse_date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None


def constraint_due_tags(c: dict[str, Any], live_keys: set[str], today: date) -> list[str]:
    """Surfacing only (#223): a passed exit or review never lifts a constraint — it tags it for
    the operator, who resolves it. `exit due` fires on a passed `exit.on_date` or a `with_parent`
    exit whose parent is no longer active; `review due` on a passed `review_by`."""
    tags: list[str] = []
    exit_ = c.get("exit") or {}
    on_date = parse_date(exit_.get("on_date"))
    parent_gone = exit_.get("with_parent") is True and c.get("parent_key") not in live_keys
    if (on_date is not None and on_date <= today) or parent_gone:
        tags.append("exit due")
    review_by = parse_date(c.get("review_by"))
    if review_by is not None and review_by <= today:
        tags.append("review due")
    return tags


def constraint_line(c: dict[str, Any], live_keys: set[str], today: date) -> str:
    """One constraint, with its tier, scope, exit, review date and — always — its authority."""
    scope = c.get("scope") or {}
    kind = str(c.get("kind") or "").upper()
    if scope.get("tier") == "engine":
        side = scope.get("side") or "bilateral"
        side_str = "" if side == "bilateral" else f", {side} side only"
        what = f"{kind} (engine-enforced) — regions: {', '.join(scope.get('region_keys') or [])}{side_str}"
    else:
        what = f"{kind} (advisory — not engine-enforced) — {scope.get('text')}"
    exit_ = c.get("exit") or {}
    exits = []
    if exit_.get("on_date"):
        exits.append(f"on {exit_['on_date']}")
    if exit_.get("on_condition"):
        exits.append(f"when {exit_['on_condition']}")
    if exit_.get("with_parent") is True:
        exits.append(f"when {c.get('parent_key')} is resolved")
    authority = AUTHORITY_LABELS.get(c.get("asserted_by"), f"asserted by {c.get('asserted_by')}")
    line = (f"- {what} — ends {' or '.join(exits)} — review by {c.get('review_by')} — {authority}"
            f" [{c.get('key')}]")
    if c.get("detail"):
        line += f" — {c['detail']}"
    tags = constraint_due_tags(c, live_keys, today)
    if tags:
        line += " [" + ", ".join(tags).upper() + "]"
    return line


def _cap_statement(s: Any) -> str:
    s = str(s or "")
    if len(s) <= FINDING_STATEMENT_MAX_CHARS:
        return s
    return s[:FINDING_STATEMENT_MAX_CHARS].rstrip() + "…"


def finding_line(f: dict[str, Any], *, full: bool = False) -> str:
    """One finding: `as_of` and status always visible. `full=True` (the MCP read tool) carries
    the whole statement and its basis; the standing chat section caps the statement."""
    bits = [str(f.get("as_of")), str(f.get("status"))]
    if f.get("marker_status"):
        bits.append(f"marker: {f['marker_status']}")
    stmt = str(f.get("statement") or "") if full else _cap_statement(f.get("statement"))
    line = f"- [{' · '.join(bits)}] {stmt}"
    if f.get("parent_key"):
        line += f" (re: {f['parent_key']})"
    authority = AUTHORITY_LABELS.get(f.get("asserted_by"))
    if authority:
        line += f" — {authority}"
    if full:
        basis = f.get("basis") or {}
        if basis.get("text"):
            line += f"\n  basis: {basis['text']}"
        for ev in basis.get("evidence") or []:
            line += f"\n  evidence: {ev.get('door')} {ev.get('ref')}"
        line += f"\n  [{f.get('key')}, domain {f.get('domain')}]"
    return line


def budget_findings(visible: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Split visible findings (already newest first) into full lines that fit the standing
    budget and the overflow, named by (capped) statement only. Stops at the first line that
    does not fit, so the rendered set is always a newest-first prefix — never a gap."""
    lines: list[str] = []
    used = 0
    for i, f in enumerate(visible):
        line = finding_line(f)
        if used + len(line) + 1 > FINDINGS_CHAR_BUDGET:
            return lines, [_cap_statement(o.get("statement")) for o in visible[i:]]
        lines.append(line)
        used += len(line) + 1
    return lines, []


def withheld_labs_line(n: int, where: str) -> str:
    return (f"- {n} lab-derived finding{'s' if n != 1 else ''} withheld — lab results are never "
            f"interpreted here; see the {where}.")
