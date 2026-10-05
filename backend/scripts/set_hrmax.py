"""Operator script: record a user's HRmax in force from a date (Q159 stage 2, R2; #383/#384).

The ONLY writer of `user_hrmax`: no route, no UI, and the chat knowledge lane cannot reach the
table. Append-only: every change is a NEW row and an existing row is never edited or deleted. After a
write, the next chain run recomputes every health_connect row (Training-page open, the 02:00 sweep, or
`python -m scripts.refresh_load --user N`); this script prints the rows whose HRmax-in-force will
change so the operator can see what moves.

Two kinds of change (#383), told apart by `--restate`:

* DATED (default): a value that genuinely changes with fitness. It applies from `--effective-from`
  FORWARD only; a date that already has a row is REFUSED.
* RESTATEMENT (`--restate`): a correction from better evidence about the same physiology. It carries
  the SAME `--effective-from` as the row it corrects (the date must already have a row), stands in for
  that row over its whole span, and so reflows history. The corrected row is kept, untouched, and the
  new row points at it. Restating a date that was already restated corrects the latest one (a chain).
  `--rationale` (why the value was wrong) is required.

Run inside the container, from /app (`railway ssh --service health-app-backend`; `railway run` cannot, its database host is private); the shell there is the container's, so single-quote the text arguments:

    /opt/venv/bin/python -m scripts.set_hrmax --user 1 --effective-from 2026-06-01 --bpm 173 --provenance observed --note 'H10 chest strap max, Fitness sessions 2026-06-17 and 2026-07-17'
    /opt/venv/bin/python -m scripts.set_hrmax --user 1 --effective-from 2026-03-01 --bpm 175 --provenance adjusted --restate --base-bpm 173 --rationale '...' --note '...'
    ... --dry-run          # print the plan and the touched rows, write nothing

Provenance is a closed set: `tested` (a maximal-effort test), `observed` (a session maximum from a chest
strap - measured) or `adjusted` (an observed maximum plus a documented correction: `--base-bpm`, the
observation it starts from, and `--rationale` are both required, and `--bpm` must differ from the base).
There is no `estimated`: SCHEMA.md forbids age-predicted HRmax. `--bpm` and `--base-bpm` must lie inside
the zoning plausibility bounds (`hr_zones.PLAUSIBLE_BPM`).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import Optional

from sqlalchemy.exc import IntegrityError

import models
from hr_zones import PLAUSIBLE_BPM, HrmaxEntry, entry_from_row, hrmax_in_force
from reads.aerobic_reads import HEALTH_CONNECT

PROVENANCE = ("tested", "observed", "adjusted")


def _entries(db, user_id: int) -> list[HrmaxEntry]:
    return [entry_from_row(h)
            for h in db.query(models.UserHrmax).filter(models.UserHrmax.user_id == user_id).all()]


def plan(db, user_id: int, effective_from: date, bpm: int, *, restates_id: Optional[int] = None) -> list[dict]:
    """The health_connect rows whose HRmax in force differs once the new row exists (a dated change,
    or, with `restates_id`, a restatement of that row)."""
    entries = _entries(db, user_id)
    after = entries + [HrmaxEntry(effective_from, bpm, id=None, restates=restates_id)]
    touched = []
    rows = (db.query(models.AerobicSession)
            .filter(models.AerobicSession.user_id == user_id,
                    models.AerobicSession.source == HEALTH_CONNECT)
            .order_by(models.AerobicSession.session_date, models.AerobicSession.id).all())
    for r in rows:
        before_v, after_v = hrmax_in_force(entries, r.session_date), hrmax_in_force(after, r.session_date)
        if before_v != after_v:
            touched.append({"id": r.id, "date": r.session_date.isoformat(), "sport": r.sport_name,
                            "source_package": r.source_package, "from": before_v, "to": after_v})
    return touched


def _restatement_target(db, user_id: int, effective_from: date) -> "models.UserHrmax":
    """The row a restatement on `effective_from` corrects: the latest of that date's chain (the one
    nothing restates yet). Raises ValueError with the way out when the date has no row."""
    on_date = (db.query(models.UserHrmax)
               .filter_by(user_id=user_id, effective_from=effective_from).all())
    if not on_date:
        in_force = (db.query(models.UserHrmax)
                    .filter(models.UserHrmax.user_id == user_id, models.UserHrmax.effective_from < effective_from)
                    .order_by(models.UserHrmax.effective_from.desc()).first())
        hint = (f"; the row in force then is dated {in_force.effective_from} - restate it with "
                f"--effective-from {in_force.effective_from}") if in_force is not None else ""
        raise ValueError(
            f"nothing to restate: user {user_id} has no HRmax dated {effective_from}. A restatement carries "
            f"the date of the row it corrects; a new value from a new date is a dated change (omit "
            f"--restate){hint}")
    restated = {h.restates_id for h in on_date if h.restates_id is not None}
    heads = [h for h in on_date if h.id not in restated]
    if len(heads) != 1:     # unreachable while uq_user_hrmax_dated / uq_user_hrmax_restates hold
        raise ValueError(f"user {user_id} has {len(heads)} unrestated HRmax rows dated {effective_from}; "
                         "the chain is not linear - refusing to guess")
    return heads[0]


def set_hrmax(db, *, user_id: int, effective_from: date, bpm: int, provenance: str,
              note: str, dry_run: bool = False, restate: bool = False,
              base_bpm: Optional[int] = None, rationale: Optional[str] = None) -> dict:
    """Validate, plan, and (unless `dry_run`) insert one row. Raises ValueError on a refused write;
    never updates or deletes. Returns `{"touched": [...], "written": bool, "restates": dict | None}`,
    where `restates` names the row a restatement corrects (id, bpm, provenance, effective_from)."""
    if provenance not in PROVENANCE:
        raise ValueError(f"provenance must be one of {PROVENANCE}, got {provenance!r}")
    lo, hi = PLAUSIBLE_BPM
    if not lo <= bpm <= hi:
        raise ValueError(f"bpm {bpm} outside the plausibility bounds {lo}-{hi}")
    if not note or not note.strip():
        raise ValueError("a note naming the evidence is required")
    rationale = rationale.strip() if rationale and rationale.strip() else None
    if provenance == "adjusted":
        if base_bpm is None:
            raise ValueError("adjusted needs --base-bpm: the observed maximum the correction starts from")
        if not lo <= base_bpm <= hi:
            raise ValueError(f"base bpm {base_bpm} outside the plausibility bounds {lo}-{hi}")
        if base_bpm == bpm:
            raise ValueError(f"adjusted records a correction, but bpm equals the base ({bpm}); "
                             "record it as observed")
        if rationale is None:
            raise ValueError("adjusted needs --rationale: the documented correction")
    elif base_bpm is not None:
        raise ValueError("--base-bpm only applies to provenance adjusted")
    if restate and rationale is None:
        raise ValueError("a restatement needs --rationale: why the value it corrects was wrong")
    if db.get(models.User, user_id) is None:
        raise ValueError(f"no user {user_id}")

    target = None
    if restate:
        target = _restatement_target(db, user_id, effective_from)
        if target.hrmax_bpm == bpm:
            raise ValueError(f"user {user_id}'s HRmax dated {effective_from} is already {bpm}; "
                             "a restatement to the same value changes nothing")
    else:
        dup = (db.query(models.UserHrmax)
               .filter_by(user_id=user_id, effective_from=effective_from).first())
        if dup is not None:
            raise ValueError(
                f"user {user_id} already has an HRmax effective {effective_from} ({dup.hrmax_bpm} bpm, "
                f"{dup.provenance}); rows are append-only - use a later effective_from for a new value, "
                f"or --restate to correct this one")

    touched = plan(db, user_id, effective_from, bpm, restates_id=target.id if target else None)
    restates = (None if target is None else
                {"id": target.id, "bpm": target.hrmax_bpm, "provenance": target.provenance,
                 "effective_from": target.effective_from})
    if dry_run:
        return {"touched": touched, "written": False, "restates": restates}
    db.add(models.UserHrmax(user_id=user_id, effective_from=effective_from, hrmax_bpm=bpm,
                            provenance=provenance, note=note.strip(), restates_id=target.id if target else None,
                            base_bpm=base_bpm, rationale=rationale))
    try:
        db.commit()
    except IntegrityError as exc:       # a concurrent writer took the key between check and insert
        db.rollback()
        raise ValueError(f"refused by the database (duplicate key?): {exc.orig}") from exc
    return {"touched": touched, "written": True, "restates": restates}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Record a user's HRmax in force from a date (append-only).")
    ap.add_argument("--user", type=int, required=True)
    ap.add_argument("--effective-from", dest="effective_from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--bpm", type=int, required=True)
    ap.add_argument("--provenance", required=True, choices=PROVENANCE)
    ap.add_argument("--note", required=True, help="the evidence")
    ap.add_argument("--restate", action="store_true",
                    help="correct the row dated --effective-from (retroactive); default is a dated change (forward only)")
    ap.add_argument("--base-bpm", dest="base_bpm", type=int, default=None,
                    help="adjusted only: the observed maximum the correction starts from")
    ap.add_argument("--rationale", default=None,
                    help="adjusted and --restate: the correction, or why the corrected value was wrong")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    from database import SessionLocal
    db = SessionLocal()
    try:
        try:
            res = set_hrmax(db, user_id=a.user, effective_from=date.fromisoformat(a.effective_from),
                            bpm=a.bpm, provenance=a.provenance, note=a.note, dry_run=a.dry_run,
                            restate=a.restate, base_bpm=a.base_bpm, rationale=a.rationale)
        except ValueError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
    finally:
        db.close()

    kind = "restatement" if res["restates"] else "dated change"
    print(f"{'WROTE' if res['written'] else 'DRY RUN (nothing written)'}: user {a.user} HRmax {a.bpm} "
          f"({a.provenance}, {kind}) effective {a.effective_from}")
    if res["restates"]:
        r = res["restates"]
        print(f"  restates row #{r['id']}: {r['bpm']} bpm ({r['provenance']}) effective {r['effective_from']} "
              "- kept unchanged, now superseded")
    print(f"health_connect rows whose HRmax in force changes: {len(res['touched'])}")
    for t in res["touched"]:
        print(f"  #{t['id']} {t['date']} {t['sport']} [{t['source_package']}]  {t['from']} -> {t['to']}")
    if res["written"]:
        print("Recompute: the next chain run (Training-page open / 02:00 sweep) or "
              f"`python -m scripts.refresh_load --user {a.user}`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
