"""Location keys are never kept in `garmin_activity_metrics.summary_raw` (written, or scrubbed from old rows), and
the read-only readiness probe asks the Personal API whether it serves recovery time. The probe runs through the
REAL `PersonalClient` against a fake host at the TRANSPORT (FEEDBACK section 23)."""
from datetime import date

import garmin_activity_metrics as gam
import models
from connectors import garmin_personal as gp
from garmin_personal_fakes import FAKE_KEY, FakeHost
from scripts import garmin_activity_scrub as scrub_script
from scripts import garmin_readiness_probe as rp
from scripts.garmin_activity_backfill import GuardedSource
from test_garmin_activity_metrics import AID, NOW, _metric_rows, _summary, _user

COORDS = {"startLatitude": -27.4, "startLongitude": 153.0, "endLatitude": -27.4, "endLongitude": 153.0}


def test_location_keys_are_dropped_at_any_depth_and_nothing_else():
    obj = {**COORDS, "calories": 1.0, "nested": [{"pointLatitude": 1, "x": 2}], "laps": {"endlongitude": 3}}
    assert gam.location_keys(obj) == 6
    assert gam.scrub_location(obj) == {"calories": 1.0, "nested": [{"x": 2}], "laps": {}}
    assert "startLatitude" in obj                                      # the input is untouched


def test_the_write_path_never_stores_coordinates(db_session):
    _user(db_session)
    gam.upsert_metrics(db_session, 1, AID, {"summaryDTO": _summary(**COORDS)}, now=NOW)
    db_session.commit()
    (m,) = _metric_rows(db_session)
    assert gam.location_keys(m.summary_raw) == 0 and m.summary_raw["calories"] == 612.0


def _old_row(db):
    db.add(models.GarminActivityMetric(user_id=1, garmin_activity_id=AID, summary_raw=_summary(**COORDS), fetched_at=NOW))
    db.commit()


def test_the_scrub_dry_run_counts_and_writes_nothing(db_session):
    _user(db_session)
    _old_row(db_session)
    out = scrub_script.scrub(db_session, confirm=False)
    assert out == {"rows": 1, "rows_with_location": 1, "keys_removed": 4, "rows_written": 0}
    db_session.expire_all()
    assert gam.location_keys(_metric_rows(db_session)[0].summary_raw) == 4


def test_the_scrub_removes_only_location_keys_and_is_idempotent(db_session):
    _user(db_session)
    _old_row(db_session)
    assert scrub_script.scrub(db_session, confirm=True)["rows_written"] == 1
    db_session.expire_all()
    raw = _metric_rows(db_session)[0].summary_raw
    assert gam.location_keys(raw) == 0 and raw == _summary()            # every other key exactly as stored
    assert scrub_script.scrub(db_session, confirm=True) == {"rows": 1, "rows_with_location": 0, "keys_removed": 0,
                                                            "rows_written": 0}


DAY = date(2026, 11, 6)


def _guarded(host):
    client = gp.PersonalClient(FAKE_KEY, transport=host.transport())
    client.exchange()
    return client, GuardedSource(client)


def test_the_probe_prints_shapes_and_recovery_keys_only():
    host = FakeHost()
    host.set(rp.READINESS_PATH.format(date=DAY.isoformat()),
             [{"calendarDate": "2026-11-06", "score": 41, "recoveryTime": 1980, "hrvFactorPercent": 60}])
    host.set(rp.STATUS_PATH.format(date=DAY.isoformat()),
             {"mostRecentTrainingStatus": {"latestTrainingStatusData": {"x": {"trainingStatus": 4}}}})
    client, src = _guarded(host)
    lines = rp.probe(src, DAY)
    client.close()
    text = "\n".join(lines)
    assert "training readiness (/metrics-service/metrics/trainingreadiness/2026-11-06): list of 1" in text
    assert "[0].recoveryTime = 1980" in text
    assert "training status (/metrics-service/metrics/trainingstatus/aggregated/2026-11-06): object" in text
    assert "no key matching 'recovery'" in text
    assert "41" not in text and "60" not in text                         # no other value is printed
    assert [p for _, p, _ in host.requests] == ["/metrics-service/metrics/trainingreadiness/2026-11-06",
                                               "/metrics-service/metrics/trainingstatus/aggregated/2026-11-06"]


def test_the_probe_reports_a_404_and_a_refusal_by_class():
    host = FakeHost()
    host.status_for[rp.STATUS_PATH.format(date=DAY.isoformat())] = 403
    client, src = _guarded(host)
    lines = rp.probe(src, DAY)
    client.close()
    assert lines[0].endswith("404 (not served, or nothing for 2026-11-06)")
    assert lines[1].endswith("fetch failed: PersonalAuthError")


def test_the_details_payload_is_never_kept_beyond_its_hr_samples(db_session):
    """The details response carries `geoPolylineDTO` (the GPS track). Only (time, bpm) pairs leave it: the metrics
    row gains its two stream columns and nothing else, and no other table is written."""
    from sqlalchemy import inspect as sa_inspect
    from test_garmin_activity_metrics import _details, _metrics_row, _ride, _stream

    _user(db_session)
    _metrics_row(db_session)
    before_raw = dict(_metric_rows(db_session)[0].summary_raw)
    counts = {t: db_session.execute(models.Base.metadata.tables[t].select()).fetchall().__len__()
              for t in sa_inspect(db_session.get_bind()).get_table_names()}
    details = _details(_ride(seconds=9))
    details["geoPolylineDTO"] = {"polyline": [{"lat": -27.4, "lon": 153.0, "time": 1}], "startPoint": {"lat": -27.4}}
    host = FakeHost()
    host.set(f"{gp.ACTIVITY_PATH}/{AID}/details", details)
    with gp.PersonalClient(FAKE_KEY, transport=host.transport()) as client:
        gam.sync_streams(db_session, 1, client, now=NOW)
    db_session.expire_all()
    after = {t: db_session.execute(models.Base.metadata.tables[t].select()).fetchall().__len__() for t in counts}
    assert {t: after[t] - counts[t] for t in counts if after[t] != counts[t]} == {"hr_samples": 10}
    m = _metric_rows(db_session)[0]
    assert m.summary_raw == before_raw and "geoPolylineDTO" not in str(m.summary_raw)
    assert m.hr_stream_samples == 10 and len(_stream(db_session)) == 10
