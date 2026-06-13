"""structured_knowledge_schema

Revision ID: f4e9d2c1b3a7
Revises: da60d2b93599
Create Date: 2026-06-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4e9d2c1b3a7'
down_revision: Union[str, Sequence[str], None] = 'a3f7e9b1c2d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_knowledge_entries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('key', sa.String(255), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('added_at', sa.Date(), nullable=False, server_default=sa.text('CURRENT_DATE')),
        sa.Column('expires_at', sa.Date(), nullable=True),
        sa.Column('superseded_by', sa.Integer(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column('notes', sa.String(1000), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['superseded_by'], ['user_knowledge_entries.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_uke_user_type_active',
        'user_knowledge_entries',
        ['user_id', 'type', 'active'],
    )


def downgrade() -> None:
    op.drop_index('ix_uke_user_type_active', table_name='user_knowledge_entries')
    op.drop_table('user_knowledge_entries')
