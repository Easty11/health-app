"""`garmin_spo2` -- raw Garmin overnight SpO2 capture into spo2_nights / spo2_samples (Q150).

Layers on purpose (FEEDBACK section 23), as in `test_garmin_selfeval`: parsing and storage are tested with
plain payloads, the capture logic with a faked source that records every request, and the no-refresh /
GET-only guarantees against the REAL `garminconnect` client faked at the TRANSPORT, because they live in the
library's own request path.

Payload fixtures carry the shape the live probe saw (16-17 Oct 2026): `epochTimestamp` as an ISO GMT STRING,
`spo2Reading`, `readingConfidence`, `epochDuration: 60`, and the profile id / device id fields the payload also
carries. The two ids are synthetic stand-ins on purpose: they must never reach a column or a log line.
"""
import json
import logging
from datetime import date, datetime, timedelta, timezone

import pytest
from garminconnect import (GarminConnectAuthenticationError, GarminConnectConnectionError,
                           GarminConnectNotFoundError, GarminConnectTooManyRequestsError)
from sqlalchemy import text

import encryption
import garmin_spo2 as gs
import models
from scripts import garmin_identity as gi
from scripts import garmin_spo2_backfill as bf
from scripts import garmin_sync
from tests.test_garmin_selfeval_probe import FakeResp, FakeSession, _blob  # the transport-fake precedent

T0 = datetime(2026, 10, 15, 12, 40, tzinfo=timezone.utc)        # first epoch of a synthetic night
WAKE = date(2026, 10, 16)
FAKE_PROFILE_PK = 111111111                                      # synthetic; never a real id
FAKE_DEVICE_ID = 222222222
FAKE_NAME = "Fake Display Name"


def _epoch(i, *, spo2=97, conf=3, iso=True, dur=60, start=T0):
    t = start + timedelta(minutes=i)
    return {"userProfilePK": FAKE_PROFILE_PK,
            "epochTimestamp": t.strftime("%Y-%m-%dT%H:%M:%S.0") if iso else int(t.timestamp() * 1000),
            "deviceId": FAKE_DEVICE_ID, "calendarDate": "2026-10-15T00:00:00.0",
            "epochDuration": dur, "spo2Reading": spo2, "readingConfidence": conf}


def _ms(dt):
    return int(dt.timestamp() * 1000)


def _payload(n=350, *, skip=(), spo2=None, iso=True, intervals="default", start=T0):
    """`n` one-minute slots from `start`, minus the indexes in `skip` (each a missing epoch)."""
    epochs = [_epoch(i, spo2=(spo2(i) if spo2 else 97), iso=iso, start=start) for i in range(n) if i not in skip]
    if intervals == "default":
        intervals = [{"value": 2, "startGMT": _ms(start), "endGMT": _ms(start)},
                     {"value": 3, "startGMT": _ms(start), "endGMT": _ms(start + timedelta(minutes=50))}]
    return {"dailySleepDTO": {"calendarDate": "2026-10-16", "sleepStartTimestampGMT": _ms(start),
                              "sleepEndTimestampGMT": _ms(start + timedelta(minutes=n)),
                              "averageSpO2Value": 97.0, "lowestSpO2Value": 85},
            gs.SPO2_KEY: epochs, gs.BREATHING_KEY: intervals, "sleepMovement": [{"x": 1}]}


def _user(db, uid=1):
    if db.get(models.User, uid) is None:
        db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
        db.commit()


def _garmin(db, uid=1, secret="garmin-token"):
    _user(db, uid)
    db.add(models.UserIntegration(user_id=uid, provider="garmin", api_key_encrypted=encryption.encrypt(secret)))
    db.commit()


def _nights(db):
    return db.query(models.Spo2Night).order_by(models.Spo2Night.captured_at).all()


def _samples(db, night=None):
    q = db.query(models.Spo2Sample)
    if night is not None:
        q = q.filter_by(spo2_night_id=night.id)
    return q.order_by(models.Spo2Sample.reading_time).all()


class FakeSource:
    """Stands in for ProbeSource: a social profile, then one sleep payload per requested date; records requests.
    `payloads` maps an ISO date to a payload (or an exception instance to raise); an unlisted date has no SpO2."""

    def __init__(self, payloads=None, name=FAKE_NAME):
        self.calls, self.payloads, self.name = [], payloads or {}, name

    def social_profile(self):
        self.calls.append(("profile", None))
        return {"displayName": self.name, "profileId": FAKE_PROFILE_PK}

    def get(self, path, params=None):
        self.calls.append((path, params))
        v = self.payloads.get(params["date"], {"dailySleepDTO": {"calendarDate": params["date"]}})
        if isinstance(v, Exception):
            raise v
        return v


def _run(db, source, start=WAKE, end=WAKE):
    return gs.sync_user(db, 1, start=start, end=end, factory=lambda blob: source)


# -- parsing -----------------------------------------------------------------------------------------

def test_the_real_iso_string_layout_parses_to_utc_epochs_with_every_named_field():
    n = gs.parse_sleep_night(_payload(5), WAKE)
    assert n["reading_count"] == 5 and n["gap_count"] == 0 and n["captured_at"] == WAKE
    first = n["samples"][0]
    assert first == {"reading_time": T0, "spo2_pct": 97.0, "reading_confidence": 3.0, "epoch_duration_s": 60}
    assert n["samples"][-1]["reading_time"] == T0 + timedelta(minutes=4)
    assert n["sleep_start"] == T0 and n["sleep_end"] == T0 + timedelta(minutes=5)


def test_epoch_milliseconds_parse_the_same_as_iso_strings():
    assert gs.parse_sleep_night(_payload(5, iso=False), WAKE)["samples"] == gs.parse_sleep_night(_payload(5), WAKE)["samples"]


def test_a_continuous_night_has_no_gap_and_a_three_minute_hole_is_one_gap_not_two():
    control = gs.parse_sleep_night(_payload(439), WAKE)
    assert (control["reading_count"], control["gap_count"]) == (439, 0)          # the control night: 439 / 0 gaps
    event = gs.parse_sleep_night(_payload(352, skip={100, 101}), WAKE)           # two missing minutes in a row
    assert (event["reading_count"], event["gap_count"]) == (350, 1)              # the event night: 350 / 1 gap
    two = gs.parse_sleep_night(_payload(352, skip={100, 101, 200}), WAKE)
    assert two["gap_count"] == 2


def test_gap_is_measured_against_the_epoch_length_the_epochs_name():
    """Spacing LONGER than the 60 s default but within the named epoch length is not a gap; spacing beyond the
    named length is. (A writer that ignored `epochDuration` would call the first case two gaps.)"""
    def spaced(step_s, dur):
        p = _payload(4)
        for i, e in enumerate(p[gs.SPO2_KEY]):
            e["epochTimestamp"] = (T0 + timedelta(seconds=step_s * i)).strftime("%Y-%m-%dT%H:%M:%S.0")
            e["epochDuration"] = dur
        return gs.parse_sleep_night(p, WAKE)["gap_count"]
    assert spaced(120, 120) == 0                                                  # 2-minute epochs, back to back
    assert spaced(150, 120) == 3                                                  # 30 s over the named length each time
    assert spaced(60, 60) == 0


def test_values_are_stored_raw_no_range_no_confidence_threshold_nulls_kept():
    p = _payload(4)
    p[gs.SPO2_KEY][0]["spo2Reading"] = 0
    p[gs.SPO2_KEY][1]["spo2Reading"] = 255.5
    p[gs.SPO2_KEY][2]["spo2Reading"] = None
    p[gs.SPO2_KEY][3]["readingConfidence"] = 0
    p[gs.SPO2_KEY][3]["spo2Reading"] = "93"                                       # Garmin sometimes sends numbers as strings
    s = gs.parse_sleep_night(p, WAKE)["samples"]
    assert [x["spo2_pct"] for x in s] == [0.0, 255.5, None, 93.0]
    assert s[3]["reading_confidence"] == 0.0


def test_an_element_with_no_usable_time_is_skipped_and_counted_never_a_valued_one():
    p = _payload(3)
    p[gs.SPO2_KEY] += [{"spo2Reading": 90}, "junk", None, {"epochTimestamp": "not-a-time", "spo2Reading": 91}]
    n = gs.parse_sleep_night(p, WAKE)
    assert n["reading_count"] == 3 and n["skipped"] == 4


def test_a_repeated_epoch_time_keeps_the_first_and_counts_the_rest():
    p = _payload(3)
    p[gs.SPO2_KEY].append(_epoch(1, spo2=50))
    n = gs.parse_sleep_night(p, WAKE)
    assert n["reading_count"] == 3 and n["duplicates"] == 1
    assert [x["spo2_pct"] for x in n["samples"]] == [97.0, 97.0, 97.0]


def test_breathing_disruption_intervals_are_kept_raw_zero_length_and_repeated_starts_included():
    n = gs.parse_sleep_night(_payload(3), WAKE)
    assert n["intervals"] == [
        {"seq": 0, "start_time": T0, "end_time": T0, "value": 2.0},
        {"seq": 1, "start_time": T0, "end_time": T0 + timedelta(minutes=50), "value": 3.0}]
    assert gs.parse_sleep_night(_payload(3, intervals=None), WAKE)["intervals"] == []


@pytest.mark.parametrize("payload", [None, [], "x", {}, {gs.SPO2_KEY: None}, {gs.SPO2_KEY: []},
                                     {gs.SPO2_KEY: [{"spo2Reading": 90}]}])
def test_a_payload_with_no_usable_spo2_epochs_is_none(payload):
    assert gs.parse_sleep_night(payload, WAKE) is None


# -- storage -----------------------------------------------------------------------------------------

def test_a_night_is_inserted_with_its_samples_and_intervals(db_session):
    _garmin(db_session)
    out = _run(db_session, FakeSource({"2026-10-16": _payload(352, skip={100, 101})}))
    assert out["nights_inserted"] == 1 and out["readings"] == 350 and out["errors"] == 0
    (night,) = _nights(db_session)
    assert (night.user_id, night.captured_at, night.source) == (1, WAKE, "garmin")
    assert (night.reading_count, night.gap_count) == (350, 1)
    assert _utc(night.sleep_start) == T0 and _utc(night.sleep_end) == T0 + timedelta(minutes=352)
    assert len(_samples(db_session, night)) == 350
    assert db_session.query(models.BreathingDisruptionInterval).filter_by(spo2_night_id=night.id).count() == 2


def _utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def test_a_second_identical_pull_writes_nothing(db_session):
    _garmin(db_session)
    _run(db_session, FakeSource({"2026-10-16": _payload(50)}))
    before = [s.id for s in _samples(db_session)]
    out = _run(db_session, FakeSource({"2026-10-16": _payload(50)}))
    assert out["nights_unchanged"] == 1 and out["nights_inserted"] == 0 and out["readings"] == 0
    assert [s.id for s in _samples(db_session)] == before                         # not even a delete-and-reinsert


def test_a_changed_payload_replaces_the_nights_children_without_accumulating(db_session):
    _garmin(db_session)
    _run(db_session, FakeSource({"2026-10-16": _payload(50)}))
    out = _run(db_session, FakeSource({"2026-10-16": _payload(60, skip={5})}))    # a late device sync added epochs
    assert out["nights_replaced"] == 1 and out["readings"] == 59
    (night,) = _nights(db_session)
    assert (night.reading_count, night.gap_count) == (59, 1)
    assert len(_samples(db_session)) == 59
    assert db_session.query(models.BreathingDisruptionInterval).count() == 2      # replaced, not doubled


def test_a_pull_with_no_spo2_never_wipes_a_stored_night(db_session):
    _garmin(db_session)
    _run(db_session, FakeSource({"2026-10-16": _payload(50)}))
    out = _run(db_session, FakeSource({"2026-10-16": {"dailySleepDTO": {"calendarDate": "2026-10-16"}}}))
    assert out["nights_empty"] == 1
    assert len(_nights(db_session)) == 1 and len(_samples(db_session)) == 50


def test_stored_values_are_raw_including_the_ones_a_detector_would_throw_away(db_session):
    _garmin(db_session)
    p = _payload(4, spo2=lambda i: [0, 255, 85, 100][i])
    p[gs.SPO2_KEY][2]["readingConfidence"] = 0
    _run(db_session, FakeSource({"2026-10-16": p}))
    assert [s.spo2_pct for s in _samples(db_session)] == [0.0, 255.0, 85.0, 100.0]
    assert _samples(db_session)[2].reading_confidence == 0.0


def test_nothing_derived_is_stored_no_min_avg_or_dip_columns():
    cols = {c.name for t in (models.Spo2Night, models.Spo2Sample, models.BreathingDisruptionInterval)
            for c in t.__table__.columns}
    assert cols == {"id", "user_id", "captured_at", "source", "sleep_start", "sleep_end", "reading_count",
                    "gap_count", "created_at", "spo2_night_id", "reading_time", "spo2_pct", "reading_confidence",
                    "epoch_duration_s", "seq", "start_time", "end_time", "value"}


def test_the_garmin_profile_id_and_device_id_never_reach_the_database(db_session):
    _garmin(db_session)
    _run(db_session, FakeSource({"2026-10-16": _payload(20)}))
    for table in ("spo2_nights", "spo2_samples", "breathing_disruption_intervals"):
        rows = db_session.execute(text(f"SELECT * FROM {table}")).fetchall()
        assert rows, table
        dump = json.dumps([[str(v) for v in r] for r in rows])
        assert str(FAKE_PROFILE_PK) not in dump and str(FAKE_DEVICE_ID) not in dump and FAKE_NAME not in dump


def test_two_users_and_two_nights_are_separate_rows(db_session):
    _garmin(db_session, 1)
    _garmin(db_session, 4)
    src = FakeSource({"2026-10-15": _payload(10), "2026-10-16": _payload(12)})
    gs.sync_user(db_session, 1, start=date(2026, 10, 15), end=WAKE, factory=lambda b: src)
    gs.sync_user(db_session, 4, start=WAKE, end=WAKE, factory=lambda b: src)
    assert sorted((n.user_id, n.captured_at, n.reading_count) for n in _nights(db_session)) == [
        (1, date(2026, 10, 15), 10), (1, WAKE, 12), (4, WAKE, 12)]


def test_deleting_the_user_cascades_the_whole_capture(db_session):
    _garmin(db_session)
    _run(db_session, FakeSource({"2026-10-16": _payload(20)}))
    db_session.delete(db_session.get(models.User, 1))
    db_session.commit()
    assert _nights(db_session) == [] and _samples(db_session) == []
    assert db_session.query(models.BreathingDisruptionInterval).count() == 0


def test_retire_user_discovers_the_new_tables_from_the_live_schema(db_session):
    from scripts import retire_user as ru
    graph = ru.discover_graph(db_session.get_bind())
    for t in ("spo2_nights", "spo2_samples", "breathing_disruption_intervals"):
        assert t in graph.scope, t
    assert graph.unenforced == []


# -- the read: requests, stop-at-first-failure, isolation --------------------------------------------

def test_one_profile_get_then_one_sleep_get_per_wake_date_with_the_libraries_params(db_session):
    _garmin(db_session)
    src = FakeSource()
    out = _run(db_session, src, start=date(2026, 10, 14), end=WAKE)
    assert out["nights_fetched"] == 3 and out["nights_empty"] == 3
    assert [c[0] for c in src.calls] == ["profile"] + [f"{gs.SLEEP_PATH}/Fake%20Display%20Name"] * 3
    assert [c[1]["date"] for c in src.calls[1:]] == ["2026-10-14", "2026-10-15", "2026-10-16"]   # oldest first
    assert all(c[1]["nonSleepBufferMinutes"] == "60" for c in src.calls[1:])
    assert _nights(db_session) == []                                              # an empty night makes no row


def test_the_read_stops_at_the_first_failure_and_keeps_what_was_stored(db_session):
    _garmin(db_session)
    src = FakeSource({"2026-10-14": _payload(10), "2026-10-15": RuntimeError("boom"), "2026-10-16": _payload(10)})
    out = _run(db_session, src, start=date(2026, 10, 14), end=WAKE)
    assert out["errors"] == 1 and out["nights_inserted"] == 1 and out["nights_fetched"] == 1
    assert len(src.calls) == 3                                                    # profile, 14th, 15th: the 16th never asked
    assert [n.captured_at for n in _nights(db_session)] == [date(2026, 10, 14)]


def test_a_missing_display_name_is_an_error_not_a_blind_request(db_session):
    _garmin(db_session)
    src = FakeSource(name="")
    out = _run(db_session, src)
    assert out["errors"] == 1 and [c[0] for c in src.calls] == ["profile"]


def test_a_stale_token_is_visible_and_stores_nothing(db_session):
    _garmin(db_session)

    class Stale:
        def social_profile(self):
            raise gi.RefreshWouldBeNeeded()
    out = _run(db_session, Stale())
    assert out["skipped_needs_refresh"] == 1 and out["errors"] == 0 and _nights(db_session) == []


def test_a_user_with_no_garmin_connection_is_a_no_op(db_session):
    _user(db_session)
    assert _run(db_session, FakeSource()) == {k: 0 for k in (
        "nights_fetched", "nights_inserted", "nights_replaced", "nights_unchanged", "nights_empty", "readings",
        "skipped_epochs", "duplicate_epochs", "skipped_needs_refresh", "errors")}


def test_failures_log_the_exception_class_only(db_session, caplog):
    _garmin(db_session)
    src = FakeSource({"2026-10-16": ValueError(f"secret {FAKE_PROFILE_PK} {FAKE_NAME}")})
    with caplog.at_level(logging.DEBUG):
        _run(db_session, src)
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "ValueError" in logged
    assert str(FAKE_PROFILE_PK) not in logged and FAKE_NAME not in logged


# -- no refresh, GET only: the REAL client, faked at the transport ------------------------------------

@pytest.fixture()
def no_token_endpoint(monkeypatch):
    from garminconnect import client as gc

    def forbidden(*a, **k):
        raise AssertionError("a token refresh request was sent")
    monkeypatch.setattr(gc.Client, "_http_post", forbidden)


def _real(db, sess, blob):
    return gs.sync_user(db, 1, start=WAKE, end=WAKE, factory=lambda b: gs.ProbeSource(b, session=sess))


def test_a_real_client_run_is_get_only_hits_the_sleep_endpoint_and_leaves_the_token_alone(db_session, no_token_endpoint):
    blob = _blob(+3600)
    _garmin(db_session, secret=blob)
    stored = db_session.query(models.UserIntegration).first().api_key_encrypted
    sess = FakeSession(FakeResp(200, {"displayName": FAKE_NAME}), FakeResp(200, _payload(30)))
    out = _real(db_session, sess, blob)
    assert [m for m, _, _ in sess.calls] == ["GET", "GET"]
    assert sess.calls[0][1].endswith("/userprofile-service/socialProfile")
    assert sess.calls[1][1].endswith(f"{gs.SLEEP_PATH}/Fake%20Display%20Name")
    assert sess.calls[1][2] == {"date": "2026-10-16", "nonSleepBufferMinutes": "60"}
    assert out["nights_inserted"] == 1 and _nights(db_session)[0].reading_count == 30
    assert db_session.query(models.UserIntegration).first().api_key_encrypted == stored


def test_an_expiring_token_sends_nothing_and_stores_nothing(db_session, no_token_endpoint):
    blob = _blob(-60)
    _garmin(db_session, secret=blob)
    stored = db_session.query(models.UserIntegration).first().api_key_encrypted
    sess = FakeSession()                                                          # any request would IndexError
    out = _real(db_session, sess, blob)
    assert out["skipped_needs_refresh"] == 1 and out["errors"] == 0
    assert sess.calls == [] and _nights(db_session) == []
    assert db_session.query(models.UserIntegration).first().api_key_encrypted == stored


def test_a_401_mid_read_does_not_trigger_the_retry_refresh(db_session, no_token_endpoint):
    blob = _blob(+3600)
    _garmin(db_session, secret=blob)
    sess = FakeSession(FakeResp(200, {"displayName": FAKE_NAME}), FakeResp(401))
    out = _real(db_session, sess, blob)
    assert out["skipped_needs_refresh"] == 1 and len(sess.calls) == 2 and _nights(db_session) == []


def test_the_module_never_sends_a_non_get_or_names_a_write_path():
    import inspect
    src = inspect.getsource(gs)
    for forbidden in ("_http_post", "connectapi(", ".login(", "upload", "requests.", "set_activity"):
        assert forbidden not in src, forbidden
    assert gs.ProbeSource.__mro__[1] is gi.LibrarySource


# -- the sweep: placement, isolation, counts ---------------------------------------------------------

def _fake_hrv(db, uid, start, end):
    return {"from": start.isoformat(), "to": end.isoformat(), "days_with_data": 1, "readings_upserted": 1,
            "samples_upserted": 5}


class NoActivities:
    """A self-evaluation source with nothing to read, so these tests exercise the SpO2 step alone."""
    def get(self, *a, **k):
        return []


def _sweep(db, spo2_factory, **kw):
    return garmin_sync.sweep_garmin_hrv(db, selfeval_factory=lambda b: NoActivities(), spo2_factory=spo2_factory,
                                        start=date(2026, 10, 15), end=WAKE, **kw)


def test_the_sweep_runs_spo2_after_each_users_hrv_pull_and_sums_the_counts(db_session, monkeypatch):
    _garmin(db_session, 1)
    _garmin(db_session, 4)
    order = []
    monkeypatch.setattr(garmin_sync, "sync_hrv_for_user",
                        lambda db, uid, s, e: order.append(f"hrv{uid}") or _fake_hrv(db, uid, s, e))

    def factory(blob):
        order.append("spo2")
        return FakeSource({"2026-10-16": _payload(40)})
    summary = _sweep(db_session, factory)
    assert order == ["hrv1", "spo2", "hrv4", "spo2"]
    assert summary["per_user"][1]["spo2"]["nights_inserted"] == 1
    assert summary["spo2"]["nights_inserted"] == 2 and summary["spo2"]["readings"] == 80
    assert summary["spo2"]["nights_empty"] == 2 and summary["spo2"]["errors"] == 0
    assert {(n.user_id, n.captured_at) for n in _nights(db_session)} == {(1, WAKE), (4, WAKE)}


def test_a_dead_token_user_gets_no_spo2_read_and_the_others_are_unaffected(db_session, monkeypatch):
    from connectors.garmin import GarminReconnectError
    _garmin(db_session, 1)
    _garmin(db_session, 4)

    def hrv(db, uid, s, e):
        if uid == 4:
            raise GarminReconnectError("dead")
        return _fake_hrv(db, uid, s, e)
    monkeypatch.setattr(garmin_sync, "sync_hrv_for_user", hrv)
    built = []
    summary = _sweep(db_session, lambda b: built.append("x") or FakeSource())
    assert built == ["x"]
    assert "spo2" not in summary["per_user"][4] and summary["per_user"][4]["status"] == "reconnect_required"


def test_a_spo2_failure_is_soft_and_never_changes_the_hrv_or_selfeval_outcome(db_session, monkeypatch):
    _garmin(db_session, 1)
    monkeypatch.setattr(garmin_sync, "sync_hrv_for_user", _fake_hrv)

    def factory(blob):
        raise RuntimeError("library blew up")
    summary = _sweep(db_session, factory)
    u = summary["per_user"][1]
    assert u["status"] == "succeeded" and summary["users_succeeded"] == 1 and summary["users_failed"] == 0
    assert u["selfeval"]["errors"] == 0                                           # its sibling step is untouched
    assert u["spo2"]["errors"] == 1 and summary["spo2"]["errors"] == 1


def test_a_failure_outside_the_read_is_also_soft_and_reported(db_session, monkeypatch):
    """`sync_user` catches its own read failures; this is the step's own net, for anything that escapes it."""
    _garmin(db_session, 1)
    monkeypatch.setattr(garmin_sync, "sync_hrv_for_user", _fake_hrv)

    def boom(*a, **k):
        raise RuntimeError("exploded")
    monkeypatch.setattr(gs, "sync_user", boom)
    summary = _sweep(db_session, lambda b: FakeSource())
    u = summary["per_user"][1]
    assert u["status"] == "succeeded" and u["spo2"] == {"error": "RuntimeError: exploded"}
    assert summary["spo2"]["errors"] == 1 and summary["users_failed"] == 0


def test_a_selfeval_failure_does_not_stop_the_spo2_step(db_session, monkeypatch):
    _garmin(db_session, 1)
    monkeypatch.setattr(garmin_sync, "sync_hrv_for_user", _fake_hrv)

    def bad_selfeval(blob):
        raise RuntimeError("selfeval blew up")
    summary = garmin_sync.sweep_garmin_hrv(
        db_session, selfeval_factory=bad_selfeval, spo2_factory=lambda b: FakeSource({"2026-10-16": _payload(10)}),
        start=WAKE, end=WAKE)
    assert summary["per_user"][1]["spo2"]["nights_inserted"] == 1


def test_a_stale_token_is_visible_in_the_sweep_summary(db_session, monkeypatch):
    _garmin(db_session, 1)
    monkeypatch.setattr(garmin_sync, "sync_hrv_for_user", _fake_hrv)

    class Stale:
        def social_profile(self):
            raise gi.RefreshWouldBeNeeded()
    assert _sweep(db_session, lambda b: Stale())["spo2"]["skipped_needs_refresh"] == 1


def test_the_nightly_brief_carries_the_spo2_counts():
    import load_sweep
    brief = load_sweep._summary_brief({"load": {}, "garmin": {"users_attempted": 1, "spo2": {"nights_inserted": 2}}})
    assert brief["garmin"]["spo2"] == {"nights_inserted": 2}


# -- the backfill ------------------------------------------------------------------------------------

def _history(first=date(2026, 10, 16), nights=4, n=20):
    """SpO2 on `nights` consecutive wake-dates ending at `first`, counting back; nothing before that."""
    return {(first - timedelta(days=i)).isoformat(): _payload(n, start=T0 - timedelta(days=i)) for i in range(nights)}


def _walk(db, source, **kw):
    kw.setdefault("newest", WAKE)
    kw.setdefault("pause", 0)
    return bf.backfill(db, 1, source, sleep=lambda s: None, **kw)


def test_the_walk_goes_back_until_the_run_of_empty_nights_and_reports_how_far(db_session):
    _garmin(db_session)
    rep = _walk(db_session, FakeSource(_history(nights=4)), max_days=60, stop_after_empty=3)
    assert rep["stopped"] == "empty_streak" and rep["nights_tried"] == 4 + 3
    assert (rep["nights_with_spo2"], rep["epochs"], rep["nights_inserted"]) == (4, 80, 4)
    assert (rep["earliest"], rep["latest"]) == (date(2026, 10, 13), WAKE)
    assert len(_nights(db_session)) == 4
    assert rep["last_date_reached"] == date(2026, 10, 10)                         # the last empty night it asked about
    text_ = bf.format_report(rep, user_id=1, newest=WAKE, dry_run=False)
    assert "stopped at empty streak: 3 nights in a row carried no SpO2" in text_
    assert "NOT evidence that the history ends here" in text_ and "Pulse Ox switched off" in text_
    assert "last date reached: 2026-10-10" in text_ and "--newest 2026-10-09" in text_
    assert "exhausted" not in text_.lower()                                        # never "history exhausted"


def test_a_rerun_is_idempotent(db_session):
    _garmin(db_session)
    _walk(db_session, FakeSource(_history()), max_days=60, stop_after_empty=3)
    ids = [s.id for s in _samples(db_session)]
    rep = _walk(db_session, FakeSource(_history()), max_days=60, stop_after_empty=3)
    assert rep["nights_unchanged"] == 4 and rep["nights_inserted"] == 0
    assert [s.id for s in _samples(db_session)] == ids


def test_an_isolated_empty_night_inside_the_history_does_not_end_the_walk(db_session):
    _garmin(db_session)
    h = _history(nights=6)
    del h["2026-10-14"]                                                            # a night the watch was off
    rep = _walk(db_session, FakeSource(h), max_days=60, stop_after_empty=3)
    assert rep["nights_with_spo2"] == 5 and rep["earliest"] == date(2026, 10, 11)
    assert rep["nights_tried"] == 9                  # 16..11 (one empty among them), then three empties in a row: 10, 9, 8


def test_dry_run_fetches_and_reports_but_writes_nothing(db_session):
    _garmin(db_session)
    rep = _walk(db_session, FakeSource(_history()), max_days=60, stop_after_empty=3, dry_run=True)
    assert rep["nights_with_spo2"] == 4 and rep["epochs"] == 80 and rep["nights_inserted"] == 0
    assert _nights(db_session) == [] and _samples(db_session) == []


def test_the_day_cap_is_reported_as_the_reason_when_data_is_still_coming(db_session):
    _garmin(db_session)
    rep = _walk(db_session, FakeSource(_history(nights=10)), max_days=5, stop_after_empty=3)
    assert rep["stopped"] == "max_days" and rep["nights_tried"] == 5 and rep["earliest"] == date(2026, 10, 12)
    text_ = bf.format_report(rep, user_id=1, newest=WAKE, dry_run=False)
    assert "stopped at the --max-days cap" in text_ and "--newest 2026-10-11" in text_ and "last date reached: 2026-10-12" in text_


def test_a_failure_stops_the_walk_keeps_what_was_stored_and_names_the_class(db_session):
    _garmin(db_session)
    h = _history(nights=4)
    h["2026-10-14"] = RuntimeError(f"secret {FAKE_NAME}")
    rep = _walk(db_session, FakeSource(h), max_days=60, stop_after_empty=3)
    assert rep["stopped"] == "error:RuntimeError" and rep["nights_inserted"] == 2
    text_ = bf.format_report(rep, user_id=1, newest=WAKE, dry_run=False)
    assert FAKE_NAME not in text_ and "RuntimeError" in text_
    assert rep["last_date_reached"] == date(2026, 10, 15) and rep["failed_on"] == date(2026, 10, 14)
    assert "last date reached: 2026-10-15" in text_


def test_a_stale_token_stops_the_walk_before_anything_is_sent_for_a_night(db_session):
    _garmin(db_session)

    class Stale:
        def social_profile(self):
            raise gi.RefreshWouldBeNeeded()
    rep = _walk(db_session, Stale())
    assert rep["stopped"] == "needs_refresh" and rep["nights_tried"] == 0
    assert "Open the app's Garmin card" in bf.format_report(rep, user_id=1, newest=WAKE, dry_run=False)


def test_the_walk_pauses_between_nights_not_before_the_first(db_session):
    _garmin(db_session)
    pauses = []
    bf.backfill(db_session, 1, FakeSource(_history(nights=3)), newest=WAKE, max_days=3, stop_after_empty=9,
                pause=1.5, sleep=pauses.append)
    assert pauses == [1.5, 1.5]


def test_main_runs_end_to_end_prints_how_far_back_and_exits_clean(db_session, monkeypatch, capsys):
    _garmin(db_session)
    monkeypatch.setattr(bf, "SessionLocal", lambda: db_session)
    pauses = []
    rc = bf.main(["--user-id", "1", "--newest", "2026-10-16", "--stop-after-empty", "3"],
                 factory=lambda blob: FakeSource(_history(nights=3)), sleep=pauses.append)
    out = capsys.readouterr().out
    assert rc == 0
    assert "nights with SpO2 found: 2026-10-14 -> 2026-10-16 (3 calendar days, 3 nights with data)" in out
    assert "stopped at empty streak" in out and "inserted 3" in out
    assert pauses and set(pauses) == {3.0}                                         # the default pause is the 3 s floor
    assert FAKE_NAME not in out and str(FAKE_PROFILE_PK) not in out and "garmin-token" not in out


def test_main_exit_codes_no_connection_and_stale_token(db_session, monkeypatch, capsys):
    monkeypatch.setattr(bf, "SessionLocal", lambda: db_session)
    _user(db_session)
    assert bf.main(["--user-id", "1"], factory=lambda b: FakeSource()) == 1
    assert "no Garmin connection" in capsys.readouterr().out

    class Stale:
        def social_profile(self):
            raise gi.RefreshWouldBeNeeded()
    _garmin(db_session)
    assert bf.main(["--user-id", "1"], factory=lambda b: Stale(), sleep=lambda s: None) == 2


def test_main_dry_run_says_so_and_writes_nothing(db_session, monkeypatch, capsys):
    _garmin(db_session)
    monkeypatch.setattr(bf, "SessionLocal", lambda: db_session)
    rc = bf.main(["--user-id", "1", "--newest", "2026-10-16", "--stop-after-empty", "2", "--dry-run"],
                 factory=lambda blob: FakeSource(_history(nights=2)), sleep=lambda s: None)
    assert rc == 0 and "[DRY RUN: nothing written]" in capsys.readouterr().out
    assert _nights(db_session) == []


# -- the backfill's pacing and its abort on Garmin pushing back -------------------------------------

def test_the_pause_floor_is_three_seconds_and_the_command_line_enforces_it(db_session, capsys):
    assert bf.MIN_PAUSE_S == 3.0 and bf.DEFAULT_PAUSE_S >= bf.MIN_PAUSE_S
    for bad in ("0", "1", "2.9"):
        with pytest.raises(SystemExit) as e:
            bf.main(["--user-id", "1", "--pause", bad])
        assert e.value.code == 2
    assert "at least 3 seconds" in capsys.readouterr().err


@pytest.mark.parametrize("exc, expect", [
    (GarminConnectTooManyRequestsError("login rate limited"), "HTTP 429"),
    (GarminConnectConnectionError("API Error 429"), "HTTP 429"),
    (GarminConnectConnectionError("API Error 429 - slow down"), "HTTP 429"),
    (GarminConnectConnectionError("API Error 403"), "HTTP 403"),
    (json.JSONDecodeError("Expecting value", "<html>Just a moment...</html>", 0), "not JSON"),
])
def test_garmin_pushing_back_is_recognised(exc, expect):
    assert expect in bf.classify_block(exc)


@pytest.mark.parametrize("exc", [
    GarminConnectNotFoundError("API Error 404"),                  # a missing resource: loud, but not a block
    GarminConnectConnectionError("API Error 500"),
    GarminConnectConnectionError("API Error 4290"),               # not 429
    GarminConnectAuthenticationError("auth"),
    ValueError("Invalid API path: 'x'"),                          # our own bug, not a challenge page
    RuntimeError("boom"),
])
def test_other_failures_are_not_mistaken_for_a_block(exc):
    assert bf.classify_block(exc) is None


@pytest.mark.parametrize("exc, words", [
    (GarminConnectTooManyRequestsError("429"), "HTTP 429"),
    (GarminConnectConnectionError("API Error 429"), "HTTP 429"),
    (GarminConnectConnectionError("API Error 403"), "HTTP 403"),
    (json.JSONDecodeError("Expecting value", "<html>", 0), "not JSON"),
])
def test_the_first_429_403_or_challenge_aborts_the_whole_run_with_no_retry(db_session, exc, words):
    _garmin(db_session)
    h = _history(nights=6)
    h["2026-10-14"] = exc                                          # the third night asked about
    src = FakeSource(h)
    pauses = []
    rep = bf.backfill(db_session, 1, src, newest=WAKE, max_days=60, stop_after_empty=3, pause=3.0, sleep=pauses.append)
    assert rep["stopped"] == "blocked" and words in rep["block"]
    assert rep["failed_on"] == date(2026, 10, 14) and rep["last_date_reached"] == date(2026, 10, 15)
    dates_asked = [c[1]["date"] for c in src.calls[1:]]
    assert dates_asked == ["2026-10-16", "2026-10-15", "2026-10-14"]  # the failing night once; nothing after it, no retry
    assert len(pauses) == 2                                          # no extra wait to "try again"
    assert [n.captured_at for n in _nights(db_session)] == [date(2026, 10, 15), WAKE]   # what was stored stays
    text_ = bf.format_report(rep, user_id=1, newest=WAKE, dry_run=False)
    assert "ABORTED" in text_ and "Nothing was retried" in text_ and "Wait hours, not minutes" in text_
    assert "last date reached: 2026-10-15" in text_ and "--newest 2026-10-14" in text_


def test_main_exits_3_on_a_block_and_prints_the_last_date_reached(db_session, monkeypatch, capsys):
    _garmin(db_session)
    monkeypatch.setattr(bf, "SessionLocal", lambda: db_session)
    h = _history(nights=4)
    h["2026-10-15"] = GarminConnectConnectionError("API Error 403")
    rc = bf.main(["--user-id", "1", "--newest", "2026-10-16"], factory=lambda b: FakeSource(h), sleep=lambda s: None)
    out = capsys.readouterr().out
    assert rc == 3 and "ABORTED" in out and "last date reached: 2026-10-16" in out


# The classification reads the status out of the library's message, so it is proved against the REAL client, faked
# at the transport (FEEDBACK section 23): 429 and 403 come back as "API Error <n>", a challenge page as a non-JSON 200.

class _HtmlResp(FakeResp):
    def json(self):
        raise json.JSONDecodeError("Expecting value", "<html>Just a moment...</html>", 0)


@pytest.mark.parametrize("bad, words", [
    (FakeResp(429), "HTTP 429"),
    (FakeResp(403), "HTTP 403"),
    (_HtmlResp(200), "not JSON"),
])
def test_the_real_client_surfaces_429_403_and_a_challenge_page_as_a_block_with_exactly_one_request(
        db_session, no_token_endpoint, bad, words):
    _garmin(db_session)
    sess = FakeSession(FakeResp(200, {"displayName": FAKE_NAME}), bad, FakeResp(200, _payload(5)))   # a 3rd reply must stay unused
    rep = bf.backfill(db_session, 1, gs.ProbeSource(_blob(+3600), session=sess), newest=WAKE, max_days=5,
                      stop_after_empty=3, pause=3.0, sleep=lambda s: None)
    assert rep["stopped"] == "blocked" and words in rep["block"]
    assert [m for m, _, _ in sess.calls] == ["GET", "GET"]            # the profile and the one sleep GET; no retry
    assert rep["last_date_reached"] is None and rep["failed_on"] == WAKE
    assert _nights(db_session) == []
