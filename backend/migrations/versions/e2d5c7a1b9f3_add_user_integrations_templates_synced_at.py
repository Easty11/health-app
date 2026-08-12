"""add user_integrations.templates_synced_at

Per-user catalogue-freshness marker (DECISIONS_LOG #211 / Q75 option (c)). Stamped by
`sync_one_user` when a user's Hevy template pull completes; read (single column) by the
staleness gate that piggybacks a sync on the workout-fetch path. Nullable: existing rows
back-fill to NULL, which the gate treats as "never synced" -> stale -> a first fetch
triggers a sync (self-healing, no data migration needed).

Chosen over an aggregate MAX(hevy_exercise_templates.synced_at): that column is per-row
and its default rows are re-stamped by ANY user's sync, so the aggregate reads fresh off
another user's run while this user's own customs are stale — wrong now that multi-user is
live (4 users in prod).

Revision ID: e2d5c7a1b9f3
Revises: c3f1a8b2d9e4
Create Date: 2026-08-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e2d5c7a1b9f3'
down_revision: Union[str, Sequence[str], None] = 'c3f1a8b2d9e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'user_integrations',
        sa.Column('templates_synced_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('user_integrations', 'templates_synced_at')
