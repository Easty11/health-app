"""add clinical_documents (Q142 option b: a dedicated store for imaging reports and clinical letters)

HELD for the operator's release (hold (a): a schema migration). Not applied to prod by the PR
that carries it; Railway auto-runs `alembic upgrade head` on deploy, so the merge IS the release.

Adds `clinical_documents`: one row per imaging report or clinical letter, keyed by a stable
per-user `doc_key`. The `LabReport` envelope pattern -- an observed document, so neither a
`user_knowledge_entries` type nor the deferred `health_events` spine. It is the target the
`document` evidence door of a finding resolves against.

Additive: one table, one unique constraint (user_id, doc_key), one index (user_id, service_date).
Both leading-user_id structures serve the per-user reads, so no separate user_id index.
`source_doc_filenames` / `structured` / `letter` / `extraction_notes` are JSONB on Postgres and
generic JSON on SQLite (the models._JSONB variant), so the create_all test path builds them too.

Downgrade drops the table (index and unique constraint go with it). It is lossless only while the
table is empty or re-importable: the payload file is the canonical extraction, and the import
endpoint rebuilds every row from it.

Revision ID: c3e5a7d9b1f4
Revises: a8c4e1f72b93
Create Date: 2026-10-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'c3e5a7d9b1f4'
down_revision: Union[str, Sequence[str], None] = 'a8c4e1f72b93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirror models._JSONB: JSONB under Postgres (the deployed engine), generic JSON elsewhere.
_JSONB = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "clinical_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("doc_key", sa.String(length=100), nullable=False),
        sa.Column("doc_type", sa.String(length=20), nullable=False),
        sa.Column("modality", sa.String(length=10), nullable=True),
        sa.Column("subtype", sa.String(length=30), nullable=True),
        sa.Column("study", sa.String(length=255), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("laterality", sa.String(length=10), nullable=True),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("reported_date", sa.Date(), nullable=True),
        sa.Column("provider", sa.String(length=255), nullable=True),
        sa.Column("referrer_name_raw", sa.String(length=255), nullable=True),
        sa.Column("author_name_raw", sa.String(length=255), nullable=True),
        sa.Column("recipient", sa.String(length=255), nullable=True),
        sa.Column("accession", sa.String(length=50), nullable=True),
        sa.Column("source_doc_filenames", _JSONB, nullable=False),
        sa.Column("clinical_history", sa.Text(), nullable=True),
        sa.Column("conclusion_verbatim", sa.Text(), nullable=True),
        sa.Column("conclusion_label", sa.String(length=100), nullable=True),
        sa.Column("findings_summary", sa.Text(), nullable=True),
        sa.Column("structured", _JSONB, nullable=True),
        sa.Column("letter", _JSONB, nullable=True),
        sa.Column("extraction_notes", _JSONB, nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("schema_version", sa.String(length=30), nullable=False),
        sa.Column("extracted_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "doc_key", name="uq_clinical_document_user_key"),
    )
    op.create_index(
        "ix_clinical_document_user_service", "clinical_documents", ["user_id", "service_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_clinical_document_user_service", table_name="clinical_documents")
    op.drop_table("clinical_documents")
