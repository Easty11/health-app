"""add fortification_profiles.weekly_template

The capacity-quota microcycle (DECISIONS_LOG #221). One JSON object per profile:

    {"slots": [{"capacity": "STABILITY", "sessions_per_week": 2, "minutes": 15}, ...]}

Sport-agnostic by construction — a slot names a taxonomy `Capacity` and a dose, never
a sport, position, or exercise. Sport-specificity is expressed through the fields that
already exist (`vehicle_bias`, `horizon`, `primary_target`), so two users with identical
templates and different bias get different programmes. That is the design, not a gap.

Nullable with no server_default: NULL means "no template", a valid state rather than a
degraded one, and every existing row back-fills to it. `upsert_profile` cannot write NULL
back (its `is not None` guard, shared with every other field), so retirement is expressed
as the empty-slot sentinel `{"slots": []}` rather than a clear.

Revision ID: b7c3e91f2a48
Revises: a7c3f19d5e28
Create Date: 2026-08-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b7c3e91f2a48'
down_revision: Union[str, Sequence[str], None] = 'a7c3f19d5e28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'fortification_profiles',
        sa.Column('weekly_template', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('fortification_profiles', 'weekly_template')
