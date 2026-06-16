"""widen api_key_encrypted to text

Revision ID: a7d4f8e21c93
Revises: e3b2d1c4a5f6
Create Date: 2026-06-16 00:00:00.000000

v4 OAuth tokens (long JWT access_token + refresh_token) exceed the original
varchar(512) once Fernet-encrypted (~2.3k chars). Widen to TEXT.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7d4f8e21c93'
down_revision: Union[str, Sequence[str], None] = 'e3b2d1c4a5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'user_integrations',
        'api_key_encrypted',
        existing_type=sa.String(length=512),
        type_=sa.Text(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'user_integrations',
        'api_key_encrypted',
        existing_type=sa.Text(),
        type_=sa.String(length=512),
        existing_nullable=False,
    )
