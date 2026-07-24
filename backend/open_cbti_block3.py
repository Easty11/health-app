"""Open CBT-I block 3 — one-shot, manual and witnessed (#118).

Block 3 has been running on paper since the night of 23->24 Jul 2026; every surface
gates on an open `cbti_blocks` row and none exists, so Steps 2-3 are built but
invisible. This mints the row and its opening `adopt` prescription.

Follows import_cbti_block.py: dry-run by DEFAULT, `--apply` to write, and a
duplicate-ABORT guard (refuses if a block already exists for this user opened on the
resolved date). The opening basis is DEVICE-DERIVED (Samsung actual_sleep_time_minutes),
computed here from prod at run time rather than hardcoded, so the printed dry-run is the
exact thing that would be written.

RESOLVED FROM PROD, not inferred (block 2 = id 1):
  - opened_on / effective_from tracks the WAKE-DATE label of night 1. Block 2's first
    diary date, opened_on, and first effective_from are all 2026-03-19. Night 23->24 Jul
    terminates on the morning of the 24th -> label 2026-07-24.
  - opening decision token is 'adopt' (what the importer wrote for block 2).

THE PRESCRIPTION is set by the operator, not derived: 23:45 -> 05:45 = 360 min. That is
~the mean recent TST (a deliberate restriction), and sits BELOW the titration rule's
mean+30. The basis fields are context, not the window driver.

THE RECORDED GAP: nothing in the schema distinguishes a device-derived basis_tst from a
diary one (basis_source_composition = n_samsung/n_diary covers ADHERENCE source, a
different axis). Stated in rationale and filed in OPEN_QUESTIONS; no column added mid-block.
"""
import argparse
import datetime as dt
import os
import statistics as st

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import models

USER_ID = 1
OPENED_ON = dt.date(2026, 7, 24)          # wake-date label of night 23->24 Jul (VERIFY 1)
WAKE_ANCHOR = "05:45"
LIGHTS_OUT = "23:45"
WINDOW_MIN = 360                          # 23:45 -> 05:45, set by operator
BASIS_START = dt.date(2026, 6, 23)
BASIS_END = dt.date(2026, 7, 23)
PARTIAL_MIN = 200                         # captures below this are partial, excluded
MIN_PER_DAY = 1440


def _to_min(s):
    if not s:
        return None
    p = s.strip().split(":")
    if len(p) < 2:
        return None
    try:
        h, m = int(p[0]), int(p[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def _wrap(b, w):
    if b is None or w is None:
        return None
    return (w - b) if w >= b else (w + MIN_PER_DAY - b)


def compute_basis(db):
    """Device-derived basis over BASIS_START..BASIS_END. Excludes partial captures
    (<200 min) and physically impossible rows (scored sleep > clock window)."""
    rows = db.execute(text(
        "SELECT captured_at, bedtime, wake_time, actual_sleep_time_minutes, sleep_efficiency_pct "
        "FROM samsung_hrv_readings WHERE user_id=:u AND context='passive_overnight' "
        "AND captured_at BETWEEN :d0 AND :d1 ORDER BY captured_at"
    ), {"u": USER_ID, "d0": BASIS_START, "d1": BASIS_END}).fetchall()

    kept_tst, kept_se, kept_tib, excluded = [], [], [], {}
    for captured_at, bedtime, wake, actual, se in rows:
        key = captured_at.isoformat() if hasattr(captured_at, "isoformat") else str(captured_at)
        win = _wrap(_to_min(bedtime), _to_min(wake))
        if actual is None:
            excluded[key] = "no_actual_sleep"
            continue
        if actual < PARTIAL_MIN:
            excluded[key] = "partial_capture"
            continue
        if win is not None and actual > win:
            excluded[key] = "impossible_sleep_gt_window"
            continue
        kept_tst.append(actual)
        if se is not None:
            kept_se.append(se)
        if win is not None:
            kept_tib.append(win)

    n = len(kept_tst)
    return {
        "scanned": len(rows),
        "basis_nights_n": n,
        "basis_tst_min": round(st.mean(kept_tst)) if kept_tst else None,
        "basis_se_pct": round(st.mean(kept_se), 1) if kept_se else None,
        # entire basis is device-derived: every kept night is a Samsung reading, none diary
        "basis_n_samsung": n,
        "basis_n_diary": 0,
        # every basis night admitted with alcohol unrecorded (device rows carry no alcohol) —
        # the whole basis rests on an unverified assumption of no alcohol effect
        "basis_n_alcohol_unknown": n,
        # mean actual TIB minus the prescribed window (instrumented, not gated)
        "basis_tib_over_run_min": round(st.mean(kept_tib) - WINDOW_MIN, 1) if kept_tib else None,
        "basis_window_start": BASIS_START,
        "basis_window_end": BASIS_END,
        "excluded_nights": excluded,
    }


def main():
    ap = argparse.ArgumentParser(description="Open CBT-I block 3 (dry-run unless --apply).")
    ap.add_argument("--apply", action="store_true", help="write to the database")
    args = ap.parse_args()

    url = os.environ["DATABASE_URL"]
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(url)

    with Session(engine) as db:
        existing = (db.query(models.CBTIBlock)
                    .filter_by(user_id=USER_ID, opened_on=OPENED_ON).first())
        if existing:
            raise SystemExit(
                f"ABORT: a cbti_block already exists for user {USER_ID} opened_on "
                f"{OPENED_ON} (id={existing.id}). Refusing to double-open.")

        b = compute_basis(db)
        rationale = (
            "Opening prescription for block 3 (third CBT-I block; block 2 = id 1, "
            "2026-03-19..2026-05-11). Window 360 (23:45->05:45) set by the operator as the "
            f"running restriction — ~the mean recent TST (basis_tst_min={b['basis_tst_min']}) "
            "and BELOW the titration rule's mean+30, a deliberate restriction. BASIS IS "
            f"DEVICE-DERIVED, not diary (basis_n_samsung={b['basis_n_samsung']}, basis_n_diary=0): "
            "no schema column distinguishes device-vs-diary basis_tst provenance "
            "(basis_source_composition covers adherence source only). Filed in OPEN_QUESTIONS. "
            f"basis_n_alcohol_unknown={b['basis_n_alcohol_unknown']}: whole basis admitted with "
            "alcohol unrecorded."
        )
        open_reason = (
            "Third CBT-I block (two prior completions). Opened live and witnessed per #118. "
            "Opening basis is device-derived (Samsung actual_sleep_time_minutes, "
            f"{BASIS_START}..{BASIS_END}), not diary."
        )

        print(f"[basis] scanned={b['scanned']} kept={b['basis_nights_n']} "
              f"tst={b['basis_tst_min']}m se={b['basis_se_pct']}% "
              f"tib_over_run={b['basis_tib_over_run_min']}m excluded={b['excluded_nights']}")
        print(f"[block] user={USER_ID} opened_on={OPENED_ON} anchor={WAKE_ANCHOR}")
        print(f"[rx]    adopt effective_from={OPENED_ON} lights_out={LIGHTS_OUT} "
              f"window={WINDOW_MIN} anchor={WAKE_ANCHOR}")

        if not args.apply:
            print("[dry-run] no write. Re-run with --apply to open the block.")
            return

        block = models.CBTIBlock(
            user_id=USER_ID, opened_on=OPENED_ON, closed_on=None,
            wake_anchor=WAKE_ANCHOR, open_reason=open_reason,
            notes="Opened by open_cbti_block3.py — live block, not an import.",
        )
        db.add(block)
        db.flush()

        rx = models.CBTIPrescription(
            block_id=block.id, effective_from=OPENED_ON, effective_to=None,
            prescribed_lights_out=LIGHTS_OUT, wake_anchor=WAKE_ANCHOR,
            window_minutes=WINDOW_MIN, decision="adopt",
            basis_tst_min=b["basis_tst_min"], basis_se_pct=b["basis_se_pct"],
            basis_nights_n=b["basis_nights_n"],
            basis_n_samsung=b["basis_n_samsung"], basis_n_diary=b["basis_n_diary"],
            basis_n_alcohol_unknown=b["basis_n_alcohol_unknown"],
            basis_tib_over_run_min=b["basis_tib_over_run_min"],
            basis_window_start=b["basis_window_start"], basis_window_end=b["basis_window_end"],
            excluded_nights=b["excluded_nights"], rationale=rationale, superseded_by=None,
        )
        db.add(rx)
        db.commit()
        print(f"[applied] block id={block.id}, prescription id={rx.id}. Block 3 is open.")


if __name__ == "__main__":
    main()
