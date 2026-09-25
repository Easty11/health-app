"""add health_connect_syncs sleep session clocks (source-agnostic)

Released by the operator 2026-09-25 (hold (a) lifted, #328). Additive, all
nullable, no backfill — historical rows fill on the next re-sync (the operator's 30-day
deep sync, HCA SyncScreen.handleSync(30), repopulates the window).

Adds the clocks of the night's MAIN sleep period (#328) — the same period the duration
already comes from (#254/#256):
  * sleep_start / sleep_end (timestamptz): earliest / latest segment edge of the period.
  * sleep_start_source_package / sleep_end_source_package (text): the writer package of
    the segment supplying each edge. Per-endpoint, because a main period can span two
    writers (e.g. a Garmin night stitched to a Samsung Health fragment).
  * sleep_onset (timestamptz): first ASLEEP (LIGHT/DEEP/REM) stage from a REAL stage
    record; NULL when the period has none (a stageless session's synthetic span never
    counts).

Additive nullable columns are dialect-safe on SQLite (create_all test path) and Postgres.

Revision ID: f7a2c9e1d3b5
Revises: e3b7c5a1f942
Create Date: 2026-09-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'f7a2c9e1d3b5'
down_revision: Union[str, Sequence[str], None] = 'e3b7c5a1f942'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLS = [
    ("sleep_start", sa.DateTime(timezone=True)),
    ("sleep_end", sa.DateTime(timezone=True)),
    ("sleep_onset", sa.DateTime(timezone=True)),
    ("sleep_start_source_package", sa.String()),
    ("sleep_end_source_package", sa.String()),
]


def upgrade() -> None:
    for name, type_ in _COLS:
        op.add_column("health_connect_syncs", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _type in reversed(_COLS):
        op.drop_column("health_connect_syncs", name)
