"""add_hrv_readings_and_hrv_samples

Revision ID: b7c3e9d15a20
Revises: d4a1c9f6b230
Create Date: 2026-09-01 00:00:00.000000

Source-agnostic HRV storage (DECISIONS_LOG — Garmin HRV server-side ingestion):
  hrv_readings — nightly RMSSD summary, one row per (user, night, source);
                 Garmin-richer status/baseline/weekly fields NULL for nightly-only
                 sources. Unique (user_id, captured_at, source).
  hrv_samples  — the 5-min RMSSD series for a night, FK to hrv_readings (CASCADE).
                 Garmin populates it; nightly-only sources leave it empty.
                 Unique (hrv_reading_id, reading_time).

Additive only — no data move. Existing Samsung HRV stays in samsung_hrv_readings
until the deferred unification follow-on (OPEN_QUESTIONS).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c3e9d15a20'
down_revision: Union[str, Sequence[str], None] = 'd4a1c9f6b230'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'hrv_readings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('captured_at', sa.Date(), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('rmssd_ms', sa.Float(), nullable=True),
        sa.Column('status', sa.String(30), nullable=True),
        sa.Column('baseline_low', sa.Float(), nullable=True),
        sa.Column('baseline_high', sa.Float(), nullable=True),
        sa.Column('weekly_avg', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'captured_at', 'source', name='uq_hrv_reading_user_date_source'),
    )
    op.create_index('ix_hrv_readings_id', 'hrv_readings', ['id'])
    op.create_index('ix_hrv_readings_user_id', 'hrv_readings', ['user_id'])
    op.create_index('ix_hrv_readings_captured_at', 'hrv_readings', ['captured_at'])

    op.create_table(
        'hrv_samples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('hrv_reading_id', sa.Integer(), nullable=False),
        sa.Column('reading_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('rmssd_ms', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['hrv_reading_id'], ['hrv_readings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('hrv_reading_id', 'reading_time', name='uq_hrv_sample_reading_time'),
    )
    op.create_index('ix_hrv_samples_id', 'hrv_samples', ['id'])
    op.create_index('ix_hrv_samples_hrv_reading_id', 'hrv_samples', ['hrv_reading_id'])


def downgrade() -> None:
    op.drop_index('ix_hrv_samples_hrv_reading_id', table_name='hrv_samples')
    op.drop_index('ix_hrv_samples_id', table_name='hrv_samples')
    op.drop_table('hrv_samples')
    op.drop_index('ix_hrv_readings_captured_at', table_name='hrv_readings')
    op.drop_index('ix_hrv_readings_user_id', table_name='hrv_readings')
    op.drop_index('ix_hrv_readings_id', table_name='hrv_readings')
    op.drop_table('hrv_readings')
