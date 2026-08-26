"""add_bw_fraction to hevy_exercise_templates

Revision ID: d4a1f8c609e2
Revises: c7d9e2f14a86
Create Date: 2026-08-26 00:00:00.000000

The per-template bodyweight fraction (Q6, DECISIONS_LOG #245; promoted from the Q121
Tier-0 gap so the distortion never enters the EWMA history that gate 3's Banister builds).

`bw_fraction` — the fraction of bodyweight moved per rep for a bodyweight-CLASS movement
(push-up ~0.65, chin/dip ~1.0, BW squat/lunge ~0.85, Nordic ~0.9, dead bug ~0.25).
**NULL = not bodyweight-class** → the transform prices the set on `weight_kg` as logged.
The Tier-0 transform reads it ONLY for rep-based sets with `weight_kg` NULL or 0:
`eff_w = BODYWEIGHT_KG × COALESCE(bw_fraction, 1.0)`. A set with a logged `weight_kg > 0` is
never touched by it — `bw_fraction` scales no real load.

Operator-owned, mirroring `laterality`/`adjudicated_at`: assigned by the operator's tagging
pass (worklist from `audit_bodyweight_templates.py`), NEVER by `_upsert_template`, so a Hevy
resync preserves it.

Does NOT touch load_events (recompute, not migration — D-B) or exercise_sessions (#19).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4a1f8c609e2'
down_revision: Union[str, Sequence[str], None] = 'c7d9e2f14a86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'hevy_exercise_templates',
        sa.Column('bw_fraction', sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('hevy_exercise_templates', 'bw_fraction')
