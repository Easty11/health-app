"""add daily_records.got_into_bed (CBT-I phase 2)

Revision ID: a7b3f1c8d240
Revises: e5f2a9c7b104
Create Date: 2026-07-22

The VA CBT-I diary separates "got into bed" from "tried to sleep". Phase 1
imported only the latter as `lights_out`, because sleep efficiency is computed
over the tried-to-sleep window (SE = TST / (out_of_bed - lights_out)), and
importing a second bedtime moment that nothing consumed would have been dead
data. Phase 2's capture surface asks for both, so the column lands now.

Additive and nullable. Historical rows (the 53 imported nights) stay NULL by
design — the source recorded the value but phase 1 did not import it, and
backfilling it would violate the frozen-at-capture contract the AM fields carry.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b3f1c8d240'
down_revision: Union[str, Sequence[str], None] = 'e5f2a9c7b104'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('daily_records', sa.Column(
        'got_into_bed', sa.String(5), nullable=True,
        comment='Clock time got into bed. Distinct from lights_out (tried to sleep), '
                'which is where the SE window opens. NULL on phase-1 imported rows.',
    ))


def downgrade() -> None:
    op.drop_column('daily_records', 'got_into_bed')
