"""add health_connect_sync_events

Adds health_connect_sync_events — ONE row per POST to /health-connect/sync, holding
the client build fingerprint (git_sha/built_at/app_version/platform) and the fetch
telemetry (fetch_meta) HCA now sends under the `client` / `fetchMeta` keys
(HCA DECISIONS #40; cross-ref HCA Q22, the HR-lag deployment gap this makes prod-readable).

Per-POST, not per-date: a periodDays=7 POST fans out to ~7 health_connect_syncs rows,
but the fingerprint describes the sync EVENT, not a calendar day — a distinct grain from
the (user, date)-keyed health_connect_syncs. Capture-only: no aggregation or read path
touches it. git_sha nullable is the "still on an old build" SIGNAL (queryable), not a gap.
synced_at is the server clock (server_default now()), deliberately not the client syncedAt.

fetch_meta is JSONB on Postgres / JSON on SQLite (the models._JSONB variant), so the
create_all test path builds it too. Add-table is dialect-safe on SQLite and Postgres.

Revision ID: d9f2a1c7e4b8
Revises: b2c4d6e8f0a1
Create Date: 2026-09-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'd9f2a1c7e4b8'
down_revision: Union[str, Sequence[str], None] = 'b2c4d6e8f0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirror models._JSONB: JSONB under Postgres (the deployed engine), generic JSON elsewhere.
_JSONB = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        'health_connect_sync_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('git_sha', sa.String(80), nullable=True),
        sa.Column('built_at', sa.String(40), nullable=True),
        sa.Column('app_version', sa.String(40), nullable=True),
        sa.Column('platform', sa.String(40), nullable=True),
        sa.Column('period_days', sa.Integer(), nullable=True),
        sa.Column('fetch_meta', _JSONB, nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_health_connect_sync_events_id', 'health_connect_sync_events', ['id'])
    op.create_index('ix_health_connect_sync_events_user_id', 'health_connect_sync_events', ['user_id'])
    op.create_index('ix_health_connect_sync_events_synced_at', 'health_connect_sync_events', ['synced_at'])
    op.create_index('ix_hc_sync_events_user_synced', 'health_connect_sync_events', ['user_id', 'synced_at'])


def downgrade() -> None:
    op.drop_index('ix_hc_sync_events_user_synced', table_name='health_connect_sync_events')
    op.drop_index('ix_health_connect_sync_events_synced_at', table_name='health_connect_sync_events')
    op.drop_index('ix_health_connect_sync_events_user_id', table_name='health_connect_sync_events')
    op.drop_index('ix_health_connect_sync_events_id', table_name='health_connect_sync_events')
    op.drop_table('health_connect_sync_events')
