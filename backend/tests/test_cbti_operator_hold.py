"""The operator's refusal path: POST /checkin-v2/cbti/evaluation/hold (R2, #446; extends #118).

The operator may REFUSE a move, never AUTHOR a window. A refused cycle mints a `hold` row at
the live prescription's UNCHANGED window, with the operator's reason and the engine's rejected
decision in the same `rationale` string. No new column, no migration.

These go over HTTP (a TestClient on the real router) because two of the contracts are
framework-level: a blank reason is a 422, and a body field the route does not declare is ignored
rather than honoured. The write side is asserted on the ledger rows, not on the response.

SYNTHETIC data only; no real rows (both repos are public).
"""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

import models
from auth import get_current_user
from cbti.engine import CYCLE_NIGHTS, RULESET_VERSION
from database import get_db
from routers import checkin_v2
from routers.checkin_v2 import _today_aest

BASE = "/checkin-v2/cbti/evaluation"


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(checkin_v2.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _user(db, email="hold@x.io"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _block(db, uid, *, opened):
    b = models.CBTIBlock(user_id=uid, opened_on=opened, closed_on=None,
                         wake_anchor="05:00", open_reason="test")
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def _rx(db, bid, *, eff, win=390, lo="22:30"):
    r = models.CBTIPrescription(
        block_id=bid, effective_from=eff, effective_to=None, prescribed_lights_out=lo,
        wake_anchor="05:00", window_minutes=win, decision="adopt",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _nights(db, uid, start, n, *, tst=420, se=92.0, skip=()):
    for i in range(n):
        if i in skip:
            continue
        db.add(models.DailyRecord(
            user_id=uid, date=start + timedelta(days=i), diary_tst_min=tst,
            diary_se_pct=se, lights_out="22:30", out_of_bed=None, final_wake="05:00",
            naps_min=0, alcohol_units=0,
        ))
    db.commit()


def _extend_offer(db, u, *, win=390):
    """A full cycle at mean SE 92 against `win`: the engine offers an extend of one step."""
    start = _today_aest() - timedelta(days=CYCLE_NIGHTS)
    b = _block(db, u.id, opened=start)
    rx = _rx(db, b.id, eff=start, win=win)
    _nights(db, u.id, start, CYCLE_NIGHTS)
    return b, rx


def _rows(db, block_id):
    return (db.query(models.CBTIPrescription).filter_by(block_id=block_id)
            .order_by(models.CBTIPrescription.id).all())


# ── the route exists, and the reason is mandatory ────────────────────────────

@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}, {"reason": "\n\t "}])
def test_a_blank_or_missing_reason_is_422_and_writes_nothing(db_session, body):
    u = _user(db_session)
    b, _ = _extend_offer(db_session, u)
    r = _client(db_session, u).post(f"{BASE}/hold", json=body)
    assert r.status_code == 422
    assert len(_rows(db_session, b.id)) == 1


# ── same gates as accept ─────────────────────────────────────────────────────

def test_an_insufficient_cycle_is_409_and_writes_nothing(db_session):
    """Only 2 of 4 nights logged: the engine reached no decision, so there is nothing to
    refuse either. Refused server-side, exactly as accept refuses it (#218)."""
    u = _user(db_session)
    start = _today_aest() - timedelta(days=CYCLE_NIGHTS)
    b = _block(db_session, u.id, opened=start)
    _rx(db_session, b.id, eff=start)
    _nights(db_session, u.id, start, CYCLE_NIGHTS, skip=(1, 2))

    r = _client(db_session, u).post(f"{BASE}/hold", json={"reason": "too tired"})
    assert r.status_code == 409
    assert "Not enough logged nights" in r.json()["detail"]
    rows = _rows(db_session, b.id)
    assert len(rows) == 1 and rows[0].effective_to is None


def test_a_cycle_still_in_progress_is_409(db_session):
    u = _user(db_session)
    start = _today_aest() - timedelta(days=2)
    b = _block(db_session, u.id, opened=start)
    _rx(db_session, b.id, eff=start)
    _nights(db_session, u.id, start, 2)
    r = _client(db_session, u).post(f"{BASE}/hold", json={"reason": "x"})
    assert r.status_code == 409 and "cycle_in_progress" in r.json()["detail"]
    assert len(_rows(db_session, b.id)) == 1


def test_no_open_block_is_409(db_session):
    u = _user(db_session)
    r = _client(db_session, u).post(f"{BASE}/hold", json={"reason": "x"})
    assert r.status_code == 409


def test_a_second_hold_is_409_and_so_is_an_accept_after_it(db_session):
    u = _user(db_session)
    b, _ = _extend_offer(db_session, u)
    c = _client(db_session, u)
    assert c.post(f"{BASE}/hold", json={"reason": "first"}).status_code == 200
    assert c.post(f"{BASE}/hold", json={"reason": "second"}).status_code == 409
    assert c.post(f"{BASE}/accept").status_code == 409
    assert len(_rows(db_session, b.id)) == 2


# ── the row ──────────────────────────────────────────────────────────────────

def test_the_hold_row_keeps_the_window_and_carries_both_the_operator_text_and_the_engines_offer(db_session):
    u = _user(db_session)
    b, rx = _extend_offer(db_session, u)

    r = _client(db_session, u).post(f"{BASE}/hold", json={"reason": "  ill this week  "})
    assert r.status_code == 200

    prior, hold = _rows(db_session, b.id)
    # the window and the lights-out are the live prescription's own — never the engine's proposal
    assert hold.decision == "hold"
    assert hold.window_minutes == 390 and hold.prescribed_lights_out == "22:30"
    assert hold.wake_anchor == "05:00"
    # the operator's text (stripped) and the engine's rejected decision, in one string
    assert hold.rationale == ("operator_declined: ill this week | engine offered: extend — "
                              "extended 390->405min (mean SE 92.0 >= 90)")
    # basis and ledger snapshot exactly as accept writes them
    assert hold.basis_se_pct == 92.0 and hold.basis_tst_min == 420
    assert hold.basis_nights_n == CYCLE_NIGHTS
    assert len(hold.basis_ledger) == CYCLE_NIGHTS
    assert hold.ruleset_version == RULESET_VERSION
    # the response states the window actually written, not the rejected proposal
    out = r.json()
    assert out["decision"] == "hold" and out["reason"] == "held_by_operator"
    assert out["basis"]["window_minutes_proposed"] == 390
    assert out["basis"]["lights_out_proposed"] == "22:30"
    assert out["decision_reason"] == hold.rationale


def test_the_operator_cannot_author_a_window_through_the_body(db_session):
    """The body declares only `reason`. A posted window or lights-out is ignored, so no
    request can mint a prescription the engine and the live row did not already carry."""
    u = _user(db_session)
    b, _ = _extend_offer(db_session, u)
    r = _client(db_session, u).post(
        f"{BASE}/hold",
        json={"reason": "x", "window_minutes": 600, "prescribed_lights_out": "20:00",
              "decision": "extend"},
    )
    assert r.status_code == 200
    hold = _rows(db_session, b.id)[-1]
    assert hold.window_minutes == 390 and hold.prescribed_lights_out == "22:30"
    assert hold.decision == "hold"


def test_the_hold_supersedes_the_prior_and_resets_the_cycle_clock(db_session):
    u = _user(db_session)
    b, _ = _extend_offer(db_session, u)
    c = _client(db_session, u)

    before = c.get(f"{BASE}").json()
    assert before["eligible"] is True and before["days_since_effective_from"] == CYCLE_NIGHTS

    assert c.post(f"{BASE}/hold", json={"reason": "x"}).status_code == 200

    prior, hold = _rows(db_session, b.id)
    assert prior.superseded_by == hold.id
    assert prior.effective_to == _today_aest() - timedelta(days=1)
    assert hold.effective_from == _today_aest() and hold.effective_to is None

    after = c.get(f"{BASE}").json()
    assert after["eligible"] is False
    assert after["days_since_effective_from"] == 0


def test_the_block_is_not_closed_by_a_hold(db_session):
    u = _user(db_session)
    b, _ = _extend_offer(db_session, u)
    _client(db_session, u).post(f"{BASE}/hold", json={"reason": "x"})
    db_session.refresh(b)
    assert b.closed_on is None


def test_accept_still_writes_no_rationale_and_takes_no_body(db_session):
    """The factored mint must leave accept exactly as it was: the engine's own decision,
    the engine's window, and no operator text."""
    u = _user(db_session)
    b, _ = _extend_offer(db_session, u)
    r = _client(db_session, u).post(f"{BASE}/accept")
    assert r.status_code == 200 and r.json()["decision"] == "extend"
    _, acc = _rows(db_session, b.id)
    assert acc.window_minutes == 405 and acc.rationale is None
