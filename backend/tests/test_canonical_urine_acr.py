"""The three urine-ACR markers map canonically and are held apart from their serum
homographs by the §6 unit guard.

This is a DATA addition — `backend/reference/marker_canonical.json` gained three entries,
no code changed. What is worth testing is the §7 over-collapse landmine it walks onto:
`R U-Creatinine` (urine, mmol/L) shares an analyte with `Creatinine` (serum, umol/L), and
`R U-Albumin` (urine, mg/L) with `Albumin` (serum, g/L). Two mechanisms keep them apart,
and both are asserted here:

  * exact-string keying — `R U-Creatinine` is a different key from `Creatinine`, so it
    never resolves to the serum entry (no fuzzy match exists); and
  * the §6 unit guard — even a mis-keyed row is refused when its unit does not match the
    mapped `unit_established`.

The guard test is the point: it proves the map discriminates urine from a serum-unit
mis-entry, which is the 1000x-gap protection §7 relies on, now doing real work.

Route-level, not handler-level: the map resolves inside `confirm_lab_report`, but the
§6 refusal is an HTTPException, so these drive `/labs/confirm` over a standalone app —
the `test_labs_confirm_refless_row_e2e` precedent.

NOTE the units are pinned here to `mmol/L` / `mg/L` / `mg/mmol` — the clinically-standard
SNP ASCII forms and the file's own convention (cf. serum `umol/L`, `ug/L`). If a live
extraction's stored `unit_canonical` differs in BYTE form, these tests still pass (they
construct the body) but a real upload would trip the §6 guard — which is exactly why the
brief's precision-check against the stored rows is OWED before the map is trusted in prod.
That failure is loud and self-naming (#177), never silent.
"""
import json
from pathlib import Path

import models
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from auth import get_current_user
from database import get_db
from routers import labs

# The map is a DB table now (#220); this file asserts over the JSON that SEEDS it, which
# is the artefact these data-addition tests were always really about. Reading the seed
# directly keeps the assertions honest about what the migration will insert.
_CANONICAL_MAP = {
    e["marker_name_raw"]: e
    for e in json.loads(
        (Path(labs.__file__).resolve().parent.parent / "reference" / "marker_canonical.json")
        .read_text(encoding="utf-8")
    )["entries"]
}

COLLECTED_ISO = "2026-08-04T08:35:00+10:00"

URINE = {
    "R U-Creatinine": ("creatinine_urine", "mmol/L"),
    "R U-Albumin": ("albumin_urine", "mg/L"),
    "R U-Albumin/Creat": ("albumin_creatinine_ratio_urine", "mg/mmol"),
}


# ---------- the map itself ----------

def test_all_three_urine_markers_are_loaded_and_keyed_by_raw_name():
    for raw, (canonical, unit) in URINE.items():
        assert raw in _CANONICAL_MAP, f"{raw} not loaded"
        assert _CANONICAL_MAP[raw]["marker_canonical"] == canonical
        assert _CANONICAL_MAP[raw]["unit_established"] == unit


def test_urine_keys_are_distinct_from_their_serum_homographs():
    """Exact-string keying: the urine entry and the serum entry are different keys, and
    the serum entries are untouched by this addition."""
    assert _CANONICAL_MAP["Creatinine"]["marker_canonical"] == "creatinine"
    assert _CANONICAL_MAP["Creatinine"]["unit_established"] == "umol/L"
    assert _CANONICAL_MAP["R U-Creatinine"]["marker_canonical"] == "creatinine_urine"
    assert _CANONICAL_MAP["Albumin"]["marker_canonical"] == "albumin"
    assert _CANONICAL_MAP["Albumin"]["unit_established"] == "g/L"
    assert _CANONICAL_MAP["R U-Albumin"]["marker_canonical"] == "albumin_urine"


def test_no_duplicate_raw_names_in_the_whole_file():
    """A duplicate key would make `_load_canonical_map`'s dict comprehension silently
    drop one entry — the last write wins and the shadowed marker vanishes."""
    path = Path(labs.__file__).resolve().parent.parent / "reference" / "marker_canonical.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    names = [e["marker_name_raw"] for e in data["entries"]]
    assert len(names) == len(set(names)), "duplicate marker_name_raw"
    assert len(names) == 70


# ---------- §6 guard: urine vs serum-unit mis-entry ----------

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


def _body(raw, unit):
    return {
        "report": {
            "lab_name": "Sullivan Nicolaides Pathology",
            "panel_name_raw": "Albumin/Creat Ratio",
            "dates": {"collected": COLLECTED_ISO},
            "source_completeness": "sonic_dx_extract",
            "extraction": {"extracted_at": COLLECTED_ISO, "model": "test"},
        },
        "results": [{
            "marker_name_raw": raw,
            "value_num": 8.6,
            "unit_canonical": unit,
            "ref_low": None,
            "ref_high": None,
            "ref_raw": "—",
        }],
    }


def test_fresh_urine_creatinine_auto_maps_and_passes_the_guard(db_session):
    """A new confirm of the correctly-united urine marker resolves to its canonical key
    and is written — the whole objective of the map addition."""
    user = _user(db_session, "urine-ok@example.com")
    res = _client(db_session, user).post("/labs/confirm", json=_body("R U-Creatinine", "mmol/L"))

    assert res.status_code == 201, res.text
    assert res.json()["unmapped"] == []   # it is now MAPPED, no longer in the unmapped list
    row = db_session.query(models.LabResult).filter_by(
        lab_report_id=res.json()["lab_report_id"]).one()
    assert row.marker_canonical == "creatinine_urine"


def test_urine_creatinine_at_a_serum_unit_trips_the_over_collapse_guard(db_session):
    """The §7 protection doing real work: `R U-Creatinine` carrying serum `umol/L`
    instead of urine `mmol/L` is REFUSED, not silently merged into the serum series.
    This is the discrimination that makes the shared-analyte keys safe."""
    user = _user(db_session, "urine-miskeyed@example.com")
    res = _client(db_session, user).post("/labs/confirm", json=_body("R U-Creatinine", "umol/L"))

    assert res.status_code == 422, res.text
    detail = res.json()["detail"]
    assert "Over-collapse guard" in detail
    assert "creatinine_urine" in detail
    assert "mmol/L" in detail    # names the established unit it expected
    assert "umol/L" in detail    # and the mismatched one it got


def test_all_three_map_without_tripping_the_guard_at_correct_units(db_session):
    """The whole SNP ACR panel, correctly united, lands three mapped rows."""
    user = _user(db_session, "urine-panel@example.com")
    body = {
        "report": {
            "lab_name": "Sullivan Nicolaides Pathology",
            "panel_name_raw": "Albumin/Creat Ratio",
            "dates": {"collected": COLLECTED_ISO},
            "source_completeness": "sonic_dx_extract",
            "extraction": {"extracted_at": COLLECTED_ISO, "model": "test"},
        },
        "results": [
            {"marker_name_raw": raw, "value_num": 1.0, "unit_canonical": unit,
             "ref_low": None, "ref_high": None}
            for raw, (_c, unit) in URINE.items()
        ],
    }
    res = _client(db_session, user).post("/labs/confirm", json=body)

    assert res.status_code == 201, res.text
    assert res.json()["result_count"] == 3
    assert res.json()["unmapped"] == []
    stored = {
        r.marker_name_raw: r.marker_canonical
        for r in db_session.query(models.LabResult).filter_by(
            lab_report_id=res.json()["lab_report_id"]).all()
    }
    assert stored == {raw: canonical for raw, (canonical, _u) in URINE.items()}
