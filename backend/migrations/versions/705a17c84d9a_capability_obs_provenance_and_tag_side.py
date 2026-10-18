"""capability_observations provenance + exercise_region_tags.side (Q27 v1 remainders)

Four nullable columns and one index, and nothing else:

* `capability_observations.administered_by` (String(20)), `.instrument` (String(40)),
  `.protocol` (String(60)) - the provenance that lets the reference gate (engine/reference.py)
  decide whether a literature band applies. ALL-OR-NOTHING, enforced in `record_observation`
  (all three or none; `instrument` must equal the protocol's declared instrument), not by a CHECK:
  the vocabularies are code (engine/observations.py, engine/protocols.py) and versioned with it.
  A row with all three NULL evaluates as reference_kind "internal" forever (#421's fail-closed rule).
* `ix_capability_obs_user_region_protocol (user_id, region_key, protocol)` - the gate and the
  observed-ratio read look a (region, protocol) series up.
* `exercise_region_tags.side` (String(20)) - `left` | `right`, NULL = bilateral or unknown. Written
  only from the reference's declared `side` by seed_exercise_region_tags.py (an operator run); never
  derived from a title.

No data migration and no backfill: every existing observation stays NULL-provenance (internal) and
every existing tag stays NULL-side until the operator runs the seeder. Additive and non-destructive;
the previous code ignores the new columns, and Railway runs `alembic upgrade head` at boot.

Downgrade drops the four columns and the index. It REFUSES while any observation carries provenance:
the ledger is append-only, and dropping the columns would silently demote a literature-eligible row
to internal. (Tag `side` is re-seedable, so it is dropped without a guard.)

Revision ID: 705a17c84d9a
Revises: e0d53feadc9d
Create Date: 2026-10-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '705a17c84d9a'
down_revision: Union[str, Sequence[str], None] = 'e0d53feadc9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('capability_observations', sa.Column('administered_by', sa.String(length=20), nullable=True))
    op.add_column('capability_observations', sa.Column('instrument', sa.String(length=40), nullable=True))
    op.add_column('capability_observations', sa.Column('protocol', sa.String(length=60), nullable=True))
    op.create_index('ix_capability_obs_user_region_protocol', 'capability_observations',
                    ['user_id', 'region_key', 'protocol'])
    op.add_column('exercise_region_tags', sa.Column('side', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    if not op.get_context().as_sql:
        n = op.get_bind().execute(sa.text(
            "SELECT count(*) FROM capability_observations "
            "WHERE administered_by IS NOT NULL OR instrument IS NOT NULL OR protocol IS NOT NULL"
        )).scalar()
        if n:
            raise RuntimeError(
                f"Refusing to downgrade: {n} capability observation(s) carry provenance; dropping "
                "the columns would silently demote them to internal. Delete or export them first."
            )
    op.drop_column('exercise_region_tags', 'side')
    op.drop_index('ix_capability_obs_user_region_protocol', table_name='capability_observations')
    op.drop_column('capability_observations', 'protocol')
    op.drop_column('capability_observations', 'instrument')
    op.drop_column('capability_observations', 'administered_by')
