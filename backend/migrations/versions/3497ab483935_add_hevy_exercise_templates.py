"""add hevy_exercise_templates

Revision ID: 3497ab483935
Revises: 217dce22fbc5
Create Date: 2026-07-08 15:15:19.012000

Isolated schema commit (DECISIONS_LOG #61). Autogenerate also surfaced local
SQLite-vs-Railway drift (exercise_sessions drop, samsung_hrv_readings.context,
user_integrations.api_key_encrypted VARCHAR->TEXT) — deliberately stripped so
this migration adds only the new table. That drift is a separate reconciliation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3497ab483935'
down_revision: Union[str, Sequence[str], None] = '217dce22fbc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'hevy_exercise_templates',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=True),
        sa.Column('is_custom', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
        sa.Column('primary_muscle_group', sa.String(length=100), nullable=True),
        sa.Column('secondary_muscle_groups', sa.JSON(), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_hevy_exercise_templates_owner_user_id', 'hevy_exercise_templates', ['owner_user_id'], unique=False)
    op.create_index('ix_hevy_exercise_templates_title', 'hevy_exercise_templates', ['title'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_hevy_exercise_templates_title', table_name='hevy_exercise_templates')
    op.drop_index('ix_hevy_exercise_templates_owner_user_id', table_name='hevy_exercise_templates')
    op.drop_table('hevy_exercise_templates')
