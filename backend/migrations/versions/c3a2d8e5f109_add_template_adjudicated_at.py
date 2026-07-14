"""add hevy_exercise_templates.adjudicated_at (three-state tag coverage)

Revision ID: c3a2d8e5f109
Revises: b2f1c9a4d7e8
Create Date: 2026-07-14

DECISIONS_LOG #76. Three-state tag coverage: NULL = never adjudicated (untagged,
keyword fallback); NOT NULL + >=1 exercise_region_tags row = tagged; NOT NULL +
zero rows = deliberate no-pattern. Set only by the --confirm seed;
`_upsert_template` never assigns it, so a Hevy resync preserves it (as with
laterality).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a2d8e5f109'
down_revision: Union[str, Sequence[str], None] = 'b2f1c9a4d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'hevy_exercise_templates',
        sa.Column('adjudicated_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('hevy_exercise_templates', 'adjudicated_at')
