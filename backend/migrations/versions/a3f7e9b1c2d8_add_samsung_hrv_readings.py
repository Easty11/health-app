"""add_samsung_hrv_readings

Revision ID: a3f7e9b1c2d8
Revises: 5f19570994b2
Create Date: 2026-06-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3f7e9b1c2d8'
down_revision: Union[str, Sequence[str], None] = '5f19570994b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'samsung_hrv_readings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('captured_at', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('hrv_ms', sa.Float(), nullable=True),
        sa.Column('sleep_hr_bpm', sa.Integer(), nullable=True),
        sa.Column('respiratory_rate', sa.Float(), nullable=True),
        sa.Column('sleep_efficiency_pct', sa.Integer(), nullable=True),
        sa.Column('actual_sleep_time_minutes', sa.Integer(), nullable=True),
        sa.Column('sleep_duration_home_tile', sa.String(length=20), nullable=True),
        sa.Column('bedtime', sa.String(length=10), nullable=True),
        sa.Column('wake_time', sa.String(length=10), nullable=True),
        sa.Column('awake_minutes', sa.Integer(), nullable=True),
        sa.Column('rem_minutes', sa.Integer(), nullable=True),
        sa.Column('light_minutes', sa.Integer(), nullable=True),
        sa.Column('deep_minutes', sa.Integer(), nullable=True),
        sa.Column('awake_pct', sa.Integer(), nullable=True),
        sa.Column('rem_pct', sa.Integer(), nullable=True),
        sa.Column('light_pct', sa.Integer(), nullable=True),
        sa.Column('deep_pct', sa.Integer(), nullable=True),
        sa.Column('total_sleep_time_minutes', sa.Integer(), nullable=True),
        sa.Column('spo2_average_pct', sa.Float(), nullable=True),
        sa.Column('extraction_method', sa.String(length=50),
                  server_default=sa.text("'accessibility'"), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'captured_at', name='uq_samsung_hrv_user_date'),
    )
    op.create_index('ix_samsung_hrv_readings_id', 'samsung_hrv_readings', ['id'], unique=False)
    op.create_index('ix_samsung_hrv_readings_user_id', 'samsung_hrv_readings', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_samsung_hrv_readings_user_id', table_name='samsung_hrv_readings')
    op.drop_index('ix_samsung_hrv_readings_id', table_name='samsung_hrv_readings')
    op.drop_table('samsung_hrv_readings')
