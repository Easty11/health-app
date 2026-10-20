"""training_phases.vehicle_ranking - the recovery-first re-rank leaves probe_posture (Q212)

`probe_posture` drove three behaviours at once: the effective probe budget (0 / fortify), the withheld
probe block, and the recovery-first vehicle re-rank. The operator ruled (20 Oct 2026, Q212) that the
re-rank gets its own per-phase field, so a phase can switch probes off without also reordering the
vehicle list. This adds `vehicle_ranking` ('standard' | 'recovery_first'), required at write with no
default (#230 discipline), with its own CHECK `ck_training_phase_vehicle_ranking`.

Backfill (one UPDATE per row, so every id and value written is printed):
* behaviour-preserving: `probe_posture = 'suppressed'` -> 'recovery_first', 'held' -> 'standard' (the
  re-rank fired on 'suppressed' alone, so this keeps every closed row reading as it did);
* EXCEPT the currently-open phase (`closed_on IS NULL`; at most one per user): 'standard', by operator
  ruling - the 5 Oct 2026 evidence is that probes off was wanted on that phase WITHOUT the
  recovery-first ranking. Its `probe_posture` is untouched.
The migration prints each id and the value it wrote, and a warning if the open-phase count is not 1.

Not an append-only breach: the ledger's "only UPDATE is closure" rule governs authored rows after
authorship; this is a schema change backfilling a column that did not exist, run once, by ruling.

Downgrade drops the CHECK and the column. It REFUSES while any row's pair is one the pre-Q212 single
column cannot express (suppressed + standard, or held + recovery_first): dropping would silently change
what the engine does for that row. Close or review those rows first.

Revision ID: c4e9a1f27b36
Revises: 705a17c84d9a
Create Date: 2026-10-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c4e9a1f27b36'
down_revision: Union[str, Sequence[str], None] = '705a17c84d9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CK = 'ck_training_phase_vehicle_ranking'


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable first so existing rows can be backfilled, then NOT NULL + CHECK (batch for SQLite).
    op.add_column('training_phases', sa.Column('vehicle_ranking', sa.String(length=15), nullable=True))

    bind = op.get_bind()
    if not op.get_context().as_sql:
        rows = bind.execute(sa.text(
            "SELECT id, user_id, probe_posture, closed_on FROM training_phases ORDER BY id"
        )).fetchall()
        open_ids = [r[0] for r in rows if r[3] is None]
        if len(open_ids) != 1:
            print(f"[Q212] WARNING: expected exactly 1 open phase, found {len(open_ids)}: {open_ids}")
        for pid, uid, posture, closed_on in rows:
            if closed_on is None:
                value, why = 'standard', 'open phase (operator ruling)'
            elif posture == 'suppressed':
                value, why = 'recovery_first', 'was suppressed'
            else:
                value, why = 'standard', 'was held'
            bind.execute(
                sa.text("UPDATE training_phases SET vehicle_ranking = :v WHERE id = :id"),
                {"v": value, "id": pid},
            )
            print(f"[Q212] training_phases id={pid} user_id={uid} probe_posture={posture} "
                  f"-> vehicle_ranking={value} ({why})")
        if not rows:
            print("[Q212] training_phases is empty: nothing to backfill")

    with op.batch_alter_table('training_phases') as batch:
        batch.alter_column('vehicle_ranking', existing_type=sa.String(length=15), nullable=False)
        batch.create_check_constraint(_CK, "vehicle_ranking IN ('standard','recovery_first')")


def downgrade() -> None:
    """Downgrade schema."""
    if not op.get_context().as_sql:
        n = op.get_bind().execute(sa.text(
            "SELECT count(*) FROM training_phases "
            "WHERE (probe_posture = 'suppressed' AND vehicle_ranking = 'standard') "
            "OR (probe_posture = 'held' AND vehicle_ranking = 'recovery_first')"
        )).scalar()
        if n:
            raise RuntimeError(
                f"Refusing to downgrade: {n} phase row(s) pair a posture and ranking the pre-Q212 column "
                "cannot express (suppressed+standard or held+recovery_first); dropping the column would "
                "silently change what the engine does for them. Close or review them first."
            )
    with op.batch_alter_table('training_phases') as batch:
        batch.drop_constraint(_CK, type_='check')
        batch.drop_column('vehicle_ranking')
