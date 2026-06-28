"""add_health_connect_record_sources

Revision ID: c9b8a7d6e5f4
Revises: e1f2a3b4c5d6
Create Date: 2026-06-29 00:00:00.000000

Adds health_connect_record_sources — per-record writer identity captured from
/health-connect/sync BEFORE _aggregate_day collapses the night.

Backend enabler for source-priority dedup (DECISIONS_LOG #35 F1 / #36 / #37).
source_package is nullable: current HCA builds send no dataOrigin, so a required
column would 422 every live sync. The aggregated health_connect_syncs table is
unchanged. uq_hc_record_source makes re-syncs idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c9b8a7d6e5f4'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'health_connect_record_sources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('record_type', sa.String(40), nullable=False),
        sa.Column('record_start', sa.String(40), nullable=False),
        sa.Column('source_package', sa.String(255), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'record_type', 'record_start', name='uq_hc_record_source'),
    )
    op.create_index('ix_health_connect_record_sources_id', 'health_connect_record_sources', ['id'])
    op.create_index('ix_health_connect_record_sources_user_id', 'health_connect_record_sources', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_health_connect_record_sources_user_id', table_name='health_connect_record_sources')
    op.drop_index('ix_health_connect_record_sources_id', table_name='health_connect_record_sources')
    op.drop_table('health_connect_record_sources')
