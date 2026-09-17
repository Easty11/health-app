"""add users.rpe_complete_from

Per-user RPE-complete epoch (DECISIONS_LOG P3 — tier0-v2 / banister-v3). The date from
which a user's RPE logging is complete enough that the strength/metabolic load calendar
should start there. When set, `load_metrics.compute_load_metrics` truncates that user's
daily series (every lane) to `occurred_at` local-day >= this date; earlier `load_events`
remain and still feed the e1RM fit, but never the stocks or ΔLoad. NULL = full history
(no truncation).

Placed on `users`, not `user_integrations`: the truncation applies to ALL lanes, the
metabolic lane included, which is not a Hevy-integration property — so the epoch is a
user-level fact, not a Hevy-credential one.

Backfill (17 Sep, health-app-DB): user 1 = 2026-05-11 (RPE presence stepped 8% -> 98%
that day); every other user NULL. User 4 has never logged RPE — her epoch stays NULL,
pending her adoption decision; if she adopts, it is set to her first RPE-present session
by a later operator-confirmed query.

Revision ID: a7f3c1e29d84
Revises: f2b7c1a4d9e0
Create Date: 2026-09-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a7f3c1e29d84'
down_revision: Union[str, Sequence[str], None] = 'f2b7c1a4d9e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column('rpe_complete_from', sa.Date(), nullable=True),
    )
    # Data backfill (same revision): only user 1 has an established RPE-complete date.
    # Every other row stays NULL (the column default) = full-history, no truncation.
    op.execute("UPDATE users SET rpe_complete_from = '2026-05-11' WHERE id = 1")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'rpe_complete_from')
