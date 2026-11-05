"""add garmin_activity_metrics — Garmin's per-activity summary metrics, displayed, never a load input

One row per Garmin activity per user, upserted from the activity DETAIL (`summaryDTO`) the Personal API
self-evaluation lane already fetches (`garmin_selfeval`), so no extra request carries the summary. The
columns are the operator's 6 Nov 2026 `--keys` probe of activity 24970929418: `trainingEffect` is the
AEROBIC Training Effect (there is no `aerobicTrainingEffect` key). Every metric column is nullable and
stored as received (a missing key is NULL); `summary_raw` keeps the whole `summaryDTO` so a field wanted
later needs no re-fetch.

The row carries the activity's own start and duration and NO link to an `aerobic_sessions` row: placement
on a session is read-time window overlap (`reads.srpe_reads._place`; ruling R1). The two `hr_stream_*`
columns record that the activity's HR stream (the details endpoint, written to `hr_samples` as
`garmin` / `activity_details`) was fetched and how many samples it gave, so a stream is fetched once.

Vendor composites (Training Effect, Garmin load) are DISPLAY ONLY: a guard test fails if the metabolic
transform or any readiness input reads this table.

One new table, nothing altered. HELD for the operator's release (a schema migration); Railway runs
`alembic upgrade head` at boot, so merging deploys it. Downgrade drops the table: every row is
re-fetchable from Garmin (the backfill script), so nothing is lost that cannot be read again.

Revision ID: a9d3f5b7c2e4
Revises: e7b2a4c9d1f3
Create Date: 2026-11-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'a9d3f5b7c2e4'
down_revision: Union[str, Sequence[str], None] = 'e7b2a4c9d1f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'garmin_activity_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('garmin_activity_id', sa.BigInteger(), nullable=False),
        sa.Column('start_time_gmt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_s', sa.Float(), nullable=True),
        sa.Column('calories', sa.Float(), nullable=True),
        sa.Column('bmr_calories', sa.Float(), nullable=True),
        sa.Column('te_aerobic', sa.Float(), nullable=True),
        sa.Column('te_anaerobic', sa.Float(), nullable=True),
        sa.Column('te_label', sa.String(length=64), nullable=True),
        sa.Column('training_load', sa.Float(), nullable=True),
        sa.Column('resp_avg', sa.Float(), nullable=True),
        sa.Column('resp_max', sa.Float(), nullable=True),
        sa.Column('resp_min', sa.Float(), nullable=True),
        sa.Column('recovery_hr', sa.Float(), nullable=True),
        sa.Column('intensity_min_moderate', sa.Float(), nullable=True),
        sa.Column('intensity_min_vigorous', sa.Float(), nullable=True),
        sa.Column('water_estimated_ml', sa.Float(), nullable=True),
        sa.Column('body_battery_delta', sa.Float(), nullable=True),
        sa.Column('summary_raw', _JSONB, nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('hr_stream_fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('hr_stream_samples', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'garmin_activity_id', name='uq_garmin_activity_metric'),
    )
    op.create_index('ix_garmin_activity_metrics_id', 'garmin_activity_metrics', ['id'])
    op.create_index('ix_garmin_activity_metrics_user_id', 'garmin_activity_metrics', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_garmin_activity_metrics_user_id', table_name='garmin_activity_metrics')
    op.drop_index('ix_garmin_activity_metrics_id', table_name='garmin_activity_metrics')
    op.drop_table('garmin_activity_metrics')
