"""backfill lab_reports.overall_confidence from per-row confidences

Revision ID: b7f3a1c92e40
Revises: f1a4c7e29b83
Create Date: 2026-07-28

Data-only migration (no schema change). DECISIONS_LOG #146: overall_confidence
was a model self-report that defaulted to 0.0 when omitted and was seeded by the
extraction prompt example, so the first ingestion run stored 0.0 on three of seven
reports whose per-row confidences were 0.92-0.99 and whose values were correct.
The forward fix derives it at confirm as min(row confidences); this migration
applies the SAME derivation to rows already stored, from the per-row `confidence`
values that were written correctly all along.

min over the rows matches both the per-row rule and confirm_lab_report. Reports
with no results are left untouched (none should exist — confirm writes >=1 row).
Idempotent: recomputing min yields the same value. Portable correlated-subquery
form (Postgres + SQLite). Blast radius = lab_reports.overall_confidence only.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b7f3a1c92e40'
down_revision: Union[str, Sequence[str], None] = 'f1a4c7e29b83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE lab_reports
        SET overall_confidence = (
            SELECT MIN(lr.confidence)
            FROM lab_results lr
            WHERE lr.lab_report_id = lab_reports.id
        )
        WHERE EXISTS (
            SELECT 1 FROM lab_results lr WHERE lr.lab_report_id = lab_reports.id
        )
        """
    )


def downgrade() -> None:
    # No-op: the prior values were the model's self-report — 0.0 where it omitted
    # the field — which is exactly what this backfill corrects. They are wrong, not
    # restorable, and there is nothing to roll back to.
    pass
