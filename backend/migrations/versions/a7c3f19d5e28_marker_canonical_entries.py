"""marker_canonical_entries — the canonical marker map becomes a table

DECISIONS_LOG #220 (fulfils #50). The map was a startup-loaded dict over
`backend/reference/marker_canonical.json`; it becomes a runtime-mutable table so a
confirmation-screen bind can write an entry. The JSON is retained as this migration's
seed (and as the interpretation layer's snapshot — see Q104), not deleted.

Upgrade reads the JSON and inserts every entry as source='seed', then self-checks that
the inserted count equals the JSON's entry count — a short seed would silently unmap
markers that resolve today.

Revision ID: a7c3f19d5e28
Revises: e2d5c7a1b9f3
"""
import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "a7c3f19d5e28"
down_revision = "e2d5c7a1b9f3"
branch_labels = None
depends_on = None

_SEED_PATH = Path(__file__).resolve().parent.parent.parent / "reference" / "marker_canonical.json"


def upgrade() -> None:
    table = op.create_table(
        "marker_canonical_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("marker_name_raw", sa.String(length=100), nullable=False),
        sa.Column("marker_canonical", sa.String(length=100), nullable=True),
        sa.Column("unit_established", sa.String(length=50), nullable=True),
        sa.Column("loinc", sa.String(length=20), nullable=True),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("marker_name_raw", name="uq_marker_canonical_entries_raw"),
    )
    op.create_index("ix_marker_canonical_entries_marker_name_raw", "marker_canonical_entries", ["marker_name_raw"])
    op.create_index("ix_marker_canonical_entries_marker_canonical", "marker_canonical_entries", ["marker_canonical"])

    entries = json.loads(_SEED_PATH.read_text(encoding="utf-8"))["entries"]
    op.bulk_insert(table, [
        {
            "marker_name_raw": e["marker_name_raw"],
            "marker_canonical": e.get("marker_canonical"),
            "unit_established": e.get("unit_established"),
            "loinc": e.get("loinc"),
            "display_name": None,
            "source": "seed",
        }
        for e in entries
    ])

    # Self-check: a partial seed unmaps markers that resolve today, and would do it
    # silently — every affected confirm would just start storing null canonical.
    seeded = op.get_bind().execute(
        sa.text("SELECT count(*) FROM marker_canonical_entries")
    ).scalar_one()
    if seeded != len(entries):
        raise RuntimeError(
            f"seed self-check failed: inserted {seeded}, JSON has {len(entries)} entries"
        )


def downgrade() -> None:
    op.drop_index("ix_marker_canonical_entries_marker_canonical", table_name="marker_canonical_entries")
    op.drop_index("ix_marker_canonical_entries_marker_name_raw", table_name="marker_canonical_entries")
    op.drop_table("marker_canonical_entries")
