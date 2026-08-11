"""add interpretation_rephrases

Disposable plain-register overlay + promotion state for interpretation increment 2
(DECISIONS_LOG #202). One row per (payload_hash, register): the presentation cache (step 4)
AND the training-wheels promotion record (step 6). A table rather than an in-memory cache
because a promotion must survive a Railway restart. Expected at zero rows on first upgrade.

Revision ID: c3f1a8b2d9e4
Revises: b6f3d92a4e17
Create Date: 2026-08-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c3f1a8b2d9e4'
down_revision: Union[str, Sequence[str], None] = 'b6f3d92a4e17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'interpretation_rephrases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('register', sa.String(20), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'ai_draft'")),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('payload_hash', 'register', name='uq_interp_rephrase_payload_register'),
    )
    op.create_index('ix_interpretation_rephrases_payload_hash',
                    'interpretation_rephrases', ['payload_hash'])


def downgrade() -> None:
    op.drop_index('ix_interpretation_rephrases_payload_hash',
                  table_name='interpretation_rephrases')
    op.drop_table('interpretation_rephrases')
