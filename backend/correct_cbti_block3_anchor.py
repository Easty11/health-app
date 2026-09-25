"""Operator correction: restore block 3's [cbti_blocks.id 2] wake anchor to 05:45 (#331).

One-shot, dry-run by DEFAULT (`--apply` to write), the shape of correct_cbti_block3_rx.py.
This is an OPERATOR CORRECTION, not a titration: the engine did not produce it.

WHAT WAS WRONG. rx 11 (2026-07-27) moved the ledger anchor 05:45 -> 05:00, and every
engine-produced row since (rx 12-17) inherited 05:00. The anchor was never followed: the
AM check-in rendered its window as `rx.prescribed_lights_out`-`block.wake_anchor`, and the
block row still reads 05:45 (append-only; routers/checkin_v2.py `_cbti_context`, fixed in
the same change). The operator ran every night to 05:45 (+/-15). So each affected row's
`window_minutes` understates the window actually run by 45 min — and the engine titrated
against those understated windows (evaluate_cycle: move = mean TST + 30 - current window).

APPEND + SUPERSEDE, the only permitted shape (models.CBTIPrescription):
  - INSERT one prescription, decision='adopt' (an operator correction must not enter the
    chain as a titration move), lights_out unchanged (21:48), anchor 05:45, window 477.
    basis_* NULL: operator-set, not basis-derived.
  - UPDATE the live row: effective_to (the wake-date before the correction) + superseded_by.
The block row is NOT touched (its 05:45 is, and always was, the true anchor).

IDENTITY GUARD (#103): the live row must be EXACTLY the one this correction was written
against — 21:48 -> 05:00, window 432. If an evaluation was accepted in the meantime the
live row differs and this aborts rather than correcting a row it never saw. Also aborts on
a second open block, a second live row, or an existing row at the correction date.

Date convention: effective_from is a WAKE-DATE label. Default = tomorrow (Brisbane), i.e.
tonight's night; pass --effective-from to override.
"""
import argparse
import datetime as dt
import os

import pytz
from sqlalchemy import create_engine, text

USER_ID = 1
EXPECT_LIVE = {"prescribed_lights_out": "21:48", "wake_anchor": "05:00", "window_minutes": 432}
NEW_LIGHTS_OUT = "21:48"
NEW_WAKE_ANCHOR = "05:45"
NEW_WINDOW_MIN = 477                          # 21:48 -> 05:45 = 7h57
NEW_DECISION = "adopt"
WRONG_ANCHOR = "05:00"
UNDERSTATED_BY_MIN = 45                       # 05:45 - 05:00
AEST = pytz.timezone("Australia/Brisbane")

RATIONALE = (
    "Operator correction (supersedes id={old_id}). NOT a titration outcome. Restores the "
    "wake anchor to 05:45: the ledger has recorded 05:00 since rx {first_id} ({first_from}), "
    "but 05:00 was never used — the check-in displayed the block anchor 05:45 and the "
    "operator ran every night to 05:45 (+/-15). The window_minutes of rx {id_range} therefore "
    "UNDERSTATE the window actually run by 45 min ({pairs}; recorded->actual), and the "
    "titration moves out of those rows were computed against the understated windows (see "
    "DECISIONS_LOG #331). Lights-out unchanged at {lo}; window {win} ({lo}->{anchor}). "
    "decision='adopt': an operator correction must not enter the titration chain as a move. "
    "basis_* NULL: operator-set, not basis-derived. cbti_blocks.wake_anchor untouched (05:45)."
)


def _span(lo: str, anchor: str) -> int:
    h0, m0 = map(int, lo.split(":"))
    h1, m1 = map(int, anchor.split(":"))
    return ((h1 * 60 + m1) - (h0 * 60 + m0)) % 1440


def correct(conn, effective_from: dt.date, apply: bool, user_id: int = USER_ID) -> dict:
    """Resolve, guard, and (if `apply`) write. Returns the plan. Raises SystemExit on any
    guard failure — nothing is written unless every guard passes."""
    assert _span(NEW_LIGHTS_OUT, NEW_WAKE_ANCHOR) == NEW_WINDOW_MIN

    blocks = conn.execute(text(
        "SELECT id, wake_anchor FROM cbti_blocks WHERE user_id=:u AND closed_on IS NULL"
    ), {"u": user_id}).fetchall()
    if len(blocks) != 1:
        raise SystemExit(f"ABORT: expected exactly 1 open block for user {user_id}, found {len(blocks)}.")
    block_id, block_anchor = blocks[0]

    live = conn.execute(text(
        "SELECT id, effective_from, prescribed_lights_out, wake_anchor, window_minutes "
        "FROM cbti_prescriptions WHERE block_id=:b AND effective_to IS NULL AND superseded_by IS NULL"
    ), {"b": block_id}).fetchall()
    if len(live) != 1:
        raise SystemExit(f"ABORT: expected exactly 1 live rx on block {block_id}, found {len(live)}.")
    old = dict(live[0]._mapping)
    got = {k: old[k] for k in EXPECT_LIVE}
    if got != EXPECT_LIVE:
        raise SystemExit(f"ABORT: live rx id={old['id']} is {got}, not the row this correction "
                         f"was written against {EXPECT_LIVE}. Was an evaluation accepted?")

    old_from = old["effective_from"]
    old_from = old_from if isinstance(old_from, dt.date) else dt.date.fromisoformat(str(old_from)[:10])
    if effective_from <= old_from:
        raise SystemExit(f"ABORT: correction {effective_from} is not after live rx effective_from {old_from}.")
    dupe = conn.execute(text(
        "SELECT id FROM cbti_prescriptions WHERE block_id=:b AND effective_from=:ef"
    ), {"b": block_id, "ef": effective_from}).fetchall()
    if dupe:
        raise SystemExit(f"ABORT: rx id={dupe[0][0]} already starts {effective_from}. Already applied?")

    # The affected rows, resolved from the ledger (not trusted from the brief).
    affected = conn.execute(text(
        "SELECT id, effective_from, window_minutes FROM cbti_prescriptions "
        "WHERE block_id=:b AND wake_anchor=:w ORDER BY effective_from, id"
    ), {"b": block_id, "w": WRONG_ANCHOR}).fetchall()
    ids = [r[0] for r in affected]
    pairs = ", ".join(f"rx {i} {w}->{w + UNDERSTATED_BY_MIN}" for i, _, w in affected)
    rationale = RATIONALE.format(
        old_id=old["id"], first_id=ids[0], first_from=str(affected[0][1])[:10],
        id_range=f"{ids[0]}-{ids[-1]}", pairs=pairs, lo=NEW_LIGHTS_OUT,
        win=NEW_WINDOW_MIN, anchor=NEW_WAKE_ANCHOR)

    plan = {
        "block_id": block_id, "block_anchor": block_anchor, "old_id": old["id"],
        "old_effective_to": effective_from - dt.timedelta(days=1),
        "effective_from": effective_from, "affected_ids": ids, "rationale": rationale,
    }
    if not apply:
        return plan

    new_id = conn.execute(text(
        "INSERT INTO cbti_prescriptions "
        "(block_id, effective_from, effective_to, prescribed_lights_out, wake_anchor, "
        " window_minutes, decision, rationale, superseded_by) "
        "VALUES (:b, :ef, NULL, :lo, :anchor, :win, :dec, :rat, NULL) RETURNING id"
    ), {"b": block_id, "ef": effective_from, "lo": NEW_LIGHTS_OUT, "anchor": NEW_WAKE_ANCHOR,
        "win": NEW_WINDOW_MIN, "dec": NEW_DECISION, "rat": rationale}).scalar_one()
    conn.execute(text(
        "UPDATE cbti_prescriptions SET effective_to=:et, superseded_by=:new WHERE id=:old"
    ), {"et": plan["old_effective_to"], "new": new_id, "old": old["id"]})
    plan["new_id"] = new_id
    return plan


def main():
    ap = argparse.ArgumentParser(description="Restore block 3 wake anchor 05:45 (dry-run unless --apply).")
    ap.add_argument("--apply", action="store_true", help="write to the database")
    ap.add_argument("--effective-from", help="wake-date YYYY-MM-DD (default: tomorrow, Brisbane)")
    args = ap.parse_args()
    ef = (dt.date.fromisoformat(args.effective_from) if args.effective_from
          else dt.datetime.now(AEST).date() + dt.timedelta(days=1))

    var = "DATABASE_PUBLIC_URL" if os.environ.get("DATABASE_PUBLIC_URL") else "DATABASE_URL"
    url = os.environ[var]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    with create_engine(url).begin() as c:
        plan = correct(c, ef, args.apply)
        print(f"[block]  id={plan['block_id']} wake_anchor={plan['block_anchor']} (UNTOUCHED)")
        print(f"[old rx] id={plan['old_id']} -> effective_to={plan['old_effective_to']}, superseded_by=<new>")
        print(f"[new rx] ef={plan['effective_from']} {NEW_LIGHTS_OUT}->{NEW_WAKE_ANCHOR} "
              f"win={NEW_WINDOW_MIN} dec={NEW_DECISION} basis_*=NULL")
        print(f"[affected rows, anchor {WRONG_ANCHOR}] {plan['affected_ids']}")
        print(f"[rationale] {plan['rationale']}")
        if not args.apply:
            print("\n[dry-run] no write. Re-run with --apply.")
            return
        print(f"\n[applied] inserted rx id={plan['new_id']}; superseded id={plan['old_id']}.")
        for r in c.execute(text(
            "SELECT id, effective_from, effective_to, prescribed_lights_out, wake_anchor, "
            "window_minutes, decision, superseded_by FROM cbti_prescriptions "
            "WHERE id IN (:a, :b) ORDER BY id"), {"a": plan["old_id"], "b": plan["new_id"]}):
            print(dict(r._mapping))


if __name__ == "__main__":
    main()
