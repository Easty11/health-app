import base64
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import anthropic
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db

load_dotenv()

MODEL = "claude-sonnet-4-6"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

router = APIRouter(prefix="/labs", tags=["labs"])

_CANONICAL_PATH = Path(__file__).resolve().parent.parent / "reference" / "marker_canonical.json"


def _load_canonical_map() -> dict[str, dict]:
    with open(_CANONICAL_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {entry["marker_name_raw"]: entry for entry in data["entries"]}


_CANONICAL_MAP = _load_canonical_map()


# ---------- schemas (LAB_EXTRACTION_SCHEMA v0.3 §2/§3) ----------

class FieldConfidence(BaseModel):
    name: float
    value: float
    unit: float
    ref: float


class ResultItem(BaseModel):
    marker_name_raw: str
    marker_canonical: str | None = None
    value_raw: str | None = None
    value_num: float | None = None
    value_operator: Literal["<", ">"] | None = None
    value_qualitative: str | None = None
    unit_raw: str | None = None
    unit_canonical: str | None = None
    ref_low: float | None = None
    ref_high: float | None = None
    ref_low_exclusive: bool = False
    ref_high_exclusive: bool = False
    ref_raw: str | None = None
    lab_flag: str | None = None
    computed_flag: str | None = None
    flag_agreement: bool | None = None
    marker_comment: str | None = None
    field_confidence: FieldConfidence | None = None


class ReportPatient(BaseModel):
    name_raw: str | None = None
    dob: date | None = None
    sex: str | None = None
    lab_accession: str | None = None


class ReportReferrer(BaseModel):
    name_raw: str | None = None
    provider_ref: str | None = None


class ReportDates(BaseModel):
    collected: datetime | None = None
    received: datetime | None = None
    reported: datetime | None = None
    document_created: datetime | None = None
    requested: date | None = None


class ReportSourceDoc(BaseModel):
    filename: str | None = None
    page_count: int | None = None


class ReportExtractionMeta(BaseModel):
    extracted_at: datetime | None = None
    model: str | None = None
    overall_confidence: float = 0.0


class ReportEnvelope(BaseModel):
    lab_name: str
    lab_provider_group: str | None = None
    accreditation_no: str | None = None
    panel_name_raw: str
    patient: ReportPatient | None = None
    referrer: ReportReferrer | None = None
    dates: ReportDates
    report_comments: list[str] = []
    source_completeness: str
    source_doc: ReportSourceDoc | None = None
    extraction: ReportExtractionMeta


class ExtractionResult(BaseModel):
    report: ReportEnvelope
    results: list[ResultItem]


class ConfirmResponse(BaseModel):
    lab_report_id: int
    result_count: int
    unmapped: list[str]


# ---------- extraction system prompt (LAB_EXTRACTION_SCHEMA v0.3 §2/§4/§5/§6) ----------

EXTRACTION_SYSTEM_PROMPT = """\
You are a lab-report extraction engine. Given a pathology report (PDF or photo), \
emit ONE JSON object matching the target shape below. Extraction must be semantic \
— read the report the way a person would, never by fixed column position, since \
column order and layout vary between reports from the same lab.

## Target object

```json
{
  "report": {
    "lab_name": "Sullivan Nicolaides Pathology",
    "lab_provider_group": "Sonic Healthcare",
    "accreditation_no": "1964",
    "panel_name_raw": "Routine Chemistry",
    "patient": {
      "name_raw": "LUKE EASTLAKE",
      "dob": "1980-11-11",
      "sex": "M",
      "lab_accession": "535723595"
    },
    "referrer": { "name_raw": "Dr Seneviratne", "provider_ref": "11064000" },
    "dates": {
      "collected":        "2026-03-06T09:26:00+10:00",
      "received":         "2026-03-06T09:27:00+10:00",
      "reported":         "2026-03-07T00:35:00+10:00",
      "document_created": "2026-03-08T00:41:16+10:00",
      "requested":        "2026-02-28"
    },
    "report_comments": ["Moderate ALT and/or AST Elev'n (LFT 1)"],
    "source_completeness": "sonic_dx_extract",
    "source_doc": { "filename": "20260306__Routine_Chemistry.pdf", "page_count": 2 },
    "extraction": {
      "extracted_at": "2026-06-22T12:00:00+10:00",
      "model": "<model-id>",
      "overall_confidence": 0.0
    }
  },
  "results": [
    {
      "marker_name_raw": "Bilirubin",
      "marker_canonical": null,
      "value_raw": "28",
      "value_num": 28.0,
      "value_operator": null,
      "value_qualitative": null,
      "unit_raw": "umol/L",
      "unit_canonical": "umol/L",
      "ref_low": null,
      "ref_high": 21.0,
      "ref_high_exclusive": true,
      "ref_raw": "<21",
      "lab_flag": "H",
      "computed_flag": "H",
      "flag_agreement": true,
      "marker_comment": null,
      "field_confidence": { "name": 0.99, "value": 0.99, "unit": 0.98, "ref": 0.97 }
    }
  ]
}
```

Notes on fields:
- `dates.collected` is REQUIRED — it is the timeline anchor (when blood left the
  body), not reported/document-created. Keep all four dates; they diverge and
  provenance matters.
- `marker_canonical` — leave `null`. Canonicalisation happens downstream at
  confirm-time, not during extraction.
- `unit_raw`/`unit_canonical` may legitimately be `null` — eGFR, anion gap
  context, and indices are unitless. Do not invent a unit.
- `lab_flag` is exactly what is printed (`H`/`L`/`HH`/`LL`/`A`/null) — never
  invent one. `computed_flag` is YOUR derivation from value vs. normalised
  range (see rules below) — compute it even when `lab_flag` is absent.
- `report_comments` are panel-level interpretive notes / protocol URLs —
  preserve verbatim.
- `source_completeness` is `sonic_dx_extract` | `full_report` | `unknown`.

## Edge cases you MUST handle correctly (real failure modes, not hypotheticals)

1. **Column order is not fixed across reports**, even from the same lab.
   e.g. one report prints `name · value · ref · units`, another prints
   `name · value · units · ref`. Read by meaning, never by position.
2. **Marker names wrap across lines.** e.g. "Calculated Free" / "Testosterone"
   on two lines is ONE result — reassemble the full name before matching it to
   its value/ref/unit row.
3. **Reference interval has four forms**: bounded (`135 - 145`), ceiling
   (`<21`), floor (`>59`), or absent entirely (e.g. an eGFR row with no upper
   bound, or a Haemolysis Index row with no unit). Normalise all four per the
   rules below; absent means both bounds null.
4. **Units are sometimes absent** — eGFR, anion-gap-adjacent rows, and indices
   routinely have no unit. `null` unit is valid, not a missed extraction.
5. **Flags appear inline and sparsely** — only printed when a value is out of
   range. Absence of a printed flag does NOT mean in-range — always compute
   `computed_flag` from the value and normalised reference range yourself.
6. **Reports may carry two page types**: a lab results table (the data) and an
   administrative/metadata wrapper page (pathologist, document IDs, requester).
   Pull results from the table; harvest `dates.collected`/`requested` and the
   referrer from whichever page has them.
7. **Censored values** — e.g. `FSH <0.1` — parse as `value_num=0.1,
   value_operator="<"`. A censored-but-technically-in-range value still gets
   `computed_flag=null` (suppression is an interpretation-layer question, not
   an extraction one).
8. **Two `<` tokens on one row** (e.g. an Oestradiol row printing `<50 <165`)
   — the FIRST token is the value, the SECOND is the reference ceiling. Do not
   swap them.

## Normalisation rules

Reference interval → `{ref_low, ref_high, ref_low_exclusive, ref_high_exclusive}`:
- `a - b`      → ref_low=a, ref_high=b, both inclusive (both exclusive flags false)
- `<x`         → ref_low=null, ref_high=x, ref_high_exclusive=true
- `>x`         → ref_low=x, ref_high=null, ref_low_exclusive=true
- empty/blank  → ref_low=null, ref_high=null (computed_flag will be null)

Value parsing:
- `28`            → value_num=28.0, value_operator=null
- `<0.1`          → value_num=0.1, value_operator="<" (treat as boundary/censored)
- `Not detected`  → value_num=null, value_qualitative="Not detected"

`computed_flag` (derive yourself — never hand-code a threshold, always compute
from THIS report's printed range):
```
if value_num is null:                                        computed_flag = null
elif ref_high set and value_num > ref_high (>= if ref_high_exclusive):  "H"
elif ref_low  set and value_num < ref_low  (<= if ref_low_exclusive):   "L"
else:                                                          computed_flag = null
```
`flag_agreement` = true when either `lab_flag` is absent, or it agrees with the
H/L direction of `computed_flag`. Disagreement usually signals an OCR error in
the value or the range — set `flag_agreement=false` rather than silently
picking one.

## Confidence and suspect-field signalling

Populate `field_confidence` (0-1 per field: name/value/unit/ref) honestly — this
drives which rows the human confirmation screen highlights for review. Fields
you had to infer, reassemble across wrapped lines, or read from a low-quality
scan should get a LOWER confidence, not a rounded-up one. A human reviews:
- any `field_confidence.*` below 0.85
- any `flag_agreement == false`
- any `value_num == null` where a unit was present (number expected but not read)
- missing `dates.collected`
so under-confidence is the honest, safe default when you are unsure — it is
what routes the row to a person, not an extraction failure.

Return ONLY the JSON object described above. No preamble, no markdown code
fences, no commentary — the response body must be valid JSON and nothing else.
"""


# ---------- GET /labs/canonical-map ----------

@router.get("/canonical-map")
def get_canonical_map(
    current_user: models.User = Depends(get_current_user),
):
    """Read-only lookup so the confirmation screen can flag unmapped markers
    client-side, before /labs/confirm does the authoritative resolution."""
    return _CANONICAL_MAP


# ---------- POST /labs/extract ----------

@router.post("/extract")
async def extract_lab_report(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY is not configured",
        )

    content_type = file.content_type or ""
    is_pdf = content_type == "application/pdf"
    is_image = content_type in ALLOWED_IMAGE_TYPES
    if not is_pdf and not is_image:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type: {content_type or 'unknown'}. Use PDF or jpeg/png/gif/webp.",
        )

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds the 20MB upload limit",
        )

    b64 = base64.b64encode(raw).decode("ascii")

    if is_pdf:
        content_block = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
        }
    else:
        content_block = {
            "type": "image",
            "source": {"type": "base64", "media_type": content_type, "data": b64},
        }

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=MODEL,
        # Dense panels (20+ markers, each with a per-field confidence object)
        # can exceed 4096 output tokens and get cut off mid-JSON.
        max_tokens=8192,
        system=EXTRACTION_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    content_block,
                    {
                        "type": "text",
                        "text": "Extract all lab results from this report. Return only the JSON object matching the schema. No preamble.",
                    },
                ],
            }
        ],
    )

    raw_text = response.content[0].text.strip()
    # Model is instructed not to fence its output, but strip fences defensively.
    raw_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text).strip()

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "Model output was not valid JSON", "raw_output": raw_text},
        )

    return parsed


# ---------- POST /labs/confirm ----------

@router.post("/confirm", response_model=ConfirmResponse, status_code=status.HTTP_201_CREATED)
def confirm_lab_report(
    body: ExtractionResult,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.report.dates.collected is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="report.dates.collected is required — it is the timeline anchor and cannot be stored null",
        )

    unmapped: list[str] = []
    resolved: list[tuple[ResultItem, str | None, str | None]] = []

    for r in body.results:
        entry = _CANONICAL_MAP.get(r.marker_name_raw)
        if entry:
            resolved.append((r, entry["marker_canonical"], entry.get("unit_established")))
        else:
            unmapped.append(r.marker_name_raw)
            resolved.append((r, None, None))

    # Over-collapse guard (§6) — validate every row before writing any of them.
    for r, canonical, established_unit in resolved:
        if canonical and established_unit and r.unit_canonical and r.unit_canonical != established_unit:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Over-collapse guard: '{r.marker_name_raw}' maps to canonical "
                    f"'{canonical}' (established unit '{established_unit}') but this "
                    f"result carries unit '{r.unit_canonical}' — refusing to write."
                ),
            )

    report = body.report
    lab_report = models.LabReport(
        user_id=current_user.id,
        lab_name=report.lab_name,
        lab_provider_group=report.lab_provider_group,
        panel_name_raw=report.panel_name_raw,
        accreditation_no=report.accreditation_no,
        referrer_name_raw=report.referrer.name_raw if report.referrer else None,
        referrer_ref=report.referrer.provider_ref if report.referrer else None,
        collected_date=report.dates.collected.date(),
        received_at=report.dates.received.date() if report.dates.received else None,
        reported_at=report.dates.reported.date() if report.dates.reported else None,
        document_created_at=report.dates.document_created.date() if report.dates.document_created else None,
        requested_date=report.dates.requested,
        report_comments=report.report_comments or None,
        source_completeness=report.source_completeness,
        source="file_extraction",
        source_doc_filename=report.source_doc.filename if report.source_doc else None,
        page_count=report.source_doc.page_count if report.source_doc else None,
        overall_confidence=report.extraction.overall_confidence,
        extracted_at=report.extraction.extracted_at,
    )
    db.add(lab_report)
    db.flush()  # get lab_report.id before inserting results

    for r, canonical, _established_unit in resolved:
        confidences = list(r.field_confidence.model_dump().values()) if r.field_confidence else None
        confidence = min(confidences) if confidences else 1.0
        db.add(models.LabResult(
            lab_report_id=lab_report.id,
            # lab_results.marker is NOT NULL (#52). An unmapped marker has no
            # canonical id yet, so the raw name is stored as a placeholder —
            # `unmapped` in the response is the actual signal for "needs a
            # human bind/declare", not nullness of this column.
            marker=canonical or r.marker_name_raw,
            value_num=r.value_num,
            value_operator=r.value_operator,
            value_qualitative=r.value_qualitative,
            unit_canonical=r.unit_canonical,
            ref_low=r.ref_low,
            ref_high=r.ref_high,
            ref_low_exclusive=r.ref_low_exclusive,
            ref_high_exclusive=r.ref_high_exclusive,
            lab_flag=r.lab_flag,
            computed_flag=r.computed_flag,
            confidence=confidence,
        ))

    db.commit()

    return ConfirmResponse(
        lab_report_id=lab_report.id,
        result_count=len(body.results),
        unmapped=unmapped,
    )
