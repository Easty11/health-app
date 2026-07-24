"""add daily_records waking-cause decomposition columns

Revision ID: b2d5f9e04a17
Revises: c4e8a2019bd7
Create Date: 2026-07-24

Three nullable counts decomposing night_wakings_n by cause: nocturia, pain,
spontaneous. night_wakings_n records HOW MANY arousals and waso_min HOW LONG, but
nothing records WHY. Sleep restriction addresses conditioned and homeostatic
fragmentation; it does not address nocturia. With PVR 229 mL on record and no
urology relationship, a titration stalling at the SE floor is ambiguous between
behavioural non-response and a urological constraint — opposite next actions.

Counts, not timestamps (3am recall does not support timestamps). Three columns, not
JSON (the series is meant to be trended). NO sum constraint tying them to
night_wakings_n: recall is imperfect and enforcement would block submission;
consistency is surfaced, never enforced.

OBSERVATIONAL ONLY — the engine must not read them. `grep -rn 'wakings_' cbti/`
returns nothing outside tests, and that isolation is what makes the columns safe to
land mid-block (block 3 is open) without perturbing an in-flight prescription.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2d5f9e04a17'
down_revision: Union[str, Sequence[str], None] = 'c4e8a2019bd7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('daily_records', sa.Column(
        'wakings_nocturia_n', sa.Integer(), nullable=True,
        comment='Night arousals attributed to nocturia. Observational; engine must not read.',
    ))
    op.add_column('daily_records', sa.Column(
        'wakings_pain_n', sa.Integer(), nullable=True,
        comment='Night arousals attributed to pain. Observational; engine must not read.',
    ))
    op.add_column('daily_records', sa.Column(
        'wakings_spontaneous_n', sa.Integer(), nullable=True,
        comment='Night arousals with no attributed cause. Observational; engine must not read.',
    ))


def downgrade() -> None:
    op.drop_column('daily_records', 'wakings_spontaneous_n')
    op.drop_column('daily_records', 'wakings_pain_n')
    op.drop_column('daily_records', 'wakings_nocturia_n')
