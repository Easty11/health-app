"""rename load_events.window to load_window

Revision ID: 1341a2cf6938
Revises: d4a1f8c609e2
Create Date: 2026-08-27 00:00:00.000000

`window` is a Postgres reserved word: every hand query and, shortly, gate 3's
`load_metrics` rollup has to quote `"window"` to read the column. Rename it to
`load_window` (keeping the D-A window vocabulary) now, while `load_events` is the sole
108-row table carrying the name and the rename is trivially reversible — before gate 3
inherits it into a second table and every rollup query (DECISIONS_LOG #246).

Column-rename only. On Postgres `ALTER TABLE ... RENAME COLUMN` automatically rewrites the
dependent objects' definitions — the unique constraint `uq_load_event_session_window_version`
and the index `ix_load_events_user_window` — to reference `load_window`; their NAMES are
deliberately left unchanged (they never appear in a query, only the column does, so renaming
them would add drop/recreate risk for zero query-surface benefit — noted in #246).

No data change: a column rename preserves every row. The derived store is recompute-safe
either way (D-B), but this is a structural rename, not a recompute — the rows and their
`(source, source_ref, load_window, formula_version)` natural key are untouched.
"""
from typing import Sequence, Union

from alembic import op


revision: str = '1341a2cf6938'
down_revision: Union[str, Sequence[str], None] = 'd4a1f8c609e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('load_events', 'window', new_column_name='load_window')


def downgrade() -> None:
    op.alter_column('load_events', 'load_window', new_column_name='window')
