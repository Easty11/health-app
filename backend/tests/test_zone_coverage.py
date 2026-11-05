"""`zone_reads.zone_coverage` and the MCP `get_zone_coverage` tool: how every aerobic row is zoned NOW, per
source, derived live from `row_zoning` (design 0010 §4). The refresh_load chain report is returned and printed,
never stored, so coverage is derived on read.

GATES (from the brief):
  * an HC row zoned lthr; an HC row zoned hrr;
  * a Polar row re-zoned from a `fi.polar.polarflow` Health Connect trace; a Polar row in vendor fallback;
  * a no_anchor row (anchors absent); a withheld row;
  * the days filter; the 20-row cap; no DB writes (the session is not dirty after the call);
  * the Polar classification is `row_zoning`'s, not a second implementation;
  * the MCP tool renders the read, stamped, read-only.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import null

import mcp_server
import models
from reads import zone_reads

TODAY = date(2026, 11, 5)
GARMIN = "com.garmin.android.apps.connectmobile"
POLAR_FLOW = "fi.polar.polarflow"
S = datetime(2026, 10, 28, 20, 0, 0, tzinfo=timezone.utc)      # 06:00 AEST 29 Oct
E = S + timedelta(minutes=30)


def _user(db, email="cov@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _seeded(db, uid):
    db.add(models.UserHrmax(user_id=uid, effective_from=date(2026, 3, 1), hrmax_bpm=179, provenance="observed", note="H10"))
    db.add(models.UserHrAnchor(user_id=uid, kind="lthr", effective_from=date(2026, 3, 1), bpm=158, provenance="observed", note="t"))
    db.add(models.UserHrAnchor(user_id=uid, kind="rhr", effective_from=date(2026, 3, 1), bpm=51, provenance="stated", note="t"))
    db.commit()


def _row(db, uid, ssid, start=S, stop=E, *, sport="Biking Stationary", source="health_connect", pkg=GARMIN, zoned=False, **kw):
    """An aerobic row. An HC row is stage-1 (z* NULL) unless `zoned`, which gives it the fill's output shape."""
    if source == "health_connect":
        for z in ("z1_seconds", "z2_seconds", "z3_seconds", "z4_seconds", "z5_seconds"):
            kw.setdefault(z, 360 if zoned else null())
    else:
        for i, z in enumerate(("z1_seconds", "z2_seconds", "z3_seconds", "z4_seconds", "z5_seconds")):
            kw.setdefault(z, i + 1)                                  # Polar's own zones, as the ingest writes them
    r = models.AerobicSession(user_id=uid, source=source, source_session_id=ssid,
                              session_date=(start + timedelta(hours=10)).date(), start_time=start, stop_time=stop,
                              sport_name=sport, duration_minutes=(stop - start).total_seconds() / 60,
                              source_package=pkg if source == "health_connect" else None, **kw)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _samples(db, uid, pkg, start, step_s, bpms):
    db.add_all(models.HrSample(user_id=uid, sample_time=start + timedelta(seconds=step_s * i), bpm=b,
                               source="health_connect", source_package=pkg) for i, b in enumerate(bpms))
    db.commit()


def _day(n):
    """Start/stop of a 30-minute bout n days after S."""
    return S + timedelta(days=n), E + timedelta(days=n)


# ---- the categories, one row each ----------------------------------------------------------------------------

def test_every_category_is_counted_per_source_and_the_polar_split_reads_from_the_same_rows(db_session):
    u = _user(db_session)
    _seeded(db_session, u.id)
    bike = _row(db_session, u.id, "bike", *_day(0), zoned=True)                                  # HC, lthr class, zoned
    walk = _row(db_session, u.id, "walk", *_day(1), sport="Walking", zoned=True)                 # HC, hrr class, zoned
    held = _row(db_session, u.id, "held", *_day(2), sport="Walking")                             # HC, no samples: withheld
    rez_s, rez_e = _day(3)
    rezoned = _row(db_session, u.id, "rez", rez_s, rez_e, source="polar_v4", sport="Indoor cycling")
    _samples(db_session, u.id, POLAR_FLOW, rez_s, 10, [134] * 181)                               # the Flow trace covers it
    fallback = _row(db_session, u.id, "fb", *_day(4), source="polar_v4", sport="Indoor cycling")  # no trace: vendor kept
    cov = zone_reads.zone_coverage(db_session, u.id, today=TODAY)

    assert cov["total"] == 5 and cov["days"] is None and cov["since"] is None
    assert cov["date_range"] == {"first": "2026-10-29", "last": "2026-11-02"}
    assert cov["by_source"]["health_connect"] == {"lthr": 1, "hrr": 1, "vendor": 0, "no_anchor": 0, "withheld": 1}
    assert cov["by_source"]["polar_v4"] == {"lthr": 1, "hrr": 0, "vendor": 1, "no_anchor": 0, "withheld": 0}
    assert cov["totals"] == {"lthr": 2, "hrr": 1, "vendor": 1, "no_anchor": 0, "withheld": 1}
    assert sum(cov["totals"].values()) == cov["total"]
    assert cov["polar"] == {"rows": 2, "rezoned": 1, "vendor_fallback": 1, "vendor_no_anchor": 0}
    listed = {r["id"]: r for r in cov["rows"]}
    assert set(listed) == {held.id, fallback.id} and bike.id not in listed and walk.id not in listed and rezoned.id not in listed
    assert listed[held.id] == {"id": held.id, "date": "2026-10-31", "sport": "Walking", "source": "health_connect",
                              "basis": "hrr", "reason": "withheld"}
    assert listed[fallback.id] == {"id": fallback.id, "date": "2026-11-02", "sport": "Indoor cycling", "source": "polar_v4",
                                  "basis": "vendor", "reason": "polar_vendor_fallback"}
    assert cov["rows_not_listed"] == 0


def test_without_anchors_every_row_is_no_anchor_and_a_polar_row_is_not_counted_as_vendor_fallback(db_session):
    """The nuance the sessions API folds together: a Polar row with no anchor reads basis `vendor`, reason
    `no_anchor`. The count keeps it under no_anchor and reports it on the Polar line, so `vendor` equals
    `polar_vendor_fallback` exactly."""
    u = _user(db_session)
    hc = _row(db_session, u.id, "bike", *_day(0))
    polar = _row(db_session, u.id, "p", *_day(1), source="polar_v4", sport="Indoor cycling")
    cov = zone_reads.zone_coverage(db_session, u.id, today=TODAY)
    assert cov["totals"] == {"lthr": 0, "hrr": 0, "vendor": 0, "no_anchor": 2, "withheld": 0}
    assert cov["by_source"] == {"health_connect": {"lthr": 0, "hrr": 0, "vendor": 0, "no_anchor": 1, "withheld": 0},
                                "polar_v4": {"lthr": 0, "hrr": 0, "vendor": 0, "no_anchor": 1, "withheld": 0}}
    assert cov["polar"] == {"rows": 1, "rezoned": 0, "vendor_fallback": 0, "vendor_no_anchor": 1}
    rows = {r["id"]: r for r in cov["rows"]}
    assert rows[hc.id]["basis"] is None and rows[hc.id]["reason"] == "no_anchor"
    assert rows[polar.id]["basis"] == "vendor" and rows[polar.id]["reason"] == "no_anchor"


def test_a_polar_flow_export_row_is_its_own_source_and_any_other_source_still_counts(db_session):
    u = _user(db_session)
    _seeded(db_session, u.id)
    _row(db_session, u.id, "fx", *_day(0), source="polar_flow_export", sport="Cycling")
    _row(db_session, u.id, "man", *_day(1), source="manual", sport="Rowing", z1_seconds=0, z2_seconds=0, z3_seconds=0,
         z4_seconds=0, z5_seconds=0)
    cov = zone_reads.zone_coverage(db_session, u.id, today=TODAY)
    assert set(cov["by_source"]) == {"polar_flow_export", "manual"}
    assert cov["by_source"]["polar_flow_export"]["vendor"] == 1 and cov["polar"]["vendor_fallback"] == 1
    assert cov["by_source"]["manual"]["hrr"] == 1                     # a non-Polar, non-HC row: the model's basis, never withheld
    assert cov["polar"]["rows"] == 1


# ---- the Polar classification is row_zoning's, not a second implementation --------------------------------------

def test_the_polar_classification_calls_row_zoning_for_every_row(db_session, monkeypatch):
    """The brief's VERIFY: the sessions API and the coverage read classify a Polar row by the same code path.
    Pinned by spying on `row_zoning`: every row, Polar rows included, goes through it exactly once, and the
    category is a pure function of what it returned."""
    u = _user(db_session)
    _seeded(db_session, u.id)
    rez_s, rez_e = _day(0)
    rez = _row(db_session, u.id, "rez", rez_s, rez_e, source="polar_v4", sport="Indoor cycling")
    _samples(db_session, u.id, POLAR_FLOW, rez_s, 10, [134] * 181)
    fb = _row(db_session, u.id, "fb", *_day(1), source="polar_v4", sport="Indoor cycling")
    hc = _row(db_session, u.id, "hc", *_day(2), zoned=True)
    seen: dict[int, dict] = {}
    real = zone_reads.row_zoning

    def spy(db, user_id, row, entries):
        assert row.id not in seen                                     # once per row
        seen[row.id] = out = real(db, user_id, row, entries)
        return out

    monkeypatch.setattr(zone_reads, "row_zoning", spy)
    cov = zone_reads.zone_coverage(db_session, u.id, today=TODAY)
    assert set(seen) == {rez.id, fb.id, hc.id}
    assert seen[rez.id]["basis"] == "lthr" and seen[fb.id]["reason"] == "polar_vendor_fallback"
    assert cov["polar"] == {"rows": 2, "rezoned": 1, "vendor_fallback": 1, "vendor_no_anchor": 0}
    for row_id, z in seen.items():
        assert zone_reads.coverage_category(z) in zone_reads.COVERAGE_CATEGORIES


def test_coverage_category_is_the_reason_first_then_the_basis():
    cat = zone_reads.coverage_category
    assert cat({"basis": "lthr", "reason": None}) == "lthr"
    assert cat({"basis": "hrr", "reason": None}) == "hrr"
    assert cat({"basis": "hrr", "reason": "withheld"}) == "withheld"
    assert cat({"basis": None, "reason": "no_anchor"}) == "no_anchor"
    assert cat({"basis": "vendor", "reason": "no_anchor"}) == "no_anchor"
    assert cat({"basis": "vendor", "reason": "polar_vendor_fallback"}) == "vendor"


# ---- the window, the cap, and read-only --------------------------------------------------------------------------

def test_the_days_filter_cuts_on_session_date_and_reports_its_window(db_session):
    u = _user(db_session)
    _seeded(db_session, u.id)
    old_s = S - timedelta(days=40)
    old = _row(db_session, u.id, "old", old_s, old_s + timedelta(minutes=30), zoned=True)         # 19 Sep
    edge_s = datetime(2026, 10, 25, 20, 0, tzinfo=timezone.utc)                                   # 26 Oct AEST = today - 10
    edge = _row(db_session, u.id, "edge", edge_s, edge_s + timedelta(minutes=30), zoned=True)
    new = _row(db_session, u.id, "new", *_day(0), zoned=True)                                     # 29 Oct
    full = zone_reads.zone_coverage(db_session, u.id, today=TODAY)
    assert full["total"] == 3 and full["date_range"]["first"] == "2026-09-19"
    cov = zone_reads.zone_coverage(db_session, u.id, days=10, today=TODAY)
    assert cov["days"] == 10 and cov["since"] == "2026-10-26"
    assert cov["total"] == 2 and cov["date_range"] == {"first": "2026-10-26", "last": "2026-10-29"}
    assert cov["totals"]["lthr"] == 2
    assert zone_reads.zone_coverage(db_session, u.id, days=9, today=TODAY)["total"] == 1       # the edge row drops
    assert {old.id, edge.id, new.id} and zone_reads.zone_coverage(db_session, u.id, days=0, today=TODAY)["total"] == 0


def test_an_empty_window_reads_as_empty_not_as_an_error(db_session):
    u = _user(db_session)
    cov = zone_reads.zone_coverage(db_session, u.id, today=TODAY)
    assert cov["total"] == 0 and cov["date_range"] is None and cov["by_source"] == {} and cov["rows"] == []
    assert cov["totals"] == {c: 0 for c in zone_reads.COVERAGE_CATEGORIES}
    assert "no aerobic sessions in the window" in zone_reads.format_zone_coverage(cov)


def test_the_listed_rows_cap_at_twenty_oldest_first_and_the_rest_are_counted(db_session):
    u = _user(db_session)
    _seeded(db_session, u.id)
    ids = []
    for i in range(23):
        s = S - timedelta(days=i)
        ids.append(_row(db_session, u.id, f"w{i}", s, s + timedelta(minutes=30), sport="Walking").id)   # withheld
    _row(db_session, u.id, "ok", *_day(1), zoned=True)                                              # zoned: never listed
    cov = zone_reads.zone_coverage(db_session, u.id, today=TODAY)
    assert cov["total"] == 24 and cov["totals"]["withheld"] == 23
    assert len(cov["rows"]) == zone_reads.COVERAGE_SAMPLE_CAP == 20 and cov["rows_not_listed"] == 3
    dates = [r["date"] for r in cov["rows"]]
    assert dates == sorted(dates) and dates[0] == (S - timedelta(days=22) + timedelta(hours=10)).date().isoformat()
    assert all(r["reason"] == "withheld" for r in cov["rows"])
    text = zone_reads.format_zone_coverage(cov)
    assert "first 20; 3 more not listed" in text


def test_the_read_writes_nothing(db_session, monkeypatch):
    uid = _user(db_session).id
    _seeded(db_session, uid)
    rez_s, rez_e = _day(0)
    _row(db_session, uid, "rez", rez_s, rez_e, source="polar_v4", sport="Indoor cycling")
    _samples(db_session, uid, POLAR_FLOW, rez_s, 10, [134] * 181)
    _row(db_session, uid, "held", *_day(1), sport="Walking")
    _row(db_session, uid, "bike", *_day(2), zoned=True)
    before = [(r.id, r.z1_seconds, r.z2_seconds, r.hr_avg, r.hr_max) for r in
              db_session.query(models.AerobicSession).order_by(models.AerobicSession.id).all()]
    db_session.expunge_all()
    monkeypatch.setattr(db_session, "commit", lambda: pytest.fail("zone_coverage committed"))
    monkeypatch.setattr(db_session, "flush", lambda *a, **k: pytest.fail("zone_coverage flushed"))
    cov = zone_reads.zone_coverage(db_session, uid, today=TODAY)
    assert cov["total"] == 3
    assert not db_session.dirty and not db_session.new and not db_session.deleted
    monkeypatch.undo()
    db_session.expunge_all()
    after = [(r.id, r.z1_seconds, r.z2_seconds, r.hr_avg, r.hr_max) for r in
             db_session.query(models.AerobicSession).order_by(models.AerobicSession.id).all()]
    assert after == before
    assert db_session.query(models.UserHrAnchor).count() == 2 and db_session.query(models.UserHrmax).count() == 1


# ---- the formatter ---------------------------------------------------------------------------------------------------

def test_the_formatter_names_the_window_each_source_the_polar_split_and_where_the_counts_come_from(db_session):
    u = _user(db_session)
    _seeded(db_session, u.id)
    _row(db_session, u.id, "bike", *_day(0), zoned=True)
    _row(db_session, u.id, "held", *_day(1), sport="Walking")
    fb = _row(db_session, u.id, "fb", *_day(2), source="polar_v4", sport="Indoor cycling")
    text = zone_reads.format_zone_coverage(zone_reads.zone_coverage(db_session, u.id, days=14, today=TODAY))
    lines = text.split("\n")
    assert lines[0].startswith("Zone coverage (as of 2026-11-05; last 14 days, since 2026-10-22;")
    assert "3 rows, 2026-10-29 to 2026-10-31: lthr 1 · hrr 0 · vendor (polar_vendor_fallback) 1 · no_anchor 0 · withheld 1" in text
    assert "  health_connect (2): lthr 1 · hrr 0 · vendor (polar_vendor_fallback) 0 · no_anchor 0 · withheld 1" in text
    assert "  polar_v4 (1): lthr 0 · hrr 0 · vendor (polar_vendor_fallback) 1 · no_anchor 0 · withheld 0" in text
    assert "  Polar rows 1: polar_rezoned 0 (zoned on the model from the fi.polar.polarflow trace) · polar_vendor_fallback 1" in text
    assert f"    row {fb.id} 2026-10-31 Indoor cycling [polar_v4]: polar_vendor_fallback (basis vendor)" in text
    assert lines[-1] == ("  Counts are derived live from reads.zone_reads.row_zoning, the sessions API's zoning path; "
                         "the refresh_load chain report is not stored, so no run-to-run delta is available here.")


# ---- the MCP tool ----------------------------------------------------------------------------------------------------

@pytest.fixture
def call(db_session, monkeypatch):
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(mcp_server, "_local_day", lambda *a, **k: TODAY)
    u = _user(db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: u.id)
    return lambda **kw: (u, mcp_server.get_zone_coverage(**kw))


def test_the_mcp_tool_renders_the_read_stamped_and_takes_days(db_session, call):
    u, _ = call()
    _seeded(db_session, u.id)
    _row(db_session, u.id, "bike", *_day(0), zoned=True)
    old_s = S - timedelta(days=40)
    _row(db_session, u.id, "old", old_s, old_s + timedelta(minutes=30), sport="Walking")
    _, out = call()
    assert out.startswith("as_of:") and "Zone coverage (as of 2026-11-05; all history;" in out
    assert "2 rows, 2026-09-19 to 2026-10-29: lthr 1 · hrr 0 · vendor (polar_vendor_fallback) 0 · no_anchor 0 · withheld 1" in out
    _, out = call(days=14)
    assert "last 14 days, since 2026-10-22" in out and "1 row, 2026-10-29 to 2026-10-29" in out
    assert out.rstrip().endswith("so no run-to-run delta is available here.")
    assert not db_session.dirty and db_session.query(models.AerobicSession).count() == 2


def test_the_mcp_tool_is_registered_read_only_derived_and_days_defaults_to_none():
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    t = tools["get_zone_coverage"]
    assert set(t.inputSchema["properties"]) == {"days"}
    assert t.inputSchema["properties"]["days"]["default"] is None and "days" not in t.inputSchema.get("required", [])
    assert "Read-only" in t.description and "DERIVED" in t.description and "not stored" in t.description
