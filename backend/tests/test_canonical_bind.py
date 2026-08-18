"""POST /labs/canonical/bind — the runtime path that fulfils #50's confirmation-populated half.

The map is a table now, so raw->canonical identity is mutable at runtime. These tests pin
the two places over-collapse can newly enter as a result: the bind itself, and the historical
backfill the bind triggers. A bind that merges two analytes into one canonical series is the
exact failure #50 exists to prevent, and it is silent — the damage shows up much later as a
trend line that never happened.
"""
import json
from datetime import date, datetime
from pathlib import Path

import models
from fastapi import FastAPI
from starlette.testclient import TestClient

from auth import get_current_user
from database import get_db
from routers import labs

COLLECTED_ISO = "2026-08-04T08:35:00+10:00"
# A raw name deliberately absent from the seed — binding it is the whole point.
NOVEL_RAW = "Lipoprotein(a)"
NOVEL_CANONICAL = "lipoprotein_a"


def _client(db, user) -> TestClient:
    app = FastAPI()
    app.include_router(labs.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _stored_row(db, user, raw, unit, value=42.0, collected=date(2026, 6, 1)):
    """One historical LabResult stored UNMAPPED — the state a bind promotes."""
    report = models.LabReport(
        user_id=user.id,
        lab_name="Sullivan Nicolaides Pathology",
        panel_name_raw=raw,
        collected_date=collected,
        source_completeness="sonic_dx_extract",
        source="upload",
        overall_confidence=1.0,
        extracted_at=datetime(2026, 6, 2, 9, 0),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    row = models.LabResult(
        lab_report_id=report.id,
        marker_name_raw=raw,
        marker_canonical=None,
        value_num=value,
        unit_canonical=unit,
        confidence=1.0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------- the seed is present and readable through the endpoint ----------

def test_canonical_map_endpoint_serves_the_table_in_the_frontend_shape(db_session):
    """The frontend reads `map[raw].marker_canonical` and truthiness of `map[raw]`.
    The shape must survive the move off the JSON dict byte-for-byte or the confirm
    screen's client-side unmapped flagging silently stops flagging."""
    user = _user(db_session, "map@example.com")
    r = _client(db_session, user).get("/labs/canonical-map")
    assert r.status_code == 200
    body = r.json()
    seed = json.loads(
        (Path(labs.__file__).resolve().parent.parent / "reference" / "marker_canonical.json")
        .read_text(encoding="utf-8")
    )["entries"]
    assert len(body) == len(seed)
    assert body["Sodium"]["marker_canonical"] == "sodium"
    assert body["Sodium"]["unit_established"] == "mmol/L"
    assert set(body["Sodium"]) == {"marker_name_raw", "marker_canonical", "unit_established", "loinc"}
    assert NOVEL_RAW not in body


# ---------- the happy path: bind + backfill ----------

def test_bind_writes_the_entry_and_promotes_history(db_session):
    """Backfill is what makes a bind worth doing (#159): the marker becomes a live series
    the moment it is promoted, not at the next draw."""
    user = _user(db_session, "bind-ok@example.com")
    old = _stored_row(db_session, user, NOVEL_RAW, "nmol/L")
    assert old.marker_canonical is None

    r = _client(db_session, user).post("/labs/canonical/bind", json={
        "marker_name_raw": NOVEL_RAW,
        "marker_canonical": NOVEL_CANONICAL,
        "unit_established": "nmol/L",
    })
    assert r.status_code == 201, r.text
    assert r.json()["backfilled_rows"] == 1

    db_session.refresh(old)
    assert old.marker_canonical == NOVEL_CANONICAL

    entry = (
        db_session.query(models.MarkerCanonicalEntry)
        .filter_by(marker_name_raw=NOVEL_RAW).one()
    )
    assert entry.source == "bind"
    assert entry.created_by_user_id == user.id
    # It resolves through the read path immediately — no restart, which is the point.
    served = _client(db_session, user).get("/labs/canonical-map").json()
    assert served[NOVEL_RAW]["marker_canonical"] == NOVEL_CANONICAL


def test_bound_marker_resolves_at_confirm_without_a_restart(db_session):
    """End-to-end: the bind is useless if the very next confirm still reads it unmapped."""
    user = _user(db_session, "bind-confirm@example.com")
    client = _client(db_session, user)
    client.post("/labs/canonical/bind", json={
        "marker_name_raw": NOVEL_RAW,
        "marker_canonical": NOVEL_CANONICAL,
        "unit_established": "nmol/L",
    })
    r = client.post("/labs/confirm", json={
        "report": {
            "lab_name": "Sullivan Nicolaides Pathology",
            "panel_name_raw": "Lipids",
            "dates": {"collected": COLLECTED_ISO},
            "source_completeness": "sonic_dx_extract",
            "extraction": {"extracted_at": COLLECTED_ISO, "model": "test"},
        },
        "results": [{
            "marker_name_raw": NOVEL_RAW, "value_num": 55.0,
            "unit_canonical": "nmol/L", "ref_low": None, "ref_high": None,
        }],
    })
    assert r.status_code in (200, 201), r.text
    assert NOVEL_RAW not in (r.json().get("unmapped") or [])
    stored = (
        db_session.query(models.LabResult)
        .filter_by(marker_name_raw=NOVEL_RAW, value_num=55.0).one()
    )
    assert stored.marker_canonical == NOVEL_CANONICAL


def test_binding_is_optional_an_unbound_marker_still_stores_null(db_session):
    """Retain-raw (#58/#155) is preserved — binding must never become mandatory to confirm."""
    user = _user(db_session, "unbound@example.com")
    r = _client(db_session, user).post("/labs/confirm", json={
        "report": {
            "lab_name": "Sullivan Nicolaides Pathology",
            "panel_name_raw": "Lipids",
            "dates": {"collected": COLLECTED_ISO},
            "source_completeness": "sonic_dx_extract",
            "extraction": {"extracted_at": COLLECTED_ISO, "model": "test"},
        },
        "results": [{
            "marker_name_raw": NOVEL_RAW, "value_num": 55.0,
            "unit_canonical": "nmol/L", "ref_low": None, "ref_high": None,
        }],
    })
    assert r.status_code in (200, 201), r.text
    stored = db_session.query(models.LabResult).filter_by(marker_name_raw=NOVEL_RAW).one()
    assert stored.marker_canonical is None
    assert stored.marker_name_raw == NOVEL_RAW  # the raw name is retained, not discarded


# ---------- refusals ----------

def test_rebinding_an_already_mapped_marker_is_409(db_session):
    """A mapped marker is not unmapped; binding it is a category error, not an update."""
    user = _user(db_session, "rebind@example.com")
    r = _client(db_session, user).post("/labs/canonical/bind", json={
        "marker_name_raw": "Sodium",
        "marker_canonical": "sodium_again",
        "unit_established": "mmol/L",
    })
    assert r.status_code == 409, r.text
    assert "already mapped" in r.json()["detail"]
    # and it did not overwrite
    kept = (
        db_session.query(models.MarkerCanonicalEntry)
        .filter_by(marker_name_raw="Sodium").one()
    )
    assert kept.marker_canonical == "sodium"


def test_over_collapse_guard_refuses_a_bind_at_a_disagreeing_unit(db_session):
    """THE guard (#50). Binding a second raw name onto an already-established canonical at a
    different unit is the total-T nmol/L vs free-T pmol/L merge, caught at bind."""
    user = _user(db_session, "collapse@example.com")
    seeded = (
        db_session.query(models.MarkerCanonicalEntry)
        .filter(models.MarkerCanonicalEntry.unit_established.isnot(None))
        .order_by(models.MarkerCanonicalEntry.id).first()
    )
    other_unit = "pmol/L" if seeded.unit_established != "pmol/L" else "nmol/L"
    r = _client(db_session, user).post("/labs/canonical/bind", json={
        "marker_name_raw": "Some Other Assay",
        "marker_canonical": seeded.marker_canonical,
        "unit_established": other_unit,
    })
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert "Over-collapse guard" in detail
    assert seeded.marker_canonical in detail
    # refused means nothing was written
    assert (
        db_session.query(models.MarkerCanonicalEntry)
        .filter_by(marker_name_raw="Some Other Assay").first() is None
    )


def test_over_collapse_in_history_refuses_the_whole_bind(db_session):
    """The same fault surfacing from history. A partial promotion is the worse outcome:
    half a migrated series is harder to see, and harder to undo, than a refused bind."""
    user = _user(db_session, "hist-collapse@example.com")
    good = _stored_row(db_session, user, NOVEL_RAW, "nmol/L", value=10.0, collected=date(2026, 5, 1))
    bad = _stored_row(db_session, user, NOVEL_RAW, "mg/dL", value=11.0, collected=date(2026, 6, 1))

    r = _client(db_session, user).post("/labs/canonical/bind", json={
        "marker_name_raw": NOVEL_RAW,
        "marker_canonical": NOVEL_CANONICAL,
        "unit_established": "nmol/L",
    })
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert "Over-collapse guard" in detail
    assert str(bad.id) in detail  # names the offending row

    db_session.refresh(good)
    db_session.refresh(bad)
    assert good.marker_canonical is None, "no row may be promoted when the bind is refused"
    assert bad.marker_canonical is None
    assert (
        db_session.query(models.MarkerCanonicalEntry)
        .filter_by(marker_name_raw=NOVEL_RAW).first() is None
    )


def test_a_unitless_bind_skips_the_unit_guard_and_still_promotes(db_session):
    """`unit_established` is legitimately null (§6) — a unitless marker has no unit claim
    to contradict, so the guard must not fire and must not block the backfill."""
    user = _user(db_session, "unitless@example.com")
    row = _stored_row(db_session, user, "Some Ratio", "ratio")
    r = _client(db_session, user).post("/labs/canonical/bind", json={
        "marker_name_raw": "Some Ratio",
        "marker_canonical": "some_ratio",
    })
    assert r.status_code == 201, r.text
    assert r.json()["backfilled_rows"] == 1
    db_session.refresh(row)
    assert row.marker_canonical == "some_ratio"
