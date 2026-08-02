"""CBT-I PM evaluation trigger — #118's owed half, reusing #128's ledger read.

The trigger offers the engine's cycle decision at PM close-out and mints the successor
prescription only on a witnessed accept. What carries risk here is not the arithmetic
(the engine and the replay already have suites) but the three seams this build adds:

  * the ELIGIBILITY UNIT. #118 says ">=7 days have elapsed"; the commissioning brief
    said ">=7 nights". Those differ the moment a night goes unlogged, and gating on
    logged nights strands the operator — cycle 1 can never reach 7 logged nights once
    one of its 7 calendar days is missing. Pinned below.
  * the APPEND-ONLY LEDGER. Accept may write exactly one new row and touch exactly two
    columns on the prior one. Everything else on that row is frozen at authorship.
  * REUSE of the effective-prescription read (#128), whose revisit clause names this
    build: adjudicate against the ledger's correction, never the block-open seed.

SYNTHETIC data only; no real rows (both repos are public).
"""
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

import models
from routers.checkin_v2 import accept_cbti_evaluation, get_cbti_evaluation


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
    b = _block(db_session, u.id, opened=date.today() - timedelta(days=3))
    _rx(db_session, b.id, eff=date.today() - timedelta(days=3))
    _nights(db_session, u.id, date.today() - timedelta(days=3), 3)

    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.block_open is True
    assert out.eligible is False
    assert out.reason.startswith("cycle_in_progress")
    assert out.days_since_effective_from == 3


def test_offer_at_seven_days_carries_decision_and_basis(db_session):
    u = _user(db_session)
    start = date.today() - timedelta(days=7)
    b = _block(db_session, u.id, opened=start)
    _rx(db_session, b.id, eff=start, win=390)
    _nights(db_session, u.id, start, 7, tst=420)

    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.eligible is True
    assert out.acceptable is True
    # TST 420 + 30 buffer = 450 target against a 390 window: a +60 move, capped to +30.
    assert out.decision == "extend"
    assert out.basis.window_minutes_current == 390
    assert out.basis.window_minutes_proposed == 420
    assert out.basis.move_capped is True
    assert out.basis.nights_counted == 7


def test_eligibility_is_calendar_days_not_logged_nights(db_session):
    """The regression the brief's ">=7 nights" spec would have introduced.

    Seven calendar days have elapsed but only six were logged. The offer must still be
    made — the engine's own sufficiency gate (>= 5 valid) decides whether the nights
    support a decision, and here they do. Gating the OFFER on logged nights would leave
    this operator with no evaluation at all, and no way to reach one: cycle 1's span is
    behind them, so its logged count can never rise to 7.
    """
    u = _user(db_session)
    start = date.today() - timedelta(days=7)
    b = _block(db_session, u.id, opened=start)
    _rx(db_session, b.id, eff=start)
    _nights(db_session, u.id, start, 7, skip=(2,))

    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.days_since_effective_from == 7
    assert out.nights_since_effective_from == 6      # the gap is visible...
    assert out.eligible is True                      # ...and does not withhold the offer
    assert out.basis.nights_counted == 6


def test_insufficient_nights_holds_rather_than_withholding_the_offer(db_session):
    u = _user(db_session)
    start = date.today() - timedelta(days=7)
    b = _block(db_session, u.id, opened=start)
    _rx(db_session, b.id, eff=start)
    _nights(db_session, u.id, start, 7, skip=(1, 2, 3, 4))   # 3 logged, need 5

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
    seed_from = date.today() - timedelta(days=10)
    corr_from = date.today() - timedelta(days=7)
    b = _block(db_session, u.id, opened=seed_from)
    _rx(db_session, b.id, eff=seed_from, to=corr_from - timedelta(days=1), lo="23:45", win=360)
    _rx(db_session, b.id, eff=corr_from, lo="22:30", win=390, decision="extend")

    _nights(db_session, u.id, seed_from, 3, lo="23:45", tst=349, se=88.0)
    _nights(db_session, u.id, corr_from, 7, lo="22:30", tst=420, se=90.0)

    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.eligible is True
    assert out.basis.lights_out_current == "22:30"      # the correction, not "23:45"
    assert out.basis.window_minutes_current == 390      # not the seed's 360
    assert out.decision == "extend"                     # not a false adherence HOLD


def test_excluded_nights_are_surfaced_not_just_counted(db_session):
    """Q45 stays open, so the operator must be able to see WHICH nights the decision
    dropped and why — a count alone hides that some exclusions rest on the unverified
    date-1 nap attribution."""
    u = _user(db_session)
    start = date.today() - timedelta(days=7)
    b = _block(db_session, u.id, opened=start)
    _rx(db_session, b.id, eff=start)
    _nights(db_session, u.id, start, 7)
    drunk = db_session.query(models.DailyRecord).filter_by(
        user_id=u.id, date=start + timedelta(days=1)).one()
    drunk.alcohol_units = 5
    db_session.commit()

    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.basis.nights_excluded                       # a dict, date -> reason
    assert (start + timedelta(days=1)).isoformat() in out.basis.nights_excluded


# ── accept: the witnessed act ────────────────────────────────────────────────

def _eligible_block(db, u):
    start = date.today() - timedelta(days=7)
    b = _block(db, u.id, opened=start)
    prior = _rx(db, b.id, eff=start, win=390)
    _nights(db, u.id, start, 7, tst=420)
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
    assert successor.effective_from == date.today()
    assert successor.window_minutes == 420
    assert successor.wake_anchor == prior.wake_anchor
    assert successor.basis_nights_n == 7
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
    b = _block(db_session, u.id, opened=date.today() - timedelta(days=2))
    _rx(db_session, b.id, eff=date.today() - timedelta(days=2))
    _nights(db_session, u.id, date.today() - timedelta(days=2), 2)

    with pytest.raises(HTTPException) as e:
        accept_cbti_evaluation(current_user=u, db=db_session)
    assert e.value.status_code == 409
    assert db_session.query(models.CBTIPrescription).filter_by(block_id=b.id).count() == 1


def test_close_recommendation_is_surfaced_but_not_acceptable(db_session):
    """Block close is engine-driven (#118) and has no built path. The trigger must show
    the recommendation and refuse to mint, rather than half-applying it by writing a
    terminal-looking prescription while leaving the block open."""
    u = _user(db_session)
    start = date.today() - timedelta(days=21)
    b = _block(db_session, u.id, opened=start)
    # two completed cycles under a superseded prescription build the plateau history
    corr = start + timedelta(days=14)
    _rx(db_session, b.id, eff=start, to=corr - timedelta(days=1), win=450)
    _rx(db_session, b.id, eff=corr, win=450, decision="hold")
    _nights(db_session, u.id, start, 21, tst=420, se=90.0)

    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.decision == "close"
    assert out.eligible is True
    assert out.acceptable is False            # surfaced, but no control offered

    with pytest.raises(HTTPException) as e:
        accept_cbti_evaluation(current_user=u, db=db_session)
    assert e.value.status_code == 409
    assert db_session.query(models.CBTIPrescription).filter_by(block_id=b.id).count() == 2


def test_no_open_block_reports_closed_and_offers_nothing(db_session):
    u = _user(db_session)
    out = get_cbti_evaluation(current_user=u, db=db_session)
    assert out.block_open is False and out.eligible is False
