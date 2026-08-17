"""The accept path discriminates on DECISION CLASS, not on a reason string (#218, Q101).

`test_cbti_eval_trigger.py` pins the OFFER half of #118 — that an insufficiency cycle is
still offered rather than withheld. This module pins the ACCEPT half, which is the
opposite question and was the live #214 defect: an offer the operator can see is not
thereby an offer they can record.

WHAT IS BEING SEPARATED. The engine returns `decision="hold"` on three quite different
grounds, and only one of them is a non-decision:

  * insufficiency HOLD — GATE 1 fired, too few valid nights. The engine reached NO
    conclusion. `sufficient=False`. NOT acceptable.
  * adherence HOLD — GATE 2 fired. A conclusion: the window was not run, so its sleep is
    not evidence about it. `sufficient=True`. Acceptable.
  * converged HOLD — a TST plateau at the SE floor. A conclusion, and the one most worth
    recording: it is the block's memory of the level it found. `sufficient=True`.
    Acceptable.

A test that asserted only "hold is refused" would therefore be WRONG in two of three
cases, which is precisely why the discriminator is structural rather than a `startswith`
on the reason. Both directions are pinned below.

The harm the 409 prevents is not a bad number in a row — it is the row's SIDE EFFECTS:
minting closes the current cycle (`effective_to` on the prior) and restarts the ~4-day
evaluation clock from today. Accepting a "could not adjudicate" therefore DISCARDS the
nights that were logged and buys nothing. Every refusal test below asserts the ledger is
untouched, not merely that a 409 was raised.

SYNTHETIC data only; no real rows (both repos are public).
"""
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

import models
from cbti.engine import (
    CYCLE_NIGHTS, MIN_VALID_NIGHTS, PLATEAU_TOL_MIN, SE_FLOOR_PCT, evaluate_cycle,
)
from routers.checkin_v2 import accept_cbti_evaluation, get_cbti_evaluation


# ── row builders ─────────────────────────────────────────────────────────────
# Restated rather than imported from `test_cbti_eval_trigger`: no module in this suite
# imports another, and a shared fixture helper would couple two modules that pin opposite
# halves of #118 — a change made for the offer suite could then silently reshape what the
# accept suite believes it is exercising.

def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _block(db, uid, *, opened, anchor="05:00"):
    b = models.CBTIBlock(user_id=uid, opened_on=opened, closed_on=None,
                         wake_anchor=anchor, open_reason="test")
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def _rx(db, bid, *, eff, to=None, lo="22:30", win=390, decision="adopt", anchor="05:00"):
    r = models.CBTIPrescription(
        block_id=bid, effective_from=eff, effective_to=to, prescribed_lights_out=lo,
        wake_anchor=anchor, window_minutes=win, decision=decision,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _nights(db, uid, start, n, *, lo="22:30", tst=420, se=90.0, wake="05:00", skip=()):
    """Diary nights. `skip` drops calendar days so a shortfall can be exercised."""
    for i in range(n):
        if i in skip:
            continue
        db.add(models.DailyRecord(
            user_id=uid, date=start + timedelta(days=i), diary_tst_min=tst,
            diary_se_pct=se, lights_out=lo, out_of_bed=wake, final_wake=wake,
            naps_min=0, alcohol_units=0,
        ))
    db.commit()


# ── fixtures, one per decision class ─────────────────────────────────────────

def _insufficiency(db, u):
    """A full cycle has elapsed but only 2 of its 4 nights were logged (need 3).

    Note the shape: the offer IS eligible. That is the whole trap — days elapsed is the
    eligibility unit (#118), so the card appears; night count is the sufficiency unit, and
    it is the one that says there is nothing to record.
    """
    start = date.today() - timedelta(days=CYCLE_NIGHTS)
    b = _block(db, u.id, opened=start)
    _rx(db, b.id, eff=start, win=390)
    _nights(db, u.id, start, CYCLE_NIGHTS, skip=(1, 2))
    return b


def _compress(db, u):
    """A decision on merits, in the direction that takes sleep opportunity AWAY.

    TST 300 + 30 buffer targets 330 against a 390 window: a -60 move capped to -15, so a
    375 proposed window.
    """
    start = date.today() - timedelta(days=CYCLE_NIGHTS)
    b = _block(db, u.id, opened=start)
    _rx(db, b.id, eff=start, win=390)
    _nights(db, u.id, start, CYCLE_NIGHTS, tst=300, se=90.0)
    return b


def _converged_hold(db, u):
    """Three complete cycles of one prescription with TST flat and SE at the floor.

    `prior_basis_tst` needs two prior observations before a plateau can be judged, and it
    accumulates over the WHOLE block replay — so the live prescription must itself span
    three cycles. Deltas are 0/0, inside PLATEAU_TOL_MIN, with SE 90 >= SE_FLOOR_PCT.
    """
    start = date.today() - timedelta(days=3 * CYCLE_NIGHTS)
    b = _block(db, u.id, opened=start)
    _rx(db, b.id, eff=start, win=390)
    _nights(db, u.id, start, 3 * CYCLE_NIGHTS, tst=420, se=90.0)
    return b


def _rx_count(db, block_id):
    return db.query(models.CBTIPrescription).filter_by(block_id=block_id).count()


# ── the engine emits the discriminator, and on exactly one path ──────────────

def test_engine_flags_only_the_sufficiency_gate_as_insufficient():
    """Pinned at the engine because that is where the flag is minted. `converged` sets
    the precedent; this asserts the new field does not accidentally follow `decision`
    (all three cases below return "hold") or `converged`.
    """
    from cbti.engine import Night

    def _n(i, **kw):
        base = dict(date=date(2026, 1, 1) + timedelta(days=i), tst_min=420, se_pct=90.0,
                    lights_out="22:30", out_of_bed="05:00", final_wake="05:00",
                    naps_min=0, alcohol_units=0)
        base.update(kw)
        return Night(**base)

    # GATE 1: two nights, need three.
    d = evaluate_cycle([_n(0), _n(1)], 390, "22:30", "05:00")
    assert d.decision == "hold"
    assert d.sufficient is False
    assert d.converged is False
    assert len(d.excluded_nights) == 0                 # not an exclusion problem — a count one

    # GATE 2: enough nights, but run far outside the prescribed lights-out.
    late = [_n(i, lights_out="01:30") for i in range(CYCLE_NIGHTS)]
    d = evaluate_cycle(late, 390, "22:30", "05:00")
    assert d.decision == "hold" and d.reason.startswith("adherence")
    assert d.sufficient is True                        # a conclusion, not a failure to reach one

    # CONVERGED: a plateau at the SE floor.
    d = evaluate_cycle([_n(i) for i in range(CYCLE_NIGHTS)], 390, "22:30", "05:00",
                       prior_basis_tst=[420, 420])
    assert d.converged is True and d.decision == "hold"
    assert d.sufficient is True

    # A move.
    d = evaluate_cycle([_n(i, tst_min=300) for i in range(CYCLE_NIGHTS)], 390, "22:30", "05:00")
    assert d.decision == "compress"
    assert d.sufficient is True


def test_engine_constants_still_make_the_fixtures_mean_what_they_say():
    """The fixtures above encode MIN_VALID_NIGHTS=3 of CYCLE_NIGHTS=4 as `skip=(1, 2)`,
    and the converged fixture encodes the plateau tolerance and SE floor. If those
    constants move, the fixtures silently stop exercising the classes they are named for —
    a green suite that tests nothing. Cheap to assert; impossible to miss if it regresses.
    """
    assert CYCLE_NIGHTS == 4 and MIN_VALID_NIGHTS == 3
    assert PLATEAU_TOL_MIN >= 0 and SE_FLOOR_PCT <= 90.0


# ── the offer surfaces it, so the client need not parse reason strings ───────

def test_offer_surfaces_the_discriminator_on_every_class(db_session):
    u = _user(db_session, "class-offer@x.io")
    _insufficiency(db_session, u)
    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.eligible is True                        # the offer is still MADE...
    assert out.sufficient is False                     # ...and still not acceptable
    assert "insufficient_nights" in out.decision_reason

    u2 = _user(db_session, "class-offer2@x.io")
    _compress(db_session, u2)
    out = get_cbti_evaluation(current_user=u2, db=db_session)
    assert out.eligible is True and out.decision == "compress"
    assert out.sufficient is True

    u3 = _user(db_session, "class-offer3@x.io")
    _converged_hold(db_session, u3)
    out = get_cbti_evaluation(current_user=u3, db=db_session)
    assert out.eligible is True and out.decision == "hold"
    assert out.sufficient is True


def test_sufficient_defaults_true_when_there_is_no_cycle_at_all(db_session):
    """A response carrying no cycle — no open block, or a cycle still in progress — must
    not read as an insufficiency. The client suppresses its accept control on an explicit
    False, so a wrong default here would go the safe direction but say something untrue.
    """
    u = _user(db_session, "class-none@x.io")
    assert get_cbti_evaluation(current_user=u, db=db_session).sufficient is True

    b = _block(db_session, u.id, opened=date.today() - timedelta(days=2))
    _rx(db_session, b.id, eff=date.today() - timedelta(days=2))
    _nights(db_session, u.id, date.today() - timedelta(days=2), 2)
    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.eligible is False and out.sufficient is True


# ── accept: refused on the finding, allowed on the decisions ─────────────────

def test_accept_refuses_an_insufficiency_hold_and_writes_nothing(db_session):
    """The #214 harm event, inverted into a control.

    The 409 is the point, but the assertions that matter are the ones after it: no row
    appended, and the prior prescription's `effective_to` still None — i.e. the current
    cycle is still open and the ~4-day clock has NOT restarted. That clock reset is what
    made the block-2 event costly; a test that stopped at the status code would pass even
    if the refusal happened after the ledger had already moved.
    """
    u = _user(db_session, "class-accept@x.io")
    b = _insufficiency(db_session, u)
    prior = (db_session.query(models.CBTIPrescription)
             .filter_by(block_id=b.id).one())

    with pytest.raises(HTTPException) as e:
        accept_cbti_evaluation(current_user=u, db=db_session)
    assert e.value.status_code == 409
    assert "Not enough logged nights" in e.value.detail

    assert _rx_count(db_session, b.id) == 1
    db_session.refresh(prior)
    assert prior.effective_to is None                   # the cycle was NOT closed
    assert prior.superseded_by is None
    db_session.refresh(b)
    assert b.closed_on is None


def test_accept_records_a_compress(db_session):
    u = _user(db_session, "class-accept2@x.io")
    b = _compress(db_session, u)

    out = accept_cbti_evaluation(current_user=u, db=db_session)
    assert out.decision == "compress"
    assert out.sufficient is True
    assert _rx_count(db_session, b.id) == 2

    successor = (db_session.query(models.CBTIPrescription)
                 .filter_by(block_id=b.id)
                 .order_by(models.CBTIPrescription.id.desc()).first())
    assert successor.window_minutes == 375              # 390 - 15 (move capped)
    assert successor.decision == "compress"


def test_accept_records_a_converged_hold(db_session):
    """The carve-out, and the reason the rule is 'insufficiency is not acceptable' rather
    than the simpler 'a HOLD is not acceptable'. A converged HOLD moves no window, so it
    LOOKS like a no-op — but it is the block's record of having found its level, and the
    engine emits no other block-ending signal (#107). Refusing it would make the found
    level unrecordable.
    """
    u = _user(db_session, "class-accept3@x.io")
    b = _converged_hold(db_session, u)

    out = accept_cbti_evaluation(current_user=u, db=db_session)
    assert out.decision == "hold"
    assert out.sufficient is True
    assert "converged" in out.decision_reason
    assert _rx_count(db_session, b.id) == 2

    successor = (db_session.query(models.CBTIPrescription)
                 .filter_by(block_id=b.id)
                 .order_by(models.CBTIPrescription.id.desc()).first())
    assert successor.window_minutes == 390              # held, not moved
    assert successor.decision == "hold"


def test_the_new_gate_does_not_swallow_the_other_refusals(db_session):
    """The insufficiency 409 must be an ADDITIONAL gate, not a rewiring of the existing
    ones — all three are 409 and a careless implementation could collapse them into one
    message, which would make an operator's error report point at the wrong cause.

    Two distinct refusals are reachable here. (The third, the idempotency branch, is not
    reachable from this fixture and is not this module's to pin: a successor's own cycle
    begins today, so a second accept is refused by the ELIGIBILITY gate at 'day 0 of 4'
    long before the superseded-row check. `test_cbti_eval_trigger` covers double-accept
    from the ledger side.)
    """
    u = _user(db_session, "class-accept4@x.io")
    b = _compress(db_session, u)
    accept_cbti_evaluation(current_user=u, db=db_session)

    # a recorded decision, re-accepted: refused for a reason that is NOT the nights one
    with pytest.raises(HTTPException) as e:
        accept_cbti_evaluation(current_user=u, db=db_session)
    assert e.value.status_code == 409
    assert "Not enough logged nights" not in e.value.detail
    assert _rx_count(db_session, b.id) == 2

    # no open block at all: still its own message
    u2 = _user(db_session, "class-accept5@x.io")
    with pytest.raises(HTTPException) as e:
        accept_cbti_evaluation(current_user=u2, db=db_session)
    assert e.value.status_code == 409
    assert "Not enough logged nights" not in e.value.detail
