"""add adaptive exposure engine tables

Revision ID: d8e1f2a3b4c5
Revises: a7d4f8e21c93
Create Date: 2026-06-22 00:00:00.000000

Adaptive Exposure Engine (Decision Support module). Two tables:

  capability_state      — "map contents" (spec §3): this user's score per
                          taxonomy region, per-side. Self-builds one probe per
                          session. Standalone for now; folds into health_events
                          when that schema lands.
  fortification_profiles — fortification-target profile (spec §9): structured
                          per-user object replacing the hardcoded injury string
                          in context_builder. One row per user.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd8e1f2a3b4c5'
down_revision: Union[str, Sequence[str], None] = 'a7d4f8e21c93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'capability_state',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('region_key', sa.String(100), nullable=False),
        sa.Column('side', sa.String(20), nullable=False, server_default=sa.text("'bilateral'")),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'untested'")),
        sa.Column('source', sa.String(30), nullable=True),
        sa.Column('detail', sa.JSON(), nullable=True),
        sa.Column('last_probed_at', sa.Date(), nullable=True),
        sa.Column('taxonomy_version', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'region_key', 'side', name='uq_capability_user_region_side'),
    )
    op.create_index('ix_capability_state_user_id', 'capability_state', ['user_id'])
    op.create_index('ix_capability_user_status', 'capability_state', ['user_id', 'status'])

    op.create_table(
        'fortification_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('floor', sa.JSON(), nullable=True),
        sa.Column('ceiling', sa.String(20), nullable=True),
        sa.Column('horizon', sa.String(30), nullable=True),
        sa.Column('horizon_date', sa.Date(), nullable=True),
        sa.Column('primary_target', sa.String(100), nullable=True),
        sa.Column('primary_target_note', sa.Text(), nullable=True),
        sa.Column('live_signals', sa.JSON(), nullable=True),
        sa.Column('hard_stops', sa.JSON(), nullable=True),
        sa.Column('vehicle_bias', sa.JSON(), nullable=True),
        sa.Column('probe_budget', sa.Float(), nullable=False, server_default=sa.text("0.25")),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_fortification_user'),
    )
    op.create_index('ix_fortification_profiles_user_id', 'fortification_profiles', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_fortification_profiles_user_id', table_name='fortification_profiles')
    op.drop_table('fortification_profiles')
    op.drop_index('ix_capability_user_status', table_name='capability_state')
    op.drop_index('ix_capability_state_user_id', table_name='capability_state')
    op.drop_table('capability_state')
