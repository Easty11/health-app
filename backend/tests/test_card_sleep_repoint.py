"""Card sleep repointed to the freshest STAGED sleep across sources (Health Connect
aggregate + Samsung scraper), source-labelled and dated — so a live Garmin-only night
shows last night's sleep instead of the frozen Samsung date once the ring dies.

The card's sleep block read ONLY samsung_hrv_readings, which froze when the Samsung ring
stopped. `/health/summary` now also carries `latest_sleep`: the newest wake-date across
{samsung_hrv_readings, health_connect_syncs}, with fields the winning source doesn't stage
rendered as None ('—' on the card) rather than mixed with another night's values.

These pin: (1) the fresh HC/Garmin night beating a stale Samsung night, (2) the sub-metric
gap surfacing as None (never a stale Samsung value under the fresh header), (3) single-source
vs multi-source labelling via health_connect_record_sources with the start-vs-wake-date join
window, (4) Samsung still winning when it is the newer night, and (5) the HRV path untouched.

No network. `/health/summary` runs against the in-memory SQLite `db_session` via a TestClient
with `get_db`/`get_current_user` overridden (the `test_recovery_source_label` pattern).
"""
from __future__ import annotations

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from routers import health

_GARMIN_PKG = "com.garmin.android.apps.connectmobile"
_SAMSUNG_PKG = "com.sec.android.app.shealth"


def _user(db, uid=7):
    u = models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _summary(db, user) -> dict:
    app = FastAPI()
    app.include_router(health.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app).get("/summary").json()


def _hc(db, user, d, *, duration=381, deep=39, rem=40, light=302, score=6):
    db.add(models.HealthConnectSync(
        user_id=user.id, date=d, sleep_duration_minutes=duration,
        deep_sleep_minutes=deep, rem_sleep_minutes=rem, light_sleep_minutes=light,
        sleep_score=score))


def _samsung_sleep(db, user, d, **fields):
    base = dict(
        user_id=user.id, captured_at=d, context="passive_overnight",
        total_sleep_time_minutes=399, deep_minutes=60, rem_minutes=90, light_minutes=240,
        awake_minutes=9, sleep_efficiency_pct=94, respiratory_rate=13.3, sleep_hr_bpm=49,
        spo2_average_pct=94.0, bedtime="22:30", wake_time="06:09",
    )
    base.update(fields)
    db.add(models.SamsungHRVReading(**base))


def _source(db, user, *, record_type="sleep", record_start, pkg):
    db.add(models.HealthConnectRecordSource(
        user_id=user.id, record_type=record_type, record_start=record_start, source_package=pkg))


# ── freshest-night selection ─────────────────────────────────────────────────────────

def test_fresh_hc_garmin_night_beats_stale_samsung(db_session):
    """Ring dead: Samsung frozen at the 14th, Garmin staged the 16th via HC. The card's
    sleep must now be the 16th (HC staging), labelled Garmin, dated — the reported bug."""
    user = _user(db_session)
    _samsung_sleep(db_session, user, date(2026, 9, 14))
    _hc(db_session, user, date(2026, 9, 16))
    # Garmin wrote the night; bedtime record_start is the PRIOR evening (join window).
    _source(db_session, user, record_start="2026-09-15T22:14:00+10:00", pkg=_GARMIN_PKG)
    db_session.commit()

    sleep = _summary(db_session, user)["latest_sleep"]
    assert sleep["night"] == "2026-09-16"
    assert sleep["source"] == "garmin"
    assert sleep["source_label"] == "Garmin"
    # Staging comes straight off the HC row.
    assert (sleep["duration_min"], sleep["deep_min"], sleep["rem_min"], sleep["light_min"]) == (381, 39, 40, 302)
    assert sleep["score"] == 6


def test_hc_night_submetric_gap_is_none_never_stale_samsung(db_session):
    """Decision A(a): fields the HC aggregate doesn't stage are None ('—'), NOT the newest
    Samsung row's values from a different night."""
    user = _user(db_session)
    _samsung_sleep(db_session, user, date(2026, 9, 14))  # has resp/hr/spo2/eff/bedtime
    _hc(db_session, user, date(2026, 9, 16))
    _source(db_session, user, record_start="2026-09-15T22:14:00+10:00", pkg=_GARMIN_PKG)
    db_session.commit()

    sleep = _summary(db_session, user)["latest_sleep"]
    for gap in ("efficiency_pct", "awake_min", "resp_rate", "sleep_hr_bpm", "spo2_pct", "bedtime", "wake_time"):
        assert sleep[gap] is None, f"{gap} must be None on an HC night, not a stale Samsung value"


def test_samsung_wins_when_it_is_the_newer_night(db_session):
    """If the Samsung scraper revives and stages a newer night than HC, it wins — full
    sub-metrics, labelled Samsung."""
    user = _user(db_session)
    _hc(db_session, user, date(2026, 9, 14))
    _samsung_sleep(db_session, user, date(2026, 9, 16))
    db_session.commit()

    sleep = _summary(db_session, user)["latest_sleep"]
    assert (sleep["night"], sleep["source"], sleep["source_label"]) == ("2026-09-16", "samsung", "Samsung")
    assert sleep["duration_min"] == 399
    assert sleep["efficiency_pct"] == 94 and sleep["sleep_hr_bpm"] == 49 and sleep["bedtime"] == "22:30"


# ── source labelling via record_sources ──────────────────────────────────────────────

def test_multi_source_night_labels_health_connect_multiple(db_session):
    """Both Garmin and Samsung wrote the same night (historical): the HC aggregate is a
    blend — label 'Health Connect (multiple)', never a single misattributed device."""
    user = _user(db_session)
    _hc(db_session, user, date(2026, 9, 12))
    _source(db_session, user, record_start="2026-09-11T22:40:00+10:00", pkg=_GARMIN_PKG)
    _source(db_session, user, record_start="2026-09-11T22:41:00+10:00", pkg=_SAMSUNG_PKG)
    db_session.commit()

    sleep = _summary(db_session, user)["latest_sleep"]
    assert sleep["source"] == "multiple"
    assert sleep["source_label"] == "Health Connect (multiple)"


def test_samsung_plus_withings_night_is_multiple_not_misattributed_to_samsung(db_session):
    """Q83: Withings is a real HC sleep writer. A Samsung+Withings blend must read 'multiple',
    NOT single-source Samsung — even though only Samsung has a mapped friendly name here the
    resolver still counts two distinct real packages."""
    user = _user(db_session)
    _hc(db_session, user, date(2026, 9, 10))
    _source(db_session, user, record_start="2026-09-09T22:30:00+10:00", pkg=_SAMSUNG_PKG)
    _source(db_session, user, record_start="2026-09-09T22:31:00+10:00", pkg="com.withings.wiscale2")
    db_session.commit()

    sleep = _summary(db_session, user)["latest_sleep"]
    assert (sleep["source"], sleep["source_label"]) == ("multiple", "Health Connect (multiple)")


def test_hc_night_with_only_unknown_identity_labels_generic_health_connect(db_session):
    """Identity-less records (pre-cutover 'unknown' sentinel): we know it's HC but not the
    device — generic 'Health Connect', not a guessed brand."""
    user = _user(db_session)
    _hc(db_session, user, date(2026, 9, 16))
    _source(db_session, user, record_start="2026-09-15T22:00:00+10:00", pkg="unknown")
    db_session.commit()

    sleep = _summary(db_session, user)["latest_sleep"]
    assert (sleep["source"], sleep["source_label"]) == ("health_connect", "Health Connect")


def test_source_join_window_matches_same_wake_date_start_too(db_session):
    """A sleep record whose start falls ON the wake-date (e.g. a late-morning nap-shaped
    session, or a tz that keeps start on the same day) still resolves via the window."""
    user = _user(db_session)
    _hc(db_session, user, date(2026, 9, 16))
    _source(db_session, user, record_start="2026-09-16T00:30:00+10:00", pkg=_GARMIN_PKG)
    db_session.commit()

    assert _summary(db_session, user)["latest_sleep"]["source"] == "garmin"


# ── edges ────────────────────────────────────────────────────────────────────────────

def test_no_sleep_anywhere_yields_null_latest_sleep(db_session):
    user = _user(db_session)
    db_session.commit()
    assert _summary(db_session, user)["latest_sleep"] is None


def test_garmin_only_user_gets_sleep_and_leaves_hrv_path_untouched(db_session):
    """A Garmin-only user has no Samsung device row: `latest` (Samsung sleep+HRV) stays None,
    but `latest_sleep` still surfaces the HC night."""
    user = _user(db_session)
    _hc(db_session, user, date(2026, 9, 16))
    _source(db_session, user, record_start="2026-09-15T22:00:00+10:00", pkg=_GARMIN_PKG)
    db_session.commit()

    body = _summary(db_session, user)
    assert body["latest"] is None                       # HRV/Samsung path unchanged
    assert body["latest_sleep"]["night"] == "2026-09-16"
    assert body["latest_sleep"]["source"] == "garmin"


def test_hc_wins_same_night_tie_over_samsung(db_session):
    """Same wake-date in both tables → prefer the HC aggregate (richer, honestly labelled)."""
    user = _user(db_session)
    d = date(2026, 9, 16)
    _samsung_sleep(db_session, user, d)
    _hc(db_session, user, d)
    _source(db_session, user, record_start="2026-09-15T22:00:00+10:00", pkg=_GARMIN_PKG)
    db_session.commit()

    sleep = _summary(db_session, user)["latest_sleep"]
    assert sleep["source"] == "garmin" and sleep["duration_min"] == 381  # HC staging, not Samsung's 399
