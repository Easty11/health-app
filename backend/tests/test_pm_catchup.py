"""Missed-PM catch-up - `POST /checkin-v2/pm` with `for_date`, `/prefill.missed_pm`, `pm_late`.

A missed nightly close-out can be completed the next morning and must land on the PREVIOUS
day's daily_record. The failure this replaces is silent: the late close-out keyed to
`_today_aest()`, putting yesterday's values on today's row, attributing yesterday's nap to
tonight's night, and blocking tonight's real close-out. Each gate below is therefore written
against a specific wrong answer that would still look like a success.

Dates derive from `_today_aest()` (no literals), so nothing here goes stale with the clock.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
import routers.checkin_v2 as c2
from auth import get_current_user
from cbti.engine import NAP_EXCLUDE_MIN, classify_night
from cbti.replay import load_nights
from database import get_db
from routers.checkin_v2 import AMPrefillOut, DailyRecordOut, get_prefill

AEST = c2.AEST


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(c2.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _row(db, uid, d, **kw):
    r = models.DailyRecord(user_id=uid, date=d, **kw)
    db.add(r); db.commit()
    return r


def _get(db, uid, d):
    db.expire_all()
    return db.query(models.DailyRecord).filter_by(user_id=uid, date=d).first()


def _freeze(monkeypatch, *, today, now_utc):
    monkeypatch.setattr(c2, "_today_aest", lambda: today)
    monkeypatch.setattr(c2, "_now_utc", lambda: now_utc)


def _block(db, uid, *, opened_on, closed_on=None):
    b = models.CBTIBlock(user_id=uid, opened_on=opened_on, closed_on=closed_on,
                         wake_anchor="05:00", open_reason="test")
    db.add(b); db.commit(); db.refresh(b)
    db.add(models.CBTIPrescription(block_id=b.id, effective_from=opened_on,
                                   prescribed_lights_out="22:30", wake_anchor="05:00",
                                   window_minutes=390, decision="adopt"))
    db.commit()
    return b


PM = {"today_rating": 4, "trained_today": False, "naps_min": None, "pm_notes": None}


# ── for_date absent == today: the pre-change behaviour ───────────────────────────

def test_absent_for_date_writes_todays_row(db_session, monkeypatch):
    u = _user(db_session, "absent@x.io")
    today = c2._today_aest()
    yday = today - timedelta(days=1)
    now = datetime.now(timezone.utc)
    _freeze(monkeypatch, today=today, now_utc=now)
    r = _client(db_session, u).post("/checkin-v2/pm", json={**PM, "today_rating": 5, "naps_min": 20, "pm_notes": "n"})
    assert r.status_code == 200
    assert r.json()["date"] == today.isoformat()
    row = _get(db_session, u.id, today)
    assert (row.today_rating, row.naps_min, row.pm_notes) == (5, 20, "n")
    assert row.pm_timestamp is not None
    assert _get(db_session, u.id, yday) is None          # no row minted for yesterday


def test_for_date_equal_to_today_is_identical_to_absent(db_session, monkeypatch):
    """Same body modulo for_date -> same stored fields. The response differs only in
    its identity/timestamp, so compare every stored PM column."""
    ua, ub = _user(db_session, "a@x.io"), _user(db_session, "b@x.io")
    today = c2._today_aest()
    now = datetime.now(timezone.utc)
    _freeze(monkeypatch, today=today, now_utc=now)
    body = {**PM, "today_rating": 2, "trained_today": True, "session_quality": 4,
            "session_rpe": 6.5, "naps_min": 0, "pm_notes": "x"}
    _client(db_session, ua).post("/checkin-v2/pm", json=body)
    _client(db_session, ub).post("/checkin-v2/pm", json={**body, "for_date": today.isoformat()})
    cols = ("date", "today_rating", "session_quality", "session_rpe", "naps_min", "pm_notes")
    a, b = _get(db_session, ua.id, today), _get(db_session, ub.id, today)
    assert [getattr(a, c) for c in cols] == [getattr(b, c) for c in cols]
    assert a.pm_timestamp is not None and b.pm_timestamp is not None


def test_same_day_resubmit_still_overwrites(db_session, monkeypatch):
    """Guard: the same-day path is unchanged. Overwrite-on-resubmit is the existing
    behaviour (logged as an OPEN_QUESTION, not changed here)."""
    u = _user(db_session, "resubmit@x.io")
    today = c2._today_aest()
    _freeze(monkeypatch, today=today, now_utc=datetime.now(timezone.utc))
    cl = _client(db_session, u)
    assert cl.post("/checkin-v2/pm", json={**PM, "today_rating": 2}).status_code == 200
    assert cl.post("/checkin-v2/pm", json={**PM, "today_rating": 5}).status_code == 200
    assert _get(db_session, u.id, today).today_rating == 5


# ── for_date = yesterday ─────────────────────────────────────────────────────────

def test_yesterday_writes_yesterdays_row_and_leaves_today_untouched(db_session, monkeypatch):
    u = _user(db_session, "yday@x.io")
    today = c2._today_aest()
    yday = today - timedelta(days=1)
    _row(db_session, u.id, today, morning_readiness=4)       # today's AM is in; PM is null
    _freeze(monkeypatch, today=today, now_utc=datetime.now(timezone.utc))
    r = _client(db_session, u).post("/checkin-v2/pm", json={
        **PM, "today_rating": 2, "trained_today": True, "session_quality": 3,
        "session_rpe": 7.0, "naps_min": 45, "pm_notes": "missed it", "for_date": yday.isoformat()})
    assert r.status_code == 200
    assert r.json()["date"] == yday.isoformat()
    y, t = _get(db_session, u.id, yday), _get(db_session, u.id, today)
    assert (y.today_rating, y.session_quality, y.session_rpe, y.naps_min, y.pm_notes) == (2, 3, 7.0, 45, "missed it")
    assert y.pm_timestamp is not None
    # today's row: PM entirely untouched, AM entirely untouched
    assert t.pm_timestamp is None and t.today_rating is None and t.naps_min is None and t.pm_notes is None
    assert t.morning_readiness == 4


def test_yesterday_with_no_row_at_all_is_created(db_session, monkeypatch):
    """A missing AM yesterday is legitimate - the row is made on demand."""
    u = _user(db_session, "norow@x.io")
    today = c2._today_aest()
    yday = today - timedelta(days=1)
    _freeze(monkeypatch, today=today, now_utc=datetime.now(timezone.utc))
    r = _client(db_session, u).post("/checkin-v2/pm", json={**PM, "for_date": yday.isoformat()})
    assert r.status_code == 200
    y = _get(db_session, u.id, yday)
    assert y is not None and y.pm_timestamp is not None and y.am_timestamp is None


def test_catchup_keeps_the_real_submit_instant(db_session, monkeypatch):
    u = _user(db_session, "instant@x.io")
    today = c2._today_aest()
    yday = today - timedelta(days=1)
    now = datetime(2031, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    _freeze(monkeypatch, today=today, now_utc=now)
    _client(db_session, u).post("/checkin-v2/pm", json={**PM, "for_date": yday.isoformat()})
    ts = _get(db_session, u.id, yday).pm_timestamp
    assert ts.replace(tzinfo=timezone.utc) == now             # not rewritten to yesterday evening


def test_the_zero_vs_null_nap_contract_is_unchanged_on_catchup(db_session, monkeypatch):
    u0, un = _user(db_session, "z@x.io"), _user(db_session, "n@x.io")
    today = c2._today_aest()
    yday = today - timedelta(days=1)
    _freeze(monkeypatch, today=today, now_utc=datetime.now(timezone.utc))
    _client(db_session, u0).post("/checkin-v2/pm", json={**PM, "naps_min": 0, "for_date": yday.isoformat()})
    _client(db_session, un).post("/checkin-v2/pm", json={**PM, "naps_min": None, "for_date": yday.isoformat()})
    assert _get(db_session, u0.id, yday).naps_min == 0
    assert _get(db_session, un.id, yday).naps_min is None


# ── the attribution gate (and its mutation check) ────────────────────────────────

def test_a_caught_up_nap_is_attributed_to_tonights_night_and_excludes_it(db_session, monkeypatch):
    """The point of the whole feature. Yesterday's nap, caught up this morning, must reach
    Night(today) via the replay's W-1 read and fire NAP_EXCLUDE_MIN. Had it keyed to today's
    row it would attach to Night(tomorrow) and today's night would read clean.

    Mutation check: with `for_date` ignored (see the next test) this assertion fails."""
    u = _user(db_session, "attrib@x.io")
    today = c2._today_aest()
    yday = today - timedelta(days=1)
    # today's night exists as a diary night (tst present) and yesterday's PM is missing
    _row(db_session, u.id, today, diary_tst_min=380, diary_se_pct=90.0, lights_out="22:30",
         out_of_bed="05:00", final_wake="05:00", alcohol_units=0)
    _row(db_session, u.id, yday, diary_tst_min=380, diary_se_pct=90.0, lights_out="22:30",
         out_of_bed="05:00", final_wake="05:00", alcohol_units=0)
    _freeze(monkeypatch, today=today, now_utc=datetime.now(timezone.utc))
    r = _client(db_session, u).post("/checkin-v2/pm", json={
        **PM, "naps_min": NAP_EXCLUDE_MIN + 15, "for_date": yday.isoformat()})
    assert r.status_code == 200

    nights = {n.date: n for n in load_nights(db_session, u.id, yday, today)}
    assert nights[today].naps_min == NAP_EXCLUDE_MIN + 15
    v = classify_night(nights[today], "22:30")
    assert v.valid is False and v.reason == "nap"
    # and not the night the nap could not have affected
    assert nights[yday].naps_min is None


def test_without_for_date_the_same_late_nap_misses_tonights_night(db_session, monkeypatch):
    """The contrast that makes the test above discriminate: the SAME late submit with no
    `for_date` is the original bug - the nap lands on today's row, so it is attributed to
    Night(tomorrow) and tonight's night reads clean while yesterday's PM stays null.

    The brief's mutation check (ignore `for_date` in submit_pm -> the attribution test must
    fail) is run against the real source, not simulated here; see the PR notes."""
    u = _user(db_session, "contrast@x.io")
    today = c2._today_aest()
    yday = today - timedelta(days=1)
    for d in (yday, today):
        _row(db_session, u.id, d, diary_tst_min=380, diary_se_pct=90.0, lights_out="22:30",
             out_of_bed="05:00", final_wake="05:00", alcohol_units=0)
    _freeze(monkeypatch, today=today, now_utc=datetime.now(timezone.utc))
    _client(db_session, u).post("/checkin-v2/pm", json={**PM, "naps_min": NAP_EXCLUDE_MIN + 15})

    nights = {n.date: n for n in load_nights(db_session, u.id, yday, today + timedelta(days=1))}
    assert nights[today].naps_min is None                  # tonight's night: nap unknown
    assert classify_night(nights[today], "22:30").valid is True
    assert _get(db_session, u.id, yday).pm_timestamp is None
    assert _get(db_session, u.id, today).naps_min == NAP_EXCLUDE_MIN + 15


# ── refusals ─────────────────────────────────────────────────────────────────────

def test_409_when_yesterday_already_has_a_pm_and_nothing_is_overwritten(db_session, monkeypatch):
    u = _user(db_session, "conflict@x.io")
    today = c2._today_aest()
    yday = today - timedelta(days=1)
    first = datetime(2030, 5, 5, 12, 0, tzinfo=timezone.utc)
    _row(db_session, u.id, yday, pm_timestamp=first, today_rating=3, naps_min=0, pm_notes="orig")
    _freeze(monkeypatch, today=today, now_utc=datetime.now(timezone.utc))
    r = _client(db_session, u).post("/checkin-v2/pm", json={
        **PM, "today_rating": 1, "naps_min": 99, "pm_notes": "clobber", "for_date": yday.isoformat()})
    assert r.status_code == 409
    assert "already" in r.json()["detail"].lower()
    y = _get(db_session, u.id, yday)
    assert (y.today_rating, y.naps_min, y.pm_notes) == (3, 0, "orig")
    assert y.pm_timestamp.replace(tzinfo=timezone.utc) == first
    assert _get(db_session, u.id, today) is None          # a refusal mints no row


@pytest.mark.parametrize("offset", [-2, -3, -30, 1, 2])
def test_422_outside_the_window(db_session, monkeypatch, offset):
    """today-2 and earlier (no general backfill) and any future day."""
    u = _user(db_session, f"win{offset}@x.io")
    today = c2._today_aest()
    _freeze(monkeypatch, today=today, now_utc=datetime.now(timezone.utc))
    target = today + timedelta(days=offset)
    r = _client(db_session, u).post("/checkin-v2/pm", json={**PM, "for_date": target.isoformat()})
    assert r.status_code == 422
    assert db_session.query(models.DailyRecord).filter_by(user_id=u.id).count() == 0


def test_the_window_follows_the_aest_clock_not_utc(db_session, monkeypatch):
    """'today' is _today_aest(): pinned to a day that differs from the UTC date."""
    u = _user(db_session, "clock@x.io")
    aest_today = date(2031, 6, 15)
    # 00:30 AEST on the 15th is still the 14th in UTC
    now = datetime(2031, 6, 14, 14, 30, tzinfo=timezone.utc)
    assert now.astimezone(AEST).date() == aest_today and now.date() != aest_today
    _freeze(monkeypatch, today=aest_today, now_utc=now)
    cl = _client(db_session, u)
    assert cl.post("/checkin-v2/pm", json={**PM, "for_date": (aest_today - timedelta(days=1)).isoformat()}).status_code == 200
    assert cl.post("/checkin-v2/pm", json={**PM, "for_date": (aest_today - timedelta(days=2)).isoformat()}).status_code == 422


# ── /prefill.missed_pm ───────────────────────────────────────────────────────────

def test_prefill_offers_missed_pm_when_yesterday_is_open(db_session, monkeypatch):
    u = _user(db_session, "pf-open@x.io")
    today = c2._today_aest()
    yday = today - timedelta(days=1)
    _row(db_session, u.id, yday, am_timestamp=datetime.now(timezone.utc))   # AM done, PM never
    out = get_prefill(current_user=u, db=db_session)
    assert out.missed_pm is not None
    assert out.missed_pm.date == yday and out.missed_pm.cbti_block_open is False


def test_prefill_offers_missed_pm_when_yesterday_has_no_row_but_older_history_exists(db_session):
    u = _user(db_session, "pf-norow@x.io")
    today = c2._today_aest()
    _row(db_session, u.id, today - timedelta(days=5), pm_timestamp=datetime.now(timezone.utc))
    out = get_prefill(current_user=u, db=db_session)
    assert out.missed_pm is not None and out.missed_pm.date == today - timedelta(days=1)


def test_prefill_has_no_missed_pm_when_yesterday_is_closed(db_session):
    u = _user(db_session, "pf-closed@x.io")
    yday = c2._today_aest() - timedelta(days=1)
    _row(db_session, u.id, yday, pm_timestamp=datetime.now(timezone.utc), today_rating=3)
    assert get_prefill(current_user=u, db=db_session).missed_pm is None


def test_prefill_has_no_missed_pm_for_a_user_with_no_records(db_session):
    u = _user(db_session, "pf-new@x.io")
    assert get_prefill(current_user=u, db=db_session).missed_pm is None


def test_prefill_has_no_missed_pm_when_the_only_record_is_today(db_session):
    """Day one: today's row is the user's first record, nothing on/before yesterday."""
    u = _user(db_session, "pf-dayone@x.io")
    _row(db_session, u.id, c2._today_aest(), am_timestamp=datetime.now(timezone.utc))
    assert get_prefill(current_user=u, db=db_session).missed_pm is None


def test_prefill_missed_pm_is_per_user(db_session):
    a, b = _user(db_session, "pf-a@x.io"), _user(db_session, "pf-b@x.io")
    yday = c2._today_aest() - timedelta(days=1)
    _row(db_session, a.id, yday, pm_timestamp=datetime.now(timezone.utc))    # a closed out
    _row(db_session, b.id, yday - timedelta(days=1), pm_timestamp=datetime.now(timezone.utc))
    assert get_prefill(current_user=a, db=db_session).missed_pm is None
    assert get_prefill(current_user=b, db=db_session).missed_pm is not None


def test_prefill_sibling_is_additive_and_absent_is_null():
    assert AMPrefillOut().missed_pm is None
    assert {"cbti", "diary_prefill", "missed_pm"} <= set(AMPrefillOut.model_fields)


def test_missed_pm_cbti_block_open_is_read_for_YESTERDAYS_date(db_session, monkeypatch):
    """The brief: cbti_block_open = _cbti_context(user, today-1).block_open. What can be
    pinned is the WIRING - the context is asked about yesterday, not today - and that the
    flag follows an open block.

    What cannot be pinned here is a case where the two days DISAGREE: `block_open` is
    `closed_on IS NULL` and ignores `for_date` (the date only picks the prescription), so
    today and yesterday always return the same flag. That gap is OPEN_QUESTIONS Q227; the
    final assertion records the current equivalence so the day it stops holding is visible."""
    u = _user(db_session, "pf-blk@x.io")
    today = c2._today_aest()
    yday = today - timedelta(days=1)
    _block(db_session, u.id, opened_on=today - timedelta(days=30))
    _row(db_session, u.id, yday, am_timestamp=datetime.now(timezone.utc))

    asked = []
    real = c2._cbti_context
    def spy(user_id, for_date, db):
        asked.append(for_date)
        return real(user_id, for_date, db)
    monkeypatch.setattr(c2, "_cbti_context", spy)

    mp = get_prefill(current_user=u, db=db_session).missed_pm
    assert mp.cbti_block_open is True
    assert yday in asked                                   # asked about the day being closed out
    assert real(u.id, yday, db_session).block_open == real(u.id, today, db_session).block_open


def test_missed_pm_block_closed_means_no_nap_field(db_session):
    u = _user(db_session, "pf-nob@x.io")
    _block(db_session, u.id, opened_on=c2._today_aest() - timedelta(days=60),
           closed_on=c2._today_aest() - timedelta(days=10))
    _row(db_session, u.id, c2._today_aest() - timedelta(days=1), am_timestamp=datetime.now(timezone.utc))
    assert get_prefill(current_user=u, db=db_session).missed_pm.cbti_block_open is False


# ── pm_late (derived, never stored) ──────────────────────────────────────────────

def _out(d, pm_ts):
    return DailyRecordOut(id=1, date=d, pm_timestamp=pm_ts)


def test_pm_late_is_not_a_column():
    assert not hasattr(models.DailyRecord, "pm_late")
    assert "pm_late" not in models.DailyRecord.__table__.columns


def test_pm_late_false_without_a_pm():
    assert _out(date(2031, 6, 14), None).pm_late is False


def test_pm_late_true_for_a_next_morning_submit_and_false_for_same_evening(db_session, monkeypatch):
    """End to end through the route, both ways, on the response `pm_late` the history reads."""
    u = _user(db_session, "late@x.io")
    day = date(2031, 6, 14)
    cl = _client(db_session, u)

    # same-evening: 20:00 AEST on the 14th, closing out the 14th -> not late
    ev = datetime(2031, 6, 14, 10, 0, tzinfo=timezone.utc)
    _freeze(monkeypatch, today=day, now_utc=ev)
    r = cl.post("/checkin-v2/pm", json=PM)
    assert r.json()["date"] == day.isoformat() and r.json()["pm_late"] is False

    # next-morning catch-up: 07:00 AEST on the 15th, closing out the 14th -> late
    u2 = _user(db_session, "late2@x.io")
    cl2 = _client(db_session, u2)
    morn = datetime(2031, 6, 14, 21, 0, tzinfo=timezone.utc)          # 07:00 AEST on the 15th
    _freeze(monkeypatch, today=day + timedelta(days=1), now_utc=morn)
    r = cl2.post("/checkin-v2/pm", json={**PM, "for_date": day.isoformat()})
    assert r.json()["date"] == day.isoformat() and r.json()["pm_late"] is True

    # and it round-trips through /history (the surface the marker is on)
    h = cl2.get("/checkin-v2/history", params={"days": 36500}).json()
    assert [x["pm_late"] for x in h if x["date"] == day.isoformat()] == [True]


@pytest.mark.parametrize("utc_ts, record_day, expected", [
    # 23:59 AEST on the 14th (13:59Z, the same UTC date): on time
    (datetime(2031, 6, 14, 13, 59, tzinfo=timezone.utc), date(2031, 6, 14), False),
    # 00:01 AEST on the 15th is 14:01Z on the 14th. A UTC-date comparison calls this ON TIME
    # (14th == 14th); the Brisbane date is the 15th, so it is late. The discriminating case.
    (datetime(2031, 6, 14, 14, 1, tzinfo=timezone.utc), date(2031, 6, 14), True),
    # 09:59 AEST / 10:01 AEST on the 15th straddle midnight UTC; both are the 15th in Brisbane
    (datetime(2031, 6, 14, 23, 59, tzinfo=timezone.utc), date(2031, 6, 14), True),
    (datetime(2031, 6, 15, 0, 1, tzinfo=timezone.utc), date(2031, 6, 14), True),
])
def test_pm_late_compares_the_BRISBANE_date_not_the_utc_date(utc_ts, record_day, expected):
    assert utc_ts.astimezone(AEST).date() is not None
    assert _out(record_day, utc_ts).pm_late is expected


def test_pm_late_treats_a_naive_timestamp_as_utc():
    """SQLite hands back naive datetimes; Postgres hands back aware ones. Same answer."""
    d = date(2031, 6, 14)
    aware = datetime(2031, 6, 14, 14, 1, tzinfo=timezone.utc)
    assert _out(d, aware.replace(tzinfo=None)).pm_late is _out(d, aware).pm_late is True


def test_prefill_existing_carries_pm_late(db_session):
    """DailyRecordOut is also nested as AMPrefillOut.existing; the computed field must not
    break that path."""
    u = _user(db_session, "pf-late@x.io")
    _row(db_session, u.id, c2._today_aest(), am_timestamp=datetime.now(timezone.utc))
    out = get_prefill(current_user=u, db=db_session)
    assert out.existing is not None and out.existing.pm_late is False
