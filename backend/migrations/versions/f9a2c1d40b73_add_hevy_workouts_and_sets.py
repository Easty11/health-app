"""add_hevy_workouts_and_sets

Revision ID: f9a2c1d40b73
Revises: b7c3e91f2a48
Create Date: 2026-08-25 00:00:00.000000

Persistence layer for the Q6 four-window strength-load lane (DECISIONS_LOG
#28/#32, the persistence-first session). Two tables:

  hevy_workouts — workout header, keyed on the Hevy workout id (PK) so ingestion
    is a PK-upsert (D-G dedup is flag-and-adjudicate, never delete). `raw` keeps
    the untouched Hevy payload (JSONB on Postgres) so any later transform version
    recomputes load from source without a re-fetch (D-B two-level store).
    `dedup_flag`/`dedup_partner_ids` are sync-derived and recompute-safe;
    `excluded_at`/`exclusion_reason` are the operator-owned adjudication mark the
    sync path never writes.

  hevy_sets — per-set grain (weight_kg × reps, rpe, set type) the D-C transform
    reads. Synthetic PK; natural key (workout_id, block_index, set_index).
    `exercise_template_id` is stored plain (keyed on id per #79) with NO FK to
    hevy_exercise_templates — a logged template id can be absent from the local
    catalogue (#79/#81), which is exactly what the usage-joined laterality audit
    must surface; a hard FK would reject those ingests. The audit LEFT-joins.

Does NOT touch exercise_sessions (#19, reserved).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'f9a2c1d40b73'
down_revision: Union[str, Sequence[str], None] = 'b7c3e91f2a48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'hevy_workouts',
        sa.Column('hevy_id', sa.String(64), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('dedup_flag', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('dedup_partner_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('excluded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('exclusion_reason', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('hevy_id'),
    )
    op.create_index('ix_hevy_workouts_user_id', 'hevy_workouts', ['user_id'])
    op.create_index('ix_hevy_workouts_start_time', 'hevy_workouts', ['start_time'])
    op.create_index('ix_hevy_workouts_user_start', 'hevy_workouts', ['user_id', 'start_time'])

    op.create_table(
        'hevy_sets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workout_id', sa.String(64), nullable=False),
        sa.Column('exercise_template_id', sa.String(64), nullable=False),
        sa.Column('block_index', sa.Integer(), nullable=False),
        sa.Column('set_index', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(20), nullable=True),
        sa.Column('weight_kg', sa.Float(), nullable=True),
        sa.Column('reps', sa.Integer(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('distance_meters', sa.Float(), nullable=True),
        sa.Column('rpe', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['workout_id'], ['hevy_workouts.hevy_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workout_id', 'block_index', 'set_index', name='uq_hevy_set_position'),
    )
    op.create_index('ix_hevy_sets_workout_id', 'hevy_sets', ['workout_id'])
    op.create_index('ix_hevy_sets_exercise_template_id', 'hevy_sets', ['exercise_template_id'])


def downgrade() -> None:
    op.drop_index('ix_hevy_sets_exercise_template_id', table_name='hevy_sets')
    op.drop_index('ix_hevy_sets_workout_id', table_name='hevy_sets')
    op.drop_table('hevy_sets')
    op.drop_index('ix_hevy_workouts_user_start', table_name='hevy_workouts')
    op.drop_index('ix_hevy_workouts_start_time', table_name='hevy_workouts')
    op.drop_index('ix_hevy_workouts_user_id', table_name='hevy_workouts')
    op.drop_table('hevy_workouts')
