"""Operator script: record a user's HRmax in force from a date (Q159 stage 2, R2).

The ONLY writer of `user_hrmax`: no route, no UI, and the chat knowledge lane cannot reach the
table. Append-only: a new value is a NEW row; a duplicate (user, effective_from) is REFUSED and an
existing row is never edited or deleted. After a write, the next chain run recomputes every
health_connect row (Training-page open, the 02:00 sweep, or `python -m scripts.refresh_load --user N`);
this script prints the rows whose HRmax-in-force will change so the operator can see what moves.

Run inside the container, from /app (`railway ssh --service health-app-backend`; `railway run` cannot, its database host is private); the shell there is the container's, so single-quote the note):

    /opt/venv/bin/python -m scripts.set_hrmax --user 1 --effective-from 2026-06-01 --bpm 173 --provenance observed --note 'H10 chest strap max, Fitness sessions 2026-06-17 and 2026-07-17'
    ... --dry-run          # print the plan and the touched rows, write nothing

Provenance is a closed set: `tested` (a maximal-effort test) or `observed` (a session maximum from a
chest strap - measured). There is no `estimated`: SCHEMA.md forbids age-predicted HRmax. `--bpm` must lie
inside the zoning plausibility bounds (`hr_zones.PLAUSIBLE_BPM`).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from typing import Optional

from sqlalchemy.exc import IntegrityError

import models
from hr_zones import PLAUSIBLE_BPM, hrmax_in_force
from reads.aerobic_reads import HEALTH_CONNECT

PROVENANCE = ("tested", "observed")


def plan(db, user_id: int, effective_from: date, bpm: int) -> list[dict]:
    """The health_connect rows whose HRmax in force differs once `(effective_from, bpm)` exists."""
    entries = [(h.effective_from, h.hrmax_bpm)
               for h in db.query(models.UserHrmax).filter(models.UserHrmax.user_id == user_id).all()]
    after = entries + [(effective_from, bpm)]
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


def set_hrmax(db, *, user_id: int, effective_from: date, bpm: int, provenance: str,
              note: str, dry_run: bool = False) -> dict:
    """Validate, plan, and (unless `dry_run`) insert one row. Raises ValueError on a refused write;
    never updates or deletes. Returns `{"touched": [...], "written": bool}`."""
    if provenance not in PROVENANCE:
        raise ValueError(f"provenance must be one of {PROVENANCE}, got {provenance!r}")
    lo, hi = PLAUSIBLE_BPM
    if not lo <= bpm <= hi:
        raise ValueError(f"bpm {bpm} outside the plausibility bounds {lo}-{hi}")
    if not note or not note.strip():
        raise ValueError("a note naming the evidence is required")
    if db.get(models.User, user_id) is None:
        raise ValueError(f"no user {user_id}")
    dup = (db.query(models.UserHrmax)
           .filter_by(user_id=user_id, effective_from=effective_from).first())
    if dup is not None:
        raise ValueError(
            f"user {user_id} already has an HRmax effective {effective_from} ({dup.hrmax_bpm} bpm, "
            f"{dup.provenance}); rows are append-only - use a later effective_from")
    touched = plan(db, user_id, effective_from, bpm)
    if dry_run:
        return {"touched": touched, "written": False}
    db.add(models.UserHrmax(user_id=user_id, effective_from=effective_from, hrmax_bpm=bpm,
                            provenance=provenance, note=note.strip()))
    try:
        db.commit()
    except IntegrityError as exc:       # a concurrent writer took the key between check and insert
        db.rollback()
        raise ValueError(f"refused by the database (duplicate key?): {exc.orig}") from exc
    return {"touched": touched, "written": True}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Record a user's HRmax in force from a date (append-only).")
    ap.add_argument("--user", type=int, required=True)
    ap.add_argument("--effective-from", dest="effective_from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--bpm", type=int, required=True)
    ap.add_argument("--provenance", required=True, choices=PROVENANCE)
    ap.add_argument("--note", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    from database import SessionLocal
    db = SessionLocal()
    try:
        try:
            res = set_hrmax(db, user_id=a.user, effective_from=date.fromisoformat(a.effective_from),
                            bpm=a.bpm, provenance=a.provenance, note=a.note, dry_run=a.dry_run)
        except ValueError as exc:
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 2
    finally:
        db.close()

    print(f"{'WROTE' if res['written'] else 'DRY RUN (nothing written)'}: user {a.user} HRmax {a.bpm} "
          f"({a.provenance}) effective {a.effective_from}")
    print(f"health_connect rows whose HRmax in force changes: {len(res['touched'])}")
    for t in res["touched"]:
        print(f"  #{t['id']} {t['date']} {t['sport']} [{t['source_package']}]  {t['from']} -> {t['to']}")
    if res["written"]:
        print("Recompute: the next chain run (Training-page open / 02:00 sweep) or "
              f"`python -m scripts.refresh_load --user {a.user}`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
