"""Post-backfill verification: any marker appearing more than once at one collection date.

RUN ONCE, AFTER THE BACKFILL COMPLETES. This is verification that the confirm-time guard
(#156) worked — not a per-episode gate. A manual check run before every upload would be the
manual-control-standing-in-for-a-mechanism pattern FEEDBACK warns against, and it was
explicitly declined when this work was scoped: the guard belongs at confirm, where it is, and
this script exists to confirm the guard held rather than to substitute for it. If it ever
starts being run per-episode, that is a signal the guard is not trusted — fix the guard.

What a hit means: `marker_series` partitions per marker over (collected_date DESC, id DESC)
and takes rn <= 2, so two rows sharing a marker AND a collection date become current+prior,
the true earlier prior is dropped, and both safety bands resolve identically — band_change
returns None and the safety arm never fires. A hit is therefore a silently masked gate, not a
cosmetic duplicate.

Usage — INSIDE the container, once this file is deployed:
    railway ssh "/opt/venv/bin/python scripts/verify_series_integrity.py"

NOT `railway run`. That injects the production `DATABASE_URL`, whose host is Railway's
INTERNAL name (`*.railway.internal`) and does not resolve from a developer machine — verified,
it fails with "could not translate host name". The check must run where the database is
reachable.

Exits 0 when clean, 1 when any duplicate is found, so it can gate a script if ever needed.
`DATABASE_URL` is read from the environment by the child process and never printed (#111).
"""
from __future__ import annotations

import os
import sys

import sqlalchemy as sa
from sqlalchemy import text

# The key mirrors `routers.labs._duplicate_key`: canonical id where mapped, raw label where
# not — because an unmapped duplicate becomes a duplicated series the moment the marker is
# promoted (#155 retroactive promotion).
_QUERY = text("""
    SELECT  lr.user_id,
            COALESCE(res.marker_canonical, 'raw:' || res.marker_name_raw) AS marker_key,
            lr.collected_date,
            COUNT(*)                        AS row_count,
            COUNT(DISTINCT res.value_num)   AS distinct_values,
            STRING_AGG(DISTINCT lr.panel_name_raw, ' | ') AS panels
    FROM lab_results res
    JOIN lab_reports lr ON lr.id = res.lab_report_id
    GROUP BY 1, 2, 3
    HAVING COUNT(*) > 1
    ORDER BY 1, 3, 2
""")


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL not set — run via `railway run` so the value never enters a transcript.")
        return 2
    engine = sa.create_engine(url.replace("postgres://", "postgresql://"))
    with engine.connect() as conn:
        rows = conn.execute(_QUERY).fetchall()

    if not rows:
        print("OK — no marker appears more than once at any collection date.")
        return 0

    print(f"FAIL — {len(rows)} duplicated (user, marker, collection date) group(s):")
    for user_id, marker_key, collected, row_count, distinct_values, panels in rows:
        same = "identical values" if distinct_values == 1 else f"{distinct_values} DIFFERENT values"
        print(f"  user={user_id}  {marker_key}  @ {collected}  rows={row_count}  ({same})")
        print(f"      panels: {panels}")
    print()
    print("Each group above masks that marker's band_change and delta against its true prior.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
