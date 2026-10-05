"""user_hrmax: the restatement path and the `adjusted` provenance (#383, #384)

#383 ruled that an HRmax correction from better evidence is a RESTATEMENT (retroactive, prior value
and reason kept) and a value that genuinely changes with fitness is a DATED change (forward only).
The table could say neither: one plain unique key refused a second row on a date, and nothing on a
row said which kind it was. This adds both, and nothing else:

* `restates_id`, `base_bpm`, `rationale` - three nullable columns. A restatement points at the row it
  corrects; `adjusted` names the observation it adjusts (`base_bpm`) and why (`rationale`).
* The plain `uq_user_hrmax_effective (user_id, effective_from)` is replaced by a PARTIAL unique index
  over DATED rows only (`restates_id IS NULL`), so a restatement may share its target's date, plus a
  partial unique index on `restates_id` so a row is restated at most once (a chain is linear and its
  latest is well defined).
* A plain self-referencing foreign key `restates_id -> id`: the row a restatement corrects must exist.
  "Same user, same date" is deliberately NOT a database rule: a composite foreign key would enforce it,
  but `scripts/retire_user.py` refuses composite foreign keys (it would refuse to run in prod). The
  script finds its target by user and date, and `hr_zones.hrmax_in_force` raises on a chain that breaks
  either rule.
* `ck_user_hrmax_provenance` widens to `tested | observed | adjusted` (amends #364 R2's closed set;
  `estimated` stays banned). Two new CHECKs: `adjusted` <=> `base_bpm` present, and an adjustment or a
  restatement must carry a `rationale`.

Additive for the data: every existing row (user 1's seed, `observed`, no link) satisfies all of it, so
there is no backfill. The prior row is never touched by a restatement. Hand-written (autogenerate
produces neither partial indexes nor CHECKs; see SCHEMA.md caveats). Railway runs `alembic upgrade
head` at boot, so merging deploys this; the code that reads the new columns ships in the same deploy,
and the previous code ignores them.

Downgrade REFUSES while any restatement or `adjusted` row exists: dropping the columns would silently
destroy an append-only ledger, and the old key cannot hold two rows on one date.

Revision ID: d6f8b1a3c5e7
Revises: c5e7a9b1d3f2
Create Date: 2026-10-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd6f8b1a3c5e7'
down_revision: Union[str, Sequence[str], None] = 'c5e7a9b1d3f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('user_hrmax', sa.Column('restates_id', sa.Integer(), nullable=True))
    op.add_column('user_hrmax', sa.Column('base_bpm', sa.Integer(), nullable=True))
    op.add_column('user_hrmax', sa.Column('rationale', sa.String(length=1000), nullable=True))

    # The FK, then the two partial keys; only then drop the old plain key (one transaction on
    # Postgres, so there is no window with neither).
    op.create_foreign_key('fk_user_hrmax_restates', 'user_hrmax', 'user_hrmax', ['restates_id'], ['id'])
    op.create_index('uq_user_hrmax_dated', 'user_hrmax', ['user_id', 'effective_from'], unique=True,
                    postgresql_where=sa.text('restates_id IS NULL'))
    op.create_index('uq_user_hrmax_restates', 'user_hrmax', ['restates_id'], unique=True,
                    postgresql_where=sa.text('restates_id IS NOT NULL'))
    op.drop_constraint('uq_user_hrmax_effective', 'user_hrmax', type_='unique')

    op.drop_constraint('ck_user_hrmax_provenance', 'user_hrmax', type_='check')
    op.create_check_constraint('ck_user_hrmax_provenance', 'user_hrmax',
                               "provenance IN ('tested', 'observed', 'adjusted')")
    op.create_check_constraint('ck_user_hrmax_adjusted_base', 'user_hrmax',
                               "(provenance = 'adjusted' AND base_bpm IS NOT NULL) "
                               "OR (provenance <> 'adjusted' AND base_bpm IS NULL)")
    op.create_check_constraint('ck_user_hrmax_rationale', 'user_hrmax',
                               "(provenance <> 'adjusted' AND restates_id IS NULL) OR rationale IS NOT NULL")


def downgrade() -> None:
    """Downgrade schema."""
    if not op.get_context().as_sql:
        n = op.get_bind().execute(sa.text(
            "SELECT count(*) FROM user_hrmax WHERE restates_id IS NOT NULL OR provenance = 'adjusted'"
        )).scalar()
        if n:
            raise RuntimeError(
                f"refusing to downgrade: {n} user_hrmax row(s) are restatements or 'adjusted'. The table "
                "is an append-only ledger; dropping these columns would destroy that record, and the "
                "old (user_id, effective_from) key cannot hold two rows on one date.")

    op.drop_constraint('ck_user_hrmax_rationale', 'user_hrmax', type_='check')
    op.drop_constraint('ck_user_hrmax_adjusted_base', 'user_hrmax', type_='check')
    op.drop_constraint('ck_user_hrmax_provenance', 'user_hrmax', type_='check')
    op.create_check_constraint('ck_user_hrmax_provenance', 'user_hrmax',
                               "provenance IN ('tested', 'observed')")

    op.create_unique_constraint('uq_user_hrmax_effective', 'user_hrmax', ['user_id', 'effective_from'])
    op.drop_index('uq_user_hrmax_restates', table_name='user_hrmax')
    op.drop_index('uq_user_hrmax_dated', table_name='user_hrmax')
    op.drop_constraint('fk_user_hrmax_restates', 'user_hrmax', type_='foreignkey')

    op.drop_column('user_hrmax', 'rationale')
    op.drop_column('user_hrmax', 'base_bpm')
    op.drop_column('user_hrmax', 'restates_id')
