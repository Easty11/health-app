"""add health_connect_syncs sleep-nadir resting HR (hr_nadir_*)

HELD for the operator's release (hold (a): a schema migration). Not applied to prod by the PR
that carries it; Railway auto-runs `alembic upgrade head` on deploy, so the merge IS the release.

Adds the derived resting rate DECISIONS_LOG.md:480 calls primary -- the lowest sustained window
inside the night's main sleep period, read from `hr_samples` on a 1-minute grid (hr_nadir.py):
  * hr_nadir_bpm (float): the nadir; NULL when withheld.
  * hr_nadir_window_start (timestamptz): where the winning window starts.
  * hr_nadir_coverage (float): fraction of the sleep period on the chosen writer's grid (0..1).
  * hr_nadir_source_package (text): the one writer the nadir read.
  * hr_nadir_reason (text): NULL iff computed; else one of no_sleep_period / no_samples /
    insufficient_coverage / no_valid_window.
  * hr_nadir_formula (text): the constants in force ('nadir-v1'), so a window or floor change is
    a recompute rather than a silent change of meaning.

All wake-date keyed (the row's `date`, like the sleep columns). `resting_heart_rate` is NOT
repurposed: it keeps the all-day median and is relabelled in the prompt and the API docs.

Additive nullable columns are dialect-safe on SQLite (create_all test path) and Postgres. No
backfill: the next sync and the nightly `hr_nadir` chain step (trailing 14 days) fill the rows;
older nights fill on the operator's 30-day deep sync or a one-off `hr_nadir.compute_user(days=N)`.

Revision ID: a8c4e1f72b93
Revises: d6f8b1a3c5e7
Create Date: 2026-10-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'a8c4e1f72b93'
down_revision: Union[str, Sequence[str], None] = 'd6f8b1a3c5e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLS = [
    ("hr_nadir_bpm", sa.Float()),
    ("hr_nadir_window_start", sa.DateTime(timezone=True)),
    ("hr_nadir_coverage", sa.Float()),
    ("hr_nadir_source_package", sa.String()),
    ("hr_nadir_reason", sa.String()),
    ("hr_nadir_formula", sa.String()),
]


def upgrade() -> None:
    for name, type_ in _COLS:
        op.add_column("health_connect_syncs", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _type in reversed(_COLS):
        op.drop_column("health_connect_syncs", name)
