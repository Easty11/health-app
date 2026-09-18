"""add aerobic_sessions.source_package + recording_method (HC exercise ingest, #189/#309)

Stage-1 Health Connect exercise ingest (discharges #189's hold): a synced HC exercise
record becomes one `aerobic_sessions` row (source='health_connect'). Two new provenance
columns, both nullable:

  source_package   — the recording app's HC package (e.g. com.garmin.android.apps
                     .connectmobile, com.sec.android.app.shealth). Drives same-bout
                     WRITER-CLASS arbitration between two health_connect rows at read
                     time (reads/aerobic_reads.writer_class_rank). NULL for Polar rows,
                     which arbitrate cross-source by `source` as before.
  recording_method — HC ExerciseRecord.recordingMethod (Q118 persistence). Samsung
                     leaves it at sentinel 0, so it is descriptive, never a gate here.

No data backfill: every existing aerobic_sessions row is a Polar import, for which both
columns are legitimately NULL. Add-column-nullable is dialect-safe on SQLite and Postgres.

Revision ID: b2c4d6e8f0a1
Revises: a7f3c1e29d84
Create Date: 2026-09-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2c4d6e8f0a1'
down_revision: Union[str, Sequence[str], None] = 'a7f3c1e29d84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'aerobic_sessions',
        sa.Column('source_package', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'aerobic_sessions',
        sa.Column('recording_method', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('aerobic_sessions', 'recording_method')
    op.drop_column('aerobic_sessions', 'source_package')
