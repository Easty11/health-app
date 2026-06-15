"""add_aerobic_sessions

Revision ID: e3b2d1c4a5f6
Revises: 0f1ac6f33c40
Create Date: 2026-06-15 00:00:00.000000

Adds aerobic_sessions table for ACWR load tracking.
Seeded from Polar Flow ZIP export; future sources include health_connect.

Key fields beyond basic session metadata:
  cardio_load / muscle_load / recovery_hours — Polar load metrics
  z1_seconds..z5_seconds — per-zone HR time
  source + source_session_id — deduplicated per-source unique key
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3b2d1c4a5f6'
down_revision: Union[str, Sequence[str], None] = '0f1ac6f33c40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'aerobic_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('source_session_id', sa.String(255), nullable=True),
        sa.Column('session_date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stop_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sport_id', sa.String(100), nullable=True),
        sa.Column('sport_name', sa.String(100), nullable=True),
        sa.Column('duration_minutes', sa.Float(), nullable=True),
        sa.Column('hr_avg', sa.Integer(), nullable=True),
        sa.Column('hr_max', sa.Integer(), nullable=True),
        sa.Column('calories', sa.Integer(), nullable=True),
        sa.Column('cardio_load', sa.Float(), nullable=True),
        sa.Column('muscle_load', sa.Float(), nullable=True),
        sa.Column('recovery_hours', sa.Float(), nullable=True),
        sa.Column('z1_seconds', sa.Integer(), nullable=True),
        sa.Column('z2_seconds', sa.Integer(), nullable=True),
        sa.Column('z3_seconds', sa.Integer(), nullable=True),
        sa.Column('z4_seconds', sa.Integer(), nullable=True),
        sa.Column('z5_seconds', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'source', 'source_session_id', name='uq_aerobic_session_source'),
    )
    op.create_index('ix_aerobic_sessions_id', 'aerobic_sessions', ['id'])
    op.create_index('ix_aerobic_sessions_user_id', 'aerobic_sessions', ['user_id'])
    op.create_index('ix_aerobic_sessions_session_date', 'aerobic_sessions', ['session_date'])


def downgrade() -> None:
    op.drop_index('ix_aerobic_sessions_session_date', table_name='aerobic_sessions')
    op.drop_index('ix_aerobic_sessions_user_id', table_name='aerobic_sessions')
    op.drop_index('ix_aerobic_sessions_id', table_name='aerobic_sessions')
    op.drop_table('aerobic_sessions')
