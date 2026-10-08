"""Clinical documents -- import and read-back (Q142 option b; SCHEMA.md section 045).

`POST /clinical-documents/import` takes the extraction payload as-is and upserts on
(user, doc_key). It defaults to a DRY RUN: nothing is written until `dry_run=false` is asked for
explicitly. `GET /clinical-documents` reads the user's documents back, oldest `service_date` first.
Both are user-scoped on the authenticated user, same auth as the lab routes.

The body is read as a raw JSON object, not a Pydantic model: a model would be one more layer that
could coerce or trim a string, and the verbatim fields must reach the table untouched.
"""
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import clinical_documents as cd
import models
from auth import get_current_user
from database import get_db

router = APIRouter(prefix="/clinical-documents", tags=["clinical-documents"])


class ClinicalDocumentOut(BaseModel):
    """The stored row, whole. Strings are returned exactly as stored -- no response-side
    normalising -- so the verbatim fields round-trip byte-for-byte."""
    doc_key: str
    doc_type: str
    modality: str | None
    subtype: str | None
    study: str | None
    region: str | None
    laterality: str | None
    service_date: date
    reported_date: date | None
    provider: str | None
    referrer_name_raw: str | None
    author_name_raw: str | None
    recipient: str | None
    accession: str | None
    source_doc_filenames: list[str]
    clinical_history: str | None
    conclusion_verbatim: str | None
    conclusion_label: str | None
    findings_summary: str | None
    structured: dict[str, Any] | None
    letter: dict[str, Any] | None
    extraction_notes: list[str] | None
    source: str
    schema_version: str
    extracted_at: date | None
    created_at: datetime | None
    updated_at: datetime | None


def document_out(row: models.ClinicalDocument) -> ClinicalDocumentOut:
    return ClinicalDocumentOut(**{f: getattr(row, f) for f in ClinicalDocumentOut.model_fields})


def parse_filters(doc_type: str | None, modality: str | None) -> tuple[str | None, str | None]:
    """Validate the enum filters; raise ValueError naming the allowed set. `modality` is matched
    case-insensitively (`mri` reads as `MRI`)."""
    if doc_type is not None and doc_type not in cd.DOC_TYPES:
        raise ValueError(f"doc_type must be one of {list(cd.DOC_TYPES)}")
    if modality is not None:
        modality = modality.upper()
        if modality not in cd.MODALITIES:
            raise ValueError(f"modality must be one of {list(cd.MODALITIES)}")
    return doc_type, modality


@router.get("", response_model=list[ClinicalDocumentOut])
def list_clinical_documents(
    since: date | None = Query(None, description="service_date on or after this date"),
    doc_type: str | None = Query(None),
    modality: str | None = Query(None),
    region: str | None = Query(None, description="case-insensitive substring of the free-text region"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The user's documents, oldest `service_date` first."""
    try:
        doc_type, modality = parse_filters(doc_type, modality)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    rows = cd.read_documents(db, current_user.id, since=since, doc_type=doc_type,
                             modality=modality, region=region)
    return [document_out(r) for r in rows]


@router.post("/import")
def import_clinical_documents(
    payload: dict[str, Any] = Body(...),
    dry_run: bool = Query(True, description="default TRUE: report what would change, write nothing"),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import a `clinical_documents` extraction payload. Returns `{would_insert[], would_update[],
    unchanged[], refused[{doc_key, reason}]}` (plus `dry_run` / `applied`). `dry_run=false` applies,
    all-or-nothing: any refused document aborts the apply with a 422 and nothing is written."""
    try:
        return cd.import_documents(db, current_user.id, payload, dry_run=dry_run)
    except cd.PayloadError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except cd.ApplyRefused as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "refused documents -- nothing was written; fix them (or run the dry run) first",
                    "refused": e.refused},
        )
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="a concurrent import wrote the same doc_key; re-run the dry run")
