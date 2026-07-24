"""add cbti_isi — Insomnia Severity Index administrations

Revision ID: d3f7a1908c62
Revises: b2d5f9e04a17
Create Date: 2026-07-25

The ISI is the outcome measure a CBT-I block is judged by, and it had no home in the
schema — capture existed only in governance markdown and a QxMD administration. Seven
items stored (the record) plus the tool's reported total; the canonical total is derived
on read, never stored. block_id nullable (screening / between-block administrations have
no block); unique on (block_id, timepoint).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3f7a1908c62'
down_revision: Union[str, Sequence[str], None] = 'b2d5f9e04a17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cbti_isi',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('block_id', sa.Integer(), nullable=True),
        sa.Column('administered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('timepoint', sa.String(length=10), nullable=False),
        sa.Column('item_1', sa.Integer(), nullable=False),
        sa.Column('item_2', sa.Integer(), nullable=False),
        sa.Column('item_3', sa.Integer(), nullable=False),
        sa.Column('item_4', sa.Integer(), nullable=False),
        sa.Column('item_5', sa.Integer(), nullable=False),
        sa.Column('item_6', sa.Integer(), nullable=False),
        sa.Column('item_7', sa.Integer(), nullable=False),
        sa.Column('total_reported', sa.Integer(), nullable=True),
        sa.Column('instrument', sa.String(length=40), server_default=sa.text("'ISI'"), nullable=False),
        sa.Column('administered_via', sa.String(length=40), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['block_id'], ['cbti_blocks.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('block_id', 'timepoint', name='uq_cbti_isi_block_timepoint'),
        sa.CheckConstraint("timepoint IN ('baseline','mid','exit')", name='ck_cbti_isi_timepoint'),
    )
    op.create_index(op.f('ix_cbti_isi_block_id'), 'cbti_isi', ['block_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_cbti_isi_block_id'), table_name='cbti_isi')
    op.drop_table('cbti_isi')
