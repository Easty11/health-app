"""add mcp_oauth_clients and mcp_oauth_tokens (Q196: persist the MCP OAuth provider)

HELD for the operator's release (hold (a): a schema migration). Not applied to prod by the PR
that carries it; Railway auto-runs `alembic upgrade head` on deploy, so the merge IS the release.
The deploy that lands this wipes today's in-memory MCP tokens, so the operator re-authenticates
once; after it a redeploy no longer drops a connected client.

Adds two tables. `mcp_oauth_clients`: one row per dynamically registered client (the SDK's
`OAuthClientInformationFull` dump as JSON). `mcp_oauth_tokens`: one row per issued access or
refresh token, keyed by sha256(token) hex -- no raw token is ever stored. `user_id` is ON DELETE
CASCADE (a deleted user's tokens die with it) and so is `client_id`. Index (user_id, kind) serves
the per-user inventory; (refresh_hash) serves "revoke a refresh token's access tokens".

Additive: two new tables, nothing existing is touched. `scopes` is JSONB on Postgres and generic
JSON on SQLite (the models._JSONB variant), so the create_all test path builds it too.

Downgrade drops both tables (indexes and the check constraint go with them), tokens first because
they reference clients. It loses every issued MCP session, so each connected client re-authenticates
once -- which is exactly the pre-migration behaviour.

Revision ID: 295da687b02e
Revises: c3e5a7d9b1f4
Create Date: 2026-10-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = '295da687b02e'
down_revision: Union[str, Sequence[str], None] = 'c3e5a7d9b1f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirror models._JSONB: JSONB under Postgres (the deployed engine), generic JSON elsewhere.
_JSONB = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "mcp_oauth_clients",
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("client_info", _JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("client_id"),
    )
    op.create_table(
        "mcp_oauth_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=7), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("scopes", _JSONB, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('access', 'refresh')", name="ck_mcp_oauth_token_kind"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["mcp_oauth_clients.client_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_mcp_oauth_token_user_kind", "mcp_oauth_tokens", ["user_id", "kind"])
    op.create_index("ix_mcp_oauth_token_refresh_hash", "mcp_oauth_tokens", ["refresh_hash"])


def downgrade() -> None:
    op.drop_index("ix_mcp_oauth_token_refresh_hash", table_name="mcp_oauth_tokens")
    op.drop_index("ix_mcp_oauth_token_user_kind", table_name="mcp_oauth_tokens")
    op.drop_table("mcp_oauth_tokens")
    op.drop_table("mcp_oauth_clients")
