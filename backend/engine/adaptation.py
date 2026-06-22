"""
The adaptation loop (spec §7) — graded exposure as an algorithm.

A logged session (fortify OR probe) carries a response tag; the tag updates the
map and the floor, and the next selection recomputes:

    absorbed_clean       → raise floor / widen exposure budget
    symptom_carryover    → hold; re-dose the same level
    flare                → stand down the provoking pattern (RA flare = both-ends)
    capability_revealed  → write the taxonomy region to pass or deficient (probe result)

Progression and probing both gate on demonstrated response — never the calendar,
never a pending appointment. Capability state is self-reported through the
education idiom (spec §12): the user logs that something "felt unstable /
asymmetric / hard", not a clinician's screen score.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytz
from sqlalchemy.orm import Session

import models
from . import taxonomy
from .taxonomy import SIDE_BILATERAL, TAXONOMY_VERSION

AEST = pytz.timezone("Australia/Brisbane")

RESPONSE_TAGS = frozenset({
    "absorbed_clean", "symptom_carryover", "flare", "capability_revealed",
})
PROBE_RESULTS = frozenset({"pass", "deficient"})


def _today():
    return datetime.now(AEST).date()


def _get_or_create(db: Session, user_id: int, region_key: str, side: str) -> models.CapabilityState:
    row = (
        db.query(models.CapabilityState)
        .filter_by(user_id=user_id, region_key=region_key, side=side)
        .first()
    )
    if row is None:
        row = models.CapabilityState(
            user_id=user_id, region_key=region_key, side=side,
            status="untested", taxonomy_version=TAXONOMY_VERSION,
        )
        db.add(row)
    return row


def apply_response(
    db: Session,
    user_id: int,
    *,
    region_key: str,
    side: str = SIDE_BILATERAL,
    tag: str,
    probe_result: str | None = None,
    signal_text: str | None = None,
    source: str = "probe",
) -> models.CapabilityState:
    """Apply one §7 response tag to a (region, side). Returns the updated row.

    Raises ValueError on an unknown region/tag/result so the caller can 4xx —
    Probe must not write to a region that isn't on the axis list.
    """
    if taxonomy.by_key(region_key) is None:
        raise ValueError(f"unknown region_key: {region_key!r}")
    if tag not in RESPONSE_TAGS:
        raise ValueError(f"unknown response tag: {tag!r}")
    if tag == "capability_revealed" and probe_result not in PROBE_RESULTS:
        raise ValueError("capability_revealed requires probe_result in {'pass','deficient'}")

    row = _get_or_create(db, user_id, region_key, side)
    detail: dict[str, Any] = dict(row.detail or {})
    detail["last_tag"] = tag
    detail["last_tag_at"] = str(_today())
    if signal_text:
        detail["signal_text"] = signal_text
    detail.pop("stand_down", None)  # cleared unless this tag re-sets it

    if tag == "absorbed_clean":
        # Clean absorption: raise the floor. A clean probe with no explicit verdict
        # demonstrates capability → pass. An already-deficient region needs an
        # explicit capability_revealed to flip, so only lift untested/fortifying.
        if row.status in ("untested", "fortifying"):
            row.status = "pass"
        detail["floor_note"] = "absorbed clean — floor raised / budget may widen"
        row.source = source

    elif tag == "symptom_carryover":
        # Hold and re-dose the same level; status unchanged.
        detail["hold_note"] = "symptom carryover — hold, re-dose same level"

    elif tag == "flare":
        # Stand down the provoking pattern. Not a capability verdict — a load
        # response — so status is not flipped to deficient.
        detail["stand_down"] = True
        detail["flare_note"] = "flare — provoking pattern stood down (re-enters on clean response)"
        if row.status == "untested":
            row.source = source

    elif tag == "capability_revealed":
        row.status = probe_result          # 'pass' | 'deficient'
        row.source = source
        row.last_probed_at = _today()
        detail["revealed"] = probe_result

    row.detail = detail
    row.taxonomy_version = TAXONOMY_VERSION
    db.commit()
    db.refresh(row)
    return row


def coverage_summary(db: Session, user_id: int) -> dict[str, Any]:
    """How much of the axis list this user's map covers — the picture accreting
    over sessions (§2.1). Untested regions are implicit (no row)."""
    rows = db.query(models.CapabilityState).filter_by(user_id=user_id).all()
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r.status] = by_status.get(r.status, 0) + 1

    eligible = taxonomy.queue_eligible_regions()
    total_cells = sum(len(r.sides()) for r in eligible)
    tested_cells = sum(1 for r in rows if r.status != "untested")
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "by_status": by_status,
        "tested_cells": tested_cells,
        "queue_eligible_cells": total_cells,
        "coverage_pct": round(100 * tested_cells / total_cells, 1) if total_cells else 0.0,
    }
