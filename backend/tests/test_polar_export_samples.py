"""The Polar Flow export's per-second HR lands in `hr_samples` and re-zones the Polar row on the model
(design 0010 row 6 rescoped; GH#634).

Covers: the sample path and its local-time parsing; the insert-or-ignore write in the same transaction
as the row, for inserted AND skipped sessions (a re-upload of an export imported before this ingest);
idempotence; dry-run writes nothing; an export without samples keeps the vendor fallback, loudly; the
Polar row is zoned on the model from the export samples (vendor zones replaced); the densest writer
wins when the Polar Flow Health Connect copy and the export both cover a bout (never mixed); the
Health Connect same-writer rule is unchanged (an HC row never reads export samples); the `--keys`
probe prints key names and no value.
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
from import_polar import EXPORT_SAMPLE_SOURCE, _hr_samples, import_flow_export, session_key_names
from reads import zone_reads

AEST = timezone(timedelta(minutes=600))
START_LOCAL = datetime(2026, 6, 1, 6, 0)                       # 06:00 AEST = 2026-05-31 20:00Z
START_UTC = START_LOCAL.replace(tzinfo=AEST).astimezone(timezone.utc)
# The row's own clock form (aware, +10:00): what `_parse_session` stores, and on SQLite the naive local
# clock the samples must share (FEEDBACK §49); one instant with START_UTC on Postgres.
START_AW = START_LOCAL.replace(tzinfo=AEST)
GARMIN = "com.garmin.android.apps.connectmobile"


def _session(sid: str, *, minutes: int = 10, samples: list | None = None, sport_id: int = 2,
             zones_seconds=(10, 20, 30, 40, 50), start: datetime = START_LOCAL) -> dict:
    """One export `training-session_*.json` body: zone totals (Polar's own) and, when given, the
    per-second HR under `exercises[0].samples.heartRate[].{dateTime, value}` with LOCAL dateTimes."""
    stop = start + timedelta(minutes=minutes)
    ex: dict = {"zones": [{"type": "ZONE_TYPE_HEART_RATE", "zones": [{"inZone": s * 1000} for s in zones_seconds]}]}
    if samples is not None:
        ex["samples"] = {
            "heartRate": [{"dateTime": (start + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%S.000"), "value": v}
                          for i, v in samples],
            "speed": [{"dateTime": start.strftime("%Y-%m-%dT%H:%M:%S.000"), "value": 0.0}],
        }
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


def _zip(sessions: dict[str, dict]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in sessions.items():
            zf.writestr(name, json.dumps(body))
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
FLAT_134 = [(i, 134) for i in range(601)]


# ---- the sample path -----------------------------------------------------------------------------

def test_samples_are_read_from_exercises_0_samples_heart_rate_as_local_time():
    body = _session("p1", samples=[(0, 120), (1, 121), (2, 122)])
    got = _hr_samples(body)
    assert got == [(START_UTC, 120), (START_UTC + timedelta(seconds=1), 121), (START_UTC + timedelta(seconds=2), 122)]
    # aware in the session's own offset, like the row's start_time (one instant; SQLite-aligned)
    assert got[0][0].utcoffset() == timedelta(minutes=600) and got[0][0] == datetime(2026, 5, 31, 20, 0, tzinfo=timezone.utc)
    body["exercises"][0]["samples"]["heartRate"][0]["dateTime"] = "2026-05-31T20:00:00Z"     # its own offset: honoured
    assert _hr_samples(body)[0] == (START_UTC, 120)


def test_null_and_non_integer_values_and_bad_times_are_skipped_and_same_second_collapses():
    body = _session("p1", samples=[(0, 120)])
    body["exercises"][0]["samples"]["heartRate"] += [
        {"dateTime": "2026-06-01T06:00:01.000", "value": None},         # a dropout: skipped
        {"dateTime": "2026-06-01T06:00:02.000", "value": "x"},
        {"dateTime": "2026-06-01T06:00:03.000", "value": True},
        {"dateTime": "not a time", "value": 130},
        {"dateTime": "2026-06-01T06:00:00.500", "value": 125},         # same second as the first: last wins
        "garbage",
    ]
    assert _hr_samples(body) == [(START_UTC, 125)]


@pytest.mark.parametrize("mutate", [
    lambda b: b.pop("exercises"),
    lambda b: b["exercises"][0].pop("samples"),
    lambda b: b["exercises"][0].__setitem__("samples", []),            # a list, not the dict shape
    lambda b: b["exercises"][0]["samples"].pop("heartRate"),
    lambda b: b["exercises"][0]["samples"].__setitem__("heartRate", {}),
])
def test_an_absent_or_differently_shaped_path_yields_no_samples_not_an_error(mutate):
    body = _session("p1", samples=[(0, 120)])
    mutate(body)
    assert _hr_samples(body) == []


# ---- the write ------------------------------------------------------------------------------------

def test_an_export_with_samples_writes_hr_samples_in_the_export_lane_with_bpm_as_received(db_session):
    _user(db_session)
    out = import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1", samples=[(0, 120), (1, 250), (2, 20)])}))
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
    import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1", samples=[(2 * i, 134) for i in range(301)])}))
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
    """A Garmin HC row inside the same bout reads only Garmin's own HC samples: the export lane is a
    Polar writer. With no Garmin samples it is `no_same_writer_hr`, exactly as before."""
    _user(db_session)
    _anchors(db_session)
    import_flow_export(db_session, 1, _zip({"training-session_1.json": _session("p1", samples=FLAT_134)}))
    hc = models.AerobicSession(user_id=1, source="health_connect", source_package=GARMIN, source_session_id="g1",
                               session_date=date(2026, 6, 1), start_time=START_AW,
                               stop_time=START_AW + timedelta(minutes=10), sport_name="Biking", duration_minutes=10)
    db_session.add(hc)
    db_session.commit()
    assert hc_zone_enrich.sample_writers_for(hc) == (("health_connect", GARMIN),)
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
    body = _session("p1", samples=[(0, 120)])
    keys = session_key_names(body)
    assert "exercises" in keys["top"] and "identifier" in keys["top"]
    assert keys["exercises[0]"] == ["samples", "zones"]
    assert keys["exercises[0].samples"] == ["heartRate", "speed"]
    assert keys["exercises[0].samples.heartRate[0]"] == ["dateTime", "value"]
    text = import_polar.format_key_names(import_polar.export_key_names(_zip({"training-session_1.json": body})))
    assert "exercises[0].samples.heartRate[0]: dateTime, value" in text
    for leaked in ("120", "p1", "2026-06-01", "42.0", "150"):
        assert leaked not in text


def test_key_names_describe_a_list_shaped_samples_block_without_values():
    body = _session("p1")
    body["exercises"][0]["samples"] = [{"type": "SAMPLE_TYPE_HEART_RATE", "values": [1, 2, 3]}, 7]
    keys = session_key_names(body)
    assert keys["exercises[0].samples"] == ["<list of 2>"]
    assert keys["exercises[0].samples[0]"] == ["type", "values"] and keys["exercises[0].samples[1]"] == ["<int>"]
    assert session_key_names({"exercises": []})["exercises[0].samples"] == []


def test_cli_keys_mode_needs_no_email_and_touches_no_database(tmp_path, monkeypatch):
    p = tmp_path / "export.zip"
    p.write_bytes(_zip({"training-session_1.json": _session("p1", samples=[(0, 120)])}))
    monkeypatch.setattr(import_polar, "SessionLocal", lambda: (_ for _ in ()).throw(AssertionError("database opened")))
    monkeypatch.setattr("sys.argv", ["import_polar.py", "--zip", str(p), "--keys"])
    out = io.StringIO()
    with redirect_stdout(out):
        import_polar.main()
    assert "heartRate[0]: dateTime, value" in out.getvalue() and "120" not in out.getvalue()
