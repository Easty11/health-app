"""add session_rpe_observations (the source-neutral per-session sRPE store) and copy the Garmin rows into it

HELD for the operator's release (hold (a): a schema migration). Railway auto-runs `alembic upgrade head`
on deploy, so the merge IS the release.

One new table of per-activity RPE observations from ANY source: user, source, the source's own activity
ref, the bout's UTC window, the raw rating and the scale it came in, the rating converted to CR-10, an
optional source-specific `feel`, capture time and free provenance. INSERT-ONLY by the writer's discipline
(`srpe_store.record_observation`, the only writer); unique on (user, source, source_activity_ref,
captured_at). `provenance` is JSONB on Postgres and generic JSON on SQLite (the models._JSONB variant).

Data step: every row of `garmin_activity_selfevals` is copied VERBATIM as source 'garmin' (captured_at,
window, rpe_cr10, feel, and unrated marker rows all preserved; `rpe_raw` is `rpe_cr10 * 10`, exact because
Garmin's scale is CR-10 times ten). The old `aerobic_session_id` link and the row id travel as provenance
only; nothing reads them. The old table is NOT touched and stays read-only, its drop proposed separately.
The copy is skipped in offline (`--sql`) mode, which cannot read rows.

Downgrade drops the new table. Observations written after the upgrade exist only there and are lost; the
Garmin sweep re-reads at most the last 14 days of them.

Revision ID: e2a4c6d8f1b3
Revises: 295da687b02e
Create Date: 2026-10-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'e2a4c6d8f1b3'
down_revision: Union[str, Sequence[str], None] = '295da687b02e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirror models._JSONB: JSONB under Postgres (the deployed engine), generic JSON elsewhere.
_JSONB = sa.JSON().with_variant(JSONB, "postgresql")

_NEW = sa.table(
    'session_rpe_observations',
    sa.column('user_id', sa.Integer), sa.column('source', sa.String), sa.column('source_activity_ref', sa.String),
    sa.column('start_time', sa.DateTime(timezone=True)), sa.column('stop_time', sa.DateTime(timezone=True)),
    sa.column('rpe_raw', sa.Float), sa.column('raw_scale', sa.String), sa.column('rpe_cr10', sa.Float),
    sa.column('feel', sa.Integer), sa.column('captured_at', sa.DateTime(timezone=True)),
    sa.column('provenance', _JSONB),
)
_OLD = sa.table(
    'garmin_activity_selfevals',
    sa.column('id', sa.Integer), sa.column('user_id', sa.Integer), sa.column('garmin_activity_id', sa.BigInteger),
    sa.column('captured_at', sa.DateTime(timezone=True)), sa.column('rpe_cr10', sa.Float),
    sa.column('feel', sa.Integer), sa.column('garmin_type', sa.String),
    sa.column('start_time', sa.DateTime(timezone=True)), sa.column('stop_time', sa.DateTime(timezone=True)),
    sa.column('aerobic_session_id', sa.Integer),
)


def _copy_garmin_rows(bind) -> None:
    rows = bind.execute(sa.select(_OLD).order_by(_OLD.c.id)).mappings().all()
    batch = [
        {
            'user_id': r['user_id'], 'source': 'garmin', 'source_activity_ref': str(r['garmin_activity_id']),
            'start_time': r['start_time'], 'stop_time': r['stop_time'],
            'rpe_raw': None if r['rpe_cr10'] is None else round(r['rpe_cr10'] * 10, 6),
            'raw_scale': 'garmin_0_100', 'rpe_cr10': r['rpe_cr10'], 'feel': r['feel'],
            'captured_at': r['captured_at'],
            'provenance': {'garmin_type': r['garmin_type'], 'aerobic_session_id': r['aerobic_session_id'],
                           'copied_from': 'garmin_activity_selfevals', 'copied_from_id': r['id']},
        }
        for r in rows
    ]
    if batch:
        op.bulk_insert(_NEW, batch)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'session_rpe_observations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('source_activity_ref', sa.String(length=128), nullable=False),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('stop_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rpe_raw', sa.Float(), nullable=True),
        sa.Column('raw_scale', sa.String(length=32), nullable=False),
        sa.Column('rpe_cr10', sa.Float(), nullable=True),
        sa.Column('feel', sa.Integer(), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('provenance', _JSONB, nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'source', 'source_activity_ref', 'captured_at', name='uq_session_rpe_obs_capture'),
    )
    op.create_index('ix_session_rpe_observations_id', 'session_rpe_observations', ['id'])
    op.create_index('ix_session_rpe_observations_user_id', 'session_rpe_observations', ['user_id'])
    if not op.get_context().as_sql:
        _copy_garmin_rows(op.get_bind())


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_session_rpe_observations_user_id', table_name='session_rpe_observations')
    op.drop_index('ix_session_rpe_observations_id', table_name='session_rpe_observations')
    op.drop_table('session_rpe_observations')
