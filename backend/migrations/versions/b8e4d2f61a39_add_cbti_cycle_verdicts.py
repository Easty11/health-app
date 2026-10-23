"""add cbti_cycle_verdicts: one frozen row per adjudicated CBT-I cycle (step 1 of #437 / #440)

Revision ID: b8e4d2f61a39
Revises: e5b2c8a91d47
Create Date: 2026-10-23

Step 1 of the verdict store designed in docs/cbti-verdict-store-design.md. Additive: ONE new
table, nothing altered, nothing reads or writes it yet, so this is a behaviour no-op. The table
is the record of a finding (a HOLD that applied, a move or converged verdict that was offered,
accepted or lapsed), not a prescription: writing a row mints nothing (#118).

All CHECKs and the two partial indexes are hand-written, as SCHEMA.md's Alembic caveats require.
`sqlite_where` is passed alongside `postgresql_where` so the SQLite test path builds the same
partial indexes. Append-only is a model-and-application invariant with no DB trigger, the repo's
discipline for cbti_blocks and cbti_prescriptions; the checks enforce the SHAPE of a row, not its
lifecycle. The `first_night` column on cbti_prescriptions (Q236, #441) is a separate migration.

Downgrade drops the indexes and then the table; it loses every verdict, so it is only safe before
the writers deploy.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8e4d2f61a39'
down_revision: Union[str, Sequence[str], None] = 'e5b2c8a91d47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cbti_cycle_verdicts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('block_id', sa.Integer(), nullable=False),
        sa.Column('prescription_id', sa.Integer(), nullable=False),
        sa.Column('cycle_start', sa.Date(), nullable=False),
        sa.Column('cycle_end', sa.Date(), nullable=False),
        sa.Column('chains_from_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('decision', sa.String(length=10), nullable=False),
        sa.Column('outcome', sa.String(length=12), nullable=False),
        sa.Column('sufficient', sa.Boolean(), nullable=False),
        sa.Column('converged', sa.Boolean(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('window_minutes', sa.Integer(), nullable=False),
        sa.Column('rec_window_minutes', sa.Integer(), nullable=False),
        sa.Column('rec_lights_out', sa.String(length=5), nullable=False),
        sa.Column('basis_tst_min', sa.Integer(), nullable=True),
        sa.Column('basis_se_pct', sa.Float(), nullable=True),
        sa.Column('basis_nights_n', sa.Integer(), nullable=False),
        sa.Column('basis_nights_logged', sa.Integer(), nullable=False),
        sa.Column('basis_n_flagged', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('excluded_nights', sa.JSON(), nullable=False),
        sa.Column('basis_ledger', sa.JSON(), nullable=False),
        sa.Column('ruleset_version', sa.String(length=40), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('applied_on', sa.Date(), nullable=True),
        sa.Column('minted_prescription_id', sa.Integer(), nullable=True),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('lapsed_by_id', sa.Integer(), nullable=True),
        sa.Column('lapsed_on', sa.Date(), nullable=True),
        sa.Column('unscored_from', sa.Date(), nullable=True),
        sa.Column('unscored_to', sa.Date(), nullable=True),
        sa.Column('surfaced_on', sa.Date(), nullable=True),
        sa.Column('origin', sa.String(length=10), server_default=sa.text("'engine'"), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['block_id'], ['cbti_blocks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['prescription_id'], ['cbti_prescriptions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['chains_from_id'], ['cbti_cycle_verdicts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['minted_prescription_id'], ['cbti_prescriptions.id']),
        sa.ForeignKeyConstraint(['lapsed_by_id'], ['cbti_cycle_verdicts.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('block_id', 'cycle_start', name='uq_cbti_verdict_cycle'),
        sa.CheckConstraint("status IN ('applied','offered','accepted','lapsed')", name='ck_cbti_verdict_status'),
        sa.CheckConstraint("decision IN ('hold','extend','compress')", name='ck_cbti_verdict_decision'),
        sa.CheckConstraint("outcome IN ('no_decision','hold','converged','extend','compress')",
                           name='ck_cbti_verdict_outcome'),
        sa.CheckConstraint("origin IN ('engine','backfill')", name='ck_cbti_verdict_origin'),
        sa.CheckConstraint('cycle_end >= cycle_start', name='ck_cbti_verdict_span'),
        sa.CheckConstraint("(status = 'applied') = (decision = 'hold' AND NOT converged)",
                           name='ck_cbti_verdict_kind'),
        sa.CheckConstraint("converged = (outcome = 'converged') AND (NOT converged OR decision = 'hold')",
                           name='ck_cbti_verdict_conv'),
        sa.CheckConstraint("sufficient OR (decision = 'hold' AND outcome = 'no_decision')",
                           name='ck_cbti_verdict_suff'),
        sa.CheckConstraint("status <> 'accepted' OR minted_prescription_id IS NOT NULL",
                           name='ck_cbti_verdict_accept'),
        sa.CheckConstraint("(status = 'lapsed') = (lapsed_by_id IS NOT NULL)", name='ck_cbti_verdict_lapse'),
        sa.CheckConstraint("origin = 'backfill' OR status <> 'applied' OR minted_prescription_id IS NULL",
                           name='ck_cbti_verdict_mint'),
    )
    op.create_index('ix_cbti_verdicts_block', 'cbti_cycle_verdicts', ['block_id', 'cycle_start'])
    op.create_index('uq_cbti_verdicts_one_offer', 'cbti_cycle_verdicts', ['block_id'], unique=True,
                    postgresql_where=sa.text("status = 'offered'"), sqlite_where=sa.text("status = 'offered'"))
    op.create_index('ix_cbti_verdicts_plateau', 'cbti_cycle_verdicts', ['block_id', 'cycle_start'],
                    postgresql_where=sa.text("status IN ('applied','accepted') AND basis_tst_min IS NOT NULL"),
                    sqlite_where=sa.text("status IN ('applied','accepted') AND basis_tst_min IS NOT NULL"))


def downgrade() -> None:
    op.drop_index('ix_cbti_verdicts_plateau', table_name='cbti_cycle_verdicts')
    op.drop_index('uq_cbti_verdicts_one_offer', table_name='cbti_cycle_verdicts')
    op.drop_index('ix_cbti_verdicts_block', table_name='cbti_cycle_verdicts')
    op.drop_table('cbti_cycle_verdicts')
