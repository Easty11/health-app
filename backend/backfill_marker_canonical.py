"""
One-shot data backfill (NOT a migration — no schema change) — standing rider,
run after ANY marker_canonical.json expansion, not just #57's four.

Every canonical-dict expansion needs this: a lab_results row extracted before
a given raw->canonical mapping existed carries that raw name with
marker_canonical still NULL. The reads' COALESCE(marker_canonical,
marker_name_raw) partition key would otherwise treat the pre-bump raw-keyed
row and a post-bump canonical-keyed row for the same real marker as two
distinct series — double-counting one marker as two in the latest-per-marker
partition. Generalised (not hardcoded to #57's four) so it also serves the
next vocab bump without a code change.

Usage:
    python backend/backfill_marker_canonical.py            # dry run (default)
    python backend/backfill_marker_canonical.py --apply     # write

Standing rule (sibling to the boolean-default rule, #55): a canonical-dict
expansion requires running this backfill on lab_results, else the COALESCE
partition double-counts the newly-mapped marker.
"""
import argparse
import json
from pathlib import Path

from sqlalchemy import text

from database import SessionLocal

_CANONICAL_PATH = Path(__file__).resolve().parent / "reference" / "marker_canonical.json"


def _load_canonical_map() -> dict[str, str]:
    with open(_CANONICAL_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {entry["marker_name_raw"]: entry["marker_canonical"] for entry in data["entries"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write the UPDATE (default: dry-run count only)")
    args = parser.parse_args()

    canonical_map = _load_canonical_map()

    db = SessionLocal()
    try:
        total = 0
        for raw, canonical in canonical_map.items():
            count = db.execute(
                text(
                    "SELECT COUNT(*) FROM lab_results "
                    "WHERE marker_name_raw = :raw AND marker_canonical IS NULL"
                ),
                {"raw": raw},
            ).scalar()
            if count:
                print(f"{raw!r} -> {canonical!r}: {count} row(s) {'to update' if args.apply else 'would update'}")
            total += count

            if args.apply and count:
                db.execute(
                    text(
                        "UPDATE lab_results SET marker_canonical = :canonical "
                        "WHERE marker_name_raw = :raw AND marker_canonical IS NULL"
                    ),
                    {"raw": raw, "canonical": canonical},
                )

        if args.apply:
            db.commit()
            print(f"Committed. {total} row(s) backfilled.")
        else:
            print(f"Dry run only — {total} row(s) would be backfilled across "
                  f"{len(canonical_map)} known mappings. Re-run with --apply to write.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
