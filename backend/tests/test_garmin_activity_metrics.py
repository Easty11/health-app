"""Garmin activity metrics (`garmin_activity_metrics`) and the activity HR stream (`garmin` / `activity_details`).

Layers (FEEDBACK section 23): the parsers on payload fixtures shaped like the operator's 6 Nov 2026 `--keys`
probe (activity 24970929418; values synthetic), the capture through a recording fake source, and the stream
fetch through the REAL `PersonalClient` against a fake host at the TRANSPORT. Then the zoning rule (a Garmin
Health Connect row may read the activity stream, densest alone; the wellness lane never), the read-time
placement on sessions and the MCP line. The backfill script: `test_garmin_activity_backfill.py`.
"""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import null

import encryption
import garmin_activity_metrics as gam
import garmin_selfeval as gs
import hc_zone_enrich
import models
from aerobic_format import format_garmin_metrics
from connectors import garmin_personal as gp
from garmin_personal_fakes import FAKE_KEY, FakeHost
from reads.garmin_metrics_reads import garmin_metrics_by_session
from scripts import garmin_sync

NOW = datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc)
START = datetime(2026, 11, 5, 7, 0, tzinfo=timezone.utc)          # the ride: 10 minutes
DUR = 600.0
GARMIN_PKG = "com.garmin.android.apps.connectmobile"
AID = 24970929418


def _user(db, uid=1):
    if db.get(models.User, uid) is None:
        db.add(models.User(id=uid, email=f"u{uid}@example.com", hashed_password="x"))
        db.commit()


def _personal(db, uid=1):
    _user(db, uid)
    db.add(models.UserIntegration(user_id=uid, provider="garmin_personal", api_key_encrypted=encryption.encrypt(FAKE_KEY)))
    db.commit()


def _summary(**over):
    s = {"calories": 612.0, "bmrCalories": 70.0, "trainingEffect": 5.0, "anaerobicTrainingEffect": 2.1,
         "trainingEffectLabel": "VO2MAX", "activityTrainingLoad": 276.0, "avgRespirationRate": 31.2,
         "maxRespirationRate": 44.0, "minRespirationRate": 18.5, "averageHR": 150.0, "maxHR": 171.0,
         "minHR": 95.0, "recoveryHeartRate": 120.0, "moderateIntensityMinutes": 2, "vigorousIntensityMinutes": 8,
         "waterEstimated": 410.0, "differenceBodyBattery": -9, "startTimeGMT": START.strftime("%Y-%m-%dT%H:%M:%S.0"),
         "startTimeLocal": "2026-11-05T17:00:00.0", "duration": DUR, "elapsedDuration": DUR,
         "directWorkoutRpe": 70, "directWorkoutFeel": 50}
    s.update(over)
    return s


def _item(aid=AID, start=START, duration=DUR):
    return {"activityId": aid, "startTimeGMT": start.strftime("%Y-%m-%d %H:%M:%S"), "duration": duration,
            "activityType": {"typeKey": "indoor_cycling"}}


def _details(rows, *, total=None, shuffle=False):
    """A details payload. `rows` are `(epoch_ms, bpm)` pairs. Shuffled: HR at index 2, the timestamp at 1, another
    metric at 0 — positions must come from `metricDescriptors`, never be assumed."""
    if shuffle:
        desc = [{"key": "directBodyBattery", "metricsIndex": 0, "unit": {"key": "dimensionless"}},
                {"key": "directHeartRate", "metricsIndex": 2, "unit": {"key": "bpm"}},
                {"key": "directTimestamp", "metricsIndex": 1, "unit": {"key": "gmt"}}]
        metrics = [{"metrics": [55.0, ts, hr]} for ts, hr in rows]
    else:
        desc = [{"key": "directTimestamp", "metricsIndex": 0, "unit": {"key": "gmt"}},
                {"key": "directHeartRate", "metricsIndex": 1, "unit": {"key": "bpm"}}]
        metrics = [{"metrics": [ts, hr]} for ts, hr in rows]
    return {"activityId": AID, "measurementCount": len(desc), "metricsCount": len(rows),
            "totalMetricsCount": len(rows) if total is None else total, "detailsAvailable": True,
            "metricDescriptors": desc, "activityDetailMetrics": metrics, "heartRateDTOs": None,
            "pendingData": None, "geoPolylineDTO": None}


def _ms(t):
    return int(t.timestamp() * 1000)


def _ride(step_s=1, bpm=120, start=START, seconds=int(DUR)):
    return [(_ms(start + timedelta(seconds=i)), float(bpm)) for i in range(0, seconds + 1, step_s)]


class FakeSource:
    """Records every request. `details` maps activity id -> detail payload; `streams` id -> details payload."""

    def __init__(self, items, details, streams=None):
        self.calls, self.items, self.details, self.streams = [], items, details, streams or {}

    def get(self, path, params=None):
        self.calls.append((path, params))
        if path == gs.ACTIVITY_LIST_PATH:
            return self.items
        if path.endswith("/details"):
            return self.streams[int(path.split("/")[-2])]
        return self.details[int(path.rsplit("/", 1)[1])]


def _metric_rows(db):
    return db.query(models.GarminActivityMetric).all()


def _stream(db):
    return db.query(models.HrSample).order_by(models.HrSample.sample_time).all()


# -- 1. summary metrics ----------------------------------------------------------------------------

def test_the_summary_is_upserted_from_the_same_detail_with_training_effect_as_aerobic(db_session):
    _user(db_session)
    src = FakeSource([_item()], {AID: {"activityId": AID, "summaryDTO": _summary()}})
    out = gs.sync_user(db_session, 1, source=src, now=NOW)
    (m,) = _metric_rows(db_session)
    assert (m.garmin_activity_id, m.calories, m.bmr_calories, m.te_aerobic, m.te_anaerobic, m.te_label,
            m.training_load) == (AID, 612.0, 70.0, 5.0, 2.1, "VO2MAX", 276.0)
    assert (m.resp_avg, m.resp_max, m.resp_min, m.recovery_hr) == (31.2, 44.0, 18.5, 120.0)
    assert (m.intensity_min_moderate, m.intensity_min_vigorous, m.water_estimated_ml, m.body_battery_delta) == (2, 8, 410.0, -9)
    assert m.start_time_gmt.replace(tzinfo=timezone.utc) == START and m.duration_s == DUR
    assert m.summary_raw == _summary() and m.hr_stream_fetched_at is None
    assert out["metrics_upserted"] == 1 and out["metrics_errors"] == 0 and out["rated"] == 1
    # The summary cost no request: one list GET and one detail GET, no details stream.
    assert [p for p, _ in src.calls] == [gs.ACTIVITY_LIST_PATH, f"{gs.ACTIVITY_PATH}/{AID}"]


def test_a_reupsert_updates_in_place_and_keeps_the_stream_mark(db_session):
    _user(db_session)
    gam.upsert_metrics(db_session, 1, AID, {"summaryDTO": _summary()}, now=NOW)
    db_session.commit()
    _metric_rows(db_session)[0].hr_stream_fetched_at = NOW
    db_session.commit()
    gam.upsert_metrics(db_session, 1, AID, {"summaryDTO": _summary(activityTrainingLoad=280.0)}, now=NOW + timedelta(days=1))
    db_session.commit()
    (m,) = _metric_rows(db_session)
    assert m.training_load == 280.0 and m.hr_stream_fetched_at is not None


def test_missing_and_unusable_keys_are_null_never_an_error(db_session):
    _user(db_session)
    summary = {"calories": "612", "trainingEffect": True, "anaerobicTrainingEffect": None, "duration": float("nan")}
    assert gam.upsert_metrics(db_session, 1, AID, {"summaryDTO": summary}, now=NOW, start=START, duration_s=DUR)
    db_session.commit()
    (m,) = _metric_rows(db_session)
    assert (m.calories, m.te_aerobic, m.te_anaerobic, m.te_label, m.training_load, m.resp_avg) == (None,) * 6
    assert m.start_time_gmt.replace(tzinfo=timezone.utc) == START and m.duration_s == DUR     # the list's window


@pytest.mark.parametrize("detail", [{}, {"summaryDTO": None}, {"summaryDTO": []}, None, "x"])
def test_a_detail_without_a_summary_object_writes_no_row(db_session, detail):
    _user(db_session)
    assert gam.upsert_metrics(db_session, 1, AID, detail, now=NOW) is False
    assert _metric_rows(db_session) == []


def test_a_metrics_failure_never_costs_the_rating(db_session, monkeypatch):
    _user(db_session)
    monkeypatch.setattr(gam, "upsert_metrics", lambda *a, **k: 1 / 0)
    out = gs.sync_user(db_session, 1, source=FakeSource([_item()], {AID: {"summaryDTO": _summary()}}), now=NOW)
    assert out["metrics_errors"] == 1 and out["rated"] == 1 and out["errors"] == 0
    assert db_session.query(models.SessionRpeObservation).count() == 1


# -- 2. the HR stream: parsing -------------------------------------------------------------------------

def test_indices_come_from_the_descriptors_not_positions():
    p = gam.parse_hr_stream(_details(_ride(seconds=4, bpm=131), shuffle=True))
    assert [b for _, b in p.samples] == [131] * 5
    assert p.samples[0][0] == START and p.interval_s == 1.0 and p.has_hr


def test_null_bpm_and_null_timestamps_are_skipped_and_counted():
    rows = [(_ms(START), 120.0), (_ms(START + timedelta(seconds=1)), None), (None, 125.0),
            (_ms(START + timedelta(seconds=2)), 122.6)]
    p = gam.parse_hr_stream(_details(rows))
    assert p.samples == [(START, 120), (START + timedelta(seconds=2), 123)] and p.null_bpm == 1


def test_no_hr_descriptor_means_no_samples_not_an_error():
    d = _details(_ride(seconds=3))
    d["metricDescriptors"] = [x for x in d["metricDescriptors"] if x["key"] != "directHeartRate"]
    p = gam.parse_hr_stream(d)
    assert p.samples == [] and not p.has_hr


def test_a_non_object_payload_is_a_shape_change():
    with pytest.raises(ValueError):
        gam.parse_hr_stream([1, 2])


def test_thinning_is_reported_with_the_effective_interval():
    p = gam.parse_hr_stream(_details(_ride(step_s=5, seconds=100), total=101))
    assert p.thinned and p.rows == 21 and p.total_rows == 101 and p.interval_s == 5.0
    assert not gam.parse_hr_stream(_details(_ride(seconds=10))).thinned


# -- 3. the HR stream: capture through the real client ------------------------------------------------

def _host(details):
    host = FakeHost()
    host.set(f"{gp.ACTIVITY_PATH}/{AID}/details", details)
    return host


def _metrics_row(db, aid=AID, start=START):
    gam.upsert_metrics(db, 1, aid, {"summaryDTO": _summary(startTimeGMT=start.strftime("%Y-%m-%d %H:%M:%S"))}, now=NOW)
    db.commit()


def test_the_stream_is_written_under_r2_only_with_full_resolution_asked(db_session):
    _user(db_session)
    _metrics_row(db_session)
    host = _host(_details(_ride(seconds=59)))
    with gp.PersonalClient(FAKE_KEY, transport=host.transport()) as client:
        out = gam.sync_streams(db_session, 1, client, now=NOW)
    samples = _stream(db_session)
    assert len(samples) == 60 and {(s.source, s.source_package) for s in samples} == {("garmin", "activity_details")}
    assert out == {"stream_fetched": 1, "stream_samples": 60, "stream_thinned": 0, "stream_param_fallback": 0,
                   "stream_errors": 0}
    (_, path, params), = host.requests
    assert path.endswith(f"/{AID}/details") and params == {"maxChartSize": "100000", "maxPolylineSize": "0"}
    (m,) = _metric_rows(db_session)
    assert m.hr_stream_samples == 60 and m.hr_stream_fetched_at is not None


def test_a_captured_stream_is_not_fetched_again_and_a_restore_inserts_nothing(db_session):
    _user(db_session)
    _metrics_row(db_session)
    host = _host(_details(_ride(seconds=9)))
    with gp.PersonalClient(FAKE_KEY, transport=host.transport()) as client:
        gam.sync_streams(db_session, 1, client, now=NOW)
        again = gam.sync_streams(db_session, 1, client, now=NOW)
    assert again["stream_fetched"] == 0 and len(host.requests) == 1
    assert gam.store_stream_samples(db_session, 1, gam.parse_hr_stream(_details(_ride(seconds=9))).samples) == 0


def test_a_404_marks_the_stream_captured_with_no_samples(db_session):
    _user(db_session)
    _metrics_row(db_session)
    with gp.PersonalClient(FAKE_KEY, transport=FakeHost().transport()) as client:
        out = gam.sync_streams(db_session, 1, client, now=NOW)
    assert out["stream_fetched"] == 1 and out["stream_errors"] == 0 and _metric_rows(db_session)[0].hr_stream_samples == 0


def test_a_host_refusing_the_parameters_is_retried_once_without_them(db_session):
    _user(db_session)
    _metrics_row(db_session)
    host = FakeHost()
    host.set(f"{gp.ACTIVITY_PATH}/{AID}/details", _details(_ride(step_s=5, seconds=100), total=101))
    orig = host._handle

    def handle(request):                         # a 400 when the resolution parameters are sent
        if request.url.path.endswith("/details") and request.url.params:
            import httpx
            return httpx.Response(400)
        return orig(request)
    host._handle = handle
    with gp.PersonalClient(FAKE_KEY, transport=host.transport()) as client:
        out = gam.sync_streams(db_session, 1, client, now=NOW)
    assert out["stream_param_fallback"] == 1 and out["stream_thinned"] == 1 and out["stream_samples"] == 21


def test_a_stream_failure_stops_the_pass_soft_and_leaves_the_row_unmarked(db_session):
    _user(db_session)
    _metrics_row(db_session)
    host = FakeHost()
    host.status_for[f"{gp.ACTIVITY_PATH}/{AID}/details"] = 429
    with gp.PersonalClient(FAKE_KEY, transport=host.transport()) as client:
        out = gam.sync_streams(db_session, 1, client, now=NOW)
    assert out["stream_errors"] == 1 and out["stream_fetched"] == 0
    assert _metric_rows(db_session)[0].hr_stream_fetched_at is None and _stream(db_session) == []


def test_the_sweep_reads_ratings_metrics_and_streams_and_sums_the_counts(db_session, monkeypatch):
    _personal(db_session, 1)
    monkeypatch.setattr(garmin_sync, "sync_hrv_for_user", lambda db, uid, s, e: {
        "from": s.isoformat(), "to": e.isoformat(), "days_with_data": 0, "readings_upserted": 0, "samples_upserted": 0})
    host = FakeHost()
    host.set(gp.ACTIVITY_LIST_PATH, [_item()])
    host.set(f"{gp.ACTIVITY_PATH}/{AID}", {"activityId": AID, "summaryDTO": _summary()})
    host.set(f"{gp.ACTIVITY_PATH}/{AID}/details", _details(_ride(seconds=29)))
    summary = garmin_sync.sweep_garmin_hrv(db_session, personal_transport=host.transport())
    ev = summary["selfeval"]
    assert (ev["rated"], ev["metrics_upserted"], ev["stream_fetched"], ev["stream_samples"], ev["errors"]) == (1, 1, 1, 30, 0)


# -- 4. zoning: a Garmin HC row may read the activity stream, densest alone ---------------------------

def _anchors(db):
    db.add(models.UserHrmax(user_id=1, effective_from=date(2026, 6, 1), hrmax_bpm=173, provenance="observed", note="t"))
    db.add(models.UserHrAnchor(user_id=1, kind="rhr", effective_from=date(2026, 6, 1), bpm=0, provenance="stated", note="t"))
    db.commit()


def _hc_row(db, *, pkg=GARMIN_PKG, source="health_connect", ssid="g1", sport="Walking"):
    kw = {z: null() for z in ("z1_seconds", "z2_seconds", "z3_seconds", "z4_seconds", "z5_seconds")} \
        if source == "health_connect" else {"z1_seconds": 10, "z2_seconds": 20, "z3_seconds": 30, "z4_seconds": 40,
                                            "z5_seconds": 50, "hr_avg": 150, "hr_max": 170}
    r = models.AerobicSession(user_id=1, source=source, source_session_id=ssid, session_date=START.date(),
                              start_time=START, stop_time=START + timedelta(seconds=DUR), sport_name=sport,
                              duration_minutes=DUR / 60, source_package=pkg if source == "health_connect" else None, **kw)
    db.add(r)
    db.commit()
    return r


def _put(db, source, pkg, step_s, bpm):
    db.add_all(models.HrSample(user_id=1, sample_time=START + timedelta(seconds=i), bpm=bpm, source=source,
                               source_package=pkg) for i in range(0, int(DUR) + 1, step_s))
    db.commit()


def _zones(db, row):
    db.expire_all()
    r = db.get(models.AerobicSession, row.id)
    return (r.z1_seconds, r.z2_seconds, r.z3_seconds, r.z4_seconds, r.z5_seconds), r.hr_avg


def test_a_garmin_hc_row_zones_from_the_denser_activity_stream(db_session):
    _user(db_session)
    _anchors(db_session)
    row = _hc_row(db_session)
    _put(db_session, "health_connect", GARMIN_PKG, 120, 150)          # sparse: coverage 0.5, withheld alone
    _put(db_session, "garmin", "activity_details", 1, 120)            # the dense stream: 120/173 = z2
    out = hc_zone_enrich.enrich_user(db_session, 1)
    zones, avg = _zones(db_session, row)
    assert out["zoned"] == 1 and zones == (0, 600, 0, 0, 0) and avg == 120


def test_a_denser_hc_trace_still_wins_and_a_tie_keeps_the_hc_trace(db_session):
    _user(db_session)
    _anchors(db_session)
    row = _hc_row(db_session)
    _put(db_session, "health_connect", GARMIN_PKG, 1, 150)
    _put(db_session, "garmin", "activity_details", 1, 120)
    hc_zone_enrich.enrich_user(db_session, 1)
    assert _zones(db_session, row)[1] == 150


def test_the_wellness_lane_is_never_read_for_a_session(db_session):
    _user(db_session)
    _anchors(db_session)
    row = _hc_row(db_session)
    _put(db_session, "garmin", "personal_api", 1, 120)                 # dense all-day HR inside the bout
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["zoned"] == 0 and _zones(db_session, row) == ((None,) * 5, None)   # INV-7: withheld, NULL
    for src, pkg in (("health_connect", GARMIN_PKG), ("health_connect", "x"), ("polar_v4", None),
                     ("polar_flow_export", None), ("hevy", None)):
        assert gam.WELLNESS_WRITER not in hc_zone_enrich.sample_writers_for(SimpleNamespace(source=src, source_package=pkg))


def test_no_other_row_type_gains_the_activity_stream(db_session):
    assert hc_zone_enrich.GARMIN_ACTIVITY_WRITER == gam.GARMIN_ACTIVITY_WRITER
    for src, pkg in (("health_connect", "com.sec.android.app.shealth"), ("health_connect", "fi.polar.polarflow"),
                     ("health_connect", None), ("polar_v4", None), ("polar_flow_export", None)):
        assert gam.GARMIN_ACTIVITY_WRITER not in hc_zone_enrich.sample_writers_for(SimpleNamespace(source=src, source_package=pkg))
    assert hc_zone_enrich.sample_writers_for(SimpleNamespace(source="health_connect", source_package=GARMIN_PKG)) == (
        ("health_connect", GARMIN_PKG), ("garmin", "activity_details"))


def test_a_samsung_row_and_a_polar_row_ignore_a_garmin_activity_stream(db_session):
    _user(db_session)
    _anchors(db_session)
    sam = _hc_row(db_session, pkg="com.sec.android.app.shealth", ssid="s1")
    pol = _hc_row(db_session, source="polar_v4", ssid="p1")
    _put(db_session, "garmin", "activity_details", 1, 120)
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert _zones(db_session, sam) == ((None,) * 5, None)
    assert _zones(db_session, pol) == ((10, 20, 30, 40, 50), 150) and out["polar_vendor_fallback"] == 1


# -- 5. read-time placement, the API and the MCP line ---------------------------------------------------

def test_metrics_are_placed_on_the_overlapping_row_and_nowhere_else(db_session):
    _user(db_session)
    ride = _hc_row(db_session)
    other = _hc_row(db_session, ssid="g2")
    other.start_time, other.stop_time = START + timedelta(hours=3), START + timedelta(hours=3, minutes=10)
    db_session.commit()
    _metrics_row(db_session)
    placed = garmin_metrics_by_session(db_session, 1, [ride, other])
    assert set(placed) == {ride.id}
    assert placed[ride.id]["vendor"] == "Garmin" and placed[ride.id]["te_aerobic"] == 5.0
    assert placed[ride.id]["training_load"] == 276.0 and placed[ride.id]["calories"] == 612.0


def test_the_sessions_api_carries_the_metrics_on_the_canonical_row(db_session):
    from routers.polar import AerobicSessionOut, get_aerobic_sessions
    _user(db_session)
    ride = _hc_row(db_session)
    _metrics_row(db_session)
    rows = get_aerobic_sessions(limit=100, since=None, current_user=db_session.get(models.User, 1), db=db_session)
    (out,) = [AerobicSessionOut.model_validate(r) for r in rows if r.id == ride.id]
    assert out.garmin_metrics["vendor"] == "Garmin" and out.garmin_metrics["te_anaerobic"] == 2.1


def test_the_mcp_line_appends_garmin_figures_vendor_labelled():
    m = {"calories": 612.4, "te_aerobic": 5.0, "te_anaerobic": 2.1, "training_load": 276.0}
    assert format_garmin_metrics(m) == " garmin=[kcal 612 TE 5.0 aerobic / 2.1 anaerobic load 276]"
    assert format_garmin_metrics({"calories": None, "te_aerobic": 3.2, "te_anaerobic": None, "training_load": None}) == \
        " garmin=[TE 3.2 aerobic]"
    assert format_garmin_metrics(None) == "" and format_garmin_metrics({"calories": None}) == ""


def test_get_recent_sessions_formatter_carries_the_suffix(db_session):
    import mcp_server
    _user(db_session)
    ride = _hc_row(db_session)
    from reads.freshness_reads import freshness
    fresh = freshness(db_session, 1)
    text = mcp_server._format_recent_sessions(
        [ride], {}, [], [], fresh, 7, START.date() - timedelta(days=1),
        garmin_metrics={ride.id: {"calories": 612.0, "te_aerobic": 5.0, "te_anaerobic": 2.1, "training_load": 276.0}})
    assert "garmin=[kcal 612 TE 5.0 aerobic / 2.1 anaerobic load 276]" in text
