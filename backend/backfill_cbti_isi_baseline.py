"""Backfill block 3's baseline ISI — one-shot, manual, witnessed.

The Insomnia Severity Index for block 3 was administered 2026-07-24 19:10 via QxMD
(score reported 16, moderate clinical insomnia) but existed only in a chat transcript
until the cbti_isi table landed. This writes it.

Follows open_cbti_block3.py: dry-run by DEFAULT, `--apply` to write, duplicate-ABORT
guard (refuses if a baseline ISI already exists for the block).

MUST run AFTER the d3f7a1908c62 migration has reached prod via deploy — the table does
not exist until then. Running it pre-deploy would require applying a branch-only
migration to prod by hand, which is the prod-ahead-of-master hazard phase 1 flagged.

The seven items are the record; total_reported preserves QxMD's 16. Their canonical sum
is 15 (QxMD anchors one item differently) — band unchanged (moderate either way), and the
items, not the total, are what a later reader decomposes.
"""
import argparse
import datetime as dt
import os

import pytz
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import models

BLOCK_ID = 2
TIMEPOINT = "baseline"
ITEMS = [0, 3, 2, 3, 2, 2, 3]           # items 1..7; canonical sum = 15
TOTAL_REPORTED = 16                     # what QxMD returned
INSTRUMENT = "ISI"
VIA = "QxMD"
AEST = pytz.timezone("Australia/Brisbane")
ADMINISTERED_AT = AEST.localize(dt.datetime(2026, 7, 24, 19, 10))
NOTES = (
    "Baseline ISI (Morin), administered via QxMD 2026-07-24 19:10 AEST. Reported total 16; "
    "canonical anchors sum to 15 (band unchanged — moderate clinical either way). Items are "
    "the record; the total is derived. Administered ONE NIGHT after block open (opened "
    "2026-07-24), so 13 of the 14 ISI recall days are pre-block — this is a pre-treatment "
    "baseline in substance despite the administration date."
)


def main():
    ap = argparse.ArgumentParser(description="Backfill block 3 baseline ISI (dry-run unless --apply).")
    ap.add_argument("--apply", action="store_true", help="write to the database")
    args = ap.parse_args()

    url = os.environ["DATABASE_URL"]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(url)

    with Session(engine) as db:
        existing = (db.query(models.CBTIISI)
                    .filter_by(block_id=BLOCK_ID, timepoint=TIMEPOINT).first())
        if existing:
            raise SystemExit(
                f"ABORT: a {TIMEPOINT} ISI already exists for block {BLOCK_ID} "
                f"(id={existing.id}). Refusing to double-write.")

        canonical = sum(ITEMS)
        print(f"[isi] block={BLOCK_ID} timepoint={TIMEPOINT} administered_at={ADMINISTERED_AT.isoformat()}")
        print(f"[isi] items={ITEMS} canonical_total={canonical} total_reported={TOTAL_REPORTED} via={VIA}")

        if not args.apply:
            print("[dry-run] no write. Re-run with --apply once the table is deployed.")
            return

        row = models.CBTIISI(
            block_id=BLOCK_ID, administered_at=ADMINISTERED_AT, timepoint=TIMEPOINT,
            item_1=ITEMS[0], item_2=ITEMS[1], item_3=ITEMS[2], item_4=ITEMS[3],
            item_5=ITEMS[4], item_6=ITEMS[5], item_7=ITEMS[6],
            total_reported=TOTAL_REPORTED, instrument=INSTRUMENT, administered_via=VIA,
            notes=NOTES,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        print(f"[applied] cbti_isi id={row.id}, canonical_total={row.canonical_total}. Baseline stored.")


if __name__ == "__main__":
    main()
