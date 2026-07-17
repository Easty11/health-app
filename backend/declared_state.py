"""Declared-state ledger — the user's current stack as structured, queryable rows.

Three continuity-aware entry types in `user_knowledge_entries` — `protocol`
(pharma), `supplement`, `behavioural` — sharing one value schema:

    {"active": bool, "continuity": "continuous|episodic|stopped|never",
     "phase": str|None, "detail": str, "relevant_date": "YYYY-MM-DD"|None}

No migration: `type` is a free String(50).

WHY NOT backend/interpretation/: declared state is a Medical-module platform
concern, not an interpretation-specific one (context_builder has no structured
protocol either). Keeping it top-level also avoids two in-flight branches both
creating the `backend/interpretation/` package with different contents.

TWO SENSES OF "ACTIVE" — the distinction the whole module turns on:

  * `UserKnowledgeEntry.active` (the DB column) means "this DECLARATION is
    current". Every declared-state row is active=True, including the ones that
    declare a factor the user is NOT taking. "HGH — never used" and
    "tirzepatide — stopped, in washout" are both currently-true declarations.
  * `value["active"]` means "the user is CURRENTLY taking this".

They are not the same fact, and collapsing them breaks two things at once:
`current_state` loads only active=True rows, so a row-level-inactive factor
would never reach `declared_state` — making `tirzepatide -> washout`
underivable, which is precisely the distinction that makes a factor's
lab-relevance decidable. It would also break the seeder's idempotency: a skip
keyed on (user_id, key, active=True) never matches an inactive row, so every
re-run would duplicate it.

Supersession history is preserved in `value["active"]` (see
`ultra_muscleze_night`), not by deactivating the row.
"""
from __future__ import annotations

from datetime import date

import models

DECLARED_TYPES = ("protocol", "supplement", "behavioural")

CONTINUOUS = "continuous"
EPISODIC = "episodic"
STOPPED = "stopped"
NEVER = "never"


def derive_phase(entry: models.UserKnowledgeEntry, as_of: date) -> str | None:
    """Map a declared factor to its phase. Pure.

    Ordering is BY CONTINUITY, not by `value["active"]` — a stopped factor is
    still in a phase (washout/stopped) precisely because it is not being taken.
    Only a *continuous* factor that is no longer taken collapses to None: it is
    history (superseded), carrying no current phase.

    `as_of` is accepted and currently consumed by NO rule — deliberately, and
    the honest reason is worth stating rather than hiding behind a plausible
    default. Every window that would consume it (when does a washout end? when
    does titration become steady? when does re-entry become routine?) needs a
    clinical number, and this module authors none: the brief's own constraint is
    that a window must be declared by the entry, never hardcoded here. No seed
    entry declares one, so no window logic exists yet. The parameter is the seam
    those rules will use once an entry declares a window; until then a phase
    changes only when the declaration is rewritten.
    """
    value = entry.value or {}
    continuity = value.get("continuity")
    is_active = bool(value.get("active"))

    if continuity == STOPPED:
        # A dated stop is a washout; an undated one is just stopped. The date
        # is the anchor 4b needs; how long the washout lasts is a clinical
        # number this module does not own.
        return "washout" if value.get("relevant_date") else "stopped"

    if continuity == EPISODIC:
        return EPISODIC if is_active else None

    if continuity == CONTINUOUS:
        if not is_active:
            return None  # superseded / no longer taken — history, not a phase
        if entry.type == "behavioural" and value.get("relevant_date"):
            # The relevant_date IS the re-entry anchor; its presence is the
            # declaration. No window arithmetic — that would need a number.
            return "re_entering"
        return "steady"

    # NEVER, absent, or unrecognised continuity.
    return None


def is_assumable_present(phase: str | None) -> bool:
    """Can this factor be assumed present at an ARBITRARY lab draw, without a
    draw-specific call?

    True only for `steady`. The load-bearing case is `episodic`: an ad-hoc
    peptide is neither scheduled nor discontinued, so it must never be assumed
    present at a given draw — a bare `active` flag flattens exactly this.
    `washout` is False for the same reason: whether the agent is present at a
    draw depends on that draw's date against the last dose, which is a
    draw-specific resolution and out of scope here (it belongs to the draw, not
    to the factor).
    """
    return phase == "steady"


def _factor(entry: models.UserKnowledgeEntry, as_of: date) -> dict:
    value = entry.value or {}
    phase = derive_phase(entry, as_of)
    return {
        "key": entry.key,
        "type": entry.type,
        "active": bool(value.get("active")),
        "continuity": value.get("continuity"),
        "phase": phase,
        "assumable_present": is_assumable_present(phase),
        "detail": value.get("detail"),
        "relevant_date": value.get("relevant_date"),
    }


def lift_declared_state(entries: list[models.UserKnowledgeEntry], as_of: date) -> dict[str, list[dict]]:
    """Lift the declared-state factors out of an ALREADY-LOADED entries list —
    the same in-memory pass `device_profile` uses, adding zero DB queries.

    Always returns all three keys, so a consumer never branches on presence.
    """
    declared: dict[str, list[dict]] = {t: [] for t in DECLARED_TYPES}
    for entry in entries:
        if entry.type in declared:
            declared[entry.type].append(_factor(entry, as_of))
    return declared
