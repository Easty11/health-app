"""add_hrv_context

Revision ID: e1f2a3b4c5d6
Revises: d8e1f2a3b4c5
Create Date: 2026-06-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd8e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'samsung_hrv_readings',
        sa.Column(
            'context',
            sa.String(length=30),
            nullable=False,
            server_default='passive_overnight',
        ),
    )
    op.drop_constraint('uq_samsung_hrv_user_date', 'samsung_hrv_readings', type_='unique')
    op.create_unique_constraint(
        'uq_samsung_hrv_user_date_context',
        'samsung_hrv_readings',
        ['user_id', 'captured_at', 'context'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_samsung_hrv_user_date_context', 'samsung_hrv_readings', type_='unique')
    op.create_unique_constraint(
        'uq_samsung_hrv_user_date',
        'samsung_hrv_readings',
        ['user_id', 'captured_at'],
    )
    op.drop_column('samsung_hrv_readings', 'context')
