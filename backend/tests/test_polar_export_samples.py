"""The Polar Flow export's per-second HR lands in `hr_samples` and re-zones the Polar row on the model
(design 0010 row 6 rescoped; GH#634; `DECISIONS_LOG` #506, its sample path corrected to the real export shape).

The fixture carries the shape the operator's `--keys` probe read off the real export (2026-11-06):
`exercises[0].samples.samples[]` is a list of streams `{type, intervalMillis, values}`, the `HEART_RATE`
stream's `values` a list of floats (null for a dropout) at `startTime + i * intervalMillis`, `startTime`
naive local with `timezoneOffsetMinutes`. The path #506 first shipped (`samples.heartRate[].{dateTime,
value}`) is asserted GONE, not kept as a fallback.

Covers: the stream path, its index arithmetic and the one shared time conversion; null entries skipped
with the index preserved; other stream types ignored; no `HEART_RATE` stream = no samples, no error; the
insert-or-ignore write in the same transaction as the row, for inserted AND skipped sessions (a re-upload
of an export imported before this ingest); idempotence; dry-run writes nothing; an export without samples
keeps the vendor fallback, loudly; the Polar row is zoned on the model from the export samples (vendor zones
replaced); the densest writer wins when the Polar Flow Health Connect copy and the export both cover a bout
(never mixed); the Health Connect same-writer rule is unchanged (an HC row never reads export samples); the
`--keys` probe prints key names and, per member, each stream's type / interval / counts, and no value.
"""
from __future__ import annotations

import io
import json
import zipfile
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone

import pytest

import hc_zone_enrich
import import_polar
import models
from hc_zone_enrich import POLAR_EXPORT_WRITER, POLAR_FLOW_HC_WRITER
from import_polar import (EXPORT_SAMPLE_SOURCE, _hr_samples, _parse_session, import_flow_export,
                          session_key_names, session_sample_streams)
from reads import zone_reads

AEST = timezone(timedelta(minutes=600))
START_LOCAL = datetime(2026, 6, 1, 6, 0)                       # 06:00 AEST = 2026-05-31 20:00Z
START_UTC = START_LOCAL.replace(tzinfo=AEST).astimezone(timezone.utc)
# The row's own clock form (aware, +10:00): what `_parse_session` stores, and on SQLite the naive local
# clock the samples must share (FEEDBACK §49); one instant with START_UTC on Postgres.
START_AW = START_LOCAL.replace(tzinfo=AEST)
GARMIN = "com.garmin.android.apps.connectmobile"

# The operator's probe of the real export's first member (2026-11-06): the facts the fixture reproduces.
REAL_START_LOCAL = datetime(2026, 3, 1, 9, 38, 46)            # "2026-03-01T09:38:46", timezoneOffsetMinutes 600
REAL_START_UTC = datetime(2026, 2, 28, 23, 38, 46, tzinfo=timezone.utc)


def _session(sid: str, *, minutes: int = 10, samples: list | None = None, interval_ms: int = 1000,
             sport_id: int = 2, zones_seconds=(10, 20, 30, 40, 50), start: datetime = START_LOCAL) -> dict:
    """One export `training-session_*.json` body: zone totals (Polar's own) and, when given, the sample
    block in the REAL shape: `exercises[0].samples.samples[]` holding a `HEART_RATE` stream (`values` as
    floats, `None` kept as null) and a `SPEED` stream of the same length, both at `interval_ms`."""
    stop = start + timedelta(minutes=minutes)
    ex: dict = {"zones": [{"type": "ZONE_TYPE_HEART_RATE", "zones": [{"inZone": s * 1000} for s in zones_seconds]}]}
    if samples is not None:
        ex["samples"] = {"samples": [
            {"type": "HEART_RATE", "intervalMillis": interval_ms,
             "values": [float(v) if isinstance(v, int) and not isinstance(v, bool) else v for v in samples]},
            {"type": "SPEED", "intervalMillis": interval_ms, "values": [0.0] * len(samples)},
        ]}
    return {
        "startTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "stopTime": stop.strftime("%Y-%m-%dT%H:%M:%S"),
        "timezoneOffsetMinutes": 600,
        "identifier": {"id": sid},
        "sport": {"id": sport_id},                              # 2 = Cycling: the LTHR class
        "hrAvg": 150, "hrMax": 170, "calories": 300,
        "durationMillis": minutes * 60 * 1000,
        "trainingLoadReport": {"cardioLoad": 42.0, "muscleLoad": -1.0},
        "exercises": [ex],
    }


def _hr_stream(body: dict) -> dict:
    return next(s for s in body["exercises"][0]["samples"]["samples"] if s["type"] == "HEART_RATE")


def _zip(sessions: dict[str, dict]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in sessions.items():
            zf.writestr(name, body if isinstance(body, (str, bytes)) else json.dumps(body))
    return buf.getvalue()


def _user(db, uid=1):
    db.add(models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x"))
    db.commit()


def _anchors(db, uid=1, eff=date(2026, 3, 1)):
    db.add(models.UserHrmax(user_id=uid, effective_from=eff, hrmax_bpm=179, provenance="observed", note="t"))
    db.add(models.UserHrAnchor(user_id=uid, kind="rhr", effective_from=eff, bpm=51, provenance="stated", note="t"))
    db.add(models.UserHrAnchor(user_id=uid, kind="lthr", effective_from=eff, bpm=158, provenance="stated", note="t"))
    db.commit()


def _export_samples(db, uid=1):
    return (db.query(models.HrSample).filter_by(user_id=uid, source=EXPORT_SAMPLE_SOURCE)
            .order_by(models.HrSample.sample_time).all())


def _zones(r):
    return (r.z1_seconds, r.z2_seconds, r.z3_seconds, r.z4_seconds, r.z5_seconds)


# 601 one-second samples at 134 bpm cover the 10-minute bout; 134 is z2 on LTHR 158 (81% = 128, 90% = 143).
FLAT_134 = [134] * 601


# ---- the sample path: the real export shape ----------------------------------------------------------

def test_the_heart_rate_stream_is_read_at_start_time_plus_index_times_interval_in_the_session_offset():
    """The operator's probe facts: `HEART_RATE`, 1000 ms, values `[70.0, 70.0, 70.0]`, startTime
    `2026-03-01T09:38:46` naive with offset 600 → three samples at 2026-02-28T23:38:46Z + i s."""
    body = _session("p1", samples=[70, 70, 70], start=REAL_START_LOCAL)
    assert _hr_stream(body)["values"] == [70.0, 70.0, 70.0] and _hr_stream(body)["intervalMillis"] == 1000
    got = _hr_samples(body)
    assert got == [(REAL_START_UTC, 70), (REAL_START_UTC + timedelta(seconds=1), 70), (REAL_START_UTC + timedelta(seconds=2), 70)]
    # aware in the session's own offset, the row's start_time form (one instant; SQLite-aligned, FEEDBACK §49)
    assert got[0][0].utcoffset() == timedelta(minutes=600)
    assert got[0][0] == _parse_session(body)["start_time"] and got[0][0].tzinfo == _parse_session(body)["start_time"].tzinfo


def test_the_samples_anchor_on_the_same_conversion_as_the_row_including_a_start_time_with_its_own_offset():
    body = _session("p1", samples=[120, 121])
    assert _hr_samples(body)[0] == (START_UTC, 120)
    body["startTime"] = "2026-05-31T20:00:00Z"                   # its own offset: honoured, like the row's
    assert _hr_samples(body) == [(START_UTC, 120), (START_UTC + timedelta(seconds=1), 121)]
    assert _hr_samples(body)[0][0].tzinfo == _parse_session(body)["start_time"].tzinfo == timezone.utc


def test_a_null_entry_is_skipped_and_the_index_still_advances():
    body = _session("p1", samples=[120, None, "x", True, 122])
    assert _hr_samples(body) == [(START_UTC, 120), (START_UTC + timedelta(seconds=4), 122)]


def test_bpm_is_stored_as_received_zero_and_implausible_kept_floats_truncated():
    body = _session("p1", samples=[0.0, 250.0, 70.9, 20])
    assert [b for _, b in _hr_samples(body)] == [0, 250, 70, 20]


def test_the_interval_spaces_the_samples_and_a_sub_second_interval_collapses_to_the_last_per_second():
    body = _session("p1", samples=[130, 131, 132], interval_ms=2000)
    assert _hr_samples(body) == [(START_UTC, 130), (START_UTC + timedelta(seconds=2), 131), (START_UTC + timedelta(seconds=4), 132)]
    body = _session("p1", samples=[130, 131, 132, 133], interval_ms=500)
    assert _hr_samples(body) == [(START_UTC, 131), (START_UTC + timedelta(seconds=1), 133)]


def test_other_stream_types_are_ignored():
    body = _session("p1", samples=[120])
    body["exercises"][0]["samples"]["samples"] += [
        {"type": "CADENCE", "intervalMillis": 1000, "values": [999.0, 999.0]},
        {"type": None, "intervalMillis": 1000, "values": [998.0]},
        "garbage", 7,
    ]
    assert _hr_samples(body) == [(START_UTC, 120)]


@pytest.mark.parametrize("mutate", [
    lambda b: b.pop("exercises"),
    lambda b: b.__setitem__("exercises", []),
    lambda b: b["exercises"][0].pop("samples"),
    lambda b: b["exercises"][0].__setitem__("samples", []),            # a list, not the dict shape
    lambda b: b["exercises"][0]["samples"].pop("samples"),
    lambda b: b["exercises"][0]["samples"].__setitem__("samples", {}),
    lambda b: b["exercises"][0]["samples"]["samples"].remove(_hr_stream(b)),     # SPEED only: no HEART_RATE stream
    lambda b: _hr_stream(b).pop("intervalMillis"),
    lambda b: _hr_stream(b).__setitem__("intervalMillis", 0),
    lambda b: _hr_stream(b).__setitem__("intervalMillis", "1000"),
    lambda b: _hr_stream(b).__setitem__("intervalMillis", True),
    lambda b: _hr_stream(b).__setitem__("values", None),
    lambda b: _hr_stream(b).__setitem__("values", []),
    lambda b: b.pop("startTime"),
])
def test_no_heart_rate_stream_or_a_differently_shaped_path_yields_no_samples_not_an_error(mutate):
    body = _session("p1", samples=[120])
    mutate(body)
    assert _hr_samples(body) == []


def test_the_guessed_506_path_is_gone_not_a_fallback():
    """`exercises[0].samples.heartRate[].{dateTime, value}` was never the export's shape; a member
    carrying only that reads as sample-less."""
    body = _session("p1")
    body["exercises"][0]["samples"] = {"heartRate": [{"dateTime": "2026-06-01T06:00:00.000", "value": 120}]}
    assert _hr_samples(body) == []


# ---- the write ------------------------------------------------------------------------------------

def test_an_export_with_samples_writes_hr_samples_in_the_export_lane_with_bpm_as_received(db_session):
    _user(db_session)
    out = import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1", samples=[120, 250, 20])}))
    assert out["inserted"] == 1 and out["hr_samples_found"] == 3 and out["hr_samples_stored"] == 3
    assert out["sessions_with_samples"] == 1 and out["sessions_without_samples"] == 0
    assert out["details"][0]["hr_samples"] == 3
    rows = _export_samples(db_session)
    assert [(r.source, r.source_package, r.bpm) for r in rows] == [
        (EXPORT_SAMPLE_SOURCE, EXPORT_SAMPLE_SOURCE, 120), (EXPORT_SAMPLE_SOURCE, EXPORT_SAMPLE_SOURCE, 250),
        (EXPORT_SAMPLE_SOURCE, EXPORT_SAMPLE_SOURCE, 20)]                       # implausible kept: zone time drops them
    # stored in the row's own clock form (SQLite keeps the naive local clock, like start_time; FEEDBACK §49)
    assert rows[0].sample_time.replace(tzinfo=None) == db_session.query(models.AerobicSession).one().start_time.replace(tzinfo=None)
    assert db_session.query(models.AerobicSession).count() == 1


def test_a_null_entry_leaves_a_gap_in_the_stored_samples_not_a_shift(db_session):
    _user(db_session)
    out = import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1", samples=[120, None, 122])}))
    assert out["hr_samples_found"] == 2 and out["hr_samples_stored"] == 2
    rows = _export_samples(db_session)
    assert [(r.sample_time.replace(tzinfo=None), r.bpm) for r in rows] == [(START_LOCAL, 120), (START_LOCAL + timedelta(seconds=2), 122)]


def test_a_member_without_a_heart_rate_stream_writes_nothing_and_is_not_an_error(db_session):
    _user(db_session)
    body = _session("p1", samples=[120, 121])
    body["exercises"][0]["samples"]["samples"].remove(_hr_stream(body))
    out = import_flow_export(db_session, 1, _zip({"training-session_1.json": body}))
    assert out["inserted"] == 1 and out["errors"] == 0
    assert out["hr_samples_found"] == 0 and out["hr_samples_stored"] == 0 and out["sessions_without_samples"] == 1
    assert db_session.query(models.HrSample).count() == 0


def test_a_re_import_is_idempotent_no_duplicate_samples_and_no_duplicate_row(db_session):
    _user(db_session)
    zb = _zip({"training-session_1.json": _session("p1", samples=FLAT_134)})
    first = import_flow_export(db_session, 1, zb)
    again = import_flow_export(db_session, 1, zb)
    assert first["hr_samples_stored"] == 601
    assert again == {**again, "inserted": 0, "skipped": 1, "hr_samples_found": 601, "hr_samples_stored": 0}
    assert len(_export_samples(db_session)) == 601
    assert db_session.query(models.AerobicSession).count() == 1


def test_a_skipped_session_still_gets_its_samples_the_re_upload_of_an_older_import(db_session):
    """An export imported before this ingest left its rows without samples; re-uploading the same
    export fills them without touching the row."""
    _user(db_session)
    without = import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1")}))
    assert without["inserted"] == 1 and without["hr_samples_found"] == 0 and without["sessions_without_samples"] == 1
    row_id = db_session.query(models.AerobicSession).one().id
    with_samples = import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1", samples=FLAT_134)}))
    assert with_samples["inserted"] == 0 and with_samples["skipped"] == 1
    assert with_samples["hr_samples_found"] == 601 and with_samples["hr_samples_stored"] == 601
    assert with_samples["details"][0] == {"name": "training-session_1.json", "status": "skipped",
                                          "source_session_id": "p1", "hr_samples": 601}
    assert len(_export_samples(db_session)) == 601
    row = db_session.query(models.AerobicSession).one()
    assert row.id == row_id and _zones(row) == (10, 20, 30, 40, 50)      # the row is the fill's to change, not the import's


def test_a_dry_run_writes_no_sample_but_counts_them(db_session):
    _user(db_session)
    out = import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1", samples=FLAT_134)}), dry_run=True)
    assert out["hr_samples_found"] == 601 and out["hr_samples_stored"] == 0 and out["inserted"] == 1
    assert db_session.query(models.HrSample).count() == 0 and db_session.query(models.AerobicSession).count() == 0


def test_the_samples_ride_the_row_transaction(db_session, monkeypatch):
    """One commit carries the row and its samples: with the commit withheld, both are pending in the
    session and a rollback removes both."""
    _user(db_session)
    commits = []
    monkeypatch.setattr(db_session, "commit", lambda: commits.append(1))
    out = import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1", samples=FLAT_134)}))
    assert out["inserted"] == 1 and out["hr_samples_stored"] == 601 and commits == [1]
    db_session.flush()                       # the suite's session does not autoflush; the row is pending, uncommitted
    assert db_session.query(models.HrSample).count() == 601 and db_session.query(models.AerobicSession).count() == 1
    db_session.rollback()
    assert db_session.query(models.HrSample).count() == 0 and db_session.query(models.AerobicSession).count() == 0


# ---- zoning: the export samples re-zone the Polar row on the model ---------------------------------

def test_an_export_row_is_zoned_on_the_model_from_its_own_samples_and_vendor_zones_are_replaced(db_session):
    _user(db_session)
    _anchors(db_session)
    import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1", samples=FLAT_134)}))
    row = db_session.query(models.AerobicSession).one()
    assert _zones(row) == (10, 20, 30, 40, 50)                                 # Polar's own, as imported
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["polar_rezoned"] == 1 and out["polar_vendor_fallback"] == 0 and out["by_basis"]["lthr"] == 1
    db_session.expire_all()
    row = db_session.get(models.AerobicSession, row.id)
    assert _zones(row) == (0, 600, 0, 0, 0) and row.hr_avg == 134 and row.hr_max == 134
    z = zone_reads.row_zoning(db_session, 1, row, zone_reads.anchor_entries(zone_reads.anchor_rows(db_session, 1)))
    assert z["basis"] == "lthr" and z["reason"] is None                         # the read says the same


def test_an_export_without_samples_keeps_the_vendor_fallback(db_session):
    _user(db_session)
    _anchors(db_session)
    import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1")}))
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["polar_rezoned"] == 0 and out["polar_vendor_fallback"] == 1 and out["changed"] == 0
    row = db_session.query(models.AerobicSession).one()
    assert _zones(row) == (10, 20, 30, 40, 50) and row.hr_avg == 150 and row.hr_max == 170
    assert zone_reads.coverage_category(zone_reads.row_zoning(
        db_session, 1, row, zone_reads.anchor_entries(zone_reads.anchor_rows(db_session, 1)))) == "vendor"


def test_dropping_the_export_writer_is_the_reverse_by(db_session, monkeypatch):
    monkeypatch.setattr(hc_zone_enrich, "POLAR_SAMPLE_WRITERS", (POLAR_FLOW_HC_WRITER,))
    _user(db_session)
    _anchors(db_session)
    import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1", samples=FLAT_134)}))
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["polar_rezoned"] == 0 and out["polar_vendor_fallback"] == 1
    assert len(_export_samples(db_session)) == 601                               # the samples stay, harmless


def _hc_samples(db, pkg, start, step_s, bpms, source="health_connect"):
    db.add_all(models.HrSample(user_id=1, sample_time=start + timedelta(seconds=step_s * i), bpm=b,
                               source=source, source_package=pkg) for i, b in enumerate(bpms))
    db.commit()


def test_the_densest_writer_wins_and_streams_are_never_mixed(db_session):
    """The Polar Flow Health Connect copy (every 2 s, 170 bpm: z5) and the export (every 1 s, 134: z2) both
    cover the bout; the export is denser, so the row zones wholly on it. Mixing would put time in z5."""
    _user(db_session)
    _anchors(db_session)
    import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1", samples=FLAT_134)}))
    _hc_samples(db_session, POLAR_FLOW_HC_WRITER[1], START_AW, 2, [170] * 301)
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["polar_rezoned"] == 1
    row = db_session.query(models.AerobicSession).one()
    assert _zones(row) == (0, 600, 0, 0, 0) and row.hr_max == 134


def test_the_denser_hc_copy_wins_over_a_sparser_export(db_session):
    _user(db_session)
    _anchors(db_session)
    import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1", samples=[134] * 301, interval_ms=2000)}))
    _hc_samples(db_session, POLAR_FLOW_HC_WRITER[1], START_AW, 1, [170] * 601)
    hc_zone_enrich.enrich_user(db_session, 1)
    row = db_session.query(models.AerobicSession).one()
    assert _zones(row) == (0, 0, 0, 0, 600) and row.hr_max == 170


def test_a_tie_keeps_the_writer_tuple_order_hc_copy_first(db_session):
    _user(db_session)
    _anchors(db_session)
    import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1", samples=FLAT_134)}))
    _hc_samples(db_session, POLAR_FLOW_HC_WRITER[1], START_AW, 1, [170] * 601)
    row = db_session.query(models.AerobicSession).one()
    got = hc_zone_enrich._row_samples(db_session, 1, row, START_AW, START_AW + timedelta(minutes=10))
    assert len(got) == 601 and {b for _, b in got} == {170}
    assert hc_zone_enrich.POLAR_SAMPLE_WRITERS == (POLAR_FLOW_HC_WRITER, POLAR_EXPORT_WRITER)


# ---- the Health Connect same-writer rule is unchanged ----------------------------------------------

def test_a_health_connect_row_never_reads_export_samples(db_session):
    """A Garmin HC row inside the same bout reads only Garmin's own writers (its HC trace, and since the
    activity-stream ruling Garmin's activity stream): the export lane is a Polar writer. With no Garmin
    samples it is `no_same_writer_hr`, exactly as before."""
    _user(db_session)
    _anchors(db_session)
    import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1", samples=FLAT_134)}))
    hc = models.AerobicSession(user_id=1, source="health_connect", source_package=GARMIN, source_session_id="g1",
                               session_date=date(2026, 6, 1), start_time=START_AW,
                               stop_time=START_AW + timedelta(minutes=10), sport_name="Biking", duration_minutes=10)
    db_session.add(hc)
    db_session.commit()
    assert hc_zone_enrich.sample_writers_for(hc) == (("health_connect", GARMIN), ("garmin", "activity_details"))
    assert hc_zone_enrich.POLAR_EXPORT_WRITER not in hc_zone_enrich.sample_writers_for(hc)
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["reasons"]["no_same_writer_hr"] == 1 and out["polar_rezoned"] == 1
    db_session.expire_all()
    assert _zones(db_session.get(models.AerobicSession, hc.id)) == (None,) * 5


def test_hc_samples_under_the_polar_flow_package_are_not_read_through_the_export_lane(db_session):
    """The export writer is (`polar_flow_export`, `polar_flow_export`) on BOTH columns: a Health Connect
    sample whose package happens to read `polar_flow_export`, or an export sample under another source,
    is not that writer."""
    _user(db_session)
    _anchors(db_session)
    import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1")}))
    _hc_samples(db_session, EXPORT_SAMPLE_SOURCE, START_AW, 1, [134] * 601, source="health_connect")
    _hc_samples(db_session, "accesslink_v4", START_AW, 1, [134] * 601, source="polar")
    out = hc_zone_enrich.enrich_user(db_session, 1)
    assert out["polar_vendor_fallback"] == 1 and out["polar_rezoned"] == 0


# ---- the --keys probe --------------------------------------------------------------------------------

def test_key_names_lists_the_path_keys_and_no_value():
    body = _session("p1", samples=[137, None, 141])
    keys = session_key_names(body)
    assert "exercises" in keys["top"] and "identifier" in keys["top"]
    assert keys["exercises[0]"] == ["samples", "zones"]
    assert keys["exercises[0].samples"] == ["samples"]
    assert keys["exercises[0].samples.samples[0]"] == ["intervalMillis", "type", "values"]
    text = import_polar.format_key_names(import_polar.export_key_names(_zip({"training-session_1.json": body})))
    assert "exercises[0].samples.samples[0]: intervalMillis, type, values" in text
    for leaked in ("137", "141", "p1", "2026-06-01", "42.0", "150"):
        assert leaked not in text


def test_sample_streams_report_type_interval_and_counts_per_member_never_a_value():
    speed_only = _session("p2", samples=[120, 121])
    speed_only["exercises"][0]["samples"]["samples"].remove(_hr_stream(speed_only))
    odd = _session("p4")
    odd["exercises"][0]["samples"] = {"samples": [{"type": 5, "intervalMillis": None, "values": "x"}]}
    assert session_sample_streams(_session("p1", samples=[137, None, 141], interval_ms=2000)) == [
        {"type": "HEART_RATE", "intervalMillis": 2000, "count": 3, "nulls": 1},
        {"type": "SPEED", "intervalMillis": 2000, "count": 3, "nulls": 0}]
    assert session_sample_streams(odd) == [{"type": "<int>", "intervalMillis": None, "count": None, "nulls": None}]
    assert session_sample_streams(_session("p3")) == []
    report = import_polar.export_key_names(_zip({
        "training-session_1.json": _session("p1", samples=[137, None, 141]),
        "training-session_2.json": speed_only,
        "training-session_3.json": _session("p3"),
        "training-session_4.json": "not json {",
    }))
    assert report["found"] == 4 and report["member"] == "training-session_1.json"
    assert [m["member"] for m in report["members"]] == [f"training-session_{i}.json" for i in (1, 2, 3, 4)]
    assert report["members"][1]["streams"] == [{"type": "SPEED", "intervalMillis": 1000, "count": 2, "nulls": 0}]
    assert report["members"][2]["streams"] == [] and report["members"][3]["error"] == "JSONDecodeError"
    text = import_polar.format_key_names(report)
    assert "training-session_1.json: HEART_RATE @1000ms n=3 null=1; SPEED @1000ms n=3 null=0" in text
    assert "training-session_2.json: SPEED @1000ms n=2 null=0" in text
    assert "training-session_3.json: (no sample stream)" in text
    assert "training-session_4.json: (unreadable: JSONDecodeError)" in text
    for leaked in ("137", "141", "120", "121", "p1", "p2", "2026-06-01"):
        assert leaked not in text


def test_key_names_describe_a_list_shaped_samples_block_without_values():
    body = _session("p1")
    body["exercises"][0]["samples"] = [{"type": "SAMPLE_TYPE_HEART_RATE", "values": [1, 2, 3]}, 7]
    keys = session_key_names(body)
    assert keys["exercises[0].samples"] == ["<list of 2>"]
    assert keys["exercises[0].samples[0]"] == ["type", "values"] and keys["exercises[0].samples[1]"] == ["<int>"]
    assert session_key_names({"exercises": []})["exercises[0].samples"] == []
    assert session_sample_streams(body) == []                                   # not the dict shape: no stream read


def test_cli_keys_mode_needs_no_email_and_touches_no_database(tmp_path, monkeypatch):
    p = tmp_path / "export.zip"
    p.write_bytes(_zip({"training-session_1.json": _session("p1", samples=[137])}))
    monkeypatch.setattr(import_polar, "SessionLocal", lambda: (_ for _ in ()).throw(AssertionError("database opened")))
    monkeypatch.setattr("sys.argv", ["import_polar.py", "--zip", str(p), "--keys"])
    out = io.StringIO()
    with redirect_stdout(out):
        import_polar.main()
    text = out.getvalue()
    assert "samples.samples[0]: intervalMillis, type, values" in text
    assert "training-session_1.json: HEART_RATE @1000ms n=1 null=0; SPEED @1000ms n=1 null=0" in text
    assert "137" not in text
