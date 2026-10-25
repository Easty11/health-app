"""`garmin_selfeval` -- Garmin per-activity self-evaluation, adapter #1 of the source-neutral sRPE store (Q209 path a).

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
import srpe_store
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
    q = db.query(models.SessionRpeObservation).order_by(models.SessionRpeObservation.captured_at,
                                                        models.SessionRpeObservation.id)
    if aid is not None:
        q = q.filter_by(source="garmin", source_activity_ref=str(aid))
    return q.all()


def _run(db, src, now=NOW, uid=1):
    return gs.sync_user(db, uid, factory=lambda blob: src, now=now)


GARMIN_HC_PACKAGE = "com.garmin.android.apps.connectmobile"


def _hc(db, *, uid=1, start=START, minutes=45, pkg=GARMIN_HC_PACKAGE, source="health_connect", ssid=None):
    stop = start + timedelta(minutes=minutes)
    row = models.AerobicSession(user_id=uid, source=source, source_session_id=ssid or f"{pkg}|{start.isoformat()}",
                                session_date=start.date(), start_time=start, stop_time=stop, sport_name="Strength",
                                duration_minutes=float(minutes), source_package=pkg)
    db.add(row)
    db.commit()
    return row


# -- scale conversion ----------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [40, 70, 100, 0, 45, 40.0])
def test_the_adapter_hands_the_contract_garmins_value_as_sent(raw):
    assert gs.parse_selfeval(_detail(rpe=raw), 1) == (float(raw), None)


def test_the_probe_activity_reads_as_raw_40_and_feel_25_and_is_4_of_10_in_the_store(db_session):
    """The anchor: activity 24564069469, operator-rated 4/10 and Weak, came back 40 and 25."""
    assert gs.parse_selfeval(_detail(rpe=40, feel=25), 24564069469) == (40.0, 25)
    _garmin(db_session)
    _run(db_session, FakeSource([_item(24564069469)], {24564069469: _detail(rpe=40, feel=25)}))
    (r,) = _rows(db_session)
    assert (r.rpe_raw, r.raw_scale, r.rpe_cr10, r.feel) == (40.0, "garmin_0_100", 4.0, 25)


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
    assert (r.source, r.source_activity_ref, r.rpe_cr10, r.feel) == ("garmin", "11", 4.0, 25)
    assert r.provenance == {"garmin_type": "strength_training", "transport": "di"}
    assert r.start_time.replace(tzinfo=timezone.utc) == START
    assert r.stop_time.replace(tzinfo=timezone.utc) == START + timedelta(seconds=DURATION)
    assert out == {"fetched": 1, "rated": 1, "unrated": 0, "skipped_needs_refresh": 0, "errors": 0}


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
    assert (r.rpe_raw, r.rpe_cr10, r.feel) == (None, None, None)
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
    """Immutability: across first sight, a marker and a rating, every write to the table is an INSERT."""
    _garmin(db_session)
    stmts: list[str] = []
    event.listen(db_session.get_bind(), "before_cursor_execute",
                 lambda c, cur, st, p, ctx, m: stmts.append(st.strip().upper()))
    _run(db_session, FakeSource([_item(11)], {11: _detail()}))
    _run(db_session, FakeSource([], {11: _detail()}), now=NOW + timedelta(days=1))
    _run(db_session, FakeSource([], {11: _detail(rpe=70, feel=75)}), now=NOW + timedelta(days=2))
    touching = [s for s in stmts if "SESSION_RPE_OBSERVATIONS" in s]
    assert touching and not [s for s in touching if s.startswith(("UPDATE", "DELETE"))], touching


def test_a_new_row_never_reuses_an_earlier_capture_time(db_session):
    """A re-rating found in a run with the same clock reading as the previous capture would collide on the unique
    key (user, source, activity, captured_at); the contract places the later row strictly after, so 'latest' stays
    unambiguous."""
    _garmin(db_session)
    _run(db_session, FakeSource([_item(11)], {11: _detail()}))                      # an unrated marker first
    _run(db_session, FakeSource([], {11: _detail(rpe=40, feel=25)}), now=NOW + timedelta(days=1))
    a, b = _rows(db_session, 11)
    assert (a.rpe_cr10, b.rpe_cr10) == (None, 4.0)
    assert b.captured_at.replace(tzinfo=timezone.utc) > a.captured_at.replace(tzinfo=timezone.utc)


# -- failure handling: stop at the first, never a false "unrated" ------------------------------------

def test_the_read_stops_at_the_first_failure_and_keeps_what_it_captured(db_session):
    _garmin(db_session)
    items = [_item(11), _item(12, start=START + timedelta(hours=1)), _item(13, start=START + timedelta(hours=2))]
    src = FakeSource(items, {11: _detail(rpe=40), 12: ConnectionError("boom"), 13: _detail(rpe=50)})
    out = _run(db_session, src)
    assert src.detail_ids() == [11, 12]                                  # 13 not attempted: the order invariant
    assert [r.source_activity_ref for r in _rows(db_session)] == ["11"]
    assert out["errors"] == 1 and out["rated"] == 1


def test_a_shape_change_stops_the_read_at_that_activity(db_session):
    """The same order invariant for a payload that is not a rating: nothing after it is attempted, so the last
    captured start never passes an activity that was not recorded."""
    _garmin(db_session)
    items = [_item(11), _item(12, start=START + timedelta(hours=1)), _item(13, start=START + timedelta(hours=2))]
    src = FakeSource(items, {11: _detail(rpe=40), 12: {"somethingElse": 1}, 13: _detail(rpe=50)})
    out = _run(db_session, src)
    assert src.detail_ids() == [11, 12] and [r.source_activity_ref for r in _rows(db_session)] == ["11"]
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
    assert summary["selfeval"] == {"fetched": 2, "rated": 2, "unrated": 0, "skipped_needs_refresh": 0, "errors": 0}


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
    """`sync_user` catches its own read failures; this is the step's own net, for anything that escapes it. It
    reports the error, rolls back, and the user's HRV outcome stands."""
    _garmin(db_session, 1)
    monkeypatch.setattr(garmin_sync, "sync_hrv_for_user", _fake_hrv)

    def boom(*a, **k):
        raise RuntimeError("step exploded")
    monkeypatch.setattr(gs, "sync_user", boom)
    summary = garmin_sync.sweep_garmin_hrv(db_session, selfeval_factory=lambda b: FakeSource([], {}))
    u = summary["per_user"][1]
    assert u["status"] == "succeeded" and u["selfeval"] == {"error": "RuntimeError: step exploded"}
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


# -- the readout: the MCP lines show the door's per-session rating, from any source ---------------------------------

def _obs(db, ref, rpe_raw=40, feel=25, start=START, minutes=45, now=NOW, uid=1):
    _user(db, uid)
    return srpe_store.record_observation(db, uid, source="garmin", source_activity_ref=ref, start=start,
                                         stop=start + timedelta(minutes=minutes), rpe_raw=rpe_raw,
                                         raw_scale="garmin_0_100", feel=feel, now=now)


def _rating(rpe, feel, source="garmin"):
    return type("R", (), {"rpe_cr10": rpe, "feel": feel, "source": source})


def _lines(mcp_server, db, monkeypatch):
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: 1)
    return mcp_server.get_training_sessions(days=28).split("\n")


def test_format_selfeval_renders_present_values_and_names_the_source():
    assert format_selfeval(_rating(4.0, 25)) == " selfeval=[RPE 4/10 feel 25/100 garmin]"
    assert format_selfeval(_rating(4.5, None)) == " selfeval=[RPE 4.5/10 garmin]"
    assert format_selfeval(_rating(None, 75)) == " selfeval=[feel 75/100 garmin]"
    assert format_selfeval(_rating(3.0, None, "in_app")) == " selfeval=[RPE 3/10 in_app]"


def test_get_training_sessions_shows_the_rating_on_the_session_it_overlaps_only(db_session, monkeypatch):
    import mcp_server
    from aerobic_format import format_aerobic_session
    _user(db_session)
    today = datetime.now(timezone.utc)
    rated = _hc(db_session, start=today - timedelta(days=1), ssid="a")
    plain = _hc(db_session, start=today - timedelta(days=3), ssid="b", pkg="com.sec.android.app.shealth")
    _obs(db_session, "11", start=today - timedelta(days=1), now=today)
    lines = _lines(mcp_server, db_session, monkeypatch)
    assert format_aerobic_session(rated) + " selfeval=[RPE 4/10 feel 25/100 garmin]" in lines
    assert format_aerobic_session(plain) in lines                              # byte-identical when nothing overlaps


def test_the_lines_show_the_current_value_and_not_an_unrated_marker(db_session, monkeypatch):
    import mcp_server
    from aerobic_format import format_aerobic_session
    _user(db_session)
    start = datetime.now(timezone.utc) - timedelta(days=1)
    s = _hc(db_session, start=start)
    _obs(db_session, "11", rpe_raw=40, start=start, now=NOW)
    _obs(db_session, "11", rpe_raw=60, feel=50, start=start, now=NOW + timedelta(days=1))
    assert format_aerobic_session(s) + " selfeval=[RPE 6/10 feel 50/100 garmin]" in _lines(mcp_server, db_session, monkeypatch)
    _obs(db_session, "11", rpe_raw=None, feel=None, start=start, now=NOW + timedelta(days=2))
    assert format_aerobic_session(s) in _lines(mcp_server, db_session, monkeypatch)   # un-rated: nothing shown


def test_a_rating_on_a_lost_twin_lands_on_the_canonical_session_in_the_lines(db_session, monkeypatch):
    """The Garmin Health Connect row lost arbitration to a same-bout Polar row: the rating is placed by overlap, so
    the winner carries it with no carry-over code."""
    import mcp_server
    from aerobic_format import format_aerobic_session
    _user(db_session)
    start = datetime.now(timezone.utc) - timedelta(days=1)
    _hc(db_session, start=start)
    polar = _hc(db_session, start=start, source="polar_v4", pkg=None, ssid="polar-1")
    _obs(db_session, "11", start=start, now=start)
    lines = _lines(mcp_server, db_session, monkeypatch)
    rated = [ln for ln in lines if "selfeval=" in ln]
    assert len(rated) == 1 and rated[0].startswith(format_aerobic_session(polar))


def test_the_whole_day_rating_is_never_shown_on_a_session_line(db_session, monkeypatch):
    import mcp_server
    from aerobic_format import format_aerobic_session
    _user(db_session)
    start = datetime.now(timezone.utc) - timedelta(days=1)
    s = _hc(db_session, start=start)
    db_session.add(models.DailyRecord(user_id=1, date=s.session_date, session_rpe=8.0))
    db_session.commit()
    assert format_aerobic_session(s) in _lines(mcp_server, db_session, monkeypatch)
