"""add CBT-I data substrate: diary fields on daily_records + cbti_blocks/cbti_prescriptions

Revision ID: e5f2a9c7b104
Revises: c3a2d8e5f109
Create Date: 2026-07-22

CBT-I module phase 1 (DECISIONS_LOG #107 titration-on-TST / #108 block-structured,
readiness-isolated). All additive.

daily_records gains 9 nullable AM-moment diary columns, sparse by design (captured
only while an open cbti_block exists). diary_se_pct / diary_tst_min are frozen at AM
capture — same contract as naive_baseline, never recomputed. naps_min is logged PM on
date D but belongs to the night terminating on wake-date D+1: stored at PM on D, the
engine reads it from (date - 1) — encoded in the column comment, not only in the engine.

cbti_blocks and cbti_prescriptions are append-only ledgers. The only permitted UPDATEs:
  cbti_blocks        — closed_on / close_reason / exit_tst_min / exit_se_pct (at closure)
  cbti_prescriptions — effective_to / superseded_by (when a successor takes over)
Append-only is a model+application invariant (no DB trigger — the repo has no such
precedent and the SQLite test path builds via create_all, not migrations). The one
DB-enforced domain constraint is ck_cbti_prescription_decision.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f2a9c7b104'
down_revision: Union[str, Sequence[str], None] = 'c3a2d8e5f109'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Step 2: sleep-diary fields on daily_records (additive, nullable, AM-moment) ──
    op.add_column('daily_records', sa.Column('lights_out', sa.String(5), nullable=True))
    op.add_column('daily_records', sa.Column('sleep_latency_min', sa.Integer(), nullable=True))
    op.add_column('daily_records', sa.Column('waso_min', sa.Integer(), nullable=True))
    op.add_column('daily_records', sa.Column('night_wakings_n', sa.Integer(), nullable=True))
    op.add_column('daily_records', sa.Column('final_wake', sa.String(5), nullable=True))
    op.add_column('daily_records', sa.Column('out_of_bed', sa.String(5), nullable=True))
    op.add_column('daily_records', sa.Column(
        'naps_min', sa.Integer(), nullable=True,
        comment='Logged PM on date D; belongs to night terminating D+1. Engine reads from (date-1).',
    ))
    op.add_column('daily_records', sa.Column('diary_se_pct', sa.Float(), nullable=True))
    op.add_column('daily_records', sa.Column('diary_tst_min', sa.Integer(), nullable=True))

    # ── Step 3: cbti_blocks (append-only) ───────────────────────────────────────────
    op.create_table(
        'cbti_blocks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('opened_on', sa.Date(), nullable=False),
        sa.Column('closed_on', sa.Date(), nullable=True),
        sa.Column('wake_anchor', sa.String(5), nullable=False),
        sa.Column('open_reason', sa.Text(), nullable=True),
        sa.Column('close_reason', sa.Text(), nullable=True),
        sa.Column('exit_tst_min', sa.Integer(), nullable=True),
        sa.Column('exit_se_pct', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cbti_blocks_user_id', 'cbti_blocks', ['user_id'])

    # ── Step 3: cbti_prescriptions (append-only) ────────────────────────────────────
    op.create_table(
        'cbti_prescriptions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('block_id', sa.Integer(), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=False),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('prescribed_lights_out', sa.String(5), nullable=False),
        sa.Column('wake_anchor', sa.String(5), nullable=False),
        sa.Column('window_minutes', sa.Integer(), nullable=False),
        sa.Column('decision', sa.String(10), nullable=False),
        sa.Column('basis_tst_min', sa.Integer(), nullable=True),
        sa.Column('basis_se_pct', sa.Float(), nullable=True),
        sa.Column('basis_nights_n', sa.Integer(), nullable=True),
        sa.Column('basis_window_start', sa.Date(), nullable=True),
        sa.Column('basis_window_end', sa.Date(), nullable=True),
        sa.Column('excluded_nights', sa.JSON(), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('superseded_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['block_id'], ['cbti_blocks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['superseded_by'], ['cbti_prescriptions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "decision IN ('adopt','extend','hold','compress','close')",
            name='ck_cbti_prescription_decision',
        ),
    )
    op.create_index('ix_cbti_prescriptions_block_id', 'cbti_prescriptions', ['block_id'])


def downgrade() -> None:
    op.drop_index('ix_cbti_prescriptions_block_id', table_name='cbti_prescriptions')
    op.drop_table('cbti_prescriptions')
    op.drop_index('ix_cbti_blocks_user_id', table_name='cbti_blocks')
    op.drop_table('cbti_blocks')
    for col in (
        'diary_tst_min', 'diary_se_pct', 'naps_min', 'out_of_bed', 'final_wake',
        'night_wakings_n', 'waso_min', 'sleep_latency_min', 'lights_out',
    ):
        op.drop_column('daily_records', col)
