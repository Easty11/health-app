"""rebind the unmapped Total PSA row to marker_canonical = 'psa'

Revision ID: c1e8b4d70f92
Revises: b7f3a1c92e40
Create Date: 2026-07-28

Data-only migration (no schema change). DECISIONS_LOG: the first ingestion run
left one result of 27 unmapped -- 'Total PSA', 0.7 ug/L -- because marker_canonical.json
had no psa entry. The entry is added in the same commit as this migration; adding
it does NOT retroactively map the already-stored row (marker_canonical was written
null at confirm), so this backfills it.

Gated on unit_canonical = 'ug/L' to match the new entry's unit_established: the bind
fires only when the stored row's unit confirms it is the same marker (controls
discriminate on identity, not just name). If it rebinds zero rows on Railway, the
stored unit differs from the authored 'ug/L' and BOTH the asset entry and this gate
need operator correction before PSA can bind -- do not loosen the gate to force it.
Idempotent (an already-bound row no longer matches marker_canonical IS NULL).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c1e8b4d70f92'
down_revision: Union[str, Sequence[str], None] = 'b7f3a1c92e40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE lab_results
        SET marker_canonical = 'psa'
        WHERE marker_name_raw = 'Total PSA'
          AND marker_canonical IS NULL
          AND unit_canonical = 'ug/L'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE lab_results
        SET marker_canonical = NULL
        WHERE marker_name_raw = 'Total PSA'
          AND marker_canonical = 'psa'
        """
    )
