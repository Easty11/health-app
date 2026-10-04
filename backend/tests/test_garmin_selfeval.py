"""`garmin_selfeval` -- Garmin per-activity self-evaluation into the insert-only store (Q209 path a).

Layers on purpose (FEEDBACK section 23), as in `test_garmin_selfeval_probe`: the capture logic is tested with a
faked source (which records every request), and the no-refresh guarantee against the REAL `garminconnect` client
faked at the TRANSPORT, because it lives in the library's own request path. Payload fixtures carry what the API
sends, nulls included (FEEDBACK section 60): `directWorkoutRpe` 0-100 in steps of 10, `directWorkoutFeel` 0/25/50/75/100,
both on the activity DETAIL (summaryDTO), neither on the list.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

import encryption
import garmin_selfeval as gs
import models
from aerobic_format import format_selfeval
from scripts import garmin_identity as gi
from scripts import garmin_sync
from tests.test_garmin_selfeval_probe import FakeResp, FakeSession, _blob  # the transport-fake precedent

NOW = datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc)
START = datetime(2026, 10, 3, 21, 30, tzinfo=timezone.utc)      # the activity: 45 minutes
DURATION = 2700.0


def _user(db, uid=1):
    if db.get(models.User, uid) is None:
        db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
        db.commit()


def _garmin(db, uid=1, secret="garmin-token"):
    _user(db, uid)
    db.add(models.UserIntegration(user_id=uid, provider="garmin", api_key_encrypted=encryption.encrypt(secret)))
    db.commit()


def _item(aid, start=START, duration=DURATION, tkey="strength_training"):
    return {"activityId": aid, "startTimeGMT": start.strftime("%Y-%m-%d %H:%M:%S"), "duration": duration,
            "activityType": {"typeKey": tkey, "typeId": 13}, "activityName": "SECRET-NAME"}


def _detail(rpe="absent", feel="absent"):
    s = {"averageHR": 100.0}
    if rpe != "absent":
        s["directWorkoutRpe"] = rpe
    if feel != "absent":
        s["directWorkoutFeel"] = feel
    return {"activityId": 1, "summaryDTO": s}


class FakeSource:
    """The list, then a detail per id; records every request. `details` maps activity id -> payload (or an
    exception instance to raise)."""

    def __init__(self, items, details):
        self.calls, self.items, self.details = [], items, details

    def get(self, path, params=None):
        self.calls.append((path, params))
        if path == gs.ACTIVITY_LIST_PATH:
            return self.items
        aid = int(path.rsplit("/", 1)[1])
        d = self.details[aid]
        if isinstance(d, Exception):
            raise d
        return d

    def detail_ids(self):
        return [int(p.rsplit("/", 1)[1]) for p, _ in self.calls if p != gs.ACTIVITY_LIST_PATH]


def _rows(db, aid=None):
    q = db.query(models.GarminActivitySelfEval).order_by(models.GarminActivitySelfEval.captured_at,
                                                         models.GarminActivitySelfEval.id)
    if aid is not None:
        q = q.filter_by(garmin_activity_id=aid)
    return q.all()


def _run(db, src, now=NOW, uid=1):
    return gs.sync_user(db, uid, factory=lambda blob: src, now=now)


def _hc(db, *, uid=1, start=START, minutes=45, pkg=gs.GARMIN_HC_PACKAGE, source="health_connect", ssid=None):
    stop = start + timedelta(minutes=minutes)
    row = models.AerobicSession(user_id=uid, source=source, source_session_id=ssid or f"{pkg}|{start.isoformat()}",
                                session_date=start.date(), start_time=start, stop_time=stop, sport_name="Strength",
                                duration_minutes=float(minutes), source_package=pkg)
    db.add(row)
    db.commit()
    return row


# -- scale conversion ----------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [(40, 4.0), (70, 7.0), (100, 10.0), (0, 0.0), (45, 4.5), (40.0, 4.0)])
def test_rpe_is_garmins_0_100_over_ten(raw, expected):
    assert gs.parse_selfeval(_detail(rpe=raw), 1) == (expected, None)


def test_the_probe_activity_reads_as_4_of_10_and_feel_25():
    """The anchor: activity 24564069469, operator-rated 4/10 and Weak, came back 40 and 25."""
    assert gs.parse_selfeval(_detail(rpe=40, feel=25), 24564069469) == (4.0, 25)


@pytest.mark.parametrize("bad", [-10, 101, 1000, "40", True, [], {}])
def test_unusable_values_are_unrated_not_a_rating_and_are_logged(bad, caplog):
    with caplog.at_level(logging.WARNING):
        assert gs.parse_selfeval(_detail(rpe=bad, feel=bad), 7) == (None, None)
    assert "unusable" in caplog.text


@pytest.mark.parametrize("detail", [_detail(), _detail(rpe=None, feel=None), _detail(rpe=None)])
def test_absent_or_null_keys_are_unrated(detail):
    assert gs.parse_selfeval(detail, 1) == (None, None)


@pytest.mark.parametrize("detail", [{}, {"summaryDTO": None}, {"summaryDTO": []}, None, [], "x"])
def test_a_detail_without_a_summary_object_is_a_shape_change_not_unrated(detail):
    assert gs.parse_selfeval(detail, 1) is None


# -- capture: the rated path, the unrated path, the list bound -------------------------------------

def test_a_new_rated_activity_is_stored_with_scale_type_and_interval(db_session):
    _garmin(db_session)
    src = FakeSource([_item(11)], {11: _detail(rpe=40, feel=25)})
    out = _run(db_session, src)
    (r,) = _rows(db_session)
    assert (r.garmin_activity_id, r.rpe_cr10, r.feel, r.garmin_type) == (11, 4.0, 25, "strength_training")
    assert r.start_time.replace(tzinfo=timezone.utc) == START
    assert r.stop_time.replace(tzinfo=timezone.utc) == START + timedelta(seconds=DURATION)
    assert r.aerobic_session_id is None
    assert out == {"fetched": 1, "rated": 1, "unrated": 0, "linked": 0, "relinked": 0,
                   "skipped_needs_refresh": 0, "errors": 0}


def test_two_gets_per_new_activity_and_one_list_get_nothing_else(db_session):
    _garmin(db_session)
    src = FakeSource([_item(11), _item(12, start=START + timedelta(hours=1))], {11: _detail(rpe=40), 12: _detail(rpe=50)})
    _run(db_session, src)
    assert [p for p, _ in src.calls] == [gs.ACTIVITY_LIST_PATH, f"{gs.ACTIVITY_PATH}/11", f"{gs.ACTIVITY_PATH}/12"]


def test_the_list_is_bounded_by_a_start_date_and_a_page_and_asks_oldest_first(db_session):
    _garmin(db_session)
    src = FakeSource([], {})
    _run(db_session, src)
    (path, params), = src.calls
    assert path == gs.ACTIVITY_LIST_PATH
    assert params == {"startDate": "2026-09-20", "start": "0", "limit": "50", "sortOrder": "asc"}   # now - 14 days


def test_the_list_resumes_one_day_before_the_last_captured_start(db_session):
    _garmin(db_session)
    _run(db_session, FakeSource([_item(11)], {11: _detail(rpe=40)}))
    src = FakeSource([], {})
    _run(db_session, src, now=NOW + timedelta(days=1))
    assert src.calls[0][1]["startDate"] == "2026-10-02"                  # START was 3 Oct; one day of overlap


def test_unrated_is_recorded_as_a_null_row_and_not_refetched_the_same_day(db_session):
    _garmin(db_session)
    src = FakeSource([_item(11)], {11: _detail()})
    out = _run(db_session, src)
    (r,) = _rows(db_session)
    assert (r.rpe_cr10, r.feel, r.aerobic_session_id) == (None, None, None)
    assert (out["fetched"], out["rated"], out["unrated"]) == (1, 0, 1)
    again = FakeSource([_item(11)], {11: _detail()})
    _run(db_session, again, now=NOW + timedelta(hours=2))               # inside the 20 h gap
    assert again.detail_ids() == [] and len(_rows(db_session)) == 1


def test_a_rated_activity_is_never_re_read(db_session):
    _garmin(db_session)
    _run(db_session, FakeSource([_item(11)], {11: _detail(rpe=40, feel=25)}))
    again = FakeSource([_item(11)], {11: _detail(rpe=90)})               # Garmin would now say 90: it must not be asked
    _run(db_session, again, now=NOW + timedelta(days=2))
    assert again.detail_ids() == []
    assert [(r.rpe_cr10, r.feel) for r in _rows(db_session)] == [(4.0, 25)]


# -- unrated re-check: marker rows, the 20 h gap, the 7-day stop -----------------------------------

def test_an_unrated_activity_is_rechecked_daily_with_a_marker_row_each_time(db_session):
    _garmin(db_session)
    _run(db_session, FakeSource([_item(11)], {11: _detail()}))
    for day in (1, 2):
        src = FakeSource([], {11: _detail()})
        out = _run(db_session, src, now=NOW + timedelta(days=day))
        assert src.detail_ids() == [11] and out["unrated"] == 1
    assert len(_rows(db_session, 11)) == 3                               # first sighting + two due checks


def test_a_recheck_that_finds_a_rating_inserts_a_new_row_and_leaves_the_old_one_alone(db_session):
    _garmin(db_session)
    _run(db_session, FakeSource([_item(11)], {11: _detail()}))
    first = _rows(db_session, 11)[0]
    first_values = (first.id, first.captured_at, first.rpe_cr10, first.feel)
    out = _run(db_session, FakeSource([], {11: _detail(rpe=60, feel=50)}), now=NOW + timedelta(days=1))
    rows = _rows(db_session, 11)
    assert (out["rated"], len(rows)) == (1, 2)
    assert (rows[0].id, rows[0].captured_at, rows[0].rpe_cr10, rows[0].feel) == first_values   # not rewritten
    assert (rows[1].rpe_cr10, rows[1].feel) == (6.0, 50)
    again = FakeSource([], {})
    _run(db_session, again, now=NOW + timedelta(days=2))
    assert again.detail_ids() == []                                      # rated now: never re-read


def test_the_recheck_stops_after_seven_days(db_session):
    _garmin(db_session)
    _run(db_session, FakeSource([_item(11)], {11: _detail()}))
    src = FakeSource([], {11: _detail()})
    _run(db_session, src, now=START + timedelta(days=7, hours=1))
    assert src.detail_ids() == [] and len(_rows(db_session, 11)) == 1


def test_no_update_statement_is_ever_issued_against_the_store(db_session):
    """Immutability: across first sight, a marker, a rating and a relink, every write to the table is an INSERT."""
    _garmin(db_session)
    stmts: list[str] = []
    event.listen(db_session.get_bind(), "before_cursor_execute",
                 lambda c, cur, st, p, ctx, m: stmts.append(st.strip().upper()))
    _run(db_session, FakeSource([_item(11)], {11: _detail()}))
    _run(db_session, FakeSource([], {11: _detail()}), now=NOW + timedelta(days=1))
    _hc(db_session)
    _run(db_session, FakeSource([], {11: _detail(rpe=70, feel=75)}), now=NOW + timedelta(days=2))
    _run(db_session, FakeSource([], {}), now=NOW + timedelta(days=3))     # relink pass
    touching = [s for s in stmts if "GARMIN_ACTIVITY_SELFEVALS" in s]
    assert touching and not [s for s in touching if s.startswith(("UPDATE", "DELETE"))], touching


def test_a_new_row_never_reuses_an_earlier_capture_time(db_session):
    """A relink in a run with the same clock reading as the original capture would collide on the unique key
    (user, activity, captured_at); the later row is placed strictly after, so 'latest' stays unambiguous."""
    _garmin(db_session)
    _run(db_session, FakeSource([_item(11)], {11: _detail(rpe=40, feel=25)}))
    hc = _hc(db_session)
    out = _run(db_session, FakeSource([], {}))                                 # the same NOW
    a, b = _rows(db_session, 11)
    assert out["relinked"] == 1 and b.aerobic_session_id == hc.id
    assert b.captured_at.replace(tzinfo=timezone.utc) > a.captured_at.replace(tzinfo=timezone.utc)


# -- failure handling: stop at the first, never a false "unrated" ------------------------------------

def test_the_read_stops_at_the_first_failure_and_keeps_what_it_captured(db_session):
    _garmin(db_session)
    items = [_item(11), _item(12, start=START + timedelta(hours=1)), _item(13, start=START + timedelta(hours=2))]
    src = FakeSource(items, {11: _detail(rpe=40), 12: ConnectionError("boom"), 13: _detail(rpe=50)})
    out = _run(db_session, src)
    assert src.detail_ids() == [11, 12]                                  # 13 not attempted: the order invariant
    assert [r.garmin_activity_id for r in _rows(db_session)] == [11]
    assert out["errors"] == 1 and out["rated"] == 1


def test_a_shape_change_stops_the_read_at_that_activity(db_session):
    """The same order invariant for a payload that is not a rating: nothing after it is attempted, so the last
    captured start never passes an activity that was not recorded."""
    _garmin(db_session)
    items = [_item(11), _item(12, start=START + timedelta(hours=1)), _item(13, start=START + timedelta(hours=2))]
    src = FakeSource(items, {11: _detail(rpe=40), 12: {"somethingElse": 1}, 13: _detail(rpe=50)})
    out = _run(db_session, src)
    assert src.detail_ids() == [11, 12] and [r.garmin_activity_id for r in _rows(db_session)] == [11]
    assert out["errors"] == 1


def test_a_detail_with_no_summary_is_an_error_and_records_nothing(db_session):
    _garmin(db_session)
    out = _run(db_session, FakeSource([_item(11)], {11: {"somethingElse": 1}}))
    assert _rows(db_session) == [] and out["errors"] == 1 and out["unrated"] == 0


def test_a_list_item_without_an_id_or_start_is_skipped(db_session):
    _garmin(db_session)
    src = FakeSource([{"activityId": None}, {"startTimeGMT": "2026-10-03 21:30:00"}, "x", _item(11)], {11: _detail(rpe=40)})
    assert _run(db_session, src)["rated"] == 1 and src.detail_ids() == [11]


def test_a_user_without_a_garmin_connection_makes_no_request(db_session):
    _user(db_session)
    src = FakeSource([_item(11)], {})
    out = _run(db_session, src)
    assert src.calls == [] and out["fetched"] == 0 and _rows(db_session) == []


# -- the link rule --------------------------------------------------------------------------------

def test_link_needs_50_percent_of_the_shorter_and_a_garmin_package(db_session):
    _user(db_session)
    stop = START + timedelta(seconds=DURATION)                                         # 45 min
    full = _hc(db_session)
    assert gs.find_link(db_session, 1, START, stop) == full.id
    db_session.delete(full)
    db_session.commit()
    exactly_half = _hc(db_session, start=START + timedelta(minutes=22, seconds=30), minutes=45)   # 22.5 of 45 min overlap
    assert gs.find_link(db_session, 1, START, stop) == exactly_half.id                 # 50% of the shorter: in
    db_session.delete(exactly_half)
    db_session.commit()
    _hc(db_session, start=START + timedelta(minutes=23), minutes=45)                   # 22 of 45: out
    assert gs.find_link(db_session, 1, START, stop) is None


def test_the_shorter_interval_sets_the_denominator(db_session):
    _user(db_session)
    short = _hc(db_session, start=START + timedelta(minutes=10), minutes=10)           # wholly inside a 45-minute activity
    assert gs.find_link(db_session, 1, START, START + timedelta(seconds=DURATION)) == short.id


def test_samsung_polar_and_other_users_rows_are_never_linked(db_session):
    _user(db_session)
    _user(db_session, 2)
    stop = START + timedelta(seconds=DURATION)
    _hc(db_session, pkg="com.sec.android.app.shealth")
    _hc(db_session, source="polar_v4", pkg=None, ssid="p1")
    _hc(db_session, source="polar_v4", ssid="p2")                              # a non-HC row even with the Garmin package
    _hc(db_session, uid=2, ssid="other-user")
    assert gs.find_link(db_session, 1, START, stop) is None


def test_the_greatest_overlap_wins_then_the_lowest_id(db_session):
    _user(db_session)
    stop = START + timedelta(seconds=DURATION)
    _hc(db_session, start=START + timedelta(minutes=5), minutes=45, ssid="partial")
    best = _hc(db_session, ssid="best")
    assert gs.find_link(db_session, 1, START, stop) == best.id


def test_no_stop_time_means_no_link_and_a_missing_interval_row_is_skipped(db_session):
    _user(db_session)
    row = _hc(db_session)
    assert gs.find_link(db_session, 1, START, None) is None
    row.stop_time = None
    db_session.commit()
    assert gs.find_link(db_session, 1, START, START + timedelta(seconds=DURATION)) is None


def test_a_rated_activity_is_linked_at_capture_when_the_hc_row_is_already_there(db_session):
    _garmin(db_session)
    hc = _hc(db_session)
    out = _run(db_session, FakeSource([_item(11)], {11: _detail(rpe=40, feel=25)}))
    assert _rows(db_session)[0].aerobic_session_id == hc.id and out["linked"] == 1


def test_a_garmin_only_type_that_never_reaches_hc_stays_unlinked(db_session):
    _garmin(db_session)
    out = _run(db_session, FakeSource([_item(11, tkey="breathwork")], {11: _detail(rpe=10, feel=75)}))
    r = _rows(db_session)[0]
    assert (r.garmin_type, r.aerobic_session_id, out["linked"]) == ("breathwork", None, 0)


# -- the relink pass: DB-only, inserts a linked row, needs no token ---------------------------------

def test_a_late_hc_row_is_linked_by_a_new_row_without_any_garmin_call(db_session):
    _garmin(db_session)
    _run(db_session, FakeSource([_item(11)], {11: _detail(rpe=40, feel=25)}))
    assert _rows(db_session)[0].aerobic_session_id is None
    hc = _hc(db_session)                                                       # Health Connect lands a few days late

    class NoGarmin:
        def get(self, *a, **k):
            raise gi.RefreshWouldBeNeeded()                                    # even a dead token cannot stop the relink
    out = gs.sync_user(db_session, 1, factory=lambda b: NoGarmin(), now=NOW + timedelta(days=3))
    rows = _rows(db_session, 11)
    assert out["relinked"] == 1 and out["linked"] == 1 and out["skipped_needs_refresh"] == 1
    assert rows[0].aerobic_session_id is None                                  # the first row is untouched
    assert (rows[1].aerobic_session_id, rows[1].rpe_cr10, rows[1].feel) == (hc.id, 4.0, 25)
    again = gs.sync_user(db_session, 1, factory=lambda b: NoGarmin(), now=NOW + timedelta(days=4))
    assert again["relinked"] == 0 and len(_rows(db_session, 11)) == 2          # linked now: nothing further


def test_the_relink_pass_leaves_unrated_and_old_activities_alone(db_session):
    _garmin(db_session)
    _run(db_session, FakeSource([_item(11), _item(12, start=START - timedelta(days=20))],
                                {11: _detail(), 12: _detail(rpe=40)}))
    _hc(db_session)
    _hc(db_session, start=START - timedelta(days=20), ssid="old")
    out = gs.sync_user(db_session, 1, factory=lambda b: FakeSource([], {}), now=NOW)
    assert out["relinked"] == 0                                                # 11 unrated; 12 is past RELINK_DAYS


def test_deleting_the_linked_hc_row_nulls_the_link_and_keeps_the_capture(db_session):
    _garmin(db_session)
    hc = _hc(db_session)
    _run(db_session, FakeSource([_item(11)], {11: _detail(rpe=40, feel=25)}))
    db_session.delete(hc)
    db_session.commit()
    (r,) = _rows(db_session)
    assert (r.aerobic_session_id, r.rpe_cr10, r.feel) == (None, 4.0, 25)


# -- no refresh: the REAL client, faked at the transport --------------------------------------------

@pytest.fixture()
def no_token_endpoint(monkeypatch):
    from garminconnect import client as gc

    def forbidden(*a, **k):
        raise AssertionError("a token refresh request was sent")
    monkeypatch.setattr(gc.Client, "_http_post", forbidden)


def _real(db, blob, sess):
    return gs.sync_user(db, 1, factory=lambda b: gs.ProbeSource(b, session=sess), now=NOW)


def test_an_expiring_token_sends_nothing_inserts_nothing_and_leaves_the_stored_blob(db_session, no_token_endpoint):
    blob = _blob(-60)
    _garmin(db_session, secret=blob)
    stored = db_session.query(models.UserIntegration).first().api_key_encrypted
    sess = FakeSession()                                                     # any request would IndexError
    out = _real(db_session, blob, sess)
    assert out["skipped_needs_refresh"] == 1 and out["errors"] == 0
    assert sess.calls == [] and _rows(db_session) == []
    assert db_session.query(models.UserIntegration).first().api_key_encrypted == stored


def test_a_401_mid_read_does_not_trigger_the_retry_refresh(db_session, no_token_endpoint):
    blob = _blob(+3600)
    _garmin(db_session, secret=blob)
    sess = FakeSession(FakeResp(401))
    out = _real(db_session, blob, sess)
    assert out["skipped_needs_refresh"] == 1 and len(sess.calls) == 1 and _rows(db_session) == []


def test_a_real_client_run_is_get_only_and_leaves_the_token_state_alone(db_session, no_token_endpoint):
    blob = _blob(+3600)
    _garmin(db_session, secret=blob)
    sess = FakeSession(FakeResp(200, [_item(11)]), FakeResp(200, {"summaryDTO": {"directWorkoutRpe": 40, "directWorkoutFeel": 25}}))
    stored = db_session.query(models.UserIntegration).first().api_key_encrypted
    out = _real(db_session, blob, sess)
    assert [m for m, _, _ in sess.calls] == ["GET", "GET"]
    assert sess.calls[0][1].endswith(gs.ACTIVITY_LIST_PATH) and sess.calls[1][1].endswith(f"{gs.ACTIVITY_PATH}/11")
    assert out["rated"] == 1 and _rows(db_session)[0].rpe_cr10 == 4.0
    assert db_session.query(models.UserIntegration).first().api_key_encrypted == stored   # no token writeback here


def test_the_module_never_sends_a_non_get_or_names_a_write_path():
    import inspect
    src = inspect.getsource(gs)
    for forbidden in ("_http_post", "connectapi(", ".login(", "set_activity", "upload", "requests."):
        assert forbidden not in src, forbidden
    assert gs.ProbeSource.__mro__[1] is gi.LibrarySource


def test_the_garmin_package_is_the_wearable_native_one():
    from reads.aerobic_reads import WEARABLE_NATIVE
    assert gs.GARMIN_HC_PACKAGE in WEARABLE_NATIVE


# -- the sweep: placement, isolation, counts ---------------------------------------------------------

def _fake_hrv(db, uid, start, end):
    return {"from": start.isoformat(), "to": end.isoformat(), "days_with_data": 1, "readings_upserted": 1,
            "samples_upserted": 5}


def test_the_sweep_runs_the_read_after_each_users_hrv_pull_and_sums_the_counts(db_session, monkeypatch):
    _garmin(db_session, 1)
    _garmin(db_session, 4)
    order: list[str] = []
    monkeypatch.setattr(garmin_sync, "sync_hrv_for_user", lambda db, uid, s, e: order.append(f"hrv{uid}") or _fake_hrv(db, uid, s, e))

    def factory(blob):
        order.append("read")
        return FakeSource([_item(11)], {11: _detail(rpe=40, feel=25)})
    summary = garmin_sync.sweep_garmin_hrv(db_session, selfeval_factory=factory)
    assert order == ["hrv1", "read", "hrv4", "read"]                            # a read follows its own user's refresh
    assert summary["per_user"][1]["selfeval"]["rated"] == 1
    assert summary["selfeval"] == {"fetched": 2, "rated": 2, "unrated": 0, "linked": 0, "relinked": 0,
                                   "skipped_needs_refresh": 0, "errors": 0}


def test_a_dead_token_user_gets_no_read_and_the_others_are_unaffected(db_session, monkeypatch):
    from connectors.garmin import GarminReconnectError
    _garmin(db_session, 1)
    _garmin(db_session, 4)

    def hrv(db, uid, s, e):
        if uid == 4:
            raise GarminReconnectError("dead")
        return _fake_hrv(db, uid, s, e)
    monkeypatch.setattr(garmin_sync, "sync_hrv_for_user", hrv)
    built: list[str] = []

    def factory(blob):
        built.append("x")
        return FakeSource([], {})
    summary = garmin_sync.sweep_garmin_hrv(db_session, selfeval_factory=factory)
    assert built == ["x"]                                                       # only user 1
    assert "selfeval" not in summary["per_user"][4] and summary["per_user"][4]["status"] == "reconnect_required"


def test_a_selfeval_failure_is_soft_and_never_changes_the_hrv_outcome(db_session, monkeypatch):
    _garmin(db_session, 1)
    monkeypatch.setattr(garmin_sync, "sync_hrv_for_user", _fake_hrv)

    def factory(blob):
        raise RuntimeError("library blew up")
    summary = garmin_sync.sweep_garmin_hrv(db_session, selfeval_factory=factory)
    u = summary["per_user"][1]
    assert u["status"] == "succeeded" and summary["users_succeeded"] == 1 and summary["users_failed"] == 0
    assert u["selfeval"]["errors"] == 1                                         # counted, by class (read-phase catch)


def test_a_failure_outside_the_read_is_also_soft_and_reported(db_session, monkeypatch):
    """`sync_user` catches its own read failures; this is the step's own net, for what happens before the read
    (the DB-only relink pass). It reports the error, rolls back, and the user's HRV outcome stands."""
    _garmin(db_session, 1)
    monkeypatch.setattr(garmin_sync, "sync_hrv_for_user", _fake_hrv)

    def boom(*a, **k):
        raise RuntimeError("relink exploded")
    monkeypatch.setattr(gs, "_relink", boom)
    summary = garmin_sync.sweep_garmin_hrv(db_session, selfeval_factory=lambda b: FakeSource([], {}))
    u = summary["per_user"][1]
    assert u["status"] == "succeeded" and u["selfeval"] == {"error": "RuntimeError: relink exploded"}
    assert summary["selfeval"]["errors"] == 1 and summary["users_failed"] == 0


def test_a_stale_token_is_visible_in_the_summary(db_session, monkeypatch):
    _garmin(db_session, 1)
    monkeypatch.setattr(garmin_sync, "sync_hrv_for_user", _fake_hrv)

    class Stale:
        def get(self, *a, **k):
            raise gi.RefreshWouldBeNeeded()
    summary = garmin_sync.sweep_garmin_hrv(db_session, selfeval_factory=lambda b: Stale())
    assert summary["selfeval"]["skipped_needs_refresh"] == 1


def test_the_nightly_brief_carries_the_selfeval_counts():
    import load_sweep
    brief = load_sweep._summary_brief({"load": {}, "garmin": {"users_attempted": 1, "selfeval": {"rated": 2}}})
    assert brief["garmin"]["selfeval"] == {"rated": 2}


# -- the readout --------------------------------------------------------------------------------------

def _eval_row(db, aid, session_id, rpe=4.0, feel=25, captured=NOW):
    r = models.GarminActivitySelfEval(user_id=1, garmin_activity_id=aid, captured_at=captured, rpe_cr10=rpe, feel=feel,
                                      garmin_type="strength_training", start_time=START,
                                      stop_time=START + timedelta(seconds=DURATION), aerobic_session_id=session_id)
    db.add(r)
    db.commit()
    return r


def test_format_selfeval_renders_present_values_only():
    assert format_selfeval(type("R", (), {"rpe_cr10": 4.0, "feel": 25})) == " selfeval=[RPE 4/10 feel 25/100 garmin]"
    assert format_selfeval(type("R", (), {"rpe_cr10": 4.5, "feel": None})) == " selfeval=[RPE 4.5/10 garmin]"
    assert format_selfeval(type("R", (), {"rpe_cr10": None, "feel": 75})) == " selfeval=[feel 75/100 garmin]"


def test_get_training_sessions_shows_the_value_on_a_linked_session_only(db_session, monkeypatch):
    import mcp_server
    from aerobic_format import format_aerobic_session
    _user(db_session)
    today = datetime.now(timezone.utc)
    linked = _hc(db_session, start=today - timedelta(days=1), ssid="a")
    plain = _hc(db_session, start=today - timedelta(days=3), ssid="b", pkg="com.sec.android.app.shealth")
    _eval_row(db_session, 11, linked.id, rpe=4.0, feel=25)
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: 1)
    lines = mcp_server.get_training_sessions(days=28).split("\n")
    assert format_aerobic_session(linked) + " selfeval=[RPE 4/10 feel 25/100 garmin]" in lines
    assert format_aerobic_session(plain) in lines                              # byte-identical when nothing is linked


def test_the_readout_shows_the_latest_row_and_skips_unrated_ones(db_session):
    _user(db_session)
    hc = _hc(db_session)
    _eval_row(db_session, 11, hc.id, rpe=4.0, feel=25, captured=NOW)
    _eval_row(db_session, 11, hc.id, rpe=6.0, feel=50, captured=NOW + timedelta(days=1))
    out = gs.selfeval_by_session(db_session, 1, [hc])
    assert (out[hc.id].rpe_cr10, out[hc.id].feel) == (6.0, 50)
    _eval_row(db_session, 12, hc.id, rpe=None, feel=None, captured=NOW + timedelta(days=2))
    assert gs.selfeval_by_session(db_session, 1, [hc])[hc.id].rpe_cr10 == 6.0   # an unrated marker is not a value


def test_a_value_on_a_lost_twin_moves_to_the_canonical_session(db_session):
    """The linked HC row lost arbitration to a same-bout Polar row: the readout shows the value on the winner."""
    _user(db_session)
    hc = _hc(db_session)
    polar = _hc(db_session, source="polar_v4", pkg=None, ssid="polar-1")
    hc.canonical, polar.canonical = False, True
    _eval_row(db_session, 11, hc.id)
    out = gs.selfeval_by_session(db_session, 1, [hc, polar])
    assert set(out) == {polar.id}
    elsewhere = _hc(db_session, start=START - timedelta(days=2), source="polar_v4", pkg=None, ssid="polar-2")
    elsewhere.canonical = True
    assert set(gs.selfeval_by_session(db_session, 1, [hc, elsewhere])) == set()   # no same-bout winner: nothing shown
