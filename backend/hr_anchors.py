"""The LTHR / RHR anchor writer — `user_hr_anchors` append, append-only (design 0010 §1, §6).

The ONE writer of `user_hr_anchors` (the Settings card's route calls it; nothing else constructs the
model). Mirrors `scripts/set_hrmax.py` for `user_hrmax`: every change is a NEW row, no row is ever
updated or deleted, and the two kinds of change are told apart by the caller's FORCED choice (R6):

* `change="dated"`: a value that genuinely changes with fitness. Applies from `effective_from` FORWARD
  only; a date that already has a dated row for the kind is REFUSED (restate it instead).
* `change="restate"`: a correction from better evidence about the same physiology. Carries the SAME
  `effective_from` as the row it corrects (the date must already have a row), stands in for that row over
  its whole span, reflows history. `rationale` is required. Restating an already-restated date corrects
  the latest of the chain. The no-op test is on (bpm, provenance), not bpm alone: provenance is part of
  the row's meaning (it drives the retest flag), so the same value re-evidenced under a new provenance is
  a real restatement; only a row identical in both is refused (#504).

`plan` (the bpm preview before commit, R6) reports, for today, each class's bpm edges before and after
the append, and the `aerobic_sessions` rows whose zone spec would change (count and ids), so the
operator sees what moves before anything is written. HRmax is NOT written here (`kind="hrmax"` is
refused, naming the script): the card reads it and shows the way.

After a write the caller forces the load chain (`POST /load/refresh?force=true`), which re-zones every
row and recomputes `metab-v2`.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from hr_zones import ANCHOR_KINDS, PLAUSIBLE_BPM, HrmaxEntry, resolve_zone_spec
from reads.zone_reads import HRMAX_WRITER, anchor_entries, anchor_rows, class_specs
from sport_classes import zone_basis_for

WRITABLE_KINDS = ("lthr", "rhr")
PROVENANCE = ("tested", "observed", "device_estimated", "stated")
CHANGES = ("dated", "restate")


class AnchorRefused(ValueError):
    """A refused write, with the way out in the message."""


def _restatement_target(rows: list, effective_from: date, kind: str) -> Any:
    on_date = [r for r in rows if r.effective_from == effective_from]
    if not on_date:
        earlier = [r for r in rows if r.effective_from < effective_from]
        hint = ""
        if earlier:
            latest = max(earlier, key=lambda r: r.effective_from)
            hint = f"; the {kind.upper()} in force then is dated {latest.effective_from}: restate that date"
        raise AnchorRefused(
            f"nothing to restate: no {kind.upper()} dated {effective_from}. A restatement carries the date of the "
            f"row it corrects; a new value from a new date is a dated change{hint}")
    restated = {r.restates_id for r in on_date if r.restates_id is not None}
    heads = [r for r in on_date if r.id not in restated]
    if len(heads) != 1:
        raise AnchorRefused(f"{len(heads)} unrestated {kind.upper()} rows dated {effective_from}; "
                            "the chain is not linear, refusing to guess")
    return heads[0]


def validate(*, kind: str, bpm: int, effective_from: date, provenance: str, note: str,
             change: str, rationale: Optional[str]) -> str:
    """Field-level checks shared by preview and append; returns the stripped rationale (or None)."""
    if kind == "hrmax":
        raise AnchorRefused(f"HRmax is not written here: it is `user_hrmax`, written only by {HRMAX_WRITER}")
    if kind not in WRITABLE_KINDS:
        raise AnchorRefused(f"kind must be one of {WRITABLE_KINDS}, got {kind!r}")
    if change not in CHANGES:
        raise AnchorRefused(f"change must be one of {CHANGES} (a dated change or a restatement), got {change!r}")
    if provenance not in PROVENANCE:
        raise AnchorRefused(f"provenance must be one of {PROVENANCE}, got {provenance!r}")
    lo, hi = PLAUSIBLE_BPM
    if not lo <= bpm <= hi:
        raise AnchorRefused(f"bpm {bpm} outside the plausibility bounds {lo}-{hi}")
    if not note or not note.strip():
        raise AnchorRefused("a note naming the evidence is required")
    r = rationale.strip() if rationale and rationale.strip() else None
    if change == "restate" and r is None:
        raise AnchorRefused("a restatement needs a rationale: why the value it corrects was wrong")
    return r


def plan(db: Session, user_id: int, *, kind: str, bpm: int, effective_from: date, provenance: str, change: str,
         today: date) -> dict[str, Any]:
    """The preview: today's bpm edges per class before and after, the rows whose spec changes, and the
    row a restatement corrects (None for a dated change). Raises `AnchorRefused` when the append would be.
    A restatement is a no-op, and refused, only when BOTH the value and the provenance match the row it
    would correct: a new provenance for the same value changes what the row means (the retest flag)."""
    rows = anchor_rows(db, user_id)
    target = None
    if change == "restate":
        target = _restatement_target(rows[kind], effective_from, kind)
        if target.bpm == bpm and target.provenance == provenance:
            raise AnchorRefused(f"{kind.upper()} dated {effective_from} is already {bpm} bpm, {provenance}; "
                                "a restatement to the same value and provenance changes nothing (the same value "
                                "under a different provenance is a restatement: it re-evidences the row)")
    else:
        dup = next((r for r in rows[kind] if r.effective_from == effective_from and r.restates_id is None), None)
        if dup is not None:
            raise AnchorRefused(
                f"a {kind.upper()} dated {effective_from} already exists ({dup.bpm} bpm, {dup.provenance}); rows are "
                f"append-only: use a later effective_from for a new value, or restate this one")
    before = anchor_entries(rows)
    after = {k: list(v) for k, v in before.items()}
    after[kind] = after[kind] + [HrmaxEntry(effective_from, bpm, id=None, restates=target.id if target else None)]

    touched = []
    sessions = (db.query(models.AerobicSession).filter(models.AerobicSession.user_id == user_id)
                .order_by(models.AerobicSession.session_date, models.AerobicSession.id).all())
    for s in sessions:
        basis = zone_basis_for(s.sport_name)
        kw_b = dict(hrmax_entries=before["hrmax"], lthr_entries=before["lthr"], rhr_entries=before["rhr"])
        kw_a = dict(hrmax_entries=after["hrmax"], lthr_entries=after["lthr"], rhr_entries=after["rhr"])
        sb, sa = resolve_zone_spec(basis, s.session_date, **kw_b), resolve_zone_spec(basis, s.session_date, **kw_a)
        if (sb.edges_bpm if sb else None) != (sa.edges_bpm if sa else None):
            touched.append({"id": s.id, "date": s.session_date.isoformat(), "sport": s.sport_name, "source": s.source,
                            "from": list(sb.edges_bpm) if sb else None, "to": list(sa.edges_bpm) if sa else None})
    return {
        "kind": kind, "bpm": bpm, "effective_from": effective_from.isoformat(), "provenance": provenance,
        "change": change,
        "classes_before": class_specs(before, today), "classes_after": class_specs(after, today),
        "rows_changed": len(touched), "rows": touched[:50],
        "restates": None if target is None else {"id": target.id, "bpm": target.bpm, "provenance": target.provenance,
                                                 "effective_from": target.effective_from.isoformat()},
    }


def append(db: Session, user_id: int, *, kind: str, bpm: int, effective_from: date, provenance: str, note: str,
           change: str, rationale: Optional[str], today: date) -> dict[str, Any]:
    """Validate, plan, insert ONE row, commit. Never updates or deletes. Returns the plan plus `written`."""
    r = validate(kind=kind, bpm=bpm, effective_from=effective_from, provenance=provenance, note=note,
                 change=change, rationale=rationale)
    p = plan(db, user_id, kind=kind, bpm=bpm, effective_from=effective_from, provenance=provenance, change=change,
             today=today)
    row = models.UserHrAnchor(user_id=user_id, kind=kind, effective_from=effective_from, bpm=bpm,
                              provenance=provenance, note=note.strip(),
                              restates_id=p["restates"]["id"] if p["restates"] else None, rationale=r)
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:       # a concurrent writer took the key between check and insert
        db.rollback()
        raise AnchorRefused(f"refused by the database (duplicate key?): {exc.orig}") from exc
    db.refresh(row)
    p["written"] = True
    p["row"] = {"id": row.id, "kind": row.kind, "effective_from": row.effective_from.isoformat(), "bpm": row.bpm,
                "provenance": row.provenance, "note": row.note, "restates_id": row.restates_id, "rationale": row.rationale}
    return p


__all__ = ["ANCHOR_KINDS", "AnchorRefused", "CHANGES", "PROVENANCE", "WRITABLE_KINDS", "append", "plan", "validate"]
