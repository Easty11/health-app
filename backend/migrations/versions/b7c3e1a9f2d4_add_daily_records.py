"""add_daily_records

Revision ID: b7c3e1a9f2d4
Revises: f4e9d2c1b3a7
Create Date: 2026-06-14 00:00:00.000000

Adds the new two-moment daily_records table alongside the existing
daily_check_ins (which is kept for backward-compat).

AM fields:
  morning_readiness (1-5, primary outcome), sleep_quality (1-5),
  fatigue (0-10), soreness (JSON), motivation (0-10), life_load (1-5),
  alcohol_units, alcohol_finish_time

Nightly fields:
  today_rating (1-5, outcome), session_quality (1-5, conditional),
  session_rpe (0-10), mindfulness_occurred, mindfulness_duration_min

Computed at AM capture (never recomputed):
  naive_baseline, model_forecast, model_confidence,
  passive_hrv_ms, passive_sleep_min
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c3e1a9f2d4'
down_revision: Union[str, Sequence[str], None] = 'f4e9d2c1b3a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'daily_records',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),

        # AM check-in
        sa.Column('am_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('morning_readiness', sa.Integer(), nullable=True),
        sa.Column('sleep_quality', sa.Integer(), nullable=True),
        sa.Column('fatigue', sa.Integer(), nullable=True),
        sa.Column('soreness', sa.JSON(), nullable=True),
        sa.Column('motivation', sa.Integer(), nullable=True),
        sa.Column('life_load', sa.Integer(), nullable=True),
        sa.Column('alcohol_units', sa.Integer(), nullable=True),
        sa.Column('alcohol_finish_time', sa.String(5), nullable=True),

        # Nightly close-out
        sa.Column('pm_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('today_rating', sa.Integer(), nullable=True),
        sa.Column('session_quality', sa.Integer(), nullable=True),
        sa.Column('session_rpe', sa.Float(), nullable=True),
        sa.Column('mindfulness_occurred', sa.Boolean(), nullable=True),
        sa.Column('mindfulness_duration_min', sa.Integer(), nullable=True),

        # Computed at AM capture time — never recomputed
        sa.Column('naive_baseline', sa.Float(), nullable=True),
        sa.Column('model_forecast', sa.Float(), nullable=True),
        sa.Column('model_confidence', sa.Float(), nullable=True),
        sa.Column('passive_hrv_ms', sa.Float(), nullable=True),
        sa.Column('passive_sleep_min', sa.Integer(), nullable=True),

        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'date', name='uq_daily_record_user_date'),
    )
    op.create_index('ix_daily_records_user_id', 'daily_records', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_daily_records_user_id', table_name='daily_records')
    op.drop_table('daily_records')
