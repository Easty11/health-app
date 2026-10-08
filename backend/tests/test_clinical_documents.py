"""The clinical documents store (Q142 option b; SCHEMA.md section 045).

Gates, each with its boundary or negative control:
  * the validator accepts a synthetic valid document of each `doc_type`, and REFUSES an unknown key,
    an identifier-like key (top level and nested), a missing `service_date`, a `modality` on
    correspondence and a letter key on imaging -- and a refusal names the key, never a value;
  * VERBATIM ROUND TRIP: a conclusion with double spaces, a `[sic]` token, `?`, an en-dash, CRLF and
    trailing whitespace comes back byte-identical through import -> GET -> MCP (the HTTP layer
    included), and so do the letter's `diagnosis_verbatim` / `management_plan_verbatim`;
  * a dry run writes nothing (row count unchanged) and is the default; an apply is idempotent (the
    second apply reports every document `unchanged`); an update overwrites the row in full; an
    apply with any refused document writes nothing at all;
  * cross-user isolation: user B can neither read nor collide on user A's `doc_key`;
  * the read-back filters and orders by `service_date`; the MCP tool is registered and formats both
    views.

SYNTHETIC fixtures only: placeholder studies, names and values (the repo is public). No real
clinical content appears anywhere in this file.
"""
import asyncio
import copy
import json
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import clinical_documents as cd
import mcp_server
import models
from auth import get_current_user
from database import get_db
from routers import clinical_documents as cd_router

# Double spaces, a [sic] token, a question mark, an en-dash, CRLF, a trailing space and a final
# newline: everything a "tidy-up" would change.
VERBATIM = "Appearances  in the part A region – unchanged ?  Recomend [sic] review.\r\nSecond  line, trailing space \n"
DIAGNOSIS = "Condition  A – query ?  (typo [sic]) "
PLAN = ["1.  First step  – as written", "2. Second step ?", " 3. Third, leading space"]


def imaging(**over):
    d = {
        "id": "img_20990105_mri_part_a", "doc_type": "imaging", "modality": "MRI",
        "study": "MRI synthetic part A", "region": "part a", "laterality": "L",
        "dates": {"service": "2099-01-05", "reported": "2099-01-06"},
        "provider": "Provider A", "referrer": "Referrer A", "accession": "ACC-0001",
        "source_files": ["synthetic_a.pdf"], "clinical_history": "History A.",
        "conclusion_label": "IMPRESSION", "conclusion_verbatim": VERBATIM,
        "findings_summary": "Condensed summary A.", "structured": {"level_a": 1.5, "items": ["x", "y"]},
        "extraction_notes": ["note A"],
    }
    d.update(over)
    return d


def letter(**over):
    d = {
        "id": "corr_20990201_specialist_a", "doc_type": "correspondence", "subtype": "specialist letter",
        "dates": {"service": "2099-02-01", "reported": None}, "provider": "Practice A",
        "author": "Author A", "recipient": "Recipient A", "source_files": ["synthetic_letter.pdf"],
        "reason": "Reason A", "diagnosis_verbatim": DIAGNOSIS, "management_plan_verbatim": PLAN,
        "history_summary": "History summary A.", "medications_listed": ["Drug A 1 unit daily"],
        "actions": ["Action A"], "extraction_notes": [],
    }
    d.update(over)
    return d


def dexa(**over):
    d = imaging(id="img_20990301_dxa_body", modality="DXA", study="DXA synthetic body", region="whole body",
                laterality=None, dates={"service": "2099-03-01"}, conclusion_verbatim=None,
                conclusion_label=None, structured={"total_bmd": 1.0, "segments": {"arms": 2.5}})
    d.update(over)
    return d


def payload(*docs, **over):
    p = {"schema": "clinical_documents v0.1", "extracted_at": "2099-04-01", "documents": list(docs),
         "conventions": {"x": "ignored"}, "not_extracted": ["ignored"]}
    p.update(over)
    return p


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _count(db):
    return db.query(models.ClinicalDocument).count()


def _client(db, user):
    app = FastAPI()
    app.include_router(cd_router.router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def _post(client, body, **params):
    """POST the payload as UTF-8 bytes exactly as a file would send them."""
    return client.post("/clinical-documents/import", params=params,
                       content=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                       headers={"Content-Type": "application/json"})


@pytest.fixture
def user(db_session):
    return _user(db_session, "docs-a@example.com")


# -------------------------------------------------------------------------- #
# validator                                                                  #
# -------------------------------------------------------------------------- #

def test_valid_imaging_document_maps_to_columns():
    v = cd.validate_document(imaging())
    assert v["doc_key"] == "img_20990105_mri_part_a" and v["doc_type"] == "imaging"
    assert v["service_date"] == date(2099, 1, 5) and v["reported_date"] == date(2099, 1, 6)
    assert v["source_doc_filenames"] == ["synthetic_a.pdf"] and v["referrer_name_raw"] == "Referrer A"
    assert v["modality"] == "MRI" and v["subtype"] is None and v["letter"] is None
    assert v["structured"] == {"level_a": 1.5, "items": ["x", "y"]}
    assert v["conclusion_verbatim"] == VERBATIM


def test_valid_correspondence_document_collects_the_letter():
    v = cd.validate_document(letter())
    assert v["doc_type"] == "correspondence" and v["subtype"] == "specialist letter" and v["modality"] is None
    assert v["author_name_raw"] == "Author A" and v["recipient"] == "Recipient A"
    assert v["reported_date"] is None and v["conclusion_verbatim"] is None
    assert set(v["letter"]) == {"reason", "diagnosis_verbatim", "management_plan_verbatim",
                                "history_summary", "medications_listed", "actions"}
    assert v["letter"]["diagnosis_verbatim"] == DIAGNOSIS and v["letter"]["management_plan_verbatim"] == PLAN


def test_a_dexa_has_no_conclusion_and_keeps_its_numerics():
    v = cd.validate_document(dexa())
    assert v["conclusion_verbatim"] is None and v["structured"]["segments"] == {"arms": 2.5}


def _without(d, *keys):
    d = copy.deepcopy(d)
    for k in keys:
        d.pop(k)
    return d


REFUSALS = [
    ("unknown key", imaging(extra_field="SENTINEL-VALUE"), "extra_field"),
    ("unknown key (correspondence)", letter(extra_field="SENTINEL-VALUE"), "extra_field"),
    ("ihi", imaging(ihi="SENTINEL-VALUE"), "ihi"),
    ("medicare", imaging(medicare_number="SENTINEL-VALUE"), "medicare_number"),
    ("address", letter(address="SENTINEL-VALUE"), "address"),
    ("phone", letter(phone="SENTINEL-VALUE"), "phone"),
    ("dob", imaging(dob="SENTINEL-VALUE"), "dob"),
    ("camelCase identifier", imaging(dateOfBirth="SENTINEL-VALUE"), "dateOfBirth"),
    ("nested identifier in structured", imaging(structured={"a": {"home_address": "SENTINEL-VALUE"}}),
     "structured.a.home_address"),
    ("nested identifier in a letter list", letter(actions=[{"phone": "SENTINEL-VALUE"}]), "actions[0].phone"),
    ("missing dates", _without(imaging(), "dates"), "dates"),
    ("missing service date", imaging(dates={"reported": "2099-01-06"}), "dates.service"),
    ("null service date", imaging(dates={"service": None}), "dates.service"),
    ("unparseable service date", imaging(dates={"service": "5 Jan 2099"}), "dates.service"),
    ("extra dates key", imaging(dates={"service": "2099-01-05", "other": "2099-01-01"}), "other"),
    ("modality on correspondence", letter(modality="MRI"), "modality"),
    ("study on correspondence", letter(study="Synthetic"), "study"),
    ("letter key on imaging", imaging(reason="Reason A"), "reason"),
    ("literal letter object on imaging", imaging(letter={"reason": "x"}), "letter"),
    ("diagnosis on imaging", imaging(diagnosis_verbatim="Condition A"), "diagnosis_verbatim"),
    ("bad doc_type", imaging(doc_type="lab"), "doc_type"),
    ("bad modality", imaging(modality="PET"), "modality"),
    ("imaging without modality", _without(imaging(), "modality"), "modality"),
    ("bad laterality", imaging(laterality="left"), "laterality"),
    ("bad subtype", letter(subtype="memo"), "subtype"),
    ("correspondence without subtype", _without(letter(), "subtype"), "subtype"),
    ("no source files", imaging(source_files=[]), "source_files"),
    ("source files not a list", imaging(source_files="a.pdf"), "source_files"),
    ("blank conclusion", imaging(conclusion_verbatim="   "), "conclusion_verbatim"),
    ("non-string conclusion", imaging(conclusion_verbatim=5), "conclusion_verbatim"),
    ("blank diagnosis", letter(diagnosis_verbatim=" "), "diagnosis_verbatim"),
    ("plan not a list", letter(management_plan_verbatim="one big string"), "management_plan_verbatim"),
    ("over-long study", imaging(study="x" * 256), "study"),
    ("over-long accession", imaging(accession="x" * 51), "accession"),
    ("doc_key with a space", imaging(id="img 1"), "id"),
    ("doc_key too long", imaging(id="k" * 101), "id"),
    ("missing id", _without(imaging(), "id"), "id"),
    ("structured not an object", imaging(structured=[1, 2]), "structured"),
]


@pytest.mark.parametrize("label,doc,names", REFUSALS, ids=[r[0] for r in REFUSALS])
def test_validator_refuses_and_names_the_key_not_the_value(label, doc, names):
    with pytest.raises(ValueError) as exc:
        cd.validate_document(doc)
    assert names in str(exc.value)
    assert "SENTINEL-VALUE" not in str(exc.value)


def test_validator_refuses_a_non_object():
    with pytest.raises(ValueError):
        cd.validate_document(["not", "an", "object"])


def test_the_identifier_scan_reads_keys_only_so_values_may_say_anything():
    v = cd.validate_document(imaging(clinical_history="Phone the clinic about the address."))
    assert v["clinical_history"] == "Phone the clinic about the address."


@pytest.mark.parametrize("bad", [
    {"documents": [imaging()]},                                            # no schema
    payload(imaging(), schema="something_else v1"),                        # wrong schema
    payload(imaging(), documents=[]),                                      # empty
    payload(imaging(), patient="SENTINEL-VALUE"),                          # unknown top-level key
])
def test_envelope_errors_reject_the_whole_payload(bad):
    with pytest.raises(cd.PayloadError):
        cd.validate_envelope(bad)


def test_conventions_and_not_extracted_are_accepted_and_not_stored(db_session, user):
    out = cd.import_documents(db_session, user.id, payload(imaging()), dry_run=False)
    assert out["would_insert"] == ["img_20990105_mri_part_a"]
    row = db_session.query(models.ClinicalDocument).one()
    assert row.schema_version == "clinical_documents v0.1" and row.extracted_at == date(2099, 4, 1)
    assert row.source == "file_extraction"
    assert "ignored" not in json.dumps([row.structured, row.letter, row.extraction_notes])


# -------------------------------------------------------------------------- #
# import: dry run, apply, idempotency, overwrite, atomicity                  #
# -------------------------------------------------------------------------- #

def test_dry_run_is_the_default_and_writes_nothing(db_session, user):
    out = cd.import_documents(db_session, user.id, payload(imaging(), letter(), dexa()))
    assert out["dry_run"] is True and out["applied"] is False
    assert out["would_insert"] == ["img_20990105_mri_part_a", "corr_20990201_specialist_a", "img_20990301_dxa_body"]
    assert out["would_update"] == [] and out["unchanged"] == [] and out["refused"] == []
    assert _count(db_session) == 0


def test_apply_inserts_then_is_idempotent(db_session, user):
    body = payload(imaging(), letter(), dexa())
    first = cd.import_documents(db_session, user.id, body, dry_run=False)
    assert len(first["would_insert"]) == 3 and first["applied"] is True and _count(db_session) == 3
    second = cd.import_documents(db_session, user.id, body, dry_run=False)
    assert second["would_insert"] == [] and second["would_update"] == []
    assert sorted(second["unchanged"]) == sorted(first["would_insert"]) and _count(db_session) == 3
    # and a dry run after an apply agrees
    assert len(cd.import_documents(db_session, user.id, body)["unchanged"]) == 3


def test_a_changed_document_is_a_would_update_and_overwrites_the_row_in_full(db_session, user):
    cd.import_documents(db_session, user.id, payload(imaging()), dry_run=False)
    changed = imaging(conclusion_verbatim="Replacement  text.")
    changed.pop("findings_summary")
    changed.pop("structured")
    dry = cd.import_documents(db_session, user.id, payload(changed))
    assert dry["would_update"] == ["img_20990105_mri_part_a"] and dry["unchanged"] == []
    assert db_session.query(models.ClinicalDocument).one().conclusion_verbatim == VERBATIM   # dry run: untouched
    cd.import_documents(db_session, user.id, payload(changed), dry_run=False)
    row = db_session.query(models.ClinicalDocument).one()
    assert row.conclusion_verbatim == "Replacement  text."
    assert row.findings_summary is None and row.structured is None      # full overwrite, not a merge
    assert _count(db_session) == 1


def test_a_changed_envelope_alone_is_an_update(db_session, user):
    cd.import_documents(db_session, user.id, payload(imaging()), dry_run=False)
    out = cd.import_documents(db_session, user.id, payload(imaging(), extracted_at="2099-05-01"))
    assert out["would_update"] == ["img_20990105_mri_part_a"]


def test_an_apply_with_any_refused_document_writes_nothing(db_session, user):
    body = payload(imaging(), letter(ihi="SENTINEL-VALUE"))
    dry = cd.import_documents(db_session, user.id, body)
    assert dry["would_insert"] == ["img_20990105_mri_part_a"]
    assert [r["doc_key"] for r in dry["refused"]] == ["corr_20990201_specialist_a"]
    assert "ihi" in dry["refused"][0]["reason"] and "SENTINEL-VALUE" not in dry["refused"][0]["reason"]
    with pytest.raises(cd.ApplyRefused) as exc:
        cd.import_documents(db_session, user.id, body, dry_run=False)
    assert exc.value.refused == dry["refused"]
    assert _count(db_session) == 0


def test_a_doc_key_repeated_in_the_payload_refuses_every_copy(db_session, user):
    out = cd.import_documents(db_session, user.id, payload(imaging(), imaging(study="Other"), letter()))
    assert out["would_insert"] == ["corr_20990201_specialist_a"]
    assert [r["doc_key"] for r in out["refused"]] == ["img_20990105_mri_part_a"]
    assert "duplicate" in out["refused"][0]["reason"]


def test_a_non_object_document_is_refused_by_position(db_session, user):
    out = cd.import_documents(db_session, user.id, payload(imaging(), "junk"))
    assert out["refused"] == [{"doc_key": "documents[1]", "reason": "document must be an object"}]


# -------------------------------------------------------------------------- #
# cross-user isolation                                                       #
# -------------------------------------------------------------------------- #

def test_user_b_cannot_read_or_collide_on_user_as_doc_key(db_session, user):
    b = _user(db_session, "docs-b@example.com")
    cd.import_documents(db_session, user.id, payload(imaging()), dry_run=False)

    assert cd.read_documents(db_session, b.id) == []
    assert cd.read_documents(db_session, b.id, doc_key="img_20990105_mri_part_a") == []

    # the same doc_key is B's own insert, not an update of A's row
    out_b = cd.import_documents(db_session, b.id, payload(imaging(study="B's study")), dry_run=False)
    assert out_b["would_insert"] == ["img_20990105_mri_part_a"] and out_b["would_update"] == []
    assert _count(db_session) == 2
    assert cd.read_documents(db_session, user.id)[0].study == "MRI synthetic part A"
    assert cd.read_documents(db_session, b.id)[0].study == "B's study"

    # and an update by A leaves B's row alone
    cd.import_documents(db_session, user.id, payload(imaging(study="A changed")), dry_run=False)
    assert cd.read_documents(db_session, b.id)[0].study == "B's study"


def test_the_unique_constraint_is_per_user_and_doc_key(db_session, user):
    cd.import_documents(db_session, user.id, payload(imaging()), dry_run=False)
    from sqlalchemy.exc import IntegrityError
    vals = cd.validate_document(imaging())
    vals.update(source="file_extraction", schema_version="clinical_documents v0.1", extracted_at=None)
    db_session.add(models.ClinicalDocument(user_id=user.id, **vals))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# -------------------------------------------------------------------------- #
# HTTP: import + read-back, the verbatim round trip                          #
# -------------------------------------------------------------------------- #

def test_http_import_defaults_to_a_dry_run_then_applies(db_session, user):
    client = _client(db_session, user)
    r = _post(client, payload(imaging(), letter(), dexa()))
    assert r.status_code == 200
    assert r.json()["dry_run"] is True and len(r.json()["would_insert"]) == 3 and _count(db_session) == 0
    r = _post(client, payload(imaging(), letter(), dexa()), dry_run="false")
    assert r.status_code == 200 and r.json()["applied"] is True and _count(db_session) == 3
    again = _post(client, payload(imaging(), letter(), dexa()), dry_run="false").json()
    assert again["would_insert"] == [] and len(again["unchanged"]) == 3


def test_verbatim_fields_round_trip_byte_identical_through_http(db_session, user):
    client = _client(db_session, user)
    assert _post(client, payload(imaging(), letter()), dry_run="false").status_code == 200

    got = {d["doc_key"]: d for d in client.get("/clinical-documents").json()}
    img, ltr = got["img_20990105_mri_part_a"], got["corr_20990201_specialist_a"]
    assert img["conclusion_verbatim"].encode("utf-8") == VERBATIM.encode("utf-8")
    assert ltr["letter"]["diagnosis_verbatim"].encode("utf-8") == DIAGNOSIS.encode("utf-8")
    assert [p.encode("utf-8") for p in ltr["letter"]["management_plan_verbatim"]] == [p.encode("utf-8") for p in PLAN]
    # and the stored row itself, not only the response
    row = db_session.query(models.ClinicalDocument).filter_by(doc_key="img_20990105_mri_part_a").one()
    assert row.conclusion_verbatim.encode("utf-8") == VERBATIM.encode("utf-8")


def test_verbatim_fields_round_trip_through_the_mcp_tool(db_session, user, monkeypatch):
    client = _client(db_session, user)
    _post(client, payload(imaging(), letter()), dry_run="false")
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: user.id)

    listing = mcp_server.get_clinical_documents()
    assert f"<<<\n{VERBATIM}\n>>>" in listing                       # the list view: conclusion in full, untouched
    assert f"<<<\n{DIAGNOSIS}\n>>>" in listing                      # a letter's diagnosis stands in
    full = mcp_server.get_clinical_documents(doc_key="corr_20990201_specialist_a")
    assert "<<<\n" + "\n".join(PLAN) + "\n>>>" in full
    assert f"<<<\n{DIAGNOSIS}\n>>>" in full


def test_http_refusals(db_session, user):
    client = _client(db_session, user)
    # an apply with a refused document: 422, the refusal listed, nothing written
    r = _post(client, payload(imaging(), letter(phone="SENTINEL-VALUE")), dry_run="false")
    assert r.status_code == 422 and r.json()["detail"]["refused"][0]["doc_key"] == "corr_20990201_specialist_a"
    assert "SENTINEL-VALUE" not in r.text and _count(db_session) == 0
    # the same payload as a dry run is a 200 that reports the refusal
    r = _post(client, payload(imaging(), letter(phone="SENTINEL-VALUE")))
    assert r.status_code == 200 and len(r.json()["refused"]) == 1
    # an unusable payload
    assert _post(client, {"schema": "nope", "documents": [imaging()]}).status_code == 422
    assert _post(client, payload(imaging(), patient="x")).status_code == 422


def test_http_requires_authentication(db_session):
    app = FastAPI()
    app.include_router(cd_router.router)
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)
    assert client.get("/clinical-documents").status_code == 401
    assert client.post("/clinical-documents/import", json=payload(imaging())).status_code == 401


def test_http_read_is_user_scoped(db_session, user):
    b = _user(db_session, "docs-b@example.com")
    _post(_client(db_session, user), payload(imaging()), dry_run="false")
    assert _client(db_session, b).get("/clinical-documents").json() == []
    assert len(_client(db_session, user).get("/clinical-documents").json()) == 1


# -------------------------------------------------------------------------- #
# read-back: order, filters                                                  #
# -------------------------------------------------------------------------- #

@pytest.fixture
def seeded(db_session, user):
    # written out of order on purpose
    cd.import_documents(db_session, user.id, payload(
        dexa(), letter(), imaging(),
        imaging(id="img_20990110_us_part_b", modality="US", study="US synthetic part B", region="Part B (right)",
                laterality="R", dates={"service": "2099-01-10"}, conclusion_label="CONCLUSION"),
    ), dry_run=False)
    return user


def _keys(client, **params):
    r = client.get("/clinical-documents", params=params)
    assert r.status_code == 200, r.text
    return [d["doc_key"] for d in r.json()]


def test_read_is_ordered_by_service_date_oldest_first(db_session, seeded):
    assert _keys(_client(db_session, seeded)) == [
        "img_20990105_mri_part_a", "img_20990110_us_part_b", "corr_20990201_specialist_a", "img_20990301_dxa_body"]


def test_read_filters(db_session, seeded):
    c = _client(db_session, seeded)
    assert _keys(c, since="2099-02-01") == ["corr_20990201_specialist_a", "img_20990301_dxa_body"]   # inclusive
    assert _keys(c, doc_type="correspondence") == ["corr_20990201_specialist_a"]
    assert _keys(c, doc_type="imaging", modality="us") == ["img_20990110_us_part_b"]                 # case-insensitive
    assert _keys(c, region="PART B") == ["img_20990110_us_part_b"]                                    # substring, any case
    assert _keys(c, region="part") == ["img_20990105_mri_part_a", "img_20990110_us_part_b"]
    assert _keys(c, doc_type="imaging", since="2099-01-06", modality="MRI") == []
    assert c.get("/clinical-documents", params={"doc_type": "lab"}).status_code == 422
    assert c.get("/clinical-documents", params={"modality": "PET"}).status_code == 422


# -------------------------------------------------------------------------- #
# MCP tool                                                                   #
# -------------------------------------------------------------------------- #

@pytest.fixture
def mcp_user(db_session, seeded, monkeypatch):
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: seeded.id)
    return seeded


def test_the_tool_is_registered_with_its_filters():
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    props = tools["get_clinical_documents"].inputSchema["properties"]
    assert set(props) == {"since", "doc_type", "modality", "region", "doc_key"}
    assert "verbatim" in tools["get_clinical_documents"].description


def test_list_view_shows_date_kind_title_and_the_full_conclusion(mcp_user):
    out = mcp_server.get_clinical_documents()
    assert out.startswith("as_of: ")
    lines = out.splitlines()
    assert "2099-01-05 · MRI · MRI synthetic part A · part a  [img_20990105_mri_part_a]" in lines
    assert "conclusion (IMPRESSION), verbatim:" in lines and "conclusion (CONCLUSION), verbatim:" in lines
    assert "2099-02-01 · specialist letter  [corr_20990201_specialist_a]" in lines
    assert "diagnosis, verbatim:" in lines
    assert "(no conclusion on the document)" in lines                    # the DXA
    # oldest first
    assert [l for l in lines if "  [" in l and l[:4] == "2099"] == [
        "2099-01-05 · MRI · MRI synthetic part A · part a  [img_20990105_mri_part_a]",
        "2099-01-10 · US · US synthetic part B · Part B (right)  [img_20990110_us_part_b]",
        "2099-02-01 · specialist letter  [corr_20990201_specialist_a]",
        "2099-03-01 · DXA · DXA synthetic body · whole body  [img_20990301_dxa_body]"]
    # the list view stays a list: no structured block, no condensed summary
    assert "structured:" not in out and "Condensed summary A." not in out


def test_doc_key_returns_one_document_in_full(mcp_user):
    full = mcp_server.get_clinical_documents(doc_key="img_20990301_dxa_body")
    assert "structured:" in full and '"total_bmd": 1.0' in full and '"arms": 2.5' in full
    assert "img_20990105_mri_part_a" not in full
    full_img = mcp_server.get_clinical_documents(doc_key="img_20990105_mri_part_a")
    assert "findings summary (condensed, NOT verbatim):" in full_img and "Condensed summary A." in full_img
    assert "accession: ACC-0001" in full_img and "source files: synthetic_a.pdf" in full_img
    assert "- note A" in full_img
    full_letter = mcp_server.get_clinical_documents(doc_key="corr_20990201_specialist_a")
    assert "history_summary (condensed, NOT verbatim):" in full_letter
    assert "Drug A 1 unit daily" in full_letter and "author: Author A" in full_letter


def test_tool_filters_and_messages(mcp_user):
    assert "img_20990301_dxa_body" in mcp_server.get_clinical_documents(modality="dxa")
    only = mcp_server.get_clinical_documents(doc_type="correspondence")
    assert "corr_20990201_specialist_a" in only and "img_" not in only
    assert "img_20990110_us_part_b" in mcp_server.get_clinical_documents(region="part b")
    assert "img_20990105_mri_part_a" not in mcp_server.get_clinical_documents(since="2099-01-06")
    assert "No clinical documents on file." in mcp_server.get_clinical_documents(since="2100-01-01")
    assert "No clinical document with doc_key 'nope'" in mcp_server.get_clinical_documents(doc_key="nope")
    assert "ISO date" in mcp_server.get_clinical_documents(since="yesterday")
    assert "doc_type must be one of" in mcp_server.get_clinical_documents(doc_type="lab")
    assert "modality must be one of" in mcp_server.get_clinical_documents(modality="PET")


def test_the_tool_cannot_see_another_users_documents(db_session, seeded, monkeypatch):
    b = _user(db_session, "docs-b@example.com")
    monkeypatch.setattr(mcp_server, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(mcp_server, "_current_user_id", lambda: b.id)
    assert "No clinical documents on file." in mcp_server.get_clinical_documents()
    assert "No clinical document with doc_key" in mcp_server.get_clinical_documents(doc_key="img_20990105_mri_part_a")
