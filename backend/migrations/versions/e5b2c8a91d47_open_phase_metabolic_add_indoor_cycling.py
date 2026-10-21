"""open phase: add "Indoor cycling" to the metabolic slot's device_sports (21 Oct 2026)

A Polar "Indoor cycling" session (Polar Flow sport id 18) was never counted toward the `load_window:
metabolic` slot because that sport was not in the slot's `device_sports`. The resolver matches the recorded
sport name exactly (case-insensitive, Q164 / #322 S5: no aliasing, no category match), so the session fell
into `uncounted[]` as `unclaimed_session` on 2 Oct, 14 Oct and 21 Oct. The operator ruled (21 Oct 2026) to
ADD the one sport to the open phase's list. Not an alias, and not the Polar siblings ("Road running",
"Mountain biking"): nothing the operator records arrives under those names.

What it does: for each OPEN phase (`closed_on IS NULL`), in every sub-cycle, every slot whose `load_window`
is `metabolic` and whose `device_sports` does not already name "Indoor cycling" (case-insensitive) gets it
appended at the END of the list (existing order kept). Nothing else in the row changes. Idempotent: a second
run finds it listed and writes nothing. The migration prints one line per open row.

Effect on legs: a past leg is counted against the phase row's CURRENT microcycle (`past_legs` reads the row
`phase_at` returns), so the 14 Oct session (leg 8-14 Oct of the same row) is recounted too. A session before
the row's `entered_on` (2 Oct) is in an earlier row and is untouched.

NOT an ordinary backfill. The model states that closure is the only rewrite ever made to a ledger row; this
rewrites `microcycle` on an authored row, by the operator's ruling. The append-only alternative is the
phase-change wizard's "Continue", which always writes `entered_on = today`: it closes this row and opens a
new one, re-anchoring every leg to that day and recounting nothing in the past. Which of the two is right is
recorded in DECISIONS_LOG for ratification at release; this migration is HELD until then.

Downgrade is a no-op: after this runs, the sport is indistinguishable from one the operator added later, and
removing it would silently stop counting sessions. Remove it from the phase if it is not wanted.

Revision ID: e5b2c8a91d47
Revises: c4e9a1f27b36
Create Date: 2026-10-21

"""
import copy
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e5b2c8a91d47'
down_revision: Union[str, Sequence[str], None] = 'c4e9a1f27b36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SPORT = "Indoor cycling"

_PHASES = sa.table(
    'training_phases',
    sa.column('id', sa.Integer),
    sa.column('user_id', sa.Integer),
    sa.column('closed_on', sa.Date),
    sa.column('microcycle', sa.JSON()),
)


def _add_sport(microcycle):
    """`(new_microcycle, slots_changed, metabolic_slots_seen)`. The input is never mutated."""
    new = copy.deepcopy(microcycle)
    changed = seen = 0
    subs = new.get("sub_cycles") if isinstance(new, dict) else None
    for sc in subs if isinstance(subs, list) else []:
        for slot in (sc.get("slots") or []) if isinstance(sc, dict) else []:
            if not isinstance(slot, dict) or slot.get("load_window") != "metabolic":
                continue
            seen += 1
            sports = slot.get("device_sports")
            if not isinstance(sports, list):
                continue                      # malformed; the validator refuses it at write, not our row to repair
            if any(isinstance(x, str) and x.strip().casefold() == SPORT.casefold() for x in sports):
                continue
            sports.append(SPORT)
            changed += 1
    return new, changed, seen


def upgrade() -> None:
    """Upgrade data."""
    if op.get_context().as_sql:
        return                                # offline SQL: a data migration has no DDL to emit
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(_PHASES.c.id, _PHASES.c.user_id, _PHASES.c.microcycle)
        .where(_PHASES.c.closed_on.is_(None)).order_by(_PHASES.c.id)
    ).fetchall()
    if not rows:
        print("[indoor-cycling] WARNING: no open phase found; nothing to edit")
        return
    for pid, uid, micro in rows:
        new, changed, seen = _add_sport(micro)
        if not seen:
            print(f"[indoor-cycling] training_phases id={pid} user_id={uid}: no metabolic slot; unchanged")
        elif not changed:
            print(f"[indoor-cycling] training_phases id={pid} user_id={uid}: already lists {SPORT!r}; unchanged")
        else:
            bind.execute(_PHASES.update().where(_PHASES.c.id == pid).values(microcycle=new))
            print(f"[indoor-cycling] training_phases id={pid} user_id={uid}: added {SPORT!r} to "
                  f"{changed} metabolic slot(s)")


def downgrade() -> None:
    """Downgrade: deliberately nothing (see the module docstring)."""
    print(f"[indoor-cycling] downgrade leaves {SPORT!r} in place: it cannot be told from an operator's own addition")
