"""open phase: add "Rugby" to the metabolic slot's device_sports (25 Oct 2026)

The 22 Oct 2026 Rugby session (a device-recorded session whose sport name is "Rugby") was club sprint
training plus skills, and it is the plan's Thursday `sprints/drills` item, which satisfies
`load_window: metabolic`. The slot's `device_sports` did not name "Rugby", so the resolver (exact,
case-insensitive match on the recorded sport name: Q164 / #322 S5, no aliasing, no category match) listed it
in `uncounted[]` as `unclaimed_session`. The operator ruled (25 Oct 2026) to ADD the one sport to the open
phase's list. Plan intent is unchanged, so this is a defect correction under the bounded exception of #438
(item 6): an in-place `microcycle` edit, through a logged migration, only.

What it does: for each OPEN phase (`closed_on IS NULL`), in every sub-cycle, every slot whose `load_window`
is `metabolic` and whose `device_sports` does not already name "Rugby" (case-insensitive) gets it appended at
the END of the list (existing order kept). Nothing else in the row changes. Idempotent: a second run finds it
listed and writes nothing. It prints one line per open row.

KNOWN COST, recorded in DECISIONS_LOG: the match is on the sport name alone, so ANY session the device
labels "Rugby" counts as metabolic, skills-only sessions and matches included. To be revisited at the
in-season phase change.

Effect on legs: a past leg is counted against the phase row's CURRENT microcycle, so a Rugby session in an
earlier leg of the same row is recounted too. A session before the row's `entered_on` is in an earlier row and
is untouched.

Same mechanism as e5b2c8a91d47 (which ran on Postgres on 23 Oct 2026: the JSONB bind held). Downgrade is a
no-op for the same reason: afterwards the sport cannot be told from one the operator added.

Revision ID: b8f3d6a2c915
Revises: e5b2c8a91d47
Create Date: 2026-10-25

"""
import copy
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b8f3d6a2c915'
down_revision: Union[str, Sequence[str], None] = 'e5b2c8a91d47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SPORT = "Rugby"

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
        print("[rugby] WARNING: no open phase found; nothing to edit")
        return
    for pid, uid, micro in rows:
        new, changed, seen = _add_sport(micro)
        if not seen:
            print(f"[rugby] training_phases id={pid} user_id={uid}: no metabolic slot; unchanged")
        elif not changed:
            print(f"[rugby] training_phases id={pid} user_id={uid}: already lists {SPORT!r}; unchanged")
        else:
            bind.execute(_PHASES.update().where(_PHASES.c.id == pid).values(microcycle=new))
            print(f"[rugby] training_phases id={pid} user_id={uid}: added {SPORT!r} to "
                  f"{changed} metabolic slot(s)")


def downgrade() -> None:
    """Downgrade: deliberately nothing (see the module docstring)."""
    print(f"[rugby] downgrade leaves {SPORT!r} in place: it cannot be told from an operator's own addition")
