"""Operator correction to block 3's opening prescription (supersedes id=10).

One-shot, dry-run by DEFAULT (`--apply` to write), following open_cbti_block3.py.
This is a CLINICAL-DATA SEED, not a titration: the engine did not produce it. The
block-3 opening window 360 (23:45->05:45) was set by the operator to ~ the device
mean TST (basis_tst_min=349 on id=10), a mean measured over nights already under
self-restriction; the anchor 05:45 sat above the measured wake terminus. This
correction returns the anchor to 05:00 (the wake terminus, and the anchor under
which the completed block closed at window 458) and sets window 390 (22:30->05:00).

APPEND + SUPERSEDE, the only permitted shape (models.py:278-281):
  - INSERT one new prescription row on the block, decision='adopt' (NOT 'extend' —
    an operator correction must not enter the chain as a titration move; 'adopt' is
    in the CHECK set and carries no titration semantics). basis_* left NULL:
    operator-set, not basis-derived, so id=10's device-derived provenance is NOT
    copied onto it.
  - UPDATE id=10: effective_to (last wake-date under it) and superseded_by only.

The block row (cbti_blocks id=2) is NOT touched: its wake_anchor 05:45 is a true
fact about how block 3 opened (CBTIBlock append-only invariant, models.py:253-257).
The superseding prescription is the artifact that expresses the anchor change.

RESOLVED AT READ TIME, not trusted from the brief: the target is the single live
prescription (effective_to IS NULL AND superseded_by IS NULL) on the single open
block for the user. Aborts if the shape is not exactly that, or if a row for the
correction's effective_from already exists (double-apply guard).

Date convention (open_cbti_block3.py:13-16,38): effective_from / effective_to are
WAKE-DATE labels (the morning date). The correction covers tonight's night 26->27
-> effective_from 2026-07-27; id=10's last covered night is 25->26 -> effective_to
2026-07-26.
"""
import argparse
import os

from sqlalchemy import create_engine, text

USER_ID = 1
CORRECTION_EFFECTIVE_FROM = "2026-07-27"   # wake-date label of night 26->27 (tonight)
OLD_RX_EFFECTIVE_TO = "2026-07-26"          # wake-date label of night 25->26
NEW_LIGHTS_OUT = "22:30"
NEW_WAKE_ANCHOR = "05:00"
NEW_WINDOW_MIN = 390                        # 22:30 -> 05:00 = 6h30
NEW_DECISION = "adopt"

RATIONALE = (
    "Operator correction to block 3's opening prescription (supersedes id={old_id}). "
    "NOT a titration outcome. The opening window 360 (23:45->05:45) was set by the "
    "operator to ~ the device mean TST (basis_tst_min=349 on the superseded row), a "
    "mean measured over nights already under self-restriction, and the anchor 05:45 "
    "sat above the measured wake terminus. This correction returns the anchor to 05:00 "
    "(the measured wake terminus, the anchor under which the completed block closed at "
    "window 458) and sets window 390 (22:30->05:00). decision='adopt' (not 'extend'): "
    "an operator correction must not enter the titration chain as a move. basis_* left "
    "NULL: operator-set, not basis-derived, so the superseded row's device-derived "
    "provenance is not copied forward. cbti_blocks.wake_anchor left at 05:45 (true "
    "opening state; append-only invariant); this row expresses the anchor change."
)


def _assert_window():
    h0, m0 = map(int, NEW_LIGHTS_OUT.split(":"))
    h1, m1 = map(int, NEW_WAKE_ANCHOR.split(":"))
    span = (h1 * 60 + m1) - (h0 * 60 + m0)
    if span < 0:
        span += 1440
    assert span == NEW_WINDOW_MIN, f"window mismatch: {NEW_LIGHTS_OUT}->{NEW_WAKE_ANCHOR} = {span}, not {NEW_WINDOW_MIN}"


def main():
    ap = argparse.ArgumentParser(description="Correct block 3 opening rx (dry-run unless --apply).")
    ap.add_argument("--apply", action="store_true", help="write to the database")
    args = ap.parse_args()

    _assert_window()

    var = "DATABASE_PUBLIC_URL" if os.environ.get("DATABASE_PUBLIC_URL") else "DATABASE_URL"
    url = os.environ[var]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    eng = create_engine(url)

    with eng.begin() as c:
        # ── resolve the target at read time ───────────────────────────────────
        blocks = c.execute(text(
            "SELECT id, opened_on, wake_anchor FROM cbti_blocks "
            "WHERE user_id=:u AND closed_on IS NULL ORDER BY id"
        ), {"u": USER_ID}).fetchall()
        if len(blocks) != 1:
            raise SystemExit(f"ABORT: expected exactly 1 open block for user {USER_ID}, found {len(blocks)}.")
        block_id, opened_on, block_anchor = blocks[0]

        live = c.execute(text(
            "SELECT id, effective_from, effective_to, prescribed_lights_out, wake_anchor, "
            "window_minutes, decision, superseded_by, basis_tst_min "
            "FROM cbti_prescriptions "
            "WHERE block_id=:b AND effective_to IS NULL AND superseded_by IS NULL"
        ), {"b": block_id}).fetchall()
        if len(live) != 1:
            raise SystemExit(f"ABORT: expected exactly 1 live rx on block {block_id}, found {len(live)}.")
        old_id, old_ef, old_et, old_lo, old_anchor, old_win, old_dec, old_sup, old_tst = live[0]

        if str(old_ef) >= CORRECTION_EFFECTIVE_FROM:
            raise SystemExit(
                f"ABORT: live rx effective_from {old_ef} is not before the correction "
                f"{CORRECTION_EFFECTIVE_FROM}; refusing.")

        dupe = c.execute(text(
            "SELECT id FROM cbti_prescriptions WHERE block_id=:b AND effective_from=:ef"
        ), {"b": block_id, "ef": CORRECTION_EFFECTIVE_FROM}).fetchall()
        if dupe:
            raise SystemExit(
                f"ABORT: a rx already exists on block {block_id} with effective_from "
                f"{CORRECTION_EFFECTIVE_FROM} (id={dupe[0][0]}). Already applied?")

        rationale = RATIONALE.format(old_id=old_id)

        print(f"[block]  id={block_id} opened_on={opened_on} wake_anchor={block_anchor} (UNTOUCHED)")
        print(f"[old rx] id={old_id}: ef={old_ef} et={old_et} {old_lo}->{old_anchor} "
              f"win={old_win} dec={old_dec} sup={old_sup} basis_tst={old_tst}")
        print(f"         -> will set effective_to={OLD_RX_EFFECTIVE_TO}, superseded_by=<new id>")
        print(f"[new rx] block_id={block_id} ef={CORRECTION_EFFECTIVE_FROM} et=NULL "
              f"{NEW_LIGHTS_OUT}->{NEW_WAKE_ANCHOR} win={NEW_WINDOW_MIN} dec={NEW_DECISION} "
              f"basis_*=NULL")
        print(f"[rationale] {rationale}")

        if not args.apply:
            print("\n[dry-run] no write. Re-run with --apply.")
            return

        new_id = c.execute(text(
            "INSERT INTO cbti_prescriptions "
            "(block_id, effective_from, effective_to, prescribed_lights_out, wake_anchor, "
            " window_minutes, decision, rationale, superseded_by) "
            "VALUES (:b, :ef, NULL, :lo, :anchor, :win, :dec, :rat, NULL) RETURNING id"
        ), {"b": block_id, "ef": CORRECTION_EFFECTIVE_FROM, "lo": NEW_LIGHTS_OUT,
            "anchor": NEW_WAKE_ANCHOR, "win": NEW_WINDOW_MIN, "dec": NEW_DECISION,
            "rat": rationale}).scalar_one()

        c.execute(text(
            "UPDATE cbti_prescriptions SET effective_to=:et, superseded_by=:new "
            "WHERE id=:old"
        ), {"et": OLD_RX_EFFECTIVE_TO, "new": new_id, "old": old_id})

        print(f"\n[applied] inserted rx id={new_id}; superseded id={old_id}.")

        # ── read back both rows ───────────────────────────────────────────────
        print("\n=== READ-BACK ===")
        for r in c.execute(text(
            "SELECT id, block_id, effective_from, effective_to, prescribed_lights_out, "
            "wake_anchor, window_minutes, decision, superseded_by, basis_tst_min, basis_nights_n "
            "FROM cbti_prescriptions WHERE id IN (:a, :b) ORDER BY id"
        ), {"a": old_id, "b": new_id}):
            print(dict(r._mapping))
        print("\n=== block row (must be unchanged) ===")
        for r in c.execute(text(
            "SELECT id, opened_on, closed_on, wake_anchor FROM cbti_blocks WHERE id=:b"
        ), {"b": block_id}):
            print(dict(r._mapping))


if __name__ == "__main__":
    main()
