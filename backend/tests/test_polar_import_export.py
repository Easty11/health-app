"""Polar Flow-export upload endpoint + per-user metabolic cascade + coverage flag.

Covers the Phase-1 brief gates:
  * G2  CLI-equivalence — `import_flow_export` dry-run vs write produce identical
        substance (parse + dedup unchanged; `_parse_session` used verbatim).
  * G3  full-path — upload → `aerobic_sessions` rows → metabolic `load_events`
        (`metab-v1`) → `load_metrics` metabolic rows, all scoped to the test user.
  * plus dedup, non-ZIP rejection, cap breach, cascade scoping, and coverage counts.

The endpoint is exercised through a minimal FastAPI app (router + dependency
overrides) so the test never imports `main` (which mounts the MCP sub-app).
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import models
from auth import get_current_user
from database import get_db
from import_polar import _parse_session, import_flow_export
from metabolic_cascade import run_metabolic_cascade
from load_events_metabolic import FORMULA_VERSION_METABOLIC
from reads.aerobic_reads import ZONELESS_STALE_DAYS, coverage_notice, zone_coverage
from routers import polar


# ── fixtures: synthetic Polar Flow training-session JSON + ZIP ────────────────────

def _training_session(
    sid: str,
    start: datetime,
    *,
    sport_id: int = 1,
    zones_seconds: tuple | None = (600, 300, 0, 0, 120),
    cardio_load: float | None = 42.0,
    hr_avg: int | None = 150,
) -> dict:
    """One Polar Flow export `training-session_*.json` body. `zones_seconds` is the
    per-zone in-zone SECONDS (converted to the export's millisecond `inZone`); None
    means a zoneless session (no exercises block) — the fail-closed case."""
    stop = start + timedelta(minutes=30)
    body: dict = {
        "startTime": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "stopTime": stop.strftime("%Y-%m-%dT%H:%M:%S"),
        "timezoneOffsetMinutes": 600,  # AEST
        "identifier": {"id": sid},
        "sport": {"id": sport_id},
        "hrAvg": hr_avg,
        "hrMax": 175,
        "calories": 300,
        "durationMillis": 30 * 60 * 1000,
        "recoveryTimeMillis": 20 * 3600 * 1000,
        "trainingLoadReport": {"cardioLoad": cardio_load, "muscleLoad": -1.0},
    }
    if zones_seconds is not None:
        body["exercises"] = [{
            "zones": [{
                "type": "ZONE_TYPE_HEART_RATE",
                "zones": [{"inZone": s * 1000} for s in zones_seconds],
            }],
        }]
    return body


def _zip_bytes(sessions: dict[str, dict], *, extra_members: dict | None = None) -> bytes:
    """Pack `{member_name: body}` into a ZIP. `extra_members` (name→text) become
    non-session members that must be ignored by the parser."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in sessions.items():
            zf.writestr(name, json.dumps(body))
        for name, text in (extra_members or {}).items():
            zf.writestr(name, text)
    return buf.getvalue()


def _default_zip() -> bytes:
    """3 sessions: two zone-carrying (Edwards 30 + 45) and one zoneless, plus a
    non-session member the parser must ignore."""
    base = datetime(2026, 6, 1, 6, 0)
    return _zip_bytes(
        {
            "training-session_1.json": _training_session(
                "p1", base, sport_id=1, zones_seconds=(600, 300, 0, 0, 120), cardio_load=42.0),
            "training-session_2.json": _training_session(
                "p2", base + timedelta(days=1), sport_id=2, zones_seconds=(0, 0, 900, 0, 0),
                cardio_load=30.0),
            "training-session_3.json": _training_session(
                "p3", base + timedelta(days=2), sport_id=4, zones_seconds=None, cardio_load=None),
        },
        extra_members={"account-info.json": '{"unrelated": true}', "README.txt": "ignore me"},
    )


# ── test app plumbing ─────────────────────────────────────────────────────────────

def _user(db, uid=1):
    u = models.User(id=uid, email=f"u{uid}@x.com", hashed_password="x")
    db.add(u)
    db.commit()
    return u


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(polar.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


# ── endpoint happy path ───────────────────────────────────────────────────────────

def test_upload_ingests_sessions_and_returns_cascade_and_coverage(db_session):
    user = _user(db_session)
    client = _client(db_session, user)

    resp = client.post(
        "/integrations/polar/import-export",
        files={"file": ("export.zip", _default_zip(), "application/zip")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["import"] == {
        "found": 3, "inserted": 3, "skipped": 0, "errors": 0, "pre_existing": 0,
    }
    # rows landed for this user, source polar_flow_export
    rows = db_session.query(models.AerobicSession).all()
    assert len(rows) == 3
    assert {r.source for r in rows} == {"polar_flow_export"}
    assert all(r.user_id == user.id for r in rows)

    # cascade fired: two qualifying sessions → two metabolic load_events, one skipped
    assert body["cascade"]["transform"]["events_written"] == 2
    assert body["cascade"]["transform"]["sessions_skipped_no_zones"] == 1
    assert "metabolic" in body["cascade"]["rollup"]["windows_computed"]

    # coverage reflects 2 zone-carrying + 1 zoneless (a fresh flow_export, so not stale)
    assert body["coverage"]["with_zones"] == 2
    assert body["coverage"]["zoneless"] == 1
    assert body["coverage"]["stale_zoneless"] == 0
    assert body["notice"] is None


def test_second_upload_is_a_noop_dedup(db_session):
    user = _user(db_session)
    client = _client(db_session, user)
    zb = _default_zip()

    client.post("/integrations/polar/import-export",
                files={"file": ("export.zip", zb, "application/zip")})
    resp = client.post("/integrations/polar/import-export",
                       files={"file": ("export.zip", zb, "application/zip")})
    body = resp.json()
    assert body["import"] == {
        "found": 3, "inserted": 0, "skipped": 3, "errors": 0, "pre_existing": 3,
    }
    assert db_session.query(models.AerobicSession).count() == 3  # no duplicates


# ── input hygiene ─────────────────────────────────────────────────────────────────

def test_non_zip_is_rejected_400(db_session):
    user = _user(db_session)
    client = _client(db_session, user)
    resp = client.post(
        "/integrations/polar/import-export",
        files={"file": ("not.zip", b"this is definitely not a zip", "application/zip")},
    )
    assert resp.status_code == 400
    assert "not a valid ZIP" in resp.json()["detail"]
    assert db_session.query(models.AerobicSession).count() == 0


def test_member_count_cap_breach_rejected_400(db_session, monkeypatch):
    user = _user(db_session)
    client = _client(db_session, user)
    monkeypatch.setattr(polar, "MAX_TRAINING_SESSION_MEMBERS", 1)
    resp = client.post(
        "/integrations/polar/import-export",
        files={"file": ("export.zip", _default_zip(), "application/zip")},
    )
    assert resp.status_code == 400
    assert "too many training-session members" in resp.json()["detail"]
    assert db_session.query(models.AerobicSession).count() == 0


def test_total_size_cap_breach_rejected_400(db_session, monkeypatch):
    user = _user(db_session)
    client = _client(db_session, user)
    monkeypatch.setattr(polar, "MAX_TOTAL_UNCOMPRESSED_BYTES", 10)  # 10 bytes: any real member busts it
    resp = client.post(
        "/integrations/polar/import-export",
        files={"file": ("export.zip", _default_zip(), "application/zip")},
    )
    assert resp.status_code == 400
    assert "total size cap" in resp.json()["detail"]


# ── G3: full path scoped to the user (cascade correctness + isolation) ────────────

def test_full_path_rows_events_metrics_all_scoped_to_user(db_session):
    """Upload → aerobic rows → metabolic load_events → load_metrics metabolic rows,
    every layer scoped to the uploading user; a second user's prior cascade output
    is left byte-identical."""
    u1 = _user(db_session, 1)
    u2 = _user(db_session, 2)

    # user 2 has a prior metabolic cascade of its own — must survive u1's ingest
    db_session.add(models.AerobicSession(
        user_id=2, source="polar_flow_export", source_session_id="u2s1",
        session_date=date(2026, 5, 1), start_time=datetime(2026, 5, 1, 6, 0, tzinfo=timezone.utc),
        z1_seconds=600, z2_seconds=0, z3_seconds=0, z4_seconds=0, z5_seconds=0,
    ))
    db_session.commit()
    run_metabolic_cascade(db_session, 2)
    u2_events_before = {
        (e.source_ref, e.load) for e in db_session.query(models.LoadEvent).filter_by(user_id=2)
    }
    u2_metrics_before = db_session.query(models.LoadMetric).filter_by(user_id=2).count()
    assert u2_events_before and u2_metrics_before  # non-vacuous

    _client(db_session, u1).post(
        "/integrations/polar/import-export",
        files={"file": ("export.zip", _default_zip(), "application/zip")},
    )

    # user 1: aerobic rows + metab-v1 load_events + metabolic load_metrics all present
    assert db_session.query(models.AerobicSession).filter_by(user_id=1).count() == 3
    u1_events = db_session.query(models.LoadEvent).filter_by(
        user_id=1, formula_version=FORMULA_VERSION_METABOLIC).all()
    assert len(u1_events) == 2 and all(e.load_window == "metabolic" for e in u1_events)
    u1_metrics = db_session.query(models.LoadMetric).filter_by(
        user_id=1, formula_version=FORMULA_VERSION_METABOLIC, load_window="metabolic").count()
    assert u1_metrics > 0

    # user 2 untouched
    u2_events_after = {
        (e.source_ref, e.load) for e in db_session.query(models.LoadEvent).filter_by(user_id=2)
    }
    assert u2_events_after == u2_events_before
    assert db_session.query(models.LoadMetric).filter_by(user_id=2).count() == u2_metrics_before


# ── cascade on /sync (harmless zoneless skip; both routes wired) ──────────────────

class _FakeClient:
    def __init__(self, raws):
        self._raws = raws

    def list_training_sessions_chunked(self, start, end):
        return self._raws


def test_sync_route_fires_cascade_and_surfaces_stale_notice(db_session, monkeypatch):
    user = _user(db_session)
    # two OLD zoneless v4 sessions (v4 list carries no zone split)
    old = datetime.now(timezone.utc) - timedelta(days=30)
    raws = [
        _training_session("v4a", old, zones_seconds=None, cardio_load=None),
        _training_session("v4b", old + timedelta(hours=2), zones_seconds=None, cardio_load=None),
    ]
    monkeypatch.setattr(polar, "_valid_client", lambda uid, db: _FakeClient(raws))

    resp = _client(db_session, user).post("/integrations/polar/sync")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["synced"] == 2
    rows = db_session.query(models.AerobicSession).filter_by(source="polar_v4").all()
    assert len(rows) == 2
    # cascade fired but every v4 row fail-closed skipped → no metabolic events
    assert body["cascade"]["transform"]["events_written"] == 0
    assert body["cascade"]["transform"]["sessions_skipped_no_zones"] == 2
    # coverage surfaces the stale zoneless v4 sessions
    assert body["coverage"]["stale_zoneless"] == 2
    assert body["notice"] == "2 sessions awaiting zone data — refresh export"


# ── coverage helper (unit) ────────────────────────────────────────────────────────

def _aerobic(db, uid, sid, d, zones, source="polar_flow_export"):
    z = dict(zip((1, 2, 3, 4, 5), zones))
    db.add(models.AerobicSession(
        user_id=uid, source=source, source_session_id=sid, session_date=d,
        z1_seconds=z[1], z2_seconds=z[2], z3_seconds=z[3], z4_seconds=z[4], z5_seconds=z[5],
    ))
    db.commit()


def test_zone_coverage_counts_and_stale(db_session):
    _user(db_session)
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)
    old = now.date() - timedelta(days=ZONELESS_STALE_DAYS + 1)
    fresh = now.date() - timedelta(days=1)

    _aerobic(db_session, 1, "z1", fresh, (600, 0, 0, 0, 0), source="polar_flow_export")  # zone-carrying
    _aerobic(db_session, 1, "z2", old, (0, 0, 0, 0, 0), source="polar_v4")               # stale zoneless v4
    _aerobic(db_session, 1, "z3", fresh, (0, 0, 0, 0, 0), source="polar_v4")             # fresh zoneless v4
    _aerobic(db_session, 1, "z4", old, (None, None, None, None, None), source="health_connect")  # zoneless HC (never stale)

    cov = zone_coverage(1, db_session, now=now)
    assert cov["total"] == 4
    assert cov["with_zones"] == 1
    assert cov["zoneless"] == 3
    assert cov["stale_zoneless"] == 1  # only the OLD polar_v4 one
    assert cov["by_source"]["polar_v4"] == {"with_zones": 0, "zoneless": 2}
    assert cov["by_source"]["polar_flow_export"] == {"with_zones": 1, "zoneless": 0}
    assert coverage_notice(cov) == "1 sessions awaiting zone data — refresh export"


def test_zone_coverage_only_this_user(db_session):
    _user(db_session, 1)
    _user(db_session, 2)
    _aerobic(db_session, 1, "a", date(2026, 6, 1), (600, 0, 0, 0, 0))
    _aerobic(db_session, 2, "b", date(2026, 6, 1), (0, 0, 0, 0, 0), source="polar_v4")
    cov = zone_coverage(1, db_session)
    assert cov["total"] == 1 and cov["with_zones"] == 1


# ── G2: CLI-equivalence for the import_flow_export refactor ────────────────────────

def test_import_flow_export_dry_run_matches_write_in_substance(db_session):
    """Dry-run and write produce identical substance (found/inserted/skipped/errors
    and the per-session details); dry-run writes NOTHING while write persists rows.
    `_parse_session` is used verbatim, so parse output is identical by construction —
    asserted here against a direct `_parse_session` call."""
    _user(db_session)
    zb = _default_zip()

    dry = import_flow_export(db_session, 1, zb, dry_run=True)
    assert db_session.query(models.AerobicSession).count() == 0     # dry-run wrote nothing
    assert dry["found"] == 3 and dry["inserted"] == 3 and dry["skipped"] == 0 and dry["errors"] == 0

    wet = import_flow_export(db_session, 1, zb, dry_run=False)
    assert db_session.query(models.AerobicSession).count() == 3      # write persisted
    # identical substance across the two runs (labels carry date/sport/load/hr_avg)
    assert [d["status"] for d in dry["details"]] == [d["status"] for d in wet["details"]]
    assert [d.get("label") for d in dry["details"]] == [d.get("label") for d in wet["details"]]

    # parse fidelity: the shared core uses `_parse_session` verbatim — a direct call
    # on the same body yields the same identity the core inserted.
    parsed = _parse_session(_training_session("p1", datetime(2026, 6, 1, 6, 0)))
    assert parsed["source_session_id"] == "p1"
    assert parsed["source"] == "polar_flow_export"
    assert wet["details"][0]["source_session_id"] == parsed["source_session_id"]


def test_import_flow_export_accepts_bytes_path_and_filelike(db_session, tmp_path):
    """The shared core accepts raw bytes, a filesystem path, and a file-like object
    (the CLI passes a path; the endpoint passes bytes)."""
    _user(db_session)
    zb = _default_zip()

    # bytes
    assert import_flow_export(db_session, 1, zb, dry_run=True)["found"] == 3
    # path
    p = tmp_path / "export.zip"
    p.write_bytes(zb)
    assert import_flow_export(db_session, 1, str(p), dry_run=True)["found"] == 3
    # file-like
    assert import_flow_export(db_session, 1, io.BytesIO(zb), dry_run=True)["found"] == 3
