"""Operator script: relabel stored Polar sessions to the corrected sport-id map (polar-sport-map).

`import_polar.SPORT_NAMES` was replaced with the Polar Flow sport-id list, but a deploy only labels NEW
rows: an existing session keeps the `sport_name` it was stored with (the sync skips a known
`source_session_id`). This script recomputes `sport_name` from the retained `sport_id` for every
`polar_v4` and `polar_flow_export` row and lists what would change.

REPORT BY DEFAULT: with no flag it writes nothing. `--apply` is the only write, and it touches one
column (`sport_name`) on the rows the report lists - never `sport_id`, never a row whose id is not in
the map (those keep what they have; an unknown id is never guessed), never a row with no `sport_id`.
Idempotent: a second run lists nothing.

Run from backend/ (PowerShell):

    railway run python -m scripts.polar_sport_backfill                 # report, all users
    railway run python -m scripts.polar_sport_backfill --user 1        # report, one user
    railway run python -m scripts.polar_sport_backfill --apply         # write the listed relabels

Two consequences the report flags per row:
  * `class` - the row crosses the non-training line (`sport_classes.NON_TRAINING_SPORTS`: Walking,
    Pilates, Yoga, Stretching). Readers that exclude those sports (the psychological window, the CBT-I
    training-end read) change on their next read.
  * the metabolic `load_events.provenance` copy of the label is NOT touched here. Load itself does not
    depend on the sport, so no load value moves; the stored label refreshes on the next load refresh
    (`python -m scripts.refresh_load --user N`), which is an operator step after `--apply`.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from typing import Optional

import models
from import_polar import SPORT_NAMES
from sport_classes import is_non_training

POLAR_SOURCES = ("polar_v4", "polar_flow_export")


def plan(db, user_id: Optional[int] = None) -> list[dict]:
    """The Polar rows whose stored `sport_name` differs from `SPORT_NAMES[sport_id]`, in id order.
    A row with no `sport_id`, or whose id is not in the map, is never listed (nothing to derive)."""
    q = db.query(models.AerobicSession).filter(models.AerobicSession.source.in_(POLAR_SOURCES))
    if user_id is not None:
        q = q.filter(models.AerobicSession.user_id == user_id)
    out = []
    for r in q.order_by(models.AerobicSession.id).all():
        if not r.sport_id:
            continue
        new = SPORT_NAMES.get(r.sport_id)
        if new is None or new == r.sport_name:
            continue
        out.append({"id": r.id, "user_id": r.user_id, "source": r.source,
                    "session_date": r.session_date.isoformat(), "sport_id": r.sport_id,
                    "old": r.sport_name, "new": new,
                    "class_flip": is_non_training(r.sport_name) != is_non_training(new)})
    return out


def apply(db, rows: list[dict]) -> int:
    """Write `sport_name` for exactly the planned rows, in one transaction. Returns rows updated."""
    n = 0
    for p in rows:
        r = db.get(models.AerobicSession, p["id"])
        if r is None or r.sport_id != p["sport_id"]:      # vanished or re-keyed since the plan
            continue
        r.sport_name = p["new"]
        n += 1
    db.commit()
    return n


def _label(name: Optional[str]) -> str:
    return "NULL" if name is None else name


def render(rows: list[dict]) -> str:
    lines = [f"Polar rows whose sport_name changes: {len(rows)}"]
    for p in rows:
        flip = "  [class flips]" if p["class_flip"] else ""
        lines.append(f"  #{p['id']} u{p['user_id']} {p['source']} {p['session_date']} "
                     f"sport_id={p['sport_id']}  {_label(p['old'])} -> {p['new']}{flip}")
    by = Counter((p["sport_id"], p["old"], p["new"]) for p in rows)
    if by:
        lines.append("By id:")
        for (sid, old, new), n in sorted(by.items(), key=lambda kv: int(kv[0][0])):
            lines.append(f"  sport_id={sid}  {_label(old)} -> {new}  x{n}")
    flips = sum(1 for p in rows if p["class_flip"])
    lines.append(f"Rows crossing the non-training line: {flips}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Relabel Polar sessions to the corrected sport-id map "
                                             "(report by default).")
    ap.add_argument("--user", type=int, default=None, help="limit to one user (default: all)")
    ap.add_argument("--apply", action="store_true", help="write the listed relabels (default: report only)")
    a = ap.parse_args(argv)

    from database import SessionLocal
    db = SessionLocal()
    try:
        rows = plan(db, a.user)
        print(render(rows))
        if not a.apply:
            print("REPORT ONLY (nothing written). Re-run with --apply to write these relabels.")
            return 0
        n = apply(db, rows)
    finally:
        db.close()
    print(f"WROTE: {n} row(s) relabelled. Next: `python -m scripts.refresh_load` per user to refresh the "
          "stored load provenance label (no load value changes).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
