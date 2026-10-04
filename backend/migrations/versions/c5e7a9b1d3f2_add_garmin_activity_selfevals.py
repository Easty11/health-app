"""add garmin_activity_selfevals (Q209 path a: immutable per-activity Garmin self-evaluation)

One row per observation of a Garmin Connect activity's self-evaluation: perceived effort
(`rpe_cr10`, Garmin's 0-100 `directWorkoutRpe` / 10) and `feel` (0-100), capture-timed
(`captured_at`) and INSERT-ONLY by the writer's discipline (a changed value inserts a new row;
nothing updates one). Both values are nullable: an unrated sighting is a row too, so an unrated
activity is not re-fetched daily. `aerobic_session_id` links the Health Connect row of the same
bout (nullable; ON DELETE SET NULL so a re-ingested HC row never takes a capture with it).

Additive and non-destructive: one new table, nothing altered, empty until the code that fills it
deploys. `garmin_activity_id` is BIGINT (Garmin ids exceed int32).

Revision ID: c5e7a9b1d3f2
Revises: b4d6f8a1c3e5
Create Date: 2026-10-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c5e7a9b1d3f2'
down_revision: Union[str, Sequence[str], None] = 'b4d6f8a1c3e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'garmin_activity_selfevals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('garmin_activity_id', sa.BigInteger(), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('rpe_cr10', sa.Float(), nullable=True),
        sa.Column('feel', sa.Integer(), nullable=True),
        sa.Column('garmin_type', sa.String(length=100), nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('stop_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('aerobic_session_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['aerobic_session_id'], ['aerobic_sessions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'garmin_activity_id', 'captured_at', name='uq_garmin_selfeval_capture'),
    )
    op.create_index('ix_garmin_activity_selfevals_id', 'garmin_activity_selfevals', ['id'])
    op.create_index('ix_garmin_activity_selfevals_user_id', 'garmin_activity_selfevals', ['user_id'])
    op.create_index('ix_garmin_activity_selfevals_aerobic_session_id', 'garmin_activity_selfevals',
                    ['aerobic_session_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_garmin_activity_selfevals_aerobic_session_id', table_name='garmin_activity_selfevals')
    op.drop_index('ix_garmin_activity_selfevals_user_id', table_name='garmin_activity_selfevals')
    op.drop_index('ix_garmin_activity_selfevals_id', table_name='garmin_activity_selfevals')
    op.drop_table('garmin_activity_selfevals')
