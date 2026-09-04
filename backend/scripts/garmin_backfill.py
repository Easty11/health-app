"""
Garmin HRV historical backfill — loads nightly HRV from a Garmin *account data
export* into `hrv_readings`, reaching the history the live API can't.

`get_hrv_range` serves only a ~7-day rolling window, so HRV before the live-sync
floor is unreachable online. The Garmin account data export carries nightly HRV
much further back — in `DI-Connect-Wellness/*healthStatusData.json` as
`metrics[type="HRV"].value` plus its baseline limits — but NOT the 5-min series.

This is a reusable operator tool (any user's export), run OUT-OF-BAND against prod:

    # dry-run first (writes nothing), then the real run
    python -m scripts.garmin_backfill --export <export dir> --user-id 4 --dry-run
    python -m scripts.garmin_backfill --export <export dir> --user-id 4

It is INSERT-ONLY and idempotent. For each parsed night it first checks whether a
row already exists for (user_id, captured_at, source); if so it SKIPS that night —
never updates it. The safety rationale is load-bearing: `_upsert_hrv_day` replaces a
night's samples on reingest and the export carries none, so *updating* a live-synced
night would wipe its 5-min series. Skip-existing makes the backfill additive and
incapable of touching live-sync data. The skip is the safety mechanism — not a date
bound.

`status` and `weekly_avg` are left NULL for export-sourced rows: the export's status
vocabulary (IN_RANGE / BELOW / ONBOARDING) differs from the live API's
(BALANCED / …), and `rmssd_ms` is the unambiguous signal — mixing vocabularies was
rejected (see DECISIONS_LOG). `hrv_samples` stays a going-forward artifact of the
live sync.

Reuses the app's own contract boundaries — nothing hand-rolled: `SessionLocal`
(`database`), the RMSSD bounds guard `_bounded_rmssd` (`connectors.garmin`), and the
idempotent night upsert `_upsert_hrv_day` (`routers.garmin`).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from connectors.garmin import _bounded_rmssd
from database import SessionLocal
import models
from routers.garmin import _upsert_hrv_day

logger = logging.getLogger("garmin_backfill")

# Garmin names the wellness export file `<id>_healthStatusData.json`.
_EXPORT_GLOB = "*healthStatusData.json"


def _iter_files(export_path: str) -> list[Path]:
    """A single *healthStatusData.json file, or every one under a directory."""
    p = Path(export_path)
    if p.is_dir():
        files = sorted(p.rglob(_EXPORT_GLOB))
        if not files:
            raise FileNotFoundError(
                f"no {_EXPORT_GLOB} found under {p}"
            )
        return files
    if not p.exists():
        raise FileNotFoundError(f"export path not found: {p}")
    return [p]


def _baseline(raw, *, cdate: str, field: str) -> float | None:
    """Export baseline limit → validated RMSSD or NULL.

    `0.0` is the export's pre-baseline / ONBOARDING sentinel, not a real bound → NULL
    (silently, it is expected). Any other value is bounds-checked via the connector's
    shared RMSSD guard, so a genuinely corrupt limit is nulled + logged there.
    """
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v == 0.0:
        return None
    return _bounded_rmssd(v, cdate=cdate, field=field)


def parse_export(export_path: str) -> tuple[list[dict], int]:
    """Parse every export file under `export_path` into insert-ready night dicts.

    Returns `(nights, dropped)`. Each night is the `_upsert_hrv_day` `day` contract
    shape — `{"captured_at": date, "reading": {rmssd_ms, baseline_low, baseline_high},
    "samples": []}` — with `status`/`weekly_avg` omitted (→ NULL) and `samples` always
    empty (the export has no 5-min series). `dropped` counts nights whose HRV value is
    null or out of RMSSD bounds (each logged); a record with no HRV metric at all is
    skipped silently (nothing to backfill).
    """
    nights: list[dict] = []
    dropped = 0
    for f in _iter_files(export_path):
        records = json.loads(Path(f).read_text(encoding="utf-8"))
        for rec in records:
            cdate = rec.get("calendarDate")
            hrv = next(
                (m for m in rec.get("metrics", []) if m.get("type") == "HRV"),
                None,
            )
            if hrv is None:
                continue  # no HRV metric this night — nothing to backfill
            rmssd = _bounded_rmssd(hrv.get("value"), cdate=cdate, field="HRV.value")
            if rmssd is None:
                logger.warning(
                    "garmin backfill: dropping %s — HRV value null or out of range",
                    cdate,
                )
                dropped += 1
                continue
            nights.append(
                {
                    "captured_at": date.fromisoformat(cdate),
                    "reading": {
                        "rmssd_ms": rmssd,
                        "baseline_low": _baseline(
                            hrv.get("baselineLowerLimit"),
                            cdate=cdate,
                            field="HRV.baselineLowerLimit",
                        ),
                        "baseline_high": _baseline(
                            hrv.get("baselineUpperLimit"),
                            cdate=cdate,
                            field="HRV.baselineUpperLimit",
                        ),
                    },
                    "samples": [],
                }
            )
    return nights, dropped


def backfill(db, user_id: int, source: str, nights: list[dict], *, dry_run: bool) -> dict:
    """Insert-only load of `nights` for `(user_id, source)`.

    A night already present is SKIPPED, never updated — the safety contract that keeps a
    live-synced night's 5-min series intact (see module docstring). Only absent nights
    reach `_upsert_hrv_day`. A real run commits once at the end; a dry run writes
    nothing. Returns counts plus the parsed date range.
    """
    inserted = skipped = 0
    for day in nights:
        exists = (
            db.query(models.HrvReading)
            .filter_by(user_id=user_id, captured_at=day["captured_at"], source=source)
            .first()
        )
        if exists is not None:
            skipped += 1
            logger.info(
                "garmin backfill: %s already present for user %s/%s — skipping",
                day["captured_at"], user_id, source,
            )
            continue
        if not dry_run:
            _upsert_hrv_day(db, user_id, source, day)
        inserted += 1

    if not dry_run:
        db.commit()

    dates = [d["captured_at"] for d in nights]
    return {
        "inserted": inserted,
        "skipped_existing": skipped,
        "date_range": (min(dates), max(dates)) if dates else None,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Backfill historical Garmin HRV from an account data export into "
        "hrv_readings (insert-only, nightly-only, status NULL).",
    )
    parser.add_argument(
        "--export", required=True,
        help="A *healthStatusData.json file, or a directory to glob recursively.",
    )
    parser.add_argument("--user-id", type=int, required=True, help="Target user id.")
    parser.add_argument(
        "--source", default="garmin",
        help="Provenance tag stored on each row (default: garmin).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report would-insert / would-skip / would-drop counts and the date range; write nothing.",
    )
    args = parser.parse_args()

    try:
        nights, dropped = parse_export(args.export)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        stats = backfill(db, args.user_id, args.source, nights, dry_run=args.dry_run)
    finally:
        db.close()

    ins = "would-insert" if args.dry_run else "inserted"
    skp = "would-skip" if args.dry_run else "skipped"
    rng = (
        f"{stats['date_range'][0]}..{stats['date_range'][1]}"
        if stats["date_range"] else "(none)"
    )
    print(
        f"{'DRY RUN — ' if args.dry_run else ''}user {args.user_id}/{args.source}: "
        f"{ins} {stats['inserted']}, {skp} {stats['skipped_existing']} existing, "
        f"would-drop(bounds) {dropped}; parsed date range {rng}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
