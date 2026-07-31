"""add lab_reports.zero_row_reason

Records WHY a report contributed no `lab_results` rows, so a decline can be told from a fault.

Before this column the two were indistinguishable after the fact: the confirm response carried
`duplicates`, but nothing persisted it. Hiding zero-row reports from the results list on row
count alone would therefore have hidden unparseable documents along with correctly-declined
re-uploads.

BACKFILL SAFETY — every existing zero-row report is `all_markers_declined`, and this is a proof
rather than an inference. The other value, `no_values_extracted`, was UNREACHABLE before this
migration's paired code change: a submission carrying no results tripped
`assert row_confidences` in `confirm_lab_report`, which raised before `db.commit()`, so no report
row was ever created for an unparseable document. Verified directly against the pre-change handler
(submitting `results=[]` raised AssertionError and left the report count unchanged). No legacy row
can therefore carry the fault value, and the backfill cannot mislabel one.

Revision ID: d7c4b1a90e35
Revises: c1e8b4d70f92
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd7c4b1a90e35'
down_revision: Union[str, Sequence[str], None] = 'c1e8b4d70f92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('lab_reports', sa.Column('zero_row_reason', sa.String(length=50), nullable=True))
    op.execute("""
        UPDATE lab_reports
        SET zero_row_reason = 'all_markers_declined'
        WHERE NOT EXISTS (
            SELECT 1 FROM lab_results WHERE lab_results.lab_report_id = lab_reports.id
        )
    """)


def downgrade() -> None:
    op.drop_column('lab_reports', 'zero_row_reason')
