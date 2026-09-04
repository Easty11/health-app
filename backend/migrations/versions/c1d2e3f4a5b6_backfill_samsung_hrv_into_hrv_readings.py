"""backfill_samsung_hrv_into_hrv_readings

Revision ID: c1d2e3f4a5b6
Revises: b7c3e9d15a20
Create Date: 2026-09-04 00:00:00.000000

Stage A of Q130 HRV consumption — unify existing Samsung nightly HRV into the
source-agnostic `hrv_readings` store so `reads/recovery_reads.canonical_hrv` is
source-complete and the new `/recovery/summary` `hrv` block is populated for Samsung
users, not just Garmin.

Data migration, INSERT-ONLY and idempotent:
  INSERT INTO hrv_readings (user_id, captured_at, source='samsung', rmssd_ms=hrv_ms)
  SELECT from samsung_hrv_readings WHERE context='passive_overnight' AND hrv_ms NOT NULL
  AND NOT EXISTS (a hrv_readings row for that user/date/'samsung').

Why `context = 'passive_overnight'` and not `context != 'session'`: the live unique
constraint is `uq_samsung_hrv_user_date_context` (migration e1f2a3b4c5d6 dropped the
old (user_id, captured_at) key), so a single (user, night) can hold multiple non-session
rows (passive_overnight + calibration). The nightly HRV value is the passive_overnight
row; selecting it collapses to exactly one value per (user, night). `status`/`baseline_*`/
`weekly_avg` stay NULL — Samsung supplies none.

The NOT EXISTS guard makes a re-run a no-op and means the backfill never touches a row
that already exists (a Garmin night, or a Samsung night already dual-written by
`routers/samsung_hrv.py`). Additive: `samsung_hrv_readings` is untouched (sleep still
lives there; dropping `hrv_ms` is a deferred cleanup, OPEN_QUESTIONS).

HELD for explicit operator release (schema-framework migration; prod data write). Before
release, run the dry count against prod to see how many rows it would insert:
    SELECT count(*) FROM samsung_hrv_readings s
    WHERE s.context='passive_overnight' AND s.hrv_ms IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM hrv_readings h
                      WHERE h.user_id=s.user_id AND h.captured_at=s.captured_at
                        AND h.source='samsung');

Downgrade is a deliberate no-op: the inserted rows are indistinguishable from rows the
scraper dual-write adds after this migration, so deleting `source='samsung'` on downgrade
would destroy live data. Additive-only is the safety contract (see DECISIONS_LOG).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b7c3e9d15a20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Exposed as a constant so the test suite exercises the exact statement the migration
# runs (valid on both Postgres and the SQLite test substrate — plain INSERT ... SELECT
# with a NOT EXISTS guard, no dialect-specific ON CONFLICT).
BACKFILL_SQL = """
INSERT INTO hrv_readings (user_id, captured_at, source, rmssd_ms)
SELECT s.user_id, s.captured_at, 'samsung', s.hrv_ms
FROM samsung_hrv_readings AS s
WHERE s.context = 'passive_overnight'
  AND s.hrv_ms IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM hrv_readings AS h
    WHERE h.user_id = s.user_id
      AND h.captured_at = s.captured_at
      AND h.source = 'samsung'
  )
"""


def upgrade() -> None:
    op.get_bind().execute(sa.text(BACKFILL_SQL))


def downgrade() -> None:
    # No-op by design — see module docstring. The backfilled rows cannot be told apart
    # from scraper dual-write rows, so reversing would risk deleting live data.
    pass
