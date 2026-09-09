"""add training_phases — phase-scoped A/B microcycle ledger (Q112)

Revision ID: f2b7c1a4d9e0
Revises: c1d2e3f4a5b6
Create Date: 2026-09-09

Q112 resolution (DECISIONS_LOG #270). A phase-tagged history ledger for the exposure
engine: separates DOING NOW (the open phase) from the profile's standing BUILDING TOWARD.
Append-only, structurally identical to `cbti_blocks` — the only permitted UPDATE is
`closed_on` / `close_reason` at closure (a model+application invariant, no DB trigger; the
SQLite test path builds via create_all, not migrations).

DB-enforced domain constraints, frozen snapshots of the canonical provenance tuples:
  ck_training_phase_probe_posture  — suppressed | held (required at write, no default, #230)
  ck_training_phase_asserted_by    — engine.profile.ASSERTED_BY_VALUES (#227)
  ck_training_phase_source         — routers.knowledge.SOURCE_VALUES (#230)

Additive: creates one table + its user_id index. Downgrade drops the table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2b7c1a4d9e0'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'training_phases',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(100), nullable=False),
        sa.Column('intent', sa.Text(), nullable=True),
        sa.Column('probe_posture', sa.String(10), nullable=False),
        sa.Column('capacities', sa.JSON(), nullable=True),
        sa.Column('microcycle', sa.JSON(), nullable=True),
        sa.Column('entered_on', sa.Date(), nullable=False),
        sa.Column('review_on', sa.Date(), nullable=True),
        sa.Column('closed_on', sa.Date(), nullable=True),
        sa.Column('close_reason', sa.Text(), nullable=True),
        sa.Column('asserted_by', sa.String(20), nullable=False),
        sa.Column('asserted_on', sa.Date(), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "probe_posture IN ('suppressed','held')",
            name='ck_training_phase_probe_posture',
        ),
        sa.CheckConstraint(
            "asserted_by IN ('user','engine','clinician')",
            name='ck_training_phase_asserted_by',
        ),
        sa.CheckConstraint(
            "source IN ('onboarding','chat','system','api')",
            name='ck_training_phase_source',
        ),
    )
    op.create_index('ix_training_phases_user_id', 'training_phases', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_training_phases_user_id', table_name='training_phases')
    op.drop_table('training_phases')
