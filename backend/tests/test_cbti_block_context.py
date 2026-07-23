"""Step 2 — CBT-I block status on /prefill and /today.

Backend-side only: `frontend/package.json` has scripts dev/build/lint/preview and
no `test`, so there is no runner to assert the components in. Standing up one
inside a feature brief would smuggle a second concern into the first.

The two properties that carry risk are shape properties, not value ones:
  * /today must ALWAYS return an object — PM has to show the prescribed
    lights-out on a day with no AM check-in, and null cannot carry it.
  * the record fields must stay FLAT — `NightlyCloseOut.jsx` reads
    `data?.pm_timestamp`, so nesting under a `record` key would break it silently.
"""
from datetime import date, timedelta

import models
from routers.checkin_v2 import CBTIContextOut, TodayOut, _cbti_context


def _user(db, email="ctx@x.io"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _block(db, uid, *, opened, closed=None, anchor="05:00"):
    b = models.CBTIBlock(user_id=uid, opened_on=opened, closed_on=closed,
                         wake_anchor=anchor, open_reason="test")
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def _rx(db, bid, *, eff, lo, win, decision="adopt"):
    r = models.CBTIPrescription(
        block_id=bid, effective_from=eff, prescribed_lights_out=lo,
        wake_anchor="05:00", window_minutes=win, decision=decision,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


# ── no block ─────────────────────────────────────────────────────────────────

def test_no_block_reports_closed_and_carries_no_prescription(db_session):
    u = _user(db_session)
    ctx = _cbti_context(u.id, date(2026, 7, 23), db_session)
    assert ctx.block_open is False
    assert ctx.block_id is None and ctx.prescribed_lights_out is None


def test_a_CLOSED_block_does_not_count_as_open(db_session):
    """Closure is `closed_on IS NOT NULL`; the ledger persists after close (#108),
    so a closed block must not keep the diary fields rendering."""
    u = _user(db_session, "closed@x.io")
    b = _block(db_session, u.id, opened=date(2026, 3, 19), closed=date(2026, 5, 11))
    _rx(db_session, b.id, eff=date(2026, 3, 19), lo="22:36", win=384)
    ctx = _cbti_context(u.id, date(2026, 7, 23), db_session)
    assert ctx.block_open is False


# ── open block ───────────────────────────────────────────────────────────────

def test_open_block_reports_the_prescription_in_force(db_session):
    u = _user(db_session, "open@x.io")
    b = _block(db_session, u.id, opened=date(2026, 7, 1))
    _rx(db_session, b.id, eff=date(2026, 7, 1), lo="22:30", win=390)
    ctx = _cbti_context(u.id, date(2026, 7, 5), db_session)
    assert ctx.block_open is True and ctx.block_id == b.id
    assert ctx.prescribed_lights_out == "22:30"
    assert ctx.window_minutes == 390 and ctx.wake_anchor == "05:00"


def test_the_LATEST_effective_prescription_wins_not_the_first(db_session):
    """Supersession is recorded, not deleted — 'in force' is a query over an
    append-only ledger, so a later effective_from must shadow an earlier one."""
    u = _user(db_session, "latest@x.io")
    b = _block(db_session, u.id, opened=date(2026, 7, 1))
    _rx(db_session, b.id, eff=date(2026, 7, 1), lo="22:30", win=390)
    _rx(db_session, b.id, eff=date(2026, 7, 8), lo="22:10", win=410, decision="extend")
    ctx = _cbti_context(u.id, date(2026, 7, 12), db_session)
    assert ctx.prescribed_lights_out == "22:10" and ctx.window_minutes == 410


def test_a_future_prescription_is_not_yet_in_force(db_session):
    u = _user(db_session, "future@x.io")
    b = _block(db_session, u.id, opened=date(2026, 7, 1))
    _rx(db_session, b.id, eff=date(2026, 7, 1), lo="22:30", win=390)
    _rx(db_session, b.id, eff=date(2026, 7, 20), lo="22:10", win=410, decision="extend")
    ctx = _cbti_context(u.id, date(2026, 7, 10), db_session)
    assert ctx.prescribed_lights_out == "22:30"


def test_an_open_block_with_no_prescription_yet_is_still_open(db_session):
    """block_open drives render; a missing prescription must not collapse it to
    closed, or the diary would silently stop appearing."""
    u = _user(db_session, "norx@x.io")
    _block(db_session, u.id, opened=date(2026, 7, 1))
    ctx = _cbti_context(u.id, date(2026, 7, 5), db_session)
    assert ctx.block_open is True and ctx.prescribed_lights_out is None


def test_another_users_open_block_is_not_visible(db_session):
    a = _user(db_session, "a@x.io")
    b_user = _user(db_session, "b@x.io")
    _block(db_session, b_user.id, opened=date(2026, 7, 1))
    assert _cbti_context(a.id, date(2026, 7, 5), db_session).block_open is False


# ── response shape: the two properties that carry risk ───────────────────────

def test_TodayOut_defaults_to_an_object_never_null():
    """PM must display the prescription on a day with no AM record. The endpoint
    previously returned Optional[DailyRecordOut] — null cannot carry context."""
    out = TodayOut()
    assert out.id is None and out.date is None
    assert isinstance(out.cbti, CBTIContextOut) and out.cbti.block_open is False


def test_record_fields_stay_FLAT_not_nested():
    """NightlyCloseOut.jsx reads data?.pm_timestamp / data?.today_rating /
    data?.session_quality / data?.session_rpe directly off the response. Nesting
    them under a `record` key would break those reads silently — no frontend test
    would catch it, because there is no frontend test runner."""
    for f in ("pm_timestamp", "today_rating", "session_quality", "session_rpe"):
        assert f in TodayOut.model_fields, f"{f} must remain a top-level key"
    assert "record" not in TodayOut.model_fields


def test_TodayOut_populates_flat_fields_from_a_record(db_session):
    u = _user(db_session, "flat@x.io")
    rec = models.DailyRecord(user_id=u.id, date=date(2026, 7, 23), today_rating=4)
    db_session.add(rec)
    db_session.commit()
    db_session.refresh(rec)
    out = TodayOut.model_validate(rec)
    assert out.today_rating == 4 and out.date == date(2026, 7, 23)
    assert out.cbti.block_open is False        # default until populated by the route


# ── isolation: this is a read-only projection ────────────────────────────────

def test_context_lookup_writes_nothing(db_session):
    u = _user(db_session, "ro@x.io")
    b = _block(db_session, u.id, opened=date(2026, 7, 1))
    _rx(db_session, b.id, eff=date(2026, 7, 1), lo="22:30", win=390)
    before_b = db_session.query(models.CBTIBlock).count()
    before_r = db_session.query(models.CBTIPrescription).count()
    for d in range(1, 15):
        _cbti_context(u.id, date(2026, 7, 1) + timedelta(days=d), db_session)
    assert db_session.query(models.CBTIBlock).count() == before_b
    assert db_session.query(models.CBTIPrescription).count() == before_r
