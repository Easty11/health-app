"""Gate 4 — replay the titration engine over an imported CBT-I block.

The expectation is NOT that the output matches the nine historical prescriptions.
Those came from the VA CBT-I Sleep Diary Calculator, which used a different rule
with a different exit condition and different gates. **Divergence is the output.**

One hard floor: the replay must not terminate before the block's observed
endpoint. #107's whole basis is that an SE-driven rule exits ~45 min short of
need; if this engine does the same, the rule is wrong and the finding is that,
not a tuning target.

This is the DB adapter. The engine itself is pure — every query lives here, and
the Samsung read goes through the `context = 'passive_overnight'` allowlist and
nowhere else.

Usage:
    python -m cbti.replay --user-id 1 --block-id 1
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

from sqlalchemy import text

import models
from cbti.engine import CYCLE_NIGHTS, MAX_MOVE_MIN, Night, evaluate_cycle
from cbti.timeutil import clock_to_minutes, window_minutes
from database import SessionLocal

# The ONLY permitted Samsung read. A second query path around this allowlist is
# the thing #108's isolation exists to prevent.
_SAMSUNG_SQL = text(
    "SELECT captured_at, bedtime FROM samsung_hrv_readings "
    "WHERE user_id = :uid AND context = 'passive_overnight' "
    "AND bedtime IS NOT NULL AND captured_at BETWEEN :d0 AND :d1"
)

_TRAINING_SQL = text(
    "SELECT session_date, stop_time FROM aerobic_sessions "
    "WHERE user_id = :uid AND stop_time IS NOT NULL "
    "AND session_date BETWEEN :d0 AND :d1"
)


_NIGHTS_SQL = text(
    "SELECT date, diary_tst_min, diary_se_pct, lights_out, final_wake, "
    "       naps_min, alcohol_units "
    "FROM daily_records "
    "WHERE user_id = :uid AND date BETWEEN :d0 AND :d1 "
    "ORDER BY date"
)


def load_nights(db, user_id: int, d0: date, d1: date) -> list[Night]:
    # Column-explicit for the same reason the prescription read is: a full ORM
    # load would select got_into_bed / basis_n_* and fail against a database that
    # has not yet taken this branch's migrations. The replay must be able to read
    # production BEFORE the merge deploys them — otherwise verifying the engine
    # would require applying migrations to prod ahead of master, which is exactly
    # the divergence phase 1 spent a brief undoing.
    rows = db.execute(_NIGHTS_SQL, {"uid": user_id, "d0": d0, "d1": d1}).all()
    samsung = {r[0]: r[1] for r in db.execute(_SAMSUNG_SQL, {"uid": user_id, "d0": d0, "d1": d1})}
    # a session on the calendar day BEFORE the wake date constrains that night
    training = {r[0]: r[1] for r in db.execute(_TRAINING_SQL, {"uid": user_id, "d0": d0 - timedelta(days=1), "d1": d1})}

    nights = []
    for (d, tst, se, lo, fw, naps, alc) in rows:
        if tst is None:
            continue
        nights.append(Night(
            date=d, tst_min=tst, se_pct=se, lights_out=lo, final_wake=fw,
            naps_min=naps, alcohol_units=alc,
            samsung_bedtime=samsung.get(d),
            training_end=training.get(d - timedelta(days=1)),
        ))
    return nights


def replay(nights: list[Night], opened_on: date, wake_anchor: str,
           initial_lights_out: str) -> list[dict]:
    """Walk the block in 7-day cycles from the open date, adjudicating each."""
    window = window_minutes(initial_lights_out, wake_anchor)
    rx = initial_lights_out
    prior_tst: list[int] = []
    series = []
    by_date = {n.date: n for n in nights}
    last = max(by_date) if by_date else opened_on

    cycle_start = opened_on
    idx = 0
    while cycle_start <= last:
        cycle_end = cycle_start + timedelta(days=CYCLE_NIGHTS - 1)
        wnights = [by_date[d] for d in sorted(by_date)
                   if cycle_start <= d <= cycle_end]
        idx += 1
        if not wnights:
            cycle_start = cycle_end + timedelta(days=1)
            continue

        d = evaluate_cycle(wnights, window, rx, wake_anchor, prior_basis_tst=prior_tst)
        series.append({
            "cycle": idx,
            "from": cycle_start, "to": cycle_end,
            "decision": d.decision, "reason": d.reason,
            "window": d.window_minutes, "lights_out": d.prescribed_lights_out,
            "tst": d.basis_tst_min, "se": d.basis_se_pct,
            "n": d.basis_nights_n, "n_samsung": d.basis_n_samsung,
            "n_diary": d.basis_n_diary,
            "n_alc_unk": d.basis_n_alcohol_unknown,
            "excluded": d.excluded_nights,
            "lo_sd": d.lights_out_sd_min, "wk_sd": d.wake_time_sd_min,
            "ema": d.ema_count, "capped": d.move_capped,
        })
        if d.basis_tst_min is not None:
            prior_tst.append(d.basis_tst_min)
        if d.decision == "close":
            break
        window, rx = d.window_minutes, d.prescribed_lights_out
        cycle_start = cycle_end + timedelta(days=1)
    return series


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", type=int, required=True)
    ap.add_argument("--block-id", type=int, required=True)
    ap.add_argument("--admit-unknown-alcohol", action="store_true",
                    help="DIAGNOSTIC ONLY: treat alcohol_units IS NULL as zero, "
                         "reproducing the defective `> 0` predicate. Isolates how "
                         "much of the exclusion load is unknown-vs-recorded.")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        block = db.query(models.CBTIBlock).filter_by(id=args.block_id).one()
        # Column-explicit rather than a full ORM load: the replay is read-only and
        # must run against a database that has not yet taken this branch's
        # migration. Selecting the ORM entity would pull basis_n_samsung /
        # basis_n_diary and fail on a pre-migration schema — and applying the
        # migration to prod ahead of the merge is what created the
        # prod-ahead-of-master divergence in phase 1.
        rxs = db.execute(text(
            "SELECT effective_from, prescribed_lights_out, window_minutes, decision "
            "FROM cbti_prescriptions WHERE block_id = :bid ORDER BY effective_from"
        ), {"bid": block.id}).all()
        d1 = block.closed_on or date.today()
        nights = load_nights(db, args.user_id, block.opened_on, d1)
        if args.admit_unknown_alcohol:
            for n in nights:
                if n.alcohol_units is None:
                    n.alcohol_units = 0
            print("*** DIAGNOSTIC MODE: unknown alcohol admitted as zero ***")

        print(f"block {block.id}: {block.opened_on} .. {block.closed_on} anchor {block.wake_anchor}")
        print(f"nights loaded: {len(nights)}")
        n_with_samsung = sum(1 for n in nights if n.samsung_bedtime)
        n_with_training = sum(1 for n in nights if n.training_end)
        print(f"  nights with a passive_overnight bedtime: {n_with_samsung}")
        print(f"  nights with a constraining session end : {n_with_training}")
        print(f"historical prescriptions: {len(rxs)}")

        series = replay(nights, block.opened_on, block.wake_anchor,
                        rxs[0][1] if rxs else "22:30")

        print("\n=== REPLAY SERIES ===")
        print(f"{'cy':>2} {'window':>16} {'dec':<9} {'win':>4} {'lo':>6} "
              f"{'TST':>4} {'SE':>6} {'n':>2} {'sam':>3} {'dia':>3} {'a?':>3} {'exc':>3} {'ema':>3}")
        for s in series:
            print(f"{s['cycle']:>2} {str(s['from'])[5:]}..{str(s['to'])[5:]:>5} "
                  f"{s['decision']:<9} {s['window']:>4} {s['lights_out'] or '-':>6} "
                  f"{s['tst'] if s['tst'] is not None else '-':>4} "
                  f"{s['se'] if s['se'] is not None else '-':>6} "
                  f"{s['n']:>2} {s['n_samsung']:>3} {s['n_diary']:>3} {s['n_alc_unk']:>3} "
                  f"{len(s['excluded']):>3} {s['ema']:>3}")

        print("\n=== REASONS ===")
        for s in series:
            print(f"  cy{s['cycle']}: {s['reason']}")
            if s["excluded"]:
                print(f"        excluded: {s['excluded']}")

        print("\n=== HARD FLOOR ===")
        terminal = [s for s in series if s["decision"] == "close"]
        if terminal:
            end = terminal[0]["to"]
            print(f"  replay CLOSED in cycle {terminal[0]['cycle']}, window ending {end}")
            print(f"  block observed endpoint: {block.closed_on}")
            ok = end >= block.closed_on
            print(f"  terminates at or after the observed endpoint: {ok}")
            if not ok:
                print("  *** FLOOR BREACHED — #107's premise is wrong; STOP, do not tune ***")
        else:
            print(f"  replay did NOT close within the block (ran {len(series)} cycles)")
            print(f"  block observed endpoint: {block.closed_on} — floor not breached")

        print("\n=== COMPOSITION ===")
        ts, td = sum(s["n_samsung"] for s in series), sum(s["n_diary"] for s in series)
        print(f"  basis-night adherence sources across all cycles: samsung={ts} diary={td}")
        print(f"  basis nights ADMITTED with alcohol unrecorded (assumed clean): "
              f"{sum(s['n_alc_unk'] for s in series)}")
        print(f"  move capped in {sum(1 for s in series if s['capped'])} of {len(series)} cycles"
              f" (cap {MAX_MOVE_MIN} min)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
