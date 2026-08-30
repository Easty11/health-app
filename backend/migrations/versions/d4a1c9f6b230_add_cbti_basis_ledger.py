"""add cbti_prescriptions per-night basis ledger + ruleset snapshot + flagged count

Revision ID: d4a1c9f6b230
Revises: 334526269006
Create Date: 2026-08-30

Brief B (DECISIONS_LOG #253): the CBT-I engine now emits a per-night ledger — one row
per evaluated night in the cycle window, each marked included / flagged / excluded with
a reason and evidence — and #253 reclasses a recorded-alcohol night from DISQUALIFYING
to EXCUSABLE (it stays in the basis, `flagged`, capped one per cycle).

Three columns, all nullable and NEVER backfilled (same discipline as the source-
composition columns in c4e8a2019bd7): a prescription minted before this migration has
no ledger and must read as "not recorded", never as an empty basis.

  * `basis_ledger`   — JSON list of the per-night rows, snapshotted at accept so a
                       close-out is read back, not recomputed against a since-moved
                       ruleset.
  * `ruleset_version`— the frozen `cbti/engine.RULESET_VERSION` the ledger was produced
                       under, so a stored ledger stays reproducible against its own rules.
  * `basis_n_flagged`— count of flagged (excused) basis nights; <= basis_nights_n.

The replay's column-explicit reads (`load_nights`, `_PRESCRIPTIONS_SQL`) do not select
these, so the engine can still be replayed against a database that has not yet taken this
migration — the same forward-compatibility the basis_n_* columns were landed under.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4a1c9f6b230'
down_revision: Union[str, Sequence[str], None] = '334526269006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cbti_prescriptions', sa.Column(
        'basis_n_flagged', sa.Integer(), nullable=True,
        comment='Basis nights flagged (in the basis, excused) rather than dropped - #253.',
    ))
    op.add_column('cbti_prescriptions', sa.Column(
        'basis_ledger', sa.JSON(), nullable=True,
        comment='Per-night ledger snapshotted at accept: one row per evaluated night.',
    ))
    op.add_column('cbti_prescriptions', sa.Column(
        'ruleset_version', sa.String(length=40), nullable=True,
        comment='RULESET_VERSION the ledger was produced under - reproducibility snapshot.',
    ))


def downgrade() -> None:
    op.drop_column('cbti_prescriptions', 'ruleset_version')
    op.drop_column('cbti_prescriptions', 'basis_ledger')
    op.drop_column('cbti_prescriptions', 'basis_n_flagged')
