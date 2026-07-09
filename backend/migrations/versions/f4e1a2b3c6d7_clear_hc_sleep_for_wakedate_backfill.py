"""clear health_connect_syncs sleep fields for wake-date re-sync backfill

Revision ID: f4e1a2b3c6d7
Revises: 3497ab483935
Create Date: 2026-07-09

Data-only migration (no schema change). OPEN_QUESTIONS Q4 / DECISIONS_LOG:
sleep was attributed by bed-date (and, under UTC timestamps, collapsed onto the
day before the local wake-date), landing one calendar day earlier than the
scraper. The forward fix re-attributes sleep to the LOCAL wake-date, but the
`/sync` upsert only writes non-null values, so it can never clear the stale
sleep values already sitting on the wrong (date-1) rows. This migration nulls
every sleep field so a post-deploy HCA re-sync repopulates correct wake-dates
with no stale carry-over. Idempotent (nulling an already-null column is a
no-op). Blast radius = the five sleep columns only; no other field is touched.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f4e1a2b3c6d7'
down_revision: Union[str, Sequence[str], None] = '3497ab483935'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE health_connect_syncs
        SET sleep_duration_minutes = NULL,
            sleep_score            = NULL,
            deep_sleep_minutes     = NULL,
            rem_sleep_minutes      = NULL,
            light_sleep_minutes    = NULL
        """
    )


def downgrade() -> None:
    # No-op: the cleared values were wrong (attributed to the wrong date) and are
    # not restorable. Correct sleep data comes from re-syncing under the fixed
    # wake-date attribution, not from a downgrade.
    pass
