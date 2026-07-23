"""add cbti_prescriptions.basis_n_samsung / basis_n_diary (adherence-source composition)

Revision ID: c4e8a2019bd7
Revises: a7b3f1c8d240
Create Date: 2026-07-23

The adherence gate has two sources of unequal strength: Samsung `bedtime` from the
`passive_overnight` allowlist (independent of the diary) and, where no such row
exists for a night, the diary's own `lights_out` — self-report checked against
self-report. Both are legitimate; they are not equivalent, and a prescription that
rested on the weaker one must say so on its own row.

Written at the same moment as `basis_nights_n` and never backfilled. Landed BEFORE
the replay rather than after it, so the nine replayed prescriptions carry
composition too — they are the rows a later reader compares against, and a
composition-less row would read as "not recorded" rather than "not applicable".

Concretely: Samsung `bedtime` has zero rows inside the imported block's window
(the table begins 2026-06-08; the block closed 2026-05-11), so every replayed
prescription is expected to carry n_samsung=0 and n_diary=basis_nights_n.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4e8a2019bd7'
down_revision: Union[str, Sequence[str], None] = 'a7b3f1c8d240'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cbti_prescriptions', sa.Column(
        'basis_n_samsung', sa.Integer(), nullable=True,
        comment='Basis nights whose adherence used Samsung bedtime (independent).',
    ))
    op.add_column('cbti_prescriptions', sa.Column(
        'basis_n_diary', sa.Integer(), nullable=True,
        comment='Basis nights whose adherence fell back to diary lights_out (self-report).',
    ))


def downgrade() -> None:
    op.drop_column('cbti_prescriptions', 'basis_n_diary')
    op.drop_column('cbti_prescriptions', 'basis_n_samsung')
