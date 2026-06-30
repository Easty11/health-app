"""add_health_connect_record_sources

Revision ID: c9b8a7d6e5f4
Revises: e1f2a3b4c5d6
Create Date: 2026-06-29 00:00:00.000000

Adds health_connect_record_sources — per-record writer identity captured from
/health-connect/sync BEFORE _aggregate_day collapses the night.

Backend enabler for source-priority dedup (DECISIONS_LOG #35 F1 / #36 / #37).
source_package stays column-nullable (the inbound request field is optional —
current HCA builds send no dataOrigin), but _capture_record_sources coalesces a
missing identity to the literal 'unknown' before insert, so a value always flows.
The aggregated health_connect_syncs table is unchanged.

uq_hc_record_source spans (user_id, record_type, record_start, source_package):
two apps writing the same (type, timestamp) now persist as two rows instead of
one overwriting the other — the multi-writer signal F1 needs (supersedes #37's
"natural key collapses them" caveat). The 'unknown' sentinel keeps re-syncs
idempotent on both dialects: a NULL would be UNIQUE-distinct (SQLite and
Postgres alike), so identity-less records would duplicate on every sync.

This migration is unreleased (master has not run it); edited in place rather
than stacked per the no-new-migration directive.
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
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'record_type', 'record_start', 'source_package', name='uq_hc_record_source'),
    )
    op.create_index('ix_health_connect_record_sources_id', 'health_connect_record_sources', ['id'])
    op.create_index('ix_health_connect_record_sources_user_id', 'health_connect_record_sources', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_health_connect_record_sources_user_id', table_name='health_connect_record_sources')
    op.drop_index('ix_health_connect_record_sources_id', table_name='health_connect_record_sources')
    op.drop_table('health_connect_record_sources')
