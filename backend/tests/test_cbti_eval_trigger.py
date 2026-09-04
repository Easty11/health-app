"""CBT-I PM evaluation trigger — #118's owed half, reworked onto the 4-night engine.

The trigger offers the engine's cycle decision at PM close-out and mints the successor
prescription only on a witnessed accept. What carries risk here is not the arithmetic
(the engine and the replay already have suites) but the three seams this build adds:

  * the ELIGIBILITY UNIT. #118 makes the offer once a full cycle has elapsed; the
    commissioning brief said ">= N nights". Those differ the moment a night goes
    unlogged, and gating on logged nights strands the operator — a cycle can never reach
    CYCLE_NIGHTS logged nights once one of its calendar days is missing. Pinned below.
  * the APPEND-ONLY LEDGER. Accept may write exactly one new row and touch exactly two
    columns on the prior one. Everything else on that row is frozen at authorship.
  * REUSE of the effective-prescription read (#128), whose revisit clause names this
    build: adjudicate against the ledger's correction, never the block-open seed.

All numbers here are computed from the 4-night engine (CYCLE_NIGHTS=4, MIN_VALID_NIGHTS=3,
MAX_MOVE_MIN=15, BUFFER_MIN=30): a default night tst=420 against a 390 window targets
420+30=450, a +60 move capped to +15 -> a 405 proposed window. The selected cycle is the
LAST complete 4-night span of the live prescription.

SYNTHETIC data only; no real rows (both repos are public).
"""
from datetime import timedelta

import pytest
from fastapi import HTTPException

import models
from routers.checkin_v2 import (
    _today_aest,
    accept_cbti_evaluation,
    get_cbti_evaluation,
)


def _user(db, email="trig@x.io"):
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
    """Diary nights. `skip` drops calendar days so a gap can be exercised."""
    for i in range(n):
        d = start + timedelta(days=i)
        if i in skip:
            continue
        db.add(models.DailyRecord(
            user_id=uid, date=d, diary_tst_min=tst, diary_se_pct=se,
            lights_out=lo, out_of_bed=wake, final_wake=wake, naps_min=0,
            alcohol_units=0,
        ))
    db.commit()


# ── eligibility ──────────────────────────────────────────────────────────────

def test_no_offer_before_the_cycle_has_elapsed(db_session):
    u = _user(db_session)
    b = _block(db_session, u.id, opened=_today_aest() - timedelta(days=3))
    _rx(db_session, b.id, eff=_today_aest() - timedelta(days=3))
    _nights(db_session, u.id, _today_aest() - timedelta(days=3), 3)

    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.block_open is True
    assert out.eligible is False                     # day 3 of 4 — not a full cycle yet
    assert out.reason.startswith("cycle_in_progress")
    assert out.days_since_effective_from == 3


def test_offer_once_a_full_cycle_has_elapsed_carries_decision_and_basis(db_session):
    u = _user(db_session)
    start = _today_aest() - timedelta(days=4)
    b = _block(db_session, u.id, opened=start)
    _rx(db_session, b.id, eff=start, win=390)
    _nights(db_session, u.id, start, 4, tst=420)

    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.eligible is True
    # TST 420 + 30 buffer = 450 target against a 390 window: a +60 move, capped to +15.
    assert out.decision == "extend"
    assert out.basis.window_minutes_current == 390
    assert out.basis.window_minutes_proposed == 405
    assert out.basis.move_capped is True
    assert out.basis.nights_counted == 4


def test_eligibility_is_calendar_days_not_logged_nights(db_session):
    """The regression the brief's ">= N nights" spec would have introduced.

    Four calendar days have elapsed but only three were logged. The offer must still be
    made — the engine's own sufficiency gate (>= 3 valid) decides whether the nights
    support a decision, and here they do. Gating the OFFER on logged nights would leave
    this operator with no evaluation at all, and no way to reach one: the cycle's span is
    behind them, so its logged count can never rise to 4.
    """
    u = _user(db_session)
    start = _today_aest() - timedelta(days=4)
    b = _block(db_session, u.id, opened=start)
    _rx(db_session, b.id, eff=start)
    _nights(db_session, u.id, start, 4, skip=(1,))

    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.days_since_effective_from == 4
    assert out.nights_since_effective_from == 3      # the gap is visible...
    assert out.eligible is True                      # ...and does not withhold the offer
    assert out.basis.nights_counted == 3


def test_insufficient_nights_holds_rather_than_withholding_the_offer(db_session):
    u = _user(db_session)
    start = _today_aest() - timedelta(days=4)
    b = _block(db_session, u.id, opened=start)
    _rx(db_session, b.id, eff=start)
    _nights(db_session, u.id, start, 4, skip=(1, 2))   # 2 logged, need 3

    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.eligible is True
    assert out.decision == "hold"
    assert "insufficient_nights" in out.decision_reason


# ── #128 reuse: adjudicate against the ledger, not the seed ──────────────────

def test_adjudicates_against_the_effective_prescription_not_the_seed(db_session):
    """A mid-block operator correction supersedes the opening prescription. The nights
    run under the correction adhere to IT; adjudicating them against the superseded
    lights-out would read them as adherence failures — the false GATE-2 HOLD Q49 names.
    """
    u = _user(db_session)
    seed_from = _today_aest() - timedelta(days=8)
    corr_from = _today_aest() - timedelta(days=4)
    b = _block(db_session, u.id, opened=seed_from)
    _rx(db_session, b.id, eff=seed_from, to=corr_from - timedelta(days=1), lo="23:45", win=360)
    _rx(db_session, b.id, eff=corr_from, lo="22:30", win=390, decision="extend")

    _nights(db_session, u.id, seed_from, 4, lo="23:45", tst=349, se=88.0)
    _nights(db_session, u.id, corr_from, 4, lo="22:30", tst=420, se=90.0)

    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.eligible is True
    assert out.basis.lights_out_current == "22:30"      # the correction, not "23:45"
    assert out.basis.window_minutes_current == 390      # not the seed's 360
    assert out.decision == "extend"                     # not a false adherence HOLD


def test_excluded_nights_are_surfaced_and_attributed_to_the_following_night(db_session):
    """The operator must see WHICH nights the decision dropped and why — a count alone
    hides which night the basis actually rests on. This pins offer/guard parity (G2): the
    night the offer surfaces as excluded is EXACTLY the night the engine's GATE-1 nap
    guard removed from the 4-night window, so the two can never diverge on the cadence
    that made it matter.

    It also pins the Q45 -> #219 attribution end-to-end, through the real router rather
    than through `load_nights` alone: a nap recorded on day D excludes the night ending
    the NEXT morning, D+1, not the night that had already ended on the morning of D.
    """
    u = _user(db_session)
    start = _today_aest() - timedelta(days=4)
    b = _block(db_session, u.id, opened=start)
    _rx(db_session, b.id, eff=start)
    _nights(db_session, u.id, start, 4)
    # A >30-min nap recorded on day start+1. It attributes forward to Night(start+2),
    # inside the selected 4-night cycle, leaving 3 valid — still >= MIN_VALID_NIGHTS, so
    # a decision is reached and the exclusion is visible on a real decision rather than
    # only on an insufficiency finding.
    napped = db_session.query(models.DailyRecord).filter_by(
        user_id=u.id, date=start + timedelta(days=1)).one()
    napped.naps_min = 45
    db_session.commit()

    out = get_cbti_evaluation(current_user=u, db=db_session)
    excluded_key = (start + timedelta(days=2)).isoformat()   # the night the nap PRECEDED
    nap_day_key = (start + timedelta(days=1)).isoformat()    # the nap's own row-date
    assert out.basis.nights_excluded                              # a dict, date -> reason
    assert out.basis.nights_excluded.get(excluded_key) == "nap"   # the guard's night, surfaced
    assert nap_day_key not in out.basis.nights_excluded           # and NOT the nap's own night
    assert out.basis.nights_counted == 3                          # one night off the basis


# ── accept: the witnessed act ────────────────────────────────────────────────

def _eligible_block(db, u):
    start = _today_aest() - timedelta(days=4)
    b = _block(db, u.id, opened=start)
    prior = _rx(db, b.id, eff=start, win=390)
    _nights(db, u.id, start, 4, tst=420)
    return b, prior


def test_accept_appends_one_row_and_moves_only_the_two_permitted_columns(db_session):
    u = _user(db_session)
    b, prior = _eligible_block(db_session, u)
    before = {c.name: getattr(prior, c.name)
              for c in models.CBTIPrescription.__table__.columns}

    out = accept_cbti_evaluation(current_user=u, db=db_session)
    assert out.decision == "extend"

    rows = (db_session.query(models.CBTIPrescription)
            .filter_by(block_id=b.id).order_by(models.CBTIPrescription.id).all())
    assert len(rows) == 2                                  # exactly one appended

    db_session.refresh(prior)
    after = {c.name: getattr(prior, c.name)
             for c in models.CBTIPrescription.__table__.columns}
    moved = {k for k in before if before[k] != after[k]}
    assert moved == {"effective_to", "superseded_by"}
    assert prior.superseded_by == rows[1].id

    successor = rows[1]
    assert successor.effective_from == _today_aest()
    assert successor.window_minutes == 405
    assert successor.wake_anchor == prior.wake_anchor
    assert successor.basis_nights_n == 4
    # the block itself is untouched — close stays engine-driven (#118)
    db_session.refresh(b)
    assert b.closed_on is None


def test_double_accept_does_not_mint_a_second_successor(db_session):
    u = _user(db_session)
    b, _ = _eligible_block(db_session, u)
    accept_cbti_evaluation(current_user=u, db=db_session)

    with pytest.raises(HTTPException) as e:
        accept_cbti_evaluation(current_user=u, db=db_session)
    assert e.value.status_code == 409
    assert db_session.query(models.CBTIPrescription).filter_by(block_id=b.id).count() == 2


def test_accept_refused_before_the_cycle_elapses(db_session):
    u = _user(db_session)
    b = _block(db_session, u.id, opened=_today_aest() - timedelta(days=2))
    _rx(db_session, b.id, eff=_today_aest() - timedelta(days=2))
    _nights(db_session, u.id, _today_aest() - timedelta(days=2), 2)

    with pytest.raises(HTTPException) as e:
        accept_cbti_evaluation(current_user=u, db=db_session)
    assert e.value.status_code == 409
    assert db_session.query(models.CBTIPrescription).filter_by(block_id=b.id).count() == 1


def test_no_open_block_reports_closed_and_offers_nothing(db_session):
    u = _user(db_session)
    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.block_open is False and out.eligible is False
