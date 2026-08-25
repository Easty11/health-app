"""add_load_events

Revision ID: c7d9e2f14a86
Revises: f9a2c1d40b73
Create Date: 2026-08-25 00:00:00.000000

The Q6 four-window load transform store (DECISIONS_LOG #28/#32, D-B/D-C/D-D;
gate 2). `load_events` is the derived, recomputable layer of the two-level store:
`hevy_workouts.raw` (source of truth, gate 1) → the Tier-0 transform
(`backend/load_events.py`) → `load_events` (one row per session-window per
formula_version) → the daily `load_metrics` + Banister rollup (gate 3, later).

Per D-B computed history is a RECOMPUTE, never a migration: a coefficient or
routing correction bumps `formula_version` and re-derives, so this table is
delete-and-reinsert per (user, formula_version) — the migration only builds the
empty shape.

Source-neutral by design (parallels the wearable ingestion contract, #236):
`(source, source_ref)` identifies the originating session generically, with NO
hard FK to `hevy_workouts` — the strength transform writes Mechanical /
Neuromuscular events from Hevy, but the same store will later hold Metabolic
(aerobic) and Psychological (sRPE) events from other sources. A hard FK to
`hevy_workouts.hevy_id` would reject those. `user_id` IS a hard FK (CASCADE): a
user deletion clears their load. Orphaned rows (a source session hard-deleted, or
adjudicated out via `excluded_at`) are cleaned by the next recompute, which skips
excluded/absent sessions and rewrites the user's rows.

Does NOT touch load_metrics (gate 3, reserved) or exercise_sessions (#19).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c7d9e2f14a86'
down_revision: Union[str, Sequence[str], None] = 'f9a2c1d40b73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'load_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),          # 'hevy'
        sa.Column('source_ref', sa.String(64), nullable=False),      # session id (soft ref, no FK)
        sa.Column('window', sa.String(20), nullable=False),          # 'mechanical' | 'neuromuscular'
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=True),  # session start; NULL if undated
        sa.Column('load', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(20), nullable=False),            # 'kg_reps' | 'nm_au'
        sa.Column('formula_version', sa.String(20), nullable=False),  # 'tier0-v1'
        sa.Column('provenance', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'source_ref', 'window', 'formula_version',
                            name='uq_load_event_session_window_version'),
    )
    op.create_index('ix_load_events_user_id', 'load_events', ['user_id'])
    op.create_index('ix_load_events_user_window', 'load_events', ['user_id', 'window'])
    op.create_index('ix_load_events_user_occurred', 'load_events', ['user_id', 'occurred_at'])
    op.create_index('ix_load_events_formula_version', 'load_events', ['formula_version'])


def downgrade() -> None:
    op.drop_index('ix_load_events_formula_version', table_name='load_events')
    op.drop_index('ix_load_events_user_occurred', table_name='load_events')
    op.drop_index('ix_load_events_user_window', table_name='load_events')
    op.drop_index('ix_load_events_user_id', table_name='load_events')
    op.drop_table('load_events')
