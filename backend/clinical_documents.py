"""Clinical documents store -- validators, the payload->column mapping and the importer
(Q142 option b; SCHEMA.md section 045).

One `clinical_documents` row per imaging report or clinical letter. The payload is a
`clinical_documents v0.x` extraction file: `{schema, extracted_at, documents[], conventions?,
not_extracted?}`. `conventions` and `not_extracted` are metadata about the extraction and are not
stored.

THE CLOSED-KEY LISTS BELOW ARE DERIVED FROM THE BUILD BRIEF, NOT FROM THE PAYLOAD FILE. The file
lives on the operator's laptop and was not readable when this was written. The failure mode is
loud by design: a key the lists do not know refuses ITS DOCUMENT with the key NAME in the reason
(never a value), so the first dry-run names exactly what to add. Extending a list is a one-line
change here -- `LETTER_KEYS` for a correspondence body key, the `*_KEYS` tuples for an envelope key.

VERBATIM FIELDS ARE NEVER REWRITTEN. `conclusion_verbatim`, `letter.diagnosis_verbatim` and
`letter.management_plan_verbatim` pass through this module as the very objects that were parsed
-- no strip, no collapse, no replace. Validation only CHECKS them (a string, not blank); it never
returns a modified copy. The same holds for every other free-text field: a value is stored as
received or the document is refused.

NO IDENTIFIERS. The repo is public and the payload is a medical record. A key that names an
identifier (`ihi`, `medicare*`, `address`, `phone`, `dob`, ...) anywhere in a document -- at any
nesting depth, including inside `structured` and the letter body -- refuses that document. Keys
only: values are free text and are not scanned.

NO INTERPRETATION. This module stores and reads documents back. It creates no finding, constraint
or injury change from a document's content.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models

DOC_TYPES = ("imaging", "correspondence")
MODALITIES = ("US", "CT", "MRI", "XR", "DXA")
LATERALITIES = ("L", "R", "bilateral")
SUBTYPES = ("referral", "specialist letter")
SOURCE = "file_extraction"
SCHEMA_PREFIX = "clinical_documents "

# Payload top level. `conventions` / `not_extracted` are accepted and dropped.
ENVELOPE_KEYS = ("schema", "extracted_at", "documents", "conventions", "not_extracted")
IGNORED_ENVELOPE_KEYS = ("conventions", "not_extracted")

# Per-document keys, by role. `dates` / `source_files` / `author` / `referrer` / `id` are the
# payload's own names for `service_date`+`reported_date` / `source_doc_filenames` /
# `author_name_raw` / `referrer_name_raw` / `doc_key`.
COMMON_KEYS = (
    "id", "doc_type", "dates", "source_files", "provider", "referrer", "author", "recipient",
    "accession", "region", "laterality", "extraction_notes",
)
IMAGING_KEYS = (
    "modality", "study", "clinical_history", "conclusion_verbatim", "conclusion_label",
    "findings_summary", "structured",
)
# The correspondence body: every top-level key that is not an envelope column goes into `letter`
# UNCHANGED.
LETTER_KEYS = (
    "reason", "diagnosis_verbatim", "management_plan_verbatim", "history_summary",
    "examination_summary", "imaging_review_summary", "assessment_summary", "medications_listed",
    "recorded_risk_factors", "allergies", "attachments", "actions",
)
CORRESPONDENCE_KEYS = ("subtype",) + LETTER_KEYS
DATES_KEYS = ("service", "reported")

DOC_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")
# A key that names an identifier. The short words (`ihi`, `dob`, `fax`, `mobile`) match only as
# whole `_`-separated tokens of the lower-cased key, so nothing innocent is caught by substring
# accident; the long ones match anywhere, which also catches the run-together camelCase forms
# (`homeAddress`, `dateOfBirth`).
_IDENTIFIER_KEY_RE = re.compile(
    r"(^|_)(ihi|dob|fax|mobile)(_|$)|address|phone|medicare|date_?of_?birth|birth_?date"
)

# Column widths (models.ClinicalDocument). SQLite does not enforce them and Postgres does, so the
# validator does -- an over-long value is a refusal, never a 500 on apply.
MAX_LEN = {
    "doc_key": 100, "modality": 10, "subtype": 30, "study": 255, "region": 100, "laterality": 10,
    "provider": 255, "referrer": 255, "author": 255, "recipient": 255, "accession": 50,
    "conclusion_label": 100,
}

# Columns compared for the unchanged / would_update split, and overwritten on update.
PAYLOAD_COLUMNS = (
    "doc_type", "modality", "subtype", "study", "region", "laterality", "service_date",
    "reported_date", "provider", "referrer_name_raw", "author_name_raw", "recipient", "accession",
    "source_doc_filenames", "clinical_history", "conclusion_verbatim", "conclusion_label",
    "findings_summary", "structured", "letter", "extraction_notes", "source", "schema_version",
    "extracted_at",
)


class PayloadError(ValueError):
    """The payload as a whole is unusable (not per-document): the route answers 422."""


class ApplyRefused(Exception):
    """`dry_run=false` was asked of a payload with refused documents. Nothing was written."""

    def __init__(self, refused: list[dict[str, str]]):
        super().__init__(f"{len(refused)} document(s) refused; nothing written")
        self.refused = refused


# ---------- validation ----------

def _closed(obj: Any, allowed: tuple[str, ...], where: str) -> None:
    if not isinstance(obj, dict):
        raise ValueError(f"{where} must be an object")
    extra = sorted(set(obj) - set(allowed))
    if extra:
        raise ValueError(f"{where}: unknown key(s) {extra}")


def _identifier_paths(obj: Any, path: str = "") -> list[str]:
    """Paths of every dict key, at any depth, that names an identifier."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else str(k)
            if _IDENTIFIER_KEY_RE.search(re.sub(r"[^a-z0-9]+", "_", str(k).lower())):
                hits.append(here)
            hits.extend(_identifier_paths(v, here))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(_identifier_paths(v, f"{path}[{i}]"))
    return hits


def _text(doc: dict[str, Any], key: str, where: str | None = None, *, required: bool = False) -> str | None:
    """A free-text field: None, or a non-blank string returned AS RECEIVED (never stripped)."""
    where = where or key
    v = doc.get(key)
    if v is None:
        if required:
            raise ValueError(f"{where} is required")
        return None
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{where} must be a non-blank string or null")
    cap = MAX_LEN.get(key)
    if cap is not None and len(v) > cap:
        raise ValueError(f"{where} is {len(v)} characters; the column holds {cap}")
    return v


def _iso(value: Any, where: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{where} must be an ISO date string (YYYY-MM-DD)")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{where} must be an ISO date (YYYY-MM-DD)") from None


def _string_list(value: Any, where: str, *, minimum: int = 0) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum or not all(
        isinstance(x, str) and x.strip() for x in value
    ):
        need = f" with at least {minimum} entr{'y' if minimum == 1 else 'ies'}" if minimum else ""
        raise ValueError(f"{where} must be a list of non-blank strings{need}")
    return value


def validate_document(doc: Any) -> dict[str, Any]:
    """Validate one payload document and map it to `ClinicalDocument` column values (shape only,
    no DB). Raises ValueError naming the offending KEY or FIELD, never a value. Verbatim fields
    come back as the very objects that went in."""
    if not isinstance(doc, dict):
        raise ValueError("document must be an object")
    ids = _identifier_paths(doc)
    if ids:
        raise ValueError(f"identifier-like key(s) {sorted(ids)} -- a clinical document carries none")

    doc_type = doc.get("doc_type")
    if doc_type not in DOC_TYPES:
        raise ValueError(f"doc_type must be one of {list(DOC_TYPES)}")
    imaging = doc_type == "imaging"
    _closed(doc, COMMON_KEYS + (IMAGING_KEYS if imaging else CORRESPONDENCE_KEYS), f"{doc_type} document")

    doc_key = _text(doc, "id", "id", required=True)
    if len(doc_key) > MAX_LEN["doc_key"] or not DOC_KEY_RE.match(doc_key):
        raise ValueError(f"id must be 1-{MAX_LEN['doc_key']} characters of letters, digits, '_', '.', '-'")

    dates = doc.get("dates")
    _closed(dates, DATES_KEYS, "dates")
    if dates.get("service") is None:
        raise ValueError("dates.service is required (the timeline anchor)")
    service_date = _iso(dates["service"], "dates.service")
    reported_date = _iso(dates["reported"], "dates.reported") if dates.get("reported") is not None else None

    laterality = doc.get("laterality")
    if laterality is not None and laterality not in LATERALITIES:
        raise ValueError(f"laterality must be one of {list(LATERALITIES)} or null")

    modality = subtype = None
    if imaging:
        modality = doc.get("modality")
        if modality not in MODALITIES:
            raise ValueError(f"modality must be one of {list(MODALITIES)}")
    else:
        subtype = doc.get("subtype")
        if subtype not in SUBTYPES:
            raise ValueError(f"subtype must be one of {list(SUBTYPES)}")

    structured = doc.get("structured")
    if structured is not None and not isinstance(structured, dict):
        raise ValueError("structured must be an object or null")
    notes = doc.get("extraction_notes")
    if notes is not None:
        notes = _string_list(notes, "extraction_notes")

    letter = None
    if not imaging:
        letter = {k: doc[k] for k in LETTER_KEYS if k in doc} or None
        if letter:
            if letter.get("diagnosis_verbatim") is not None:
                _text(letter, "diagnosis_verbatim", "diagnosis_verbatim")
            if letter.get("management_plan_verbatim") is not None:
                _string_list(letter["management_plan_verbatim"], "management_plan_verbatim")

    return {
        "doc_key": doc_key,
        "doc_type": doc_type,
        "modality": modality,
        "subtype": subtype,
        "study": _text(doc, "study"),
        "region": _text(doc, "region"),
        "laterality": laterality,
        "service_date": service_date,
        "reported_date": reported_date,
        "provider": _text(doc, "provider"),
        "referrer_name_raw": _text(doc, "referrer"),
        "author_name_raw": _text(doc, "author"),
        "recipient": _text(doc, "recipient"),
        "accession": _text(doc, "accession"),
        "source_doc_filenames": _string_list(doc.get("source_files"), "source_files", minimum=1),
        "clinical_history": _text(doc, "clinical_history"),
        "conclusion_verbatim": _text(doc, "conclusion_verbatim"),
        "conclusion_label": _text(doc, "conclusion_label"),
        "findings_summary": _text(doc, "findings_summary"),
        "structured": structured,
        "letter": letter,
        "extraction_notes": notes,
    }


def validate_envelope(payload: Any) -> tuple[str, date | None, list[Any]]:
    """The payload's own shape: `(schema_version, extracted_at, documents)`, or PayloadError."""
    try:
        _closed(payload, ENVELOPE_KEYS, "payload")
    except ValueError as e:
        raise PayloadError(str(e)) from None
    schema = payload.get("schema")
    if not isinstance(schema, str) or not schema.startswith(SCHEMA_PREFIX) or len(schema) > 30:
        raise PayloadError(f"payload.schema must read '{SCHEMA_PREFIX}v<version>' (30 characters at most)")
    docs = payload.get("documents")
    if not isinstance(docs, list) or not docs:
        raise PayloadError("payload.documents must be a non-empty list")
    extracted_at = None
    if payload.get("extracted_at") is not None:
        try:
            extracted_at = _iso(payload["extracted_at"], "payload.extracted_at")
        except ValueError as e:
            raise PayloadError(str(e)) from None
    return schema, extracted_at, docs


# ---------- import ----------

@dataclass
class ImportPlan:
    would_insert: list[str] = field(default_factory=list)
    would_update: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    refused: list[dict[str, str]] = field(default_factory=list)
    # doc_key -> column values, for the writes
    values: dict[str, dict[str, Any]] = field(default_factory=dict)


def plan_import(db: Session, user_id: int, payload: Any) -> ImportPlan:
    """Classify every document against the user's stored rows. Reads only."""
    schema, extracted_at, docs = validate_envelope(payload)
    plan = ImportPlan()

    validated: list[tuple[str, dict[str, Any]]] = []
    seen: dict[str, int] = {}
    for i, doc in enumerate(docs):
        label = doc["id"] if isinstance(doc, dict) and isinstance(doc.get("id"), str) else f"documents[{i}]"
        try:
            vals = validate_document(doc)
        except ValueError as e:
            plan.refused.append({"doc_key": label, "reason": str(e)})
            continue
        validated.append((vals["doc_key"], vals))
        seen[vals["doc_key"]] = seen.get(vals["doc_key"], 0) + 1

    # A doc_key that appears twice is ambiguous -- which copy is canonical? -- so every copy refuses.
    for key, vals in validated:
        if seen[key] > 1:
            if not any(r["doc_key"] == key and r["reason"].startswith("duplicate") for r in plan.refused):
                plan.refused.append({"doc_key": key, "reason": f"duplicate doc_key in payload ({seen[key]} copies)"})
            continue
        vals["source"] = SOURCE
        vals["schema_version"] = schema
        vals["extracted_at"] = extracted_at
        plan.values[key] = vals

    existing = {
        r.doc_key: r for r in db.query(models.ClinicalDocument).filter(
            models.ClinicalDocument.user_id == user_id,
            models.ClinicalDocument.doc_key.in_(list(plan.values)),
        )
    } if plan.values else {}
    for key, vals in plan.values.items():
        row = existing.get(key)
        if row is None:
            plan.would_insert.append(key)
        elif all(getattr(row, c) == vals[c] for c in PAYLOAD_COLUMNS):
            plan.unchanged.append(key)
        else:
            plan.would_update.append(key)
    return plan


def import_documents(db: Session, user_id: int, payload: Any, *, dry_run: bool = True) -> dict[str, Any]:
    """Plan, and (when `dry_run` is false) apply. An apply is ALL-OR-NOTHING: any refused document
    raises ApplyRefused and nothing is written. Upsert on (user_id, doc_key); an update overwrites
    the row in full -- one extractor, so the payload is the canonical extraction and there is no
    supersede chain."""
    plan = plan_import(db, user_id, payload)
    if not dry_run:
        if plan.refused:
            raise ApplyRefused(plan.refused)
        for key in plan.would_insert:
            db.add(models.ClinicalDocument(user_id=user_id, **plan.values[key]))
        if plan.would_update:
            rows = db.query(models.ClinicalDocument).filter(
                models.ClinicalDocument.user_id == user_id,
                models.ClinicalDocument.doc_key.in_(plan.would_update),
            ).all()
            for row in rows:
                for c in PAYLOAD_COLUMNS:
                    setattr(row, c, plan.values[row.doc_key][c])
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise
    return {
        "dry_run": dry_run,
        "applied": not dry_run,
        "would_insert": plan.would_insert,
        "would_update": plan.would_update,
        "unchanged": plan.unchanged,
        "refused": plan.refused,
    }


# ---------- read ----------

def read_documents(
    db: Session, user_id: int, *, since: date | None = None, doc_type: str | None = None,
    modality: str | None = None, region: str | None = None, doc_key: str | None = None,
) -> list[models.ClinicalDocument]:
    """The user's documents, oldest `service_date` first (id breaks ties). Every query is filtered
    on `user_id` -- another user's `doc_key` is simply absent. `region` is a case-insensitive
    substring over the free-text region."""
    q = db.query(models.ClinicalDocument).filter(models.ClinicalDocument.user_id == user_id)
    if since is not None:
        q = q.filter(models.ClinicalDocument.service_date >= since)
    if doc_type is not None:
        q = q.filter(models.ClinicalDocument.doc_type == doc_type)
    if modality is not None:
        q = q.filter(models.ClinicalDocument.modality == modality)
    if doc_key is not None:
        q = q.filter(models.ClinicalDocument.doc_key == doc_key)
    rows = q.order_by(models.ClinicalDocument.service_date, models.ClinicalDocument.id).all()
    if region is not None:
        needle = region.casefold()
        rows = [r for r in rows if r.region and needle in r.region.casefold()]
    return rows
