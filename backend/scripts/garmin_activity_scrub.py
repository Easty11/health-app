"""Remove location keys from stored Garmin activity summaries. DRY RUN BY DEFAULT.

    /opt/venv/bin/python -m scripts.garmin_activity_scrub              # dry run: counts only
    /opt/venv/bin/python -m scripts.garmin_activity_scrub --confirm    # writes

Operator-run, in `railway ssh --service health-app-backend`, from `/app`. `garmin_activity_metrics.summary_raw`
kept the whole `summaryDTO`, which carries `startLatitude` / `startLongitude` / `endLatitude` /
`endLongitude` (for a session at home, the home's coordinates). The write path now drops every key ending
in Latitude or Longitude (`garmin_activity_metrics.scrub_location`); this removes the same keys from the
rows written before it. No Garmin request, no other table, no other key. Idempotent: a second run finds 0.
Prints counts only, never a value.
"""
from __future__ import annotations

import argparse
from typing import Any

import garmin_activity_metrics as gam
import models


def scrub(db, *, confirm: bool) -> dict[str, Any]:
    out = {"rows": 0, "rows_with_location": 0, "keys_removed": 0, "rows_written": 0}
    for row in db.query(models.GarminActivityMetric).order_by(models.GarminActivityMetric.id).all():
        out["rows"] += 1
        n = gam.location_keys(row.summary_raw)
        if not n:
            continue
        out["rows_with_location"] += 1
        out["keys_removed"] += n
        if confirm:
            row.summary_raw = gam.scrub_location(row.summary_raw)      # a new dict: the JSON column sees the change
            out["rows_written"] += 1
    if confirm:
        db.commit()
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Remove location keys from garmin_activity_metrics.summary_raw.")
    p.add_argument("--confirm", action="store_true", help="write (default is a dry run)")
    args = p.parse_args(argv)
    from database import SessionLocal

    db = SessionLocal()
    try:
        result = scrub(db, confirm=args.confirm)
    finally:
        db.close()
    print(("WROTE" if args.confirm else "DRY RUN (nothing written)") + f": {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
