"""The per-night basis ledger + #253 alcohol reclass (Brief B).

Pins the six pieces of the producer:
  1. one ledger row per evaluated night (no night dropped, `unknown` the catch-all);
  2. the ledger is persisted at accept with `ruleset_version` snapshotted;
  3. a recorded-alcohol night is FLAGGED (in the basis), not excluded (#253),
     capped one per cycle, and unable to move the window on its own;
  4. `nights_logged` is clipped to the cycle window;
  5. `outcome` splits a no-decision HOLD from a merits HOLD;
  6. (render is pinned in the frontend suite).

The alcohol reclass itself is ratified in DECISIONS_LOG #253 — the behaviour these tests
assert is the ratified spec, not a fresh choice made here.

SYNTHETIC data only; no real rows (both repos are public).
"""
from datetime import date, timedelta

import models
from cbti.engine import (
    CYCLE_NIGHTS, MIN_VALID_NIGHTS, RULESET_VERSION, Night,
    NightVerdict, classify_night, evaluate_cycle, outcome_of, _ledger_status_reason,
)
from routers.checkin_v2 import accept_cbti_evaluation, get_cbti_evaluation

RX = "22:30"
ANCHOR = "05:00"
WINDOW = 390


def _n(d, *, tst=420, se=90.0, lights_out=RX, wake="05:00", naps=0,
       alcohol=0, alcohol_finish=None, travel=False):
    return Night(
        date=date(2026, 8, d), tst_min=tst, se_pct=se, lights_out=lights_out,
        out_of_bed=wake, final_wake=wake, naps_min=naps, alcohol_units=alcohol,
        alcohol_finish_time=alcohol_finish, travel_or_match=travel,
    )


# ── #253: alcohol excused, not excluded ──────────────────────────────────────

def test_a_recorded_alcohol_night_is_flagged_and_counts_toward_the_basis():
    d = evaluate_cycle([_n(20), _n(21, alcohol=2, alcohol_finish="19:30"), _n(22)],
                       WINDOW, RX, ANCHOR)
    row = next(r for r in d.basis_ledger if r["date"] == "2026-08-21")
    assert row["status"] == "flagged" and row["reason"] == "alcohol"
    assert row["evidence"] == "2u @ 19:30"
    assert d.basis_n_flagged == 1
    assert d.basis_nights_n == 3            # the flagged night is IN the basis
    assert "2026-08-21" not in d.excluded_nights


def test_the_flagged_night_is_what_makes_an_otherwise_dead_cycle_sufficient():
    """#253's whole point: pre-reclass the drink night was excluded, leaving 2 valid of
    3 — a `sufficient=False` no-decision HOLD. Reclassed, it counts and the cycle is
    adjudicable."""
    d = evaluate_cycle([_n(20), _n(21, alcohol=2, alcohol_finish="19:30"), _n(22)],
                       WINDOW, RX, ANCHOR)
    assert d.sufficient is True
    assert outcome_of(d.decision, d.sufficient, d.converged) != "no_decision"


def test_excused_nights_are_capped_at_one_per_cycle():
    """Guard (a): a second recorded-alcohol night stays a plain exclusion, so a cycle can
    never be built predominantly on compromised nights."""
    d = evaluate_cycle(
        [_n(20, alcohol=2, alcohol_finish="19:30"),
         _n(21, alcohol=3, alcohol_finish="20:00"),
         _n(22), _n(23)],
        WINDOW, RX, ANCHOR)
    flagged = [r for r in d.basis_ledger if r["status"] == "flagged"]
    excluded_alcohol = [r for r in d.basis_ledger
                        if r["status"] == "excluded" and r["reason"] == "alcohol"]
    assert len(flagged) == 1 and len(excluded_alcohol) == 1
    assert d.basis_n_flagged == 1
    # the earliest drink night is the one kept; the later one is demoted
    assert flagged[0]["date"] == "2026-08-20"
    assert d.excluded_nights["2026-08-21"] == "alcohol"


# ── guard (b): an excused night may not by itself move the window ─────────────

def test_guard_b_holds_when_only_the_excused_night_carries_a_move():
    """Three-night cycle, one flagged: the clean subset (2 nights) is below the
    sufficiency floor, so the move rests on the excused night — HOLD on the merits, not
    an insufficiency (the flagged night keeps the cycle evaluable)."""
    d = evaluate_cycle([_n(20), _n(21), _n(22, alcohol=2, alcohol_finish="19:30")],
                       WINDOW, RX, ANCHOR)
    assert d.decision == "hold" and d.sufficient is True
    assert "excused_guard" in d.reason


def test_guard_b_holds_when_the_clean_subset_would_not_move_the_same_way():
    """Four nights, one flagged. The flagged night's high TST tips the full basis to
    extend, but the three clean nights on their own would not — so the extend is not
    robust to the excused night and the cycle holds."""
    nights = [_n(20, tst=360), _n(21, tst=360), _n(22, tst=360),
              _n(23, tst=470, alcohol=2, alcohol_finish="19:30")]
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert d.decision == "hold" and "excused_guard" in d.reason


def test_guard_b_allows_a_move_robust_to_the_excused_night():
    """Four nights, one flagged, all high TST: the clean three extend on their own, so the
    excused night is not what drives the change — the move stands."""
    nights = [_n(20, tst=450), _n(21, tst=450), _n(22, tst=450),
              _n(23, tst=450, alcohol=2, alcohol_finish="19:30")]
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert d.decision == "extend"
    assert d.basis_n_flagged == 1


# ── ledger completeness + the closed enum ────────────────────────────────────

def test_every_evaluated_night_gets_exactly_one_ledger_row():
    nights = [_n(20), _n(21, alcohol=2, alcohol_finish="19:30"),
              _n(22, naps=45), _n(23, travel=True)]
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)
    assert len(d.basis_ledger) == len(nights)
    by_date = {r["date"]: r for r in d.basis_ledger}
    assert by_date["2026-08-20"]["status"] == "included"
    assert by_date["2026-08-21"]["status"] == "flagged"
    assert by_date["2026-08-22"] == {**by_date["2026-08-22"], "status": "excluded", "reason": "nap"}
    assert by_date["2026-08-23"]["reason"] == "travel_or_match"
    # no "other" bucket, no dropped night
    assert {r["status"] for r in d.basis_ledger} <= {"included", "flagged", "excluded"}


def test_unknown_is_the_closed_enum_catch_all_for_an_unmapped_reason():
    """An invalid verdict carrying a reason the ledger does not know must not crash or
    invent a code — it maps to `excluded`/`unknown`, so a future engine reason can never
    silently become an untracked status or a dropped row."""
    v = NightVerdict(_n(20), False, "some_future_reason")
    assert _ledger_status_reason(v) == ("excluded", "unknown")


# ── outcome splits hold from no_decision (step 5) ────────────────────────────

def test_outcome_does_not_render_a_no_decision_as_a_hold():
    assert outcome_of("hold", sufficient=False, converged=False) == "no_decision"
    assert outcome_of("hold", sufficient=True, converged=False) == "hold"
    assert outcome_of("hold", sufficient=True, converged=True) == "converged"
    assert outcome_of("extend", sufficient=True, converged=False) == "extend"
    # the two HOLD states are distinct — the property step 5 exists to guarantee
    assert outcome_of("hold", False, False) != outcome_of("hold", True, False)


# ── nights_logged is clipped to the cycle (step 4) ───────────────────────────

def test_nights_logged_is_the_cycle_scoped_count_not_a_running_total():
    d = evaluate_cycle([_n(20), _n(21), _n(22)], WINDOW, RX, ANCHOR)
    assert d.basis_nights_logged == 3
    assert d.basis_nights_logged == len(d.basis_ledger)
    assert d.basis_nights_logged <= CYCLE_NIGHTS


def test_ruleset_version_is_stamped_on_the_decision():
    d = evaluate_cycle([_n(20), _n(21), _n(22)], WINDOW, RX, ANCHOR)
    assert d.ruleset_version == RULESET_VERSION


# ── ACCEPTANCE (Brief B gate) ────────────────────────────────────────────────

def test_acceptance_cycle_2026_08_20_to_23_renders_three_rows_one_alcohol():
    """The brief's acceptance: cycle 2026-08-20 → 2026-08-23 yields three ledger rows,
    one coded `alcohol` with evidence `2u @ 19:30`, and the row count equals
    nights_required (MIN_VALID_NIGHTS). 08-21 is unlogged, so the window is exactly the
    brief's span over the three nights the engine saw — and the reclass is what keeps all
    three in the basis rather than starving it to two."""
    nights = [
        _n(20, tst=420, se=90.0),
        _n(22, tst=430, se=91.0, alcohol=2, alcohol_finish="19:30"),
        _n(23, tst=415, se=89.0),
    ]
    d = evaluate_cycle(nights, WINDOW, RX, ANCHOR)

    assert len(d.basis_ledger) == 3
    assert d.basis_nights_n == MIN_VALID_NIGHTS            # row count == nights_required
    assert d.basis_window_start == date(2026, 8, 20)
    assert d.basis_window_end == date(2026, 8, 23)

    flagged = [r for r in d.basis_ledger if r["status"] == "flagged"]
    assert len(flagged) == 1
    assert flagged[0]["date"] == "2026-08-22"
    assert flagged[0]["reason"] == "alcohol"
    assert flagged[0]["evidence"] == "2u @ 19:30"


# ── persistence at close-out (step 2) ────────────────────────────────────────

def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def test_accept_snapshots_the_ledger_and_ruleset_version(db_session):
    """Accept (the cycle close-out) persists the ledger, its flagged count, and the
    ruleset it was produced under onto the successor prescription — so a later read is the
    stored ledger, never a recompute against a since-moved ruleset."""
    u = _user(db_session, "ledger-persist@x.io")
    start = date.today() - timedelta(days=CYCLE_NIGHTS)
    b = models.CBTIBlock(user_id=u.id, opened_on=start, closed_on=None,
                         wake_anchor=ANCHOR, open_reason="test")
    db_session.add(b); db_session.commit(); db_session.refresh(b)
    db_session.add(models.CBTIPrescription(
        block_id=b.id, effective_from=start, effective_to=None,
        prescribed_lights_out=RX, wake_anchor=ANCHOR, window_minutes=WINDOW, decision="adopt"))
    db_session.commit()
    # three logged nights (08-2x aside, the calendar day at index 1 is skipped), one a
    # recorded-alcohol night — sufficient only because #253 keeps it in the basis.
    for i in range(CYCLE_NIGHTS):
        if i == 1:
            continue
        drink = (i == 2)
        db_session.add(models.DailyRecord(
            user_id=u.id, date=start + timedelta(days=i), diary_tst_min=420,
            diary_se_pct=90.0, lights_out=RX, out_of_bed="05:00", final_wake="05:00",
            naps_min=0, alcohol_units=2 if drink else 0,
            alcohol_finish_time="19:30" if drink else None))
    db_session.commit()

    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.eligible is True and out.sufficient is True
    assert out.basis.ruleset_version == RULESET_VERSION
    assert len(out.basis.ledger) == 3
    assert out.basis.nights_logged == 3
    assert any(r["status"] == "flagged" and r["evidence"] == "2u @ 19:30"
               for r in out.basis.ledger)

    accept_cbti_evaluation(current_user=u, db=db_session)
    successor = (db_session.query(models.CBTIPrescription)
                 .filter_by(block_id=b.id)
                 .order_by(models.CBTIPrescription.id.desc()).first())
    assert successor.ruleset_version == RULESET_VERSION
    assert successor.basis_n_flagged == 1
    assert isinstance(successor.basis_ledger, list) and len(successor.basis_ledger) == 3
    assert any(r["reason"] == "alcohol" and r["evidence"] == "2u @ 19:30"
               for r in successor.basis_ledger)
