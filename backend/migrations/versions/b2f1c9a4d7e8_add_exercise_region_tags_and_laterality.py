"""add exercise_region_tags + hevy_exercise_templates.laterality

Revision ID: b2f1c9a4d7e8
Revises: f4e1a2b3c6d7
Create Date: 2026-07-13

App-owned movement-taxonomy annotation (DECISIONS_LOG #NEXT). Two changes, one
feature:

  1. `exercise_region_tags` — a SEPARATE table (not columns on
     hevy_exercise_templates), keyed on the Hevy template id, so the
     upsert-from-sync path (`_upsert_template`) can never clobber a tag.
  2. `hevy_exercise_templates.laterality` — an exercise-level property NOT
     derivable from the region taxonomy. `_upsert_template` never assigns it,
     so a resync preserves it (proven by the G5 clobber test).

Hand-written (autogenerate would also surface unrelated SQLite-vs-Railway
drift — deliberately excluded, per the #61 migration's precedent).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2f1c9a4d7e8'
down_revision: Union[str, Sequence[str], None] = 'f4e1a2b3c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'hevy_exercise_templates',
        sa.Column('laterality', sa.String(length=20), nullable=True),
    )
    op.create_table(
        'exercise_region_tags',
        sa.Column('hevy_exercise_template_id', sa.String(length=64), nullable=False),
        sa.Column('region_key', sa.String(length=100), nullable=False),
        sa.Column('role', sa.String(length=20), server_default=sa.text("'primary'"), nullable=False),
        sa.Column('taxonomy_version', sa.String(length=20), server_default=sa.text("'v0'"), nullable=False),
        sa.Column('source', sa.String(length=20), server_default=sa.text("'llm_proposed'"), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['hevy_exercise_template_id'], ['hevy_exercise_templates.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('hevy_exercise_template_id', 'region_key'),
    )
    op.create_index('ix_exercise_region_tags_region_key', 'exercise_region_tags', ['region_key'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_exercise_region_tags_region_key', table_name='exercise_region_tags')
    op.drop_table('exercise_region_tags')
    op.drop_column('hevy_exercise_templates', 'laterality')
