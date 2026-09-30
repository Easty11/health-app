"""add user_integrations.account_fingerprint (one external account, one user)

Root-cause guard for the Garmin account mix-up (30 Sep 2026): one Garmin account was connected
to two users because nothing tied a stored token to the account it belongs to. This adds a
nullable SHA-256 fingerprint of the external account's id and a PARTIAL unique index over
(provider, account_fingerprint) where the fingerprint is set, so the database itself refuses a
second user holding the same external account.

Additive and non-destructive: one nullable column, one partial index. No backfill here: existing
rows stay NULL (unconstrained) and are recorded lazily on their next sync
(`routers/garmin.py::_record_account_fingerprint`), which is best-effort and never fails a sync.
Partial indexes are hand-written (autogenerate never produces them; see SCHEMA.md caveats).

Revision ID: a9c3e5f7b1d2
Revises: f7a2c9e1d3b5
Create Date: 2026-09-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a9c3e5f7b1d2'
down_revision: Union[str, Sequence[str], None] = 'f7a2c9e1d3b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'user_integrations',
        sa.Column('account_fingerprint', sa.String(length=64), nullable=True),
    )
    op.create_index(
        'uq_user_integrations_provider_fingerprint',
        'user_integrations',
        ['provider', 'account_fingerprint'],
        unique=True,
        postgresql_where=sa.text('account_fingerprint IS NOT NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_user_integrations_provider_fingerprint', table_name='user_integrations')
    op.drop_column('user_integrations', 'account_fingerprint')
