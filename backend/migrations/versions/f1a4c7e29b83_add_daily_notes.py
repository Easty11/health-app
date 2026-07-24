"""add daily_records free-text notes (am_notes, pm_notes)

Revision ID: f1a4c7e29b83
Revises: d3f7a1908c62
Create Date: 2026-07-25

Two nullable free-text columns for uncaptured context that does not fit a structured
field (a carnival alarm, an off night). SEPARATE am/pm columns, not one: the AM and PM
surfaces submit independently, so a shared column's later write would clobber the
earlier. Observational — read by no engine code.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a4c7e29b83'
down_revision: Union[str, Sequence[str], None] = 'd3f7a1908c62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('daily_records', sa.Column('am_notes', sa.Text(), nullable=True))
    op.add_column('daily_records', sa.Column('pm_notes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('daily_records', 'pm_notes')
    op.drop_column('daily_records', 'am_notes')
