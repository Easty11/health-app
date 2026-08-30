"""Replay the titration engine over a CBT-I block, adjudicating each cycle against
the EFFECTIVE prescription from the ledger (Q49).

The replay reads the prescription in force for each cycle from `cbti_prescriptions`;
it does NOT regenerate the chain from the engine's own decisions. So a mid-block
operator correction — or any ledger prescription the engine would not have produced —
is honoured by construction: adherence is always differenced against the prescription
the nights were actually run under, and the wake anchor comes from that prescription,
not from the block's opening state.

Cycles are anchored to each prescription's `effective_from` and NEVER span a
prescription boundary — the same "≥7 nights since the current prescription's
effective_from" unit the live evaluation trigger (#118) uses, so replay and trigger
share one model. Before Q49 the replay walked fixed 7-day cycles from the block open
and carried the engine's own output forward as the next window; a correction landing
mid-cycle (block 3: id=11 supersedes id=10 on the 4th night of cycle 1) was invisible,
and the four nights run under the correction read as adherence failures against the
seeded prescription — a false GATE-2 HOLD. That is the defect this module now fixes.

The engine's per-cycle DECISION is recorded as a RECOMMENDATION — what the engine
would prescribe given these nights — but it never becomes the next cycle's
prescription; the ledger does. A plateau "close" is recorded (for #107's
exit-too-early check) but does NOT terminate the walk, because the operator's ledger,
not the engine, decides when the block ends.

This is the DB adapter. The engine itself is pure — every query lives here, and the
Samsung read goes through the `context = 'passive_overnight'` allowlist and nowhere
else.

Usage:
    python -m cbti.replay --user-id 1 --block-id 1
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import text

import models
from cbti.engine import CYCLE_NIGHTS, MAX_MOVE_MIN, Night, evaluate_cycle, outcome_of
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
    "SELECT date, diary_tst_min, diary_se_pct, lights_out, out_of_bed, final_wake, "
    "       alcohol_units, alcohol_finish_time "
    "FROM daily_records "
    "WHERE user_id = :uid AND date BETWEEN :d0 AND :d1 "
    "ORDER BY date"
)

# Naps are read on their OWN row but attributed to the night they PRECEDE, so they cannot
# ride the night query — they need a different date window and a different null contract.
#
#   * Different window: Night(d0) reads the nap recorded on d0-1, one day outside the
#     night range. Sharing the query would silently give the first night of every cycle
#     no nap at all — an off-by-one that reads as clean data.
#   * Different null contract: the night query drops rows with no `diary_tst_min`
#     (`continue` below). A day can carry a logged nap and no diary entry — legitimately,
#     since naps are captured at PM and the diary at AM — and folding the two would
#     discard that nap rather than attribute it.
#
# `naps_min IS NOT NULL` keeps the 0-vs-absent distinction the engine's `is not None`
# guard depends on: a missing key and a null both mean UNKNOWN (pre-capture), while a
# stored 0 means "asked, no nap". `.get()` collapsing both to None is correct here.
_NAPS_SQL = text(
    "SELECT date, naps_min FROM daily_records "
    "WHERE user_id = :uid AND naps_min IS NOT NULL "
    "AND date BETWEEN :d0 AND :d1"
)

# Column-explicit for the same reason load_nights is: a full ORM load would select
# basis_n_* and fail against a database that has not yet taken a later branch's
# migrations. effective_to and wake_anchor are original cbti_prescriptions columns,
# so reading them here is safe on any schema that has the table at all.
_PRESCRIPTIONS_SQL = text(
    "SELECT effective_from, effective_to, prescribed_lights_out, wake_anchor, "
    "       window_minutes, decision "
    "FROM cbti_prescriptions WHERE block_id = :bid ORDER BY effective_from"
)


@dataclass
class LedgerRx:
    """A prescription as read from `cbti_prescriptions` for the replay to adjudicate
    against (Q49). `effective_to` is None for the live prescription of an open block.
    """
    effective_from: date
    effective_to: date | None
    lights_out: str
    wake_anchor: str
    window_minutes: int
    decision: str


def _as_date(v):
    """Normalise a DATE read back through raw SQL.

    psycopg returns `datetime.date`; SQLite hands back the ISO string, because a
    `text()` query bypasses the ORM's type coercion. Without this the adapter is
    Postgres-only — the date arithmetic below raises `str - timedelta` — which is why
    the replay suite could only ever test `replay()` on synthetic Nights and never
    `load_nights` itself. Pure normalisation: a real date passes through untouched, so
    nothing about the production read changes.
    """
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def load_nights(db, user_id: int, d0: date, d1: date) -> list[Night]:
    # Column-explicit for the same reason the prescription read is: a full ORM
    # load would select got_into_bed / basis_n_* and fail against a database that
    # has not yet taken this branch's migrations. The replay must be able to read
    # production BEFORE the merge deploys them — otherwise verifying the engine
    # would require applying migrations to prod ahead of master, which is exactly
    # the divergence phase 1 spent a brief undoing.
    rows = db.execute(_NIGHTS_SQL, {"uid": user_id, "d0": d0, "d1": d1}).all()
    samsung = {_as_date(r[0]): r[1] for r in db.execute(_SAMSUNG_SQL, {"uid": user_id, "d0": d0, "d1": d1})}
    # a session on the calendar day BEFORE the wake date constrains that night
    training = {_as_date(r[0]): r[1] for r in db.execute(_TRAINING_SQL, {"uid": user_id, "d0": d0 - timedelta(days=1), "d1": d1})}
    # likewise a nap on the calendar day BEFORE the wake date is the one that discharged
    # this night's sleep pressure — Night(W) reads the nap recorded on W-1 (Q45 -> #219).
    # This is the read `models.DailyRecord.naps_min` has documented as the contract since
    # the column was created; until now the engine took the nap off the night's own row.
    naps = {_as_date(r[0]): r[1] for r in db.execute(_NAPS_SQL, {"uid": user_id, "d0": d0 - timedelta(days=1), "d1": d1})}

    nights = []
    for (d, tst, se, lo, oob, fw, alc, alc_finish) in rows:
        if tst is None:
            continue
        d = _as_date(d)
        nights.append(Night(
            date=d, tst_min=tst, se_pct=se, lights_out=lo, out_of_bed=oob, final_wake=fw,
            naps_min=naps.get(d - timedelta(days=1)), alcohol_units=alc,
            alcohol_finish_time=alc_finish,
            samsung_bedtime=samsung.get(d),
            training_end=training.get(d - timedelta(days=1)),
        ))
    return nights


def replay(nights: list[Night], prescriptions: list[LedgerRx],
           last_night: date) -> list[dict]:
    """Walk the block by LEDGER PRESCRIPTION (Q49), adjudicating each 7-night cycle
    against the prescription actually in force over those nights.

    A prescription P governs the nights in
    ``[P.effective_from, min(P.effective_to, next.effective_from - 1, last_night)]``,
    and cycles walk 7 nights at a time from ``P.effective_from`` within that span, so
    a cycle can never straddle a prescription change. `prior_basis_tst` accumulates
    across ALL cycles (TST-plateau is a trajectory property, indifferent to window
    nudges); `nights_since_effective_from` resets at each prescription (#124).
    """
    by_date = {n.date: n for n in nights}
    rxs = sorted(prescriptions, key=lambda r: r.effective_from)
    series: list[dict] = []
    prior_tst: list[int] = []
    idx = 0

    for i, rx in enumerate(rxs):
        next_from = rxs[i + 1].effective_from if i + 1 < len(rxs) else None
        span_end = last_night
        if rx.effective_to is not None:
            span_end = min(span_end, rx.effective_to)
        if next_from is not None:
            # the successor's effective_from is a hard wall: the night before it is
            # the last night this prescription can be adjudicated over
            span_end = min(span_end, next_from - timedelta(days=1))

        cycle_start = rx.effective_from
        while cycle_start <= span_end:
            cycle_end = min(cycle_start + timedelta(days=CYCLE_NIGHTS - 1), span_end)
            wnights = [by_date[d] for d in sorted(by_date)
                       if cycle_start <= d <= cycle_end]
            if not wnights:
                cycle_start = cycle_end + timedelta(days=1)
                continue
            idx += 1
            # nights logged since THIS prescription took effect (settling period, #124)
            nse = sum(1 for dd in by_date if rx.effective_from <= dd <= cycle_end)
            d = evaluate_cycle(wnights, rx.window_minutes, rx.lights_out, rx.wake_anchor,
                               prior_basis_tst=prior_tst, nights_since_effective_from=nse)
            series.append({
                "cycle": idx,
                "from": cycle_start, "to": cycle_end,
                # the prescription these nights were ADJUDICATED AGAINST (from the ledger)
                "rx_from": rx.effective_from, "rx_decision": rx.decision,
                "rx_window": rx.window_minutes, "rx_lights_out": rx.lights_out,
                "rx_anchor": rx.wake_anchor,
                # the engine's RECOMMENDATION — never fed forward; the ledger is
                "decision": d.decision, "reason": d.reason,
                "rec_window": d.window_minutes, "rec_lights_out": d.prescribed_lights_out,
                "tst": d.basis_tst_min, "se": d.basis_se_pct,
                "n": d.basis_nights_n, "n_samsung": d.basis_n_samsung,
                "n_diary": d.basis_n_diary,
                "n_alc_unk": d.basis_n_alcohol_unknown,
                "n_flagged": d.basis_n_flagged,
                "tib_over": d.basis_tib_over_run_min,
                "excluded": d.excluded_nights,
                # Brief B: the per-night ledger the surface renders, the ruleset it was
                # produced under (snapshotted at accept, never recomputed at render), the
                # cycle-scoped logged count (clipped, not `nse`), and the non-overloaded
                # outcome that splits a no-decision HOLD from a merits HOLD.
                "ledger": d.basis_ledger,
                "ruleset_version": d.ruleset_version,
                "nights_logged": d.basis_nights_logged,
                "outcome": outcome_of(d.decision, d.sufficient, d.converged),
                "lo_sd": d.lights_out_sd_min, "wk_sd": d.wake_time_sd_min,
                "ema": d.ema_count, "capped": d.move_capped,
                "converged": d.converged,
                # The decision-class discriminator (#218). False only where the engine's
                # sufficiency gate fired; every decision-on-merits is True. Carried verbatim
                # from the engine — NEVER re-derived here from `n` against MIN_VALID_NIGHTS,
                # which would put the threshold in two places and let them drift.
                "sufficient": d.sufficient,
                "nse": d.nights_since_effective_from,
            })
            if d.basis_tst_min is not None:
                prior_tst.append(d.basis_tst_min)
            cycle_start = cycle_end + timedelta(days=1)
    return series


def load_ledger_rxs(db, block_id: int) -> list[LedgerRx]:
    """The block's prescriptions as the ledger records them, ordered by effective_from.

    Extracted from `main` so the live evaluation trigger (#118) reads prescriptions
    through the SAME query as the replay. #128's revisit clause makes this a hard
    boundary: the trigger "must reuse this same read, or the two paths diverge again".
    """
    rows = db.execute(_PRESCRIPTIONS_SQL, {"bid": block_id}).all()
    return [LedgerRx(effective_from=_as_date(ef), effective_to=_as_date(et), lights_out=lo,
                     wake_anchor=anchor, window_minutes=win, decision=dec)
            for (ef, et, lo, anchor, win, dec) in rows]


@dataclass
class LiveCycleEval:
    """The live prescription's most recent COMPLETE cycle, for the #118 PM trigger.

    `eligible` answers only "is there a finished cycle to offer"; the decision itself
    is the engine's and may still be a HOLD (insufficient nights, adherence, or a
    converged plateau).
    """
    eligible: bool
    reason: str                      # why not eligible, or "" when it is
    days_since_effective_from: int
    nights_since_effective_from: int
    live_rx: LedgerRx
    cycle: dict | None               # a `replay()` series entry


def evaluate_live_cycle(db, user_id: int, block, today: date) -> LiveCycleEval | None:
    """Evaluate the open block's LIVE prescription through the replay itself (#128).

    Returns None when the block carries no live prescription at all.

    This runs the FULL block replay rather than evaluating the live prescription in
    isolation, and that is load-bearing, not convenience: `prior_basis_tst` accumulates
    across every prior cycle in the block, and the TST-plateau detection needs two of
    them. Evaluating the live cycle alone would start that history empty, so the engine
    could never report a `converged HOLD` — the plateau signal that says "the window has
    settled here, keep watching" — and every cycle would read as a fresh titration with
    no memory of whether it had already found its level. (The engine emits no
    block-ending decision under the hunting search; convergence is a HOLD that leaves
    the block open, #107.)

    ELIGIBILITY IS CALENDAR DAYS, NOT LOGGED NIGHTS. #118 makes the offer once a full
    cycle has elapsed since the current prescription's effective_from, and `replay()`'s
    own cycle spans are calendar-dated (`cycle_start + CYCLE_NIGHTS - 1`), so days is the
    unit that matches both — the gate below is `days < CYCLE_NIGHTS`. Gating on LOGGED
    nights instead would mean a single unlogged night defers the offer indefinitely — a
    cycle can never reach CYCLE_NIGHTS logged nights once one of its calendar days is
    missing — which silently strands the operator mid-titration. Night COUNT still governs
    the decision, but through the engine's own sufficiency gate (>= MIN_VALID_NIGHTS
    valid), which returns a HOLD naming the shortfall rather than withholding the offer.
    Both quantities are reported so the operator sees each.

    THE OFFER IS STILL MADE, BUT SUCH A CYCLE IS NOT ACCEPTABLE (#218). `eligible` and
    `sufficient` are different questions: eligible says a cycle has elapsed and there is
    something to SHOW; the cycle's `sufficient` flag says whether what is shown is a
    decision at all. An insufficiency HOLD is a finding, so the accept path refuses it
    (409) and the client renders it information-only. Selection is untouched — still
    `complete[-1]`; deferring to an older sufficient cycle would resurrect a decision
    the staleness rule says has expired.
    """
    rxs = load_ledger_rxs(db, block.id)
    live = next((r for r in rxs if r.effective_to is None), None)
    if live is None:
        return None

    nights = load_nights(db, user_id, block.opened_on, today)
    logged = [n for n in nights if n.date >= live.effective_from]
    days = (today - live.effective_from).days

    def _out(eligible, reason, cycle):
        return LiveCycleEval(
            eligible=eligible, reason=reason, days_since_effective_from=days,
            nights_since_effective_from=len(logged), live_rx=live, cycle=cycle,
        )

    if days < CYCLE_NIGHTS:
        return _out(False, f"cycle_in_progress: day {days} of {CYCLE_NIGHTS}", None)

    series = replay(nights, rxs, last_night=today)
    # Cycles belonging to the live prescription whose full CYCLE_NIGHTS span has elapsed.
    # A partial trailing cycle is excluded: adjudicating a decision over a span shorter
    # than CYCLE_NIGHTS because the operator opened PM mid-cycle would decide an unfinished
    # cycle. The span test is calendar-based, so a cycle counts as complete once its days
    # have passed even if a night inside it went unlogged.
    complete = [s for s in series
                if s["rx_from"] == live.effective_from
                and (s["to"] - s["from"]).days == CYCLE_NIGHTS - 1]
    if not complete:
        return _out(False, "no_complete_cycle: no nights logged in the elapsed span", None)
    # The LAST complete cycle, not the first — if the operator let two cycles pass, the
    # decision due now rests on the week that just ended, not the stale one before it.
    return _out(True, "", complete[-1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", type=int, required=True)
    ap.add_argument("--block-id", type=int, required=True)
    args = ap.parse_args()

    db = SessionLocal()
    try:
        block = db.query(models.CBTIBlock).filter_by(id=args.block_id).one()
        rxs = load_ledger_rxs(db, block.id)

        d1 = block.closed_on or date.today()
        nights = load_nights(db, args.user_id, block.opened_on, d1)

        last_night = block.closed_on or (max((n.date for n in nights), default=d1))

        print(f"block {block.id}: {block.opened_on} .. {block.closed_on} block-anchor {block.wake_anchor}")
        print(f"nights loaded: {len(nights)}")
        n_with_samsung = sum(1 for n in nights if n.samsung_bedtime)
        n_with_training = sum(1 for n in nights if n.training_end)
        print(f"  nights with a passive_overnight bedtime: {n_with_samsung}")
        print(f"  nights with a constraining session end : {n_with_training}")
        print(f"ledger prescriptions: {len(rxs)}")
        for rx in rxs:
            print(f"  rx {rx.effective_from}..{rx.effective_to or '(live)'} "
                  f"{rx.lights_out}->{rx.wake_anchor} win={rx.window_minutes} dec={rx.decision}")

        series = replay(nights, rxs, last_night)

        print("\n=== REPLAY SERIES (adjudicated against the ledger rx) ===")
        print(f"{'cy':>2} {'window':>13} {'rxLO':>6} {'rxWin':>5} {'dec':<9} "
              f"{'recWin':>6} {'TST':>4} {'SE':>6} {'n':>2} {'dia':>3} {'exc':>3} {'ema':>3} {'nse':>3}")
        for s in series:
            print(f"{s['cycle']:>2} {str(s['from'])[5:]}..{str(s['to'])[5:]:>5} "
                  f"{s['rx_lights_out']:>6} {s['rx_window']:>5} {s['decision']:<9} "
                  f"{s['rec_window']:>6} "
                  f"{s['tst'] if s['tst'] is not None else '-':>4} "
                  f"{s['se'] if s['se'] is not None else '-':>6} "
                  f"{s['n']:>2} {s['n_diary']:>3} {len(s['excluded']):>3} "
                  f"{s['ema']:>3} {s['nse']:>3}")

        print("\n=== REASONS ===")
        for s in series:
            print(f"  cy{s['cycle']} [{s['from']}..{s['to']} vs rx {s['rx_lights_out']}]: {s['reason']}")
            if s["excluded"]:
                print(f"        excluded: {s['excluded']}")

        # #107's exit-too-early check, restated. The engine no longer emits `close` at
        # all — the titration is a perpetual hunting search and a plateau is a CONVERGED
        # HOLD that leaves the block open. So the question is no longer "would it have
        # exited too early" but "where did it settle", which is the same observation
        # without the exit: the first converged cycle is where #107's rule would have
        # closed, and the block's observed endpoint is still the comparison.
        print("\n=== CONVERGENCE CHECK (the engine never closes a block) ===")
        converged = [s for s in series if s["converged"]]
        if converged:
            first = converged[0]
            print(f"  engine FIRST converged in cycle {first['cycle']}, window ending {first['to']}")
            print(f"  block observed endpoint: {block.closed_on}")
            if block.closed_on is not None:
                early = first["to"] < block.closed_on
                print(f"  convergence precedes the observed endpoint: {early}"
                      + ("  *** #107 would have exited here ***" if early else ""))
            print(f"  cycles after first convergence: {len(series) - series.index(first) - 1}"
                  f"  (the hunt continues; nothing terminates)")
        else:
            print(f"  engine never converged across {len(series)} cycles"
                  f" — still hunting (observed endpoint {block.closed_on})")

        print("\n=== COMPOSITION ===")
        td = sum(s["n_diary"] for s in series)
        ts = sum(s["n_samsung"] for s in series)
        print(f"  basis-night adherence sources across all cycles: diary={td} samsung={ts}"
              f"  (samsung is dead as an adherence input, #127)")
        print(f"  basis nights ADMITTED with alcohol unrecorded (assumed clean): "
              f"{sum(s['n_alc_unk'] for s in series)}")
        print(f"  engine recommendation capped in {sum(1 for s in series if s['capped'])} of "
              f"{len(series)} cycles (cap {MAX_MOVE_MIN} min)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
