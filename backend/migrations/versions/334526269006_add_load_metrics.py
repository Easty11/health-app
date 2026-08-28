"""add_load_metrics

Revision ID: 334526269006
Revises: 1341a2cf6938
Create Date: 2026-08-28 00:00:00.000000

Q6 gate 3 (DECISIONS_LOG #28/#32, D-B). `load_metrics` is the per-(user, day, load_window)
daily rollup of `load_events` — the recomputable layer that carries the Banister
Fitness/Fatigue/Form curves and the #33 ΔLoad acute:chronic ratio. It reads `load_events`
(gate 2), never the raw Hevy payload; per D-B a τ tune is a recompute (bump `metrics_version`
+ delete-and-reinsert), never a migration of stored stocks.

The window column is `load_window` (never `window` — #246 renamed that reserved word out of
`load_events`; this table must not reintroduce it). Two recompute axes name the identity of a
stored row: `formula_version` (the load_events transform's, inherited) and `metrics_version`
(the τ-set / EWMA identity, this layer's own).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '334526269006'
down_revision: Union[str, Sequence[str], None] = '1341a2cf6938'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'load_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('load_window', sa.String(20), nullable=False),        # 'mechanical' | 'neuromuscular'
        sa.Column('daily_load', sa.Float(), nullable=False),            # Σ load_events.load on that local day
        sa.Column('fitness', sa.Float(), nullable=False),              # Banister EWMA, τ=42d
        sa.Column('fatigue', sa.Float(), nullable=False),              # Banister EWMA, τ per #32
        sa.Column('form', sa.Float(), nullable=False),                 # fitness − k·fatigue (k=1)
        sa.Column('acute_load', sa.Float(), nullable=False),          # #33 trailing-7d mean daily_load
        sa.Column('chronic_load', sa.Float(), nullable=False),        # #33 trailing-28d mean daily_load
        sa.Column('load_ratio', sa.Float(), nullable=True),           # acute/chronic; NULL if chronic 0
        sa.Column('unit', sa.String(20), nullable=False),             # 'kg_reps' | 'nm_au' (window-native)
        sa.Column('maturity', sa.String(8), nullable=False),         # 'low' (<42d history) | 'ok'
        sa.Column('formula_version', sa.String(20), nullable=False),  # load_events transform version
        sa.Column('metrics_version', sa.String(20), nullable=False),  # τ-set / EWMA identity ('banister-v1')
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'day', 'load_window', 'formula_version', 'metrics_version',
                            name='uq_load_metric_day_window_version'),
    )
    op.create_index('ix_load_metrics_user_window', 'load_metrics', ['user_id', 'load_window'])
    op.create_index('ix_load_metrics_user_day', 'load_metrics', ['user_id', 'day'])
    op.create_index('ix_load_metrics_metrics_version', 'load_metrics', ['metrics_version'])


def downgrade() -> None:
    op.drop_index('ix_load_metrics_metrics_version', table_name='load_metrics')
    op.drop_index('ix_load_metrics_user_day', table_name='load_metrics')
    op.drop_index('ix_load_metrics_user_window', table_name='load_metrics')
    op.drop_table('load_metrics')
