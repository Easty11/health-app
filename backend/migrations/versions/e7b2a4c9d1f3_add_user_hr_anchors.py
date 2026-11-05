"""add user_hr_anchors — the LTHR and RHR anchors of the per-class zone model (design 0010)

The zone model moves from one %HRmax band set to two bases chosen per sport class: % of
lactate-threshold HR for the cycling class and % of heart-rate reserve (HRmax - RHR) for every
other sport. HRmax already has its dated, append-only store (`user_hrmax`, §041/§043); the two new
anchors get a sibling table of the same shape rather than a `kind` column on `user_hrmax`, so the
table with a prod seed row, a single-writer guard and a restatement chain is not rewritten.

One new table, nothing altered. Empty until the operator seeds it through the Settings card after
this deploys; until then every row needing an anchor is withheld (`no_anchor`) and the metabolic
series under `metab-v2` is empty, not wrong. Hand-written (autogenerate produces neither partial
indexes nor CHECKs; see SCHEMA.md caveats). HELD for the operator's release (a schema migration);
Railway runs `alembic upgrade head` at boot, so merging deploys it.

Downgrade drops the table: it REFUSES while any row exists, because dropping an append-only
anchor ledger would silently destroy the history every re-zoned session depends on.

Revision ID: e7b2a4c9d1f3
Revises: c4a8e2f6b190
Create Date: 2026-11-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e7b2a4c9d1f3'
down_revision: Union[str, Sequence[str], None] = 'c4a8e2f6b190'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_hr_anchors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('bpm', sa.Integer(), nullable=False),
        sa.Column('provenance', sa.String(length=20), nullable=False),
        sa.Column('note', sa.String(length=1000), nullable=False),
        sa.Column('restates_id', sa.Integer(), nullable=True),
        sa.Column('rationale', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['restates_id'], ['user_hr_anchors.id'], name='fk_user_hr_anchor_restates'),
        sa.CheckConstraint("kind IN ('lthr', 'rhr')", name='ck_user_hr_anchor_kind'),
        sa.CheckConstraint("provenance IN ('tested', 'observed', 'device_estimated', 'stated')",
                           name='ck_user_hr_anchor_provenance'),
        sa.CheckConstraint('restates_id IS NULL OR rationale IS NOT NULL', name='ck_user_hr_anchor_rationale'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_user_hr_anchors_id', 'user_hr_anchors', ['id'])
    op.create_index('ix_user_hr_anchors_user_id', 'user_hr_anchors', ['user_id'])
    # One DATED row per user, kind and date; a row restated at most once (chains are linear).
    op.create_index('uq_user_hr_anchor_dated', 'user_hr_anchors', ['user_id', 'kind', 'effective_from'],
                    unique=True, postgresql_where=sa.text('restates_id IS NULL'))
    op.create_index('uq_user_hr_anchor_restates', 'user_hr_anchors', ['restates_id'],
                    unique=True, postgresql_where=sa.text('restates_id IS NOT NULL'))


def downgrade() -> None:
    """Downgrade schema — refused while the ledger holds a row."""
    conn = op.get_bind()
    n = conn.execute(sa.text('SELECT count(*) FROM user_hr_anchors')).scalar()
    if n:
        raise RuntimeError(f'refusing to drop user_hr_anchors: {n} anchor row(s) exist (append-only ledger)')
    op.drop_index('uq_user_hr_anchor_restates', table_name='user_hr_anchors')
    op.drop_index('uq_user_hr_anchor_dated', table_name='user_hr_anchors')
    op.drop_index('ix_user_hr_anchors_user_id', table_name='user_hr_anchors')
    op.drop_index('ix_user_hr_anchors_id', table_name='user_hr_anchors')
    op.drop_table('user_hr_anchors')
