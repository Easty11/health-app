"""The zone-config surface (design 0010 §6): `GET /hr-zones/config`, the anchor preview and append (the forced
choice, R6), the per-row `zoning` on the sessions API, and the MCP `get_hr_zone_config` tool (R7).

GATES:
  * the config read carries both classes with today's bpm edges, every anchor's entry in force and history, the
    derived retest flag, the R8 default date, and the Garmin mirror (observation only);
  * `change` is REQUIRED: a dated change on a date that has a row is refused with the way out, a restatement on
    a date without one likewise; a restatement needs a rationale; `kind: hrmax` is refused naming the script;
  * preview writes nothing and reports the edges before/after and the rows whose spec changes; append writes
    ONE row, never updates or deletes, and the next enrich reflows;
  * `zoning` on a session row says what zoned it (`lthr` / `hrr` / `vendor` / withheld);
  * the MCP tool renders the same read.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import null

import hc_zone_enrich
import hr_anchors
import mcp_server
import models
from auth import get_current_user
from database import get_db
from reads import zone_reads
from routers import hr_zones as hr_zones_router
from routers import polar as polar_router

TODAY = date(2026, 11, 5)
GARMIN = "com.garmin.android.apps.connectmobile"
POLAR_FLOW = "fi.polar.polarflow"
S = datetime(2026, 10, 28, 20, 0, 0, tzinfo=timezone.utc)      # 06:00 AEST 29 Oct
E = S + timedelta(minutes=30)


def _user(db, email="zones@example.com"):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _hrmax(db, uid, bpm=179, eff=date(2026, 3, 1)):
    db.add(models.UserHrmax(user_id=uid, effective_from=eff, hrmax_bpm=bpm, provenance="observed", note="H10 max"))
    db.commit()


def _anchor(db, uid, kind, bpm, eff=date(2026, 3, 1), prov="stated", **kw):
    r = models.UserHrAnchor(user_id=uid, kind=kind, effective_from=eff, bpm=bpm, provenance=prov, note="t", **kw)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _row(db, uid, ssid, start=S, stop=E, *, sport="Biking Stationary", source="health_connect", pkg=GARMIN, **kw):
    if source == "health_connect":
        for z in ("z1_seconds", "z2_seconds", "z3_seconds", "z4_seconds", "z5_seconds"):
            kw.setdefault(z, null())
    r = models.AerobicSession(user_id=uid, source=source, source_session_id=ssid, session_date=(start + timedelta(hours=10)).date(),
                              start_time=start, stop_time=stop, sport_name=sport,
                              duration_minutes=(stop - start).total_seconds() / 60,
                              source_package=pkg if source == "health_connect" else None, **kw)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _samples(db, uid, pkg, start, step_s, bpms):
    db.add_all(models.HrSample(user_id=uid, sample_time=start + timedelta(seconds=step_s * i), bpm=b,
                               source="health_connect", source_package=pkg) for i, b in enumerate(bpms))
    db.commit()


@pytest.fixture
def client(db_session, monkeypatch):
    monkeypatch.setattr(hr_zones_router, "_local_day", lambda *a, **k: TODAY)
    u = _user(db_session)
    app = FastAPI()
    app.include_router(hr_zones_router.router)
    app.include_router(polar_router.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: u
    return u, TestClient(app)


def _seeded(db, u):
    _hrmax(db, u.id)
    _anchor(db, u.id, "lthr", 158, prov="device_estimated")
    _anchor(db, u.id, "rhr", 51)


ANCHOR = dict(kind="rhr", bpm=48, effective_from="2026-10-01", provenance="observed", note="supine, 7-day strap",
              change="dated")


# ---- the read ----------------------------------------------------------------------------------------------

def test_the_config_read_carries_classes_anchors_retest_default_date_and_the_garmin_mirror(db_session, client):
    u, c = client
    _seeded(db_session, u)
    _row(db_session, u.id, "bike", S - timedelta(days=200), E - timedelta(days=200))   # the earliest session: R8
    db_session.add(models.HrZoneConfigSnapshot(user_id=u.id, source="garmin", transport="personal_api", max_hr_bpm=181,
                                               lthr_bpm=158, rhr_7d_auto_bpm=49, method="HR_RESERVE", payload_sha256="x" * 64,
                                               captured_at=datetime(2026, 11, 4, tzinfo=timezone.utc)))
    db_session.commit()
    r = c.get("/hr-zones/config")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["as_of"] == "2026-11-05"
    by = {k["key"]: k for k in cfg["classes"]}
    assert by["lthr"]["edges_bpm"] == [0, 128, 143, 149, 158] and by["lthr"]["anchors"] == {"lthr": 158}
    assert by["hrr"]["edges_bpm"] == [115, 128, 141, 154, 167] and by["hrr"]["anchors"] == {"hrmax": 179, "rhr": 51}
    assert "Biking Stationary" in by["lthr"]["sports"] and by["hrr"]["sports"] == []
    assert by["lthr"]["band_pct"] == [0, 81, 90, 94, 100] and by["hrr"]["band_pct"] == [50, 60, 70, 80, 90]
    a = cfg["anchors"]
    assert a["hrmax"]["in_force"]["bpm"] == 179 and a["hrmax"]["writable"] is False and "set_hrmax" in a["hrmax"]["writer"]
    assert a["lthr"]["in_force"]["provenance"] == "device_estimated" and a["lthr"]["retest"] is True
    assert a["rhr"]["retest"] is False and a["rhr"]["writable"] is True and len(a["rhr"]["entries"]) == 1
    assert cfg["default_effective_from"] == (S - timedelta(days=200) + timedelta(hours=10)).date().isoformat()
    assert "r8_pending" not in cfg        # R8 is ruled (design 0010 row 4); the default date is the rule, not a proposal
    assert cfg["garmin"]["profile"]["cycling"]["basis"] == "%LTHR" and cfg["garmin"]["profile"]["default"]["bands"][1] == "60-69"
    assert cfg["garmin"]["snapshot"]["lthr_bpm"] == 158 and cfg["garmin"]["snapshot"]["rhr_7d_auto_bpm"] == 49
    assert cfg["hrmax_prompts"] == []


def test_a_missing_anchor_leaves_the_class_without_bpm_edges_and_names_it(db_session, client):
    u, c = client
    _hrmax(db_session, u.id)
    cfg = c.get("/hr-zones/config").json()
    by = {k["key"]: k for k in cfg["classes"]}
    assert by["lthr"]["edges_bpm"] is None and by["lthr"]["missing"] == ["lthr"]
    assert by["hrr"]["edges_bpm"] is None and by["hrr"]["missing"] == ["rhr"]
    assert cfg["anchors"]["lthr"]["in_force"] is None and cfg["default_effective_from"] == "2026-11-05"


def test_a_restated_anchor_reads_as_the_entry_in_force_and_its_target_as_superseded(db_session, client):
    u, c = client
    _seeded(db_session, u)
    seed = db_session.query(models.UserHrAnchor).filter_by(kind="rhr").one()
    _anchor(db_session, u.id, "rhr", 48, restates_id=seed.id, rationale="a better read")
    a = c.get("/hr-zones/config").json()["anchors"]["rhr"]
    assert a["in_force"]["bpm"] == 48 and a["in_force"]["restates_id"] == seed.id
    assert [(e["bpm"], e["superseded"]) for e in a["entries"]] == [(51, True), (48, False)]


# ---- preview and append: the forced choice ---------------------------------------------------------------

def test_preview_reports_edges_before_and_after_and_the_rows_that_move_and_writes_nothing(db_session, client):
    u, c = client
    _seeded(db_session, u)
    walk = _row(db_session, u.id, "walk", sport="Walking")                                   # 29 Oct: after 1 Oct
    old_s = S - timedelta(days=60)
    _row(db_session, u.id, "old", old_s, old_s + timedelta(minutes=30), sport="Walking")     # 30 Aug: before
    bike = _row(db_session, u.id, "bike", S + timedelta(days=1), E + timedelta(days=1))       # the LTHR class: untouched
    r = c.post("/hr-zones/anchors/preview", json=ANCHOR)
    assert r.status_code == 200, r.text
    p = r.json()
    hrr_before = next(k for k in p["classes_before"] if k["key"] == "hrr")["edges_bpm"]
    hrr_after = next(k for k in p["classes_after"] if k["key"] == "hrr")["edges_bpm"]
    assert hrr_before == [115, 128, 141, 154, 167] and hrr_after == [114, 127, 140, 153, 166]    # reserve 131
    assert p["rows_changed"] == 1 and [x["id"] for x in p["rows"]] == [walk.id]
    assert p["rows"][0]["from"] == hrr_before and p["rows"][0]["to"] == hrr_after
    assert bike.id not in [x["id"] for x in p["rows"]] and p["restates"] is None
    assert db_session.query(models.UserHrAnchor).count() == 2                                 # nothing written


def test_append_writes_one_row_and_the_next_enrich_reflows(db_session, client):
    u, c = client
    _seeded(db_session, u)
    walk = _row(db_session, u.id, "walk", sport="Walking")
    _samples(db_session, u.id, GARMIN, S, 10, [140] * 181)                 # 140: z2 at RHR 51 (128-140); z3 at RHR 48 (140+)
    hc_zone_enrich.enrich_user(db_session, u.id)
    db_session.expire_all()
    assert db_session.get(models.AerobicSession, walk.id).z2_seconds == 1800
    r = c.post("/hr-zones/anchors", json=ANCHOR)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["written"] is True and body["row"]["kind"] == "rhr" and body["row"]["bpm"] == 48
    rows = db_session.query(models.UserHrAnchor).filter_by(kind="rhr").order_by(models.UserHrAnchor.id).all()
    assert [(x.bpm, x.effective_from.isoformat(), x.restates_id) for x in rows] == [(51, "2026-03-01", None), (48, "2026-10-01", None)]
    hc_zone_enrich.enrich_user(db_session, u.id)
    db_session.expire_all()
    assert db_session.get(models.AerobicSession, walk.id).z3_seconds == 1800


def test_a_dated_change_on_a_date_that_has_a_row_is_refused_and_a_restatement_there_is_accepted(db_session, client):
    u, c = client
    _seeded(db_session, u)
    r = c.post("/hr-zones/anchors", json={**ANCHOR, "effective_from": "2026-03-01"})
    assert r.status_code == 400 and "restate" in r.json()["detail"]
    r = c.post("/hr-zones/anchors", json={**ANCHOR, "effective_from": "2026-03-01", "change": "restate"})
    assert r.status_code == 400 and "rationale" in r.json()["detail"]
    r = c.post("/hr-zones/anchors", json={**ANCHOR, "effective_from": "2026-03-01", "change": "restate", "rationale": "wrong read"})
    assert r.status_code == 201, r.text
    assert r.json()["restates"]["bpm"] == 51
    rows = db_session.query(models.UserHrAnchor).filter_by(kind="rhr").all()
    assert len(rows) == 2 and {x.restates_id for x in rows} == {None, min(x.id for x in rows)}   # append-only


def test_a_restatement_on_a_date_without_a_row_is_refused_with_the_way_out(db_session, client):
    u, c = client
    _seeded(db_session, u)
    r = c.post("/hr-zones/anchors", json={**ANCHOR, "change": "restate", "rationale": "r"})   # 1 Oct has no row
    assert r.status_code == 400
    assert "nothing to restate" in r.json()["detail"] and "2026-03-01" in r.json()["detail"]


@pytest.mark.parametrize("bad,needle", [
    (dict(change="edit"), "change must be"), (dict(kind="hrmax"), "set_hrmax"), (dict(kind="vo2"), "kind must be"),
    (dict(provenance="estimated"), "provenance must be"), (dict(bpm=20), "plausibility"), (dict(note="  "), "note"),
])
def test_field_refusals_name_the_way_out(db_session, client, bad, needle):
    u, c = client
    _seeded(db_session, u)
    r = c.post("/hr-zones/anchors", json={**ANCHOR, **bad})
    assert r.status_code == 400 and needle in r.json()["detail"], r.text
    assert db_session.query(models.UserHrAnchor).count() == 2


def test_change_is_required_not_defaulted(db_session, client):
    u, c = client
    _seeded(db_session, u)
    body = {k: v for k, v in ANCHOR.items() if k != "change"}
    assert c.post("/hr-zones/anchors", json=body).status_code == 422
    assert c.post("/hr-zones/anchors/preview", json=body).status_code == 422


def test_the_writer_never_updates_or_deletes(db_session, client):
    u, c = client
    _seeded(db_session, u)
    before = {(x.id, x.bpm, x.effective_from) for x in db_session.query(models.UserHrAnchor).all()}
    c.post("/hr-zones/anchors", json=ANCHOR)
    c.post("/hr-zones/anchors", json={**ANCHOR, "kind": "lthr", "bpm": 160, "effective_from": "2026-03-01",
                                      "change": "restate", "rationale": "30-min TT", "provenance": "tested"})
    after = {(x.id, x.bpm, x.effective_from) for x in db_session.query(models.UserHrAnchor).all()}
    assert before <= after and len(after) == len(before) + 2
    cfg = c.get("/hr-zones/config").json()
    assert cfg["anchors"]["lthr"]["in_force"]["bpm"] == 160 and cfg["anchors"]["lthr"]["retest"] is False


# ---- per-row zoning on the sessions API ------------------------------------------------------------------------

def test_sessions_carry_what_zoned_them(db_session, client):
    u, c = client
    _seeded(db_session, u)
    bike = _row(db_session, u.id, "bike")                                          # LTHR class, zoned
    _samples(db_session, u.id, GARMIN, S, 10, [134] * 181)
    walk_s = S + timedelta(days=1)
    walk = _row(db_session, u.id, "walk", walk_s, walk_s + timedelta(minutes=30), sport="Walking")   # HRR class, no samples
    p_s = S + timedelta(days=2)
    polar = _row(db_session, u.id, "p", p_s, p_s + timedelta(minutes=30), source="polar_v4", sport="Indoor cycling",
                 z1_seconds=1, z2_seconds=2, z3_seconds=3, z4_seconds=4, z5_seconds=5)
    hc_zone_enrich.enrich_user(db_session, u.id)
    rows = {r["id"]: r for r in c.get("/integrations/polar/aerobic-sessions").json()}
    assert rows[bike.id]["zoning"] == {"class": "lthr", "class_label": "cycling", "basis": "lthr",
                                       "basis_label": "% of LTHR (Friel)", "anchors": {"lthr": 158},
                                       "edges_bpm": [0, 128, 143, 149, 158], "reason": None}
    assert rows[walk.id]["zoning"]["basis"] == "hrr" and rows[walk.id]["zoning"]["reason"] == "withheld"
    assert rows[walk.id]["zoning"]["anchors"] == {"hrmax": 179, "rhr": 51}
    assert rows[polar.id]["zoning"]["basis"] == "vendor" and rows[polar.id]["zoning"]["reason"] == "polar_vendor_fallback"
    assert rows[polar.id]["zoning"]["class"] == "lthr"


def test_a_polar_row_the_polar_flow_trace_covers_reads_as_zoned_on_the_model(db_session, client):
    u, c = client
    _seeded(db_session, u)
    polar = _row(db_session, u.id, "p", source="polar_v4", sport="Indoor cycling",
                 z1_seconds=1, z2_seconds=2, z3_seconds=3, z4_seconds=4, z5_seconds=5)
    _samples(db_session, u.id, POLAR_FLOW, S, 1, [134] * 1801)
    hc_zone_enrich.enrich_user(db_session, u.id)
    z = {r["id"]: r for r in c.get("/integrations/polar/aerobic-sessions").json()}[polar.id]["zoning"]
    assert z["basis"] == "lthr" and z["reason"] is None


def test_without_anchors_every_row_reads_no_anchor(db_session, client):
    u, c = client
    hc = _row(db_session, u.id, "bike")
    z = {r["id"]: r for r in c.get("/integrations/polar/aerobic-sessions").json()}[hc.id]["zoning"]
    assert z["basis"] is None and z["reason"] == "no_anchor" and z["edges_bpm"] is None


# ---- the MCP tool (R7) ------------------------------------------------------------------------------------------

def test_the_mcp_tool_renders_the_config_read_only(db_session, monkeypatch):
    u = _user(db_session)
    _seeded(db_session, u)
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(mcp_server, "_local_day", lambda *a, **k: TODAY)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: u.id)
    out = mcp_server.get_hr_zone_config()
    assert out.startswith("as_of:")
    assert "cycling: % of LTHR (Friel)" in out and "bpm today: z1 0-127 · z2 128-142 · z3 143-148 · z4 149-157 · z5 158+" in out
    assert "other sports: % of heart-rate reserve (Karvonen)" in out and "z2 128-140" in out
    assert "LTHR: 158 bpm, device_estimated, from 2026-03-01 — RETEST" in out
    assert "Resting HR: 51 bpm, stated" in out and "HRmax: 179 bpm, observed" in out
    assert "never the live daily device RHR" in out
    assert db_session.query(models.UserHrAnchor).count() == 2


def test_the_mcp_tool_is_registered_and_the_formatter_names_missing_anchors(db_session):
    import asyncio
    tools = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert "get_hr_zone_config" in tools
    u = _user(db_session)
    _hrmax(db_session, u.id)
    text = zone_reads.format_zone_config(zone_reads.zone_config(db_session, u.id, today=TODAY))
    assert "missing anchor(s): lthr" in text and "missing anchor(s): rhr" in text and "LTHR: none in force" in text


# ---- the writer module directly: plan on an empty ledger and the restatement chain ------------------------------

def test_plan_names_the_rows_a_first_anchor_would_zone(db_session):
    u = _user(db_session)
    _hrmax(db_session, u.id)
    _anchor(db_session, u.id, "lthr", 158)
    walk = _row(db_session, u.id, "walk", sport="Walking")
    p = hr_anchors.plan(db_session, u.id, kind="rhr", bpm=51, effective_from=date(2026, 3, 1), provenance="stated",
                        change="dated", today=TODAY)
    assert p["rows_changed"] == 1 and p["rows"][0]["id"] == walk.id and p["rows"][0]["from"] is None
    assert p["rows"][0]["to"] == [115, 128, 141, 154, 167]


def test_restating_an_already_restated_date_corrects_the_latest(db_session):
    u = _user(db_session)
    seed = _anchor(db_session, u.id, "rhr", 51)
    kw = dict(kind="rhr", effective_from=date(2026, 3, 1), provenance="observed", note="n", change="restate", today=TODAY)
    first = hr_anchors.append(db_session, u.id, bpm=49, rationale="first", **kw)
    second = hr_anchors.append(db_session, u.id, bpm=47, rationale="second", **kw)
    assert first["restates"]["id"] == seed.id and second["restates"]["bpm"] == 49
    with pytest.raises(hr_anchors.AnchorRefused, match="already 47 bpm, observed"):
        hr_anchors.append(db_session, u.id, bpm=47, rationale="same", **kw)


# ---- the no-op test is on (value, provenance), not value alone (#504) -------------------------------------------

def test_the_same_value_under_a_new_provenance_is_a_restatement_and_moves_the_retest_flag(db_session, client):
    """The operator's own case: LTHR 158 seeded `observed`, restated 158 `device_estimated` (Garmin auto-detect).
    Provenance is part of the row's meaning (it drives the retest flag), so the write is accepted, the chain
    records it, and the in-force entry now reads retest."""
    u, c = client
    _hrmax(db_session, u.id)
    seed = _anchor(db_session, u.id, "lthr", 158, prov="observed")
    body = {"kind": "lthr", "bpm": 158, "effective_from": "2026-03-01", "provenance": "device_estimated",
            "note": "Garmin auto-detect 2026-10-28", "change": "restate", "rationale": "the 158 was Garmin's estimate, not a strap read"}
    p = c.post("/hr-zones/anchors/preview", json=body)
    assert p.status_code == 200, p.text
    assert p.json()["restates"] == {"id": seed.id, "bpm": 158, "provenance": "observed", "effective_from": "2026-03-01"}
    assert p.json()["provenance"] == "device_estimated" and p.json()["rows_changed"] == 0     # the bpm edges do not move
    r = c.post("/hr-zones/anchors", json=body)
    assert r.status_code == 201, r.text
    rows = db_session.query(models.UserHrAnchor).filter_by(kind="lthr").order_by(models.UserHrAnchor.id).all()
    assert [(x.bpm, x.provenance, x.restates_id) for x in rows] == [(158, "observed", None), (158, "device_estimated", seed.id)]
    cfg = c.get("/hr-zones/config").json()["anchors"]["lthr"]
    assert cfg["in_force"]["bpm"] == 158 and cfg["in_force"]["provenance"] == "device_estimated"
    assert cfg["in_force"]["restates_id"] == seed.id and cfg["retest"] is True


def test_the_same_value_under_the_same_provenance_is_still_refused(db_session, client):
    u, c = client
    _hrmax(db_session, u.id)
    _anchor(db_session, u.id, "lthr", 158, prov="observed")
    body = {"kind": "lthr", "bpm": 158, "effective_from": "2026-03-01", "provenance": "observed",
            "note": "n", "change": "restate", "rationale": "r"}
    for url in ("/hr-zones/anchors/preview", "/hr-zones/anchors"):
        r = c.post(url, json=body)
        assert r.status_code == 400, r.text
        assert "already 158 bpm, observed" in r.json()["detail"] and "provenance" in r.json()["detail"]
    assert db_session.query(models.UserHrAnchor).filter_by(kind="lthr").count() == 1
