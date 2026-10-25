"""Garmin Personal API: credential columns, hrv transport, raw landing, sleep/physiology/status tables (M1)

ADDITIVE ONLY. Nothing is dropped, retyped or backfilled; every new column is nullable and every new
table is empty until the code that fills it deploys. The data step (stamping existing
`hrv_readings.transport = 'di'`) is deliberately NOT here: it is a separate held revision (M2) so it can be
reviewed and run on its own.

  user_integrations            + key_expires_on, access_token_encrypted, access_token_expires_at
                                 (provider='garmin_personal' rows; NULL on every other provider)
  hrv_readings                 + transport  ('personal_api' | 'di'; source stays 'garmin')
  garmin_raw_payloads          append-only raw landing; unique (user, endpoint, ref, payload_sha256)
  sleep_nights                 per wake-date, source-neutral; unique (user, captured_at, source)
  spo2_hourly                  hourly SpO2 averages; unique (user, hour_start, source)
  daily_physiology             per calendar day RHR / stress / body battery; unique (user, date, source)
  hr_zone_config_snapshots     append-only HR-zone config change history
  integration_lane_status      per-user, per-lane sync status; unique (user, lane)

Revision ID: c4a8e2f6b190
Revises: b8f3d6a2c915
Create Date: 2026-10-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'c4a8e2f6b190'
down_revision: Union[str, Sequence[str], None] = 'b8f3d6a2c915'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JSONB = sa.JSON().with_variant(postgresql.JSONB(), 'postgresql')
_NOW = sa.func.now()


def _user_fk():
    return sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('user_integrations', sa.Column('key_expires_on', sa.Date(), nullable=True))
    op.add_column('user_integrations', sa.Column('access_token_encrypted', sa.Text(), nullable=True))
    op.add_column('user_integrations',
                  sa.Column('access_token_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('hrv_readings', sa.Column('transport', sa.String(length=20), nullable=True))

    op.create_table(
        'garmin_raw_payloads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.String(length=48), nullable=False),
        sa.Column('ref', sa.String(length=64), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column('payload_sha256', sa.String(length=64), nullable=False),
        sa.Column('payload', _JSONB, nullable=False),
        _user_fk(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'endpoint', 'ref', 'payload_sha256', name='uq_garmin_raw_payload'),
    )
    op.create_index('ix_garmin_raw_payloads_id', 'garmin_raw_payloads', ['id'])
    op.create_index('ix_garmin_raw_payloads_user_id', 'garmin_raw_payloads', ['user_id'])
    op.create_index('ix_garmin_raw_payloads_key', 'garmin_raw_payloads', ['user_id', 'endpoint', 'ref'])

    op.create_table(
        'sleep_nights',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('captured_at', sa.Date(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('transport', sa.String(length=20), nullable=False),
        sa.Column('sleep_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sleep_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sleep_time_s', sa.Integer(), nullable=True),
        sa.Column('deep_s', sa.Integer(), nullable=True),
        sa.Column('light_s', sa.Integer(), nullable=True),
        sa.Column('rem_s', sa.Integer(), nullable=True),
        sa.Column('awake_s', sa.Integer(), nullable=True),
        sa.Column('respiration_avg', sa.Float(), nullable=True),
        sa.Column('respiration_low', sa.Float(), nullable=True),
        sa.Column('respiration_high', sa.Float(), nullable=True),
        sa.Column('spo2_avg_pct', sa.Float(), nullable=True),
        sa.Column('spo2_lowest_pct', sa.Float(), nullable=True),
        sa.Column('sleep_score', sa.Integer(), nullable=True),
        sa.Column('sleep_scores_subs', _JSONB, nullable=True),
        sa.Column('awake_count', sa.Integer(), nullable=True),
        sa.Column('avg_sleep_stress', sa.Float(), nullable=True),
        sa.Column('sleep_need', _JSONB, nullable=True),
        sa.Column('efficiency_pct', sa.Float(), nullable=True),
        sa.Column('efficiency_formula', sa.String(length=48), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=_NOW, nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=_NOW, nullable=True),
        _user_fk(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'captured_at', 'source', name='uq_sleep_night_user_date_source'),
    )
    op.create_index('ix_sleep_nights_id', 'sleep_nights', ['id'])
    op.create_index('ix_sleep_nights_user_id', 'sleep_nights', ['user_id'])
    op.create_index('ix_sleep_nights_captured_at', 'sleep_nights', ['captured_at'])

    op.create_table(
        'spo2_hourly',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('hour_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('avg_pct', sa.Float(), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('transport', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=_NOW, nullable=True),
        _user_fk(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'hour_start', 'source', name='uq_spo2_hourly_user_hour_source'),
    )
    op.create_index('ix_spo2_hourly_id', 'spo2_hourly', ['id'])
    op.create_index('ix_spo2_hourly_user_id', 'spo2_hourly', ['user_id'])

    op.create_table(
        'daily_physiology',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('transport', sa.String(length=20), nullable=False),
        sa.Column('resting_hr_bpm', sa.Integer(), nullable=True),
        sa.Column('rhr_7d_avg_bpm', sa.Integer(), nullable=True),
        sa.Column('stress_avg', sa.Integer(), nullable=True),
        sa.Column('stress_max', sa.Integer(), nullable=True),
        sa.Column('body_battery_high', sa.Integer(), nullable=True),
        sa.Column('body_battery_low', sa.Integer(), nullable=True),
        sa.Column('body_battery_charged', sa.Integer(), nullable=True),
        sa.Column('body_battery_drained', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=_NOW, nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=_NOW, nullable=True),
        _user_fk(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'date', 'source', name='uq_daily_physiology_user_date_source'),
    )
    op.create_index('ix_daily_physiology_id', 'daily_physiology', ['id'])
    op.create_index('ix_daily_physiology_user_id', 'daily_physiology', ['user_id'])
    op.create_index('ix_daily_physiology_date', 'daily_physiology', ['date'])

    op.create_table(
        'hr_zone_config_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('captured_at', sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('transport', sa.String(length=20), nullable=False),
        sa.Column('max_hr_bpm', sa.Integer(), nullable=True),
        sa.Column('lthr_bpm', sa.Integer(), nullable=True),
        sa.Column('rhr_7d_auto_bpm', sa.Integer(), nullable=True),
        sa.Column('method', sa.String(length=60), nullable=True),
        sa.Column('payload_sha256', sa.String(length=64), nullable=False),
        _user_fk(),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_hr_zone_config_snapshots_id', 'hr_zone_config_snapshots', ['id'])
    op.create_index('ix_hr_zone_config_snapshots_user_id', 'hr_zone_config_snapshots', ['user_id'])
    op.create_index('ix_hr_zone_config_user_captured', 'hr_zone_config_snapshots', ['user_id', 'captured_at'])

    op.create_table(
        'integration_lane_status',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('lane', sa.String(length=40), nullable=False),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome', sa.String(length=30), nullable=False),
        sa.Column('reason', sa.String(length=200), nullable=True),
        _user_fk(),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'lane', name='uq_integration_lane_user_lane'),
    )
    op.create_index('ix_integration_lane_status_id', 'integration_lane_status', ['id'])
    op.create_index('ix_integration_lane_status_user_id', 'integration_lane_status', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_integration_lane_status_user_id', table_name='integration_lane_status')
    op.drop_index('ix_integration_lane_status_id', table_name='integration_lane_status')
    op.drop_table('integration_lane_status')
    op.drop_index('ix_hr_zone_config_user_captured', table_name='hr_zone_config_snapshots')
    op.drop_index('ix_hr_zone_config_snapshots_user_id', table_name='hr_zone_config_snapshots')
    op.drop_index('ix_hr_zone_config_snapshots_id', table_name='hr_zone_config_snapshots')
    op.drop_table('hr_zone_config_snapshots')
    op.drop_index('ix_daily_physiology_date', table_name='daily_physiology')
    op.drop_index('ix_daily_physiology_user_id', table_name='daily_physiology')
    op.drop_index('ix_daily_physiology_id', table_name='daily_physiology')
    op.drop_table('daily_physiology')
    op.drop_index('ix_spo2_hourly_user_id', table_name='spo2_hourly')
    op.drop_index('ix_spo2_hourly_id', table_name='spo2_hourly')
    op.drop_table('spo2_hourly')
    op.drop_index('ix_sleep_nights_captured_at', table_name='sleep_nights')
    op.drop_index('ix_sleep_nights_user_id', table_name='sleep_nights')
    op.drop_index('ix_sleep_nights_id', table_name='sleep_nights')
    op.drop_table('sleep_nights')
    op.drop_index('ix_garmin_raw_payloads_key', table_name='garmin_raw_payloads')
    op.drop_index('ix_garmin_raw_payloads_user_id', table_name='garmin_raw_payloads')
    op.drop_index('ix_garmin_raw_payloads_id', table_name='garmin_raw_payloads')
    op.drop_table('garmin_raw_payloads')
    op.drop_column('hrv_readings', 'transport')
    op.drop_column('user_integrations', 'access_token_expires_at')
    op.drop_column('user_integrations', 'access_token_encrypted')
    op.drop_column('user_integrations', 'key_expires_on')
