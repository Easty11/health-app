"""add spo2_nights, spo2_samples and breathing_disruption_intervals (Q150: raw Garmin overnight SpO2 capture)

Three tables, a parent and two children, mirroring `hrv_readings` / `hrv_samples`:

  spo2_nights                    one row per (user, night, source): the wake-date, the sleep window
                                 Garmin reports, `reading_count` and `gap_count`. Unique
                                 (user_id, captured_at, source).
  spo2_samples                   one row per SpO2 epoch, exactly as sent: `spo2_pct`,
                                 `reading_confidence`, `epoch_duration_s`. Unique
                                 (spo2_night_id, reading_time). ON DELETE CASCADE from the night.
  breathing_disruption_intervals one row per `breathingDisruptionData` interval, raw, keyed by its
                                 position (`seq`) so a zero-length or repeated interval is kept.
                                 ON DELETE CASCADE from the night.

Nothing is derived, filtered or thresholded in the schema or by the writer (Q150): no minimum, no
average, no dip count. Additive and non-destructive: three new tables, nothing altered, empty until
the capture code that fills them deploys. The Garmin profile id and device id the payload also
carries are NOT columns and are never stored.

Revision ID: e0d53feadc9d
Revises: 295da687b02e
Create Date: 2026-10-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e0d53feadc9d'
down_revision: Union[str, Sequence[str], None] = '295da687b02e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'spo2_nights',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('captured_at', sa.Date(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('sleep_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sleep_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reading_count', sa.Integer(), nullable=False),
        sa.Column('gap_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'captured_at', 'source', name='uq_spo2_night_user_date_source'),
    )
    op.create_index('ix_spo2_nights_id', 'spo2_nights', ['id'])
    op.create_index('ix_spo2_nights_user_id', 'spo2_nights', ['user_id'])
    op.create_index('ix_spo2_nights_captured_at', 'spo2_nights', ['captured_at'])

    op.create_table(
        'spo2_samples',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('spo2_night_id', sa.Integer(), nullable=False),
        sa.Column('reading_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('spo2_pct', sa.Float(), nullable=True),
        sa.Column('reading_confidence', sa.Float(), nullable=True),
        sa.Column('epoch_duration_s', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['spo2_night_id'], ['spo2_nights.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('spo2_night_id', 'reading_time', name='uq_spo2_sample_night_time'),
    )
    op.create_index('ix_spo2_samples_id', 'spo2_samples', ['id'])
    op.create_index('ix_spo2_samples_spo2_night_id', 'spo2_samples', ['spo2_night_id'])

    op.create_table(
        'breathing_disruption_intervals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('spo2_night_id', sa.Integer(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('value', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['spo2_night_id'], ['spo2_nights.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('spo2_night_id', 'seq', name='uq_breathing_interval_night_seq'),
    )
    op.create_index('ix_breathing_disruption_intervals_id', 'breathing_disruption_intervals', ['id'])
    op.create_index('ix_breathing_disruption_intervals_spo2_night_id', 'breathing_disruption_intervals',
                    ['spo2_night_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_breathing_disruption_intervals_spo2_night_id', table_name='breathing_disruption_intervals')
    op.drop_index('ix_breathing_disruption_intervals_id', table_name='breathing_disruption_intervals')
    op.drop_table('breathing_disruption_intervals')
    op.drop_index('ix_spo2_samples_spo2_night_id', table_name='spo2_samples')
    op.drop_index('ix_spo2_samples_id', table_name='spo2_samples')
    op.drop_table('spo2_samples')
    op.drop_index('ix_spo2_nights_captured_at', table_name='spo2_nights')
    op.drop_index('ix_spo2_nights_user_id', table_name='spo2_nights')
    op.drop_index('ix_spo2_nights_id', table_name='spo2_nights')
    op.drop_table('spo2_nights')
