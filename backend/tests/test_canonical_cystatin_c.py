"""`Cystatin C` maps canonically to `cystatin_c` and survives the §6 unit guard.

A DATA addition — `backend/reference/marker_canonical.json` gained one entry, no code
changed. It walks onto no §7 landmine: no existing entry shares a token with `Cystatin C`,
so unlike the urine-ACR expansion there is no homograph to hold apart. What IS worth
pinning is the pair the brief flagged so nobody "fixes" it later — `cystatin_c` and
`albumin_urine` share the established unit `mg/L` while having entirely different raw
keys. Shared units are not a collision; shared raw NAMES would be, and exact-string
keying is what makes that distinction hold.

The precision check the urine file records as OWED is, for this marker, DONE: the stored
prod row (id 220, SNP draw of 2026-08-04) carries `marker_name_raw` = `Cystatin C` at
10 bytes and `unit_canonical` = `mg/L`, both byte-exact, so `unit_established` here
matches the STORED string and not merely the printed one. That is the condition under
which the §6 guard stays quiet on the next upload of this marker.

Route-level for the same reason as the urine file: the map resolves inside
`confirm_lab_report`, but the §6 refusal is an HTTPException.
"""
import models
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from auth import get_current_user
from database import get_db
from routers import labs
from routers.labs import _CANONICAL_MAP

COLLECTED_ISO = "2026-08-04T08:35:00+10:00"
STORED_VALUE = 1.24          # the actual prod row's value_num
ESTABLISHED_UNIT = "mg/L"


# ---------- the map itself ----------

def test_cystatin_c_is_loaded_and_keyed_by_its_exact_raw_name():
    assert "Cystatin C" in _CANONICAL_MAP
    entry = _CANONICAL_MAP["Cystatin C"]
    assert entry["marker_canonical"] == "cystatin_c"
    assert entry["unit_established"] == ESTABLISHED_UNIT
    assert entry["loinc"] is None


def test_the_raw_key_is_byte_exact_to_the_stored_row():
    """The lookup at `labs.py` is an exact dict hit — no normalisation, no case folding.
    The stored prod row's `marker_name_raw` is 10 bytes, single space, capital C twice;
    any drift here silently stops auto-mapping instead of failing loudly."""
    key, = [k for k in _CANONICAL_MAP if k.lower().replace(" ", "") == "cystatinc"]
    assert key == "Cystatin C"
    assert len(key) == 10
    assert key.isascii()


def test_shared_unit_with_urine_albumin_is_not_a_collision():
    """Both carry `mg/L`. The brief records this deliberately: units are shared freely,
    only raw NAMES key the map, so these two never interact."""
    assert _CANONICAL_MAP["R U-Albumin"]["unit_established"] == ESTABLISHED_UNIT
    assert _CANONICAL_MAP["Cystatin C"]["unit_established"] == ESTABLISHED_UNIT
    assert _CANONICAL_MAP["R U-Albumin"]["marker_canonical"] != _CANONICAL_MAP["Cystatin C"]["marker_canonical"]


def test_the_renal_neighbours_are_untouched_by_this_addition():
    """`creatinine` and `egfr` are Brief B's other inputs; a map edit near them must not
    disturb them."""
    assert _CANONICAL_MAP["Creatinine"]["marker_canonical"] == "creatinine"
    assert _CANONICAL_MAP["Creatinine"]["unit_established"] == "umol/L"
    assert _CANONICAL_MAP["eGFR"]["marker_canonical"] == "egfr"
    assert _CANONICAL_MAP["eGFR"]["unit_established"] is None


# ---------- §6 guard: the fresh-upload probe ----------

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


def _body(unit):
    return {
        "report": {
            "lab_name": "Sullivan Nicolaides Pathology",
            "panel_name_raw": "Cystatin C",
            "dates": {"collected": COLLECTED_ISO},
            "source_completeness": "sonic_dx_extract",
            "extraction": {"extracted_at": COLLECTED_ISO, "model": "test"},
        },
        "results": [{
            "marker_name_raw": "Cystatin C",
            "value_num": STORED_VALUE,
            "unit_canonical": unit,
            "ref_low": None,
            "ref_high": None,
        }],
    }


def test_fresh_cystatin_c_upload_auto_maps_and_passes_the_guard(db_session):
    """The objective of the addition: the next draw's Cystatin C binds at confirm with no
    unmapped banner — the state that made this brief exist."""
    user = _user(db_session, "cystatin-ok@example.com")
    res = _client(db_session, user).post("/labs/confirm", json=_body(ESTABLISHED_UNIT))

    assert res.status_code == 201, res.text
    assert res.json()["unmapped"] == []
    row = db_session.query(models.LabResult).filter_by(
        lab_report_id=res.json()["lab_report_id"]).one()
    assert row.marker_canonical == "cystatin_c"
    assert row.unit_canonical == ESTABLISHED_UNIT
    assert row.value_num == STORED_VALUE


@pytest.mark.parametrize("wrong_unit", ["mg/dL", "nmol/L", "MG/L"])
def test_cystatin_c_at_a_wrong_unit_trips_the_over_collapse_guard(db_session, wrong_unit):
    """A contrived mis-united upload is REFUSED rather than written into the series.
    `MG/L` is included on purpose: the comparison is a byte equality, so a case variant
    is a mismatch — which is precisely why `unit_established` had to be set from the
    STORED string rather than the printed one."""
    user = _user(db_session, f"cystatin-bad-{wrong_unit.replace('/', '')}@example.com")
    res = _client(db_session, user).post("/labs/confirm", json=_body(wrong_unit))

    assert res.status_code == 422, res.text
    detail = res.json()["detail"]
    assert "Over-collapse guard" in detail
    assert "cystatin_c" in detail
    assert ESTABLISHED_UNIT in detail   # names the established unit it expected
    assert wrong_unit in detail         # and the mismatched one it got
    assert db_session.query(models.LabResult).filter_by(marker_canonical="cystatin_c").count() == 0


def test_a_unitless_cystatin_row_is_written_not_refused(db_session):
    """The guard's `r.unit_canonical` arm means a null unit cannot mismatch. Recorded so
    the refusal is understood as unit-CONFLICT, not unit-REQUIRED."""
    user = _user(db_session, "cystatin-nounit@example.com")
    body = _body(ESTABLISHED_UNIT)
    body["results"][0]["unit_canonical"] = None
    res = _client(db_session, user).post("/labs/confirm", json=body)

    assert res.status_code == 201, res.text
    row = db_session.query(models.LabResult).filter_by(
        lab_report_id=res.json()["lab_report_id"]).one()
    assert row.marker_canonical == "cystatin_c"
    assert row.unit_canonical is None
