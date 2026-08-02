"""add capability_observations

Graded, timestamped capability measurement for the Adaptive Exposure Engine
(DECISIONS_LOG #NEXT). Purely additive: `capability_state` is untouched, and
nothing existing reads this table.

WHY A NEW TABLE. `capability_state` holds one row per (user, region, side) and is
overwritten in place by `engine/adaptation.py::apply_response`, so only today's
label is ever visible. Its `status` is a 4-level ordinal, which cannot be
regressed against dose. Asymmetry direction-of-travel, re-attainment curves after
injury, and dose-response slopes all require history the state table structurally
cannot hold. Dose-per-region is already computable — `exercise_region_tags` joins
templates to regions with primary/secondary roles — so this table is the missing
half, not a speculative one.

APPEND-ONLY BY CONSTRUCTION. No `updated_at` column and no UPDATE path. A
correction is a new row; supersession is by `observed_on` then `created_at`.
`observed_on` is the measurement date, not the insert date, so a backfilled
battery lands on the day it happened.

NO BACKFILL IS POSSIBLE OR ATTEMPTED. `capability_state` carries no numeric
value — only the ordinal status and free-text `detail` — so there is nothing to
migrate forward. An empty table on first upgrade is the correct and only honest
state; every row is written after this lands.

Revision ID: b6f3d92a4e17
Revises: d7c4b1a90e35
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b6f3d92a4e17'
down_revision: Union[str, Sequence[str], None] = 'd7c4b1a90e35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'capability_observations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('region_key', sa.String(100), nullable=False),
        sa.Column('side', sa.String(20), nullable=False, server_default=sa.text("'bilateral'")),
        sa.Column('observed_on', sa.Date(), nullable=False),
        sa.Column('measure_key', sa.String(60), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(20), nullable=False),
        sa.Column('method', sa.String(30), nullable=False),
        sa.Column('source', sa.String(30), nullable=False),
        sa.Column('confidence', sa.String(20), nullable=False, server_default=sa.text("'likely'")),
        sa.Column('context', sa.JSON(), nullable=True),
        sa.Column('taxonomy_version', sa.String(20), nullable=False, server_default=sa.text("'v0'")),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_capability_observations_user_id', 'capability_observations', ['user_id'])
    op.create_index(
        'ix_capability_obs_user_region_side_date',
        'capability_observations', ['user_id', 'region_key', 'side', 'observed_on'],
    )
    op.create_index(
        'ix_capability_obs_user_date',
        'capability_observations', ['user_id', 'observed_on'],
    )


def downgrade() -> None:
    op.drop_index('ix_capability_obs_user_date', table_name='capability_observations')
    op.drop_index('ix_capability_obs_user_region_side_date', table_name='capability_observations')
    op.drop_index('ix_capability_observations_user_id', table_name='capability_observations')
    op.drop_table('capability_observations')
