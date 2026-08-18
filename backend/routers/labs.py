import base64
import json
import os
import re
from datetime import date, datetime
from typing import Literal

import anthropic
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

import models
from auth import get_current_user
from database import get_db

load_dotenv()

MODEL = "claude-sonnet-4-6"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

router = APIRouter(prefix="/labs", tags=["labs"])

def _canonical_map(db: Session) -> dict[str, dict]:
    """The canonical marker map, read from `marker_canonical_entries` per request.

    Was a module-level dict loaded from `reference/marker_canonical.json` at import.
    It is a per-request query now (#220) because the map is runtime-mutable: a bind
    writes a row, and a cached dict would serve the pre-bind map to the very confirm
    the operator just bound for. No cache is warranted at this volume either — a panel
    is ~20 rows and confirms are rare — so freshness costs one indexed scan of ~70 rows.

    The returned shape is the one `/canonical-map`'s frontend consumers already read:
    `{marker_name_raw: {marker_name_raw, marker_canonical, unit_established, loinc}}`.
    """
    return {
        e.marker_name_raw: {
            "marker_name_raw": e.marker_name_raw,
            "marker_canonical": e.marker_canonical,
            "unit_established": e.unit_established,
            "loinc": e.loinc,
        }
        for e in db.query(models.MarkerCanonicalEntry).all()
    }


# ---------- schemas (LAB_EXTRACTION_SCHEMA v0.3 §2/§3) ----------

class FieldConfidence(BaseModel):
    """Per-field extraction confidence. Every sub-field is Optional, and `None` means
    NOT EXPRESSED — the field is absent from the report, so there was no extraction to
    be confident about (a ref-less row has no `ref` to score).

    LOOSEN, do not coerce — the opposite of `#178`'s exclusivity bools, and for a
    reason that does not generalise between them. An absent bound has a correct
    default (`False`: nothing to be exclusive about). A confidence has none. `1.0`
    would assert high confidence in a field that was never read, hiding a genuinely
    suspect row; `0.0` would mark it suspect on a field that legitimately does not
    exist. Both are lies with a direction. `None` is the honest type, and every
    consumer must treat it as ABSENT rather than as a number — see
    `confirm_lab_report`'s derivation and `Metrics.jsx`'s `isSuspect`/`confidencePct`,
    all three of which coerce null to 0 if left unguarded."""
    name: float | None = None
    value: float | None = None
    unit: float | None = None
    ref: float | None = None


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

    # A ref-less row nulls these, and a bare `bool` fails closed on it (#177's
    # instrument caught `results.0.ref_high_exclusive: Input should be a valid boolean`
    # on `R U-Creatinine`, whose reference interval is printed `—`). The extractor is
    # not wrong to send null: with no bound, there is nothing to be exclusive ABOUT.
    #
    # COERCE, DO NOT LOOSEN. The type stays strictly `bool`, matching the column
    # (`models.py:622-623`, `nullable=False, server_default=false`) — so nothing
    # downstream ever sees `None` and no migration is needed. `False` is the correct
    # value, not a placeholder: it is the column's own server_default, and it is
    # behaviourally inert on exactly the rows it touches, because every consumer reads
    # the flag only inside a bound-is-not-None branch (`interpretation/gates.py:108,114`;
    # `context_builder.py:965-966`).
    #
    # BOTH flags, not just the captured one. Which flag the model nulls on a sparse row
    # is nondeterministic — this report nulled `ref_high` on an absent-ref row, but a
    # `>x` floor-only row leaves the ceiling absent and a `<x` ceiling row the floor.
    # Fixing only the field the banner named would re-open this on the next report shape.
    @field_validator("ref_low_exclusive", "ref_high_exclusive", mode="before")
    @classmethod
    def _null_exclusivity_means_not_exclusive(cls, v):
        return False if v is None else v


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
    # overall_confidence is NOT a model self-report (#146): it defaulted silently
    # to 0.0 when the model omitted it and was seeded by the prompt example, so an
    # omitted field was indistinguishable from a genuine zero. It is now DERIVED at
    # confirm from the same per-row confidences already written. See confirm_lab_report.


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


class DuplicateCollision(BaseModel):
    """One marker already present for this user at this collection date.

    Surfaced, never silently absorbed — the same category of thing as `unmapped` (#58):
    something the platform saw, declined to write blind, and is telling the caller about.
    Carries both values so the caller can tell a byte-identical re-upload from a corrected
    result without another round trip."""
    marker: str                      # canonical id, or the raw label when unmapped
    marker_canonical: str | None
    collected_date: date
    existing_lab_report_id: int
    existing_value_num: float | None
    incoming_value_num: float | None
    action: str                      # "skipped" | "written"


class ConfirmResponse(BaseModel):
    lab_report_id: int
    result_count: int                # rows actually WRITTEN, which may be fewer than submitted
    unmapped: list[str]
    duplicates: list[DuplicateCollision] = []


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
      "model": "<model-id>"
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
- empty/blank  → ref_low=null, ref_high=null, ref_low_exclusive=false,
                 ref_high_exclusive=false (computed_flag will be null). The
                 exclusivity flags are ALWAYS booleans, never null: with no bound
                 there is nothing to be exclusive about, so `false` is correct.
                 Same on a one-sided interval — the absent side's flag is false.

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

A field that is ABSENT from the report has no extraction to be confident about —
emit `null` for that sub-field, or omit it. The commonest case is a row with no
reference interval: there is no `ref` to have read, so `ref` confidence is `null`,
NOT a low number and NOT a high one. Do not invent a score for something that was
never on the page.

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
    db: Session = Depends(get_db),
):
    """Read-only lookup so the confirmation screen can flag unmapped markers
    client-side, before /labs/confirm does the authoritative resolution."""
    return _canonical_map(db)


# ---------- POST /labs/canonical/bind (#220, fulfilling #50) ----------

class CanonicalBindIn(BaseModel):
    """One raw->canonical binding, supplied EXACTLY by the operator.

    Nothing is guessed. #50 refused fuzzy matching because a near-match that silently
    binds is how two different analytes become one series, and the damage is only
    visible much later as a trend that never happened."""
    marker_name_raw: str
    marker_canonical: str
    unit_established: str | None = None


class CanonicalBindOut(BaseModel):
    marker_name_raw: str
    marker_canonical: str
    unit_established: str | None
    backfilled_rows: int


@router.post("/canonical/bind", status_code=status.HTTP_201_CREATED, response_model=CanonicalBindOut)
def bind_canonical_marker(
    body: CanonicalBindIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bind an unmapped raw marker name to a canonical id, and promote its history.

    Backfill is the point of binding. Without it a bind only helps future uploads, while
    every already-stored row of that marker stays `marker_canonical IS NULL` and the reads'
    `COALESCE(marker_canonical, marker_name_raw)` partition keeps them in a separate series
    — the marker becomes a live series the moment it is promoted (#159), not at the next draw.

    Two refusals, both the over-collapse guard (§6, the reason #50 exists) at the two
    points where identity newly becomes mutable at runtime:

      * bind-time — the canonical already exists on another row with an established unit
        that disagrees. This is total-T nmol/L vs free-T pmol/L caught before it merges.
      * backfill-time — a historical row of this raw name carries a unit that disagrees
        with the unit being established. Same fault, surfacing from history instead of
        from the map, and it refuses the WHOLE bind rather than promoting a mismatched
        unit into a shared series. Partial promotion would be the worse outcome: half a
        series migrated is harder to see, and harder to undo, than a refused bind.
    """
    existing = (
        db.query(models.MarkerCanonicalEntry)
        .filter(models.MarkerCanonicalEntry.marker_name_raw == body.marker_name_raw)
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"'{body.marker_name_raw}' is already mapped to "
                f"'{existing.marker_canonical}' — binding an already-mapped marker is not "
                f"an update path. Change it via a governed map edit, not a bind."
            ),
        )

    # Over-collapse guard, bind-time.
    if body.unit_established:
        clash = (
            db.query(models.MarkerCanonicalEntry)
            .filter(
                models.MarkerCanonicalEntry.marker_canonical == body.marker_canonical,
                models.MarkerCanonicalEntry.unit_established.isnot(None),
                models.MarkerCanonicalEntry.unit_established != body.unit_established,
            )
            .first()
        )
        if clash is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Over-collapse guard: canonical '{body.marker_canonical}' is already "
                    f"established in unit '{clash.unit_established}' (via "
                    f"'{clash.marker_name_raw}'), but this bind establishes "
                    f"'{body.unit_established}' — refusing to merge two analytes into one series."
                ),
            )

    historical = (
        db.query(models.LabResult)
        .filter(
            models.LabResult.marker_name_raw == body.marker_name_raw,
            models.LabResult.marker_canonical.is_(None),
        )
        .all()
    )

    # Over-collapse guard, backfill-time — validate every row before promoting any.
    if body.unit_established:
        for row in historical:
            if row.unit_canonical and row.unit_canonical != body.unit_established:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=(
                        f"Over-collapse guard: stored result id={row.id} for "
                        f"'{body.marker_name_raw}' carries unit '{row.unit_canonical}', but "
                        f"this bind establishes '{body.unit_established}' — refusing the bind "
                        f"rather than promoting a mismatched unit into '{body.marker_canonical}'."
                    ),
                )

    entry = models.MarkerCanonicalEntry(
        marker_name_raw=body.marker_name_raw,
        marker_canonical=body.marker_canonical,
        unit_established=body.unit_established,
        loinc=None,
        display_name=None,
        source="bind",
        created_by_user_id=current_user.id,
    )
    db.add(entry)
    for row in historical:
        row.marker_canonical = body.marker_canonical
    db.commit()

    return CanonicalBindOut(
        marker_name_raw=body.marker_name_raw,
        marker_canonical=body.marker_canonical,
        unit_established=body.unit_established,
        backfilled_rows=len(historical),
    )


# ---------- GET /labs/results (#59 read-back consumer) ----------

class StoredResultOut(BaseModel):
    """One stored result, projected to the RAW education fields only (#47).

    Deliberately omits `computed_flag` (withheld-computed, contract V2), `confidence`
    (extraction QA, not a clinical read), `is_derived`, and anything interpretive
    (deltas, mechanisms, levers) — interpreted meaning is the 4b deliverable (#49).
    The boundary is enforced HERE at the projection, not only in the view."""
    marker_name_raw: str
    marker_canonical: str | None
    value_num: float | None
    value_operator: str | None
    value_qualitative: str | None
    unit_canonical: str | None
    ref_low: float | None
    ref_high: float | None
    ref_low_exclusive: bool
    ref_high_exclusive: bool
    lab_flag: str | None


class StoredReportOut(BaseModel):
    report_id: int
    lab_name: str
    panel_name_raw: str
    collected_date: date
    # Ingest PROVENANCE, not interpretation — #47 bounds what may be said about a result's
    # clinical meaning, and says nothing about which file a report came from or whether it
    # contributed rows. Both are needed by the upload history, which answers "which of my
    # documents went in" — a question nothing previously could.
    source_doc_filename: str | None
    zero_row_reason: str | None
    results: list[StoredResultOut]


@router.get("/results", response_model=list[StoredReportOut])
def get_lab_results(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Read-back of the user's confirmed lab results, grouped by report, newest
    `collected_date` first. This is #59's "consumer" — a raw values/ranges/lab-flags
    surface (#47), NOT the interpreted view (that stays 4b, #49). User-scoped (#42):
    every row is filtered on the authenticated user's id.

    A report read-back, so it is grouped by report — distinct from
    `labs_reads.latest_lab_results`, which is one-row-per-marker-latest for the
    interpretation producer."""
    reports = (
        db.query(models.LabReport)
        .filter(models.LabReport.user_id == current_user.id)
        .order_by(models.LabReport.collected_date.desc(), models.LabReport.id.desc())
        .all()
    )

    out: list[StoredReportOut] = []
    for rep in reports:
        results = (
            db.query(models.LabResult)
            .filter(models.LabResult.lab_report_id == rep.id)
            .order_by(models.LabResult.marker_canonical.is_(None), models.LabResult.marker_name_raw)
            .all()
        )
        out.append(StoredReportOut(
            report_id=rep.id,
            lab_name=rep.lab_name,
            panel_name_raw=rep.panel_name_raw,
            collected_date=rep.collected_date,
            source_doc_filename=rep.source_doc_filename,
            zero_row_reason=rep.zero_row_reason,
            results=[
                StoredResultOut(
                    marker_name_raw=r.marker_name_raw,
                    marker_canonical=r.marker_canonical,
                    value_num=r.value_num,
                    value_operator=r.value_operator,
                    value_qualitative=r.value_qualitative,
                    unit_canonical=r.unit_canonical,
                    ref_low=r.ref_low,
                    ref_high=r.ref_high,
                    ref_low_exclusive=r.ref_low_exclusive,
                    ref_high_exclusive=r.ref_high_exclusive,
                    lab_flag=r.lab_flag,
                )
                for r in results
            ],
        ))
    return out


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

def _duplicate_key(marker_canonical: str | None, marker_name_raw: str) -> str:
    """The series-identity key for one result row.

    `(user, marker, collected_date)` is the tuple `marker_series` actually partitions on,
    so it is the only key that guards what the gate model reads. Falls back to the RAW
    label when `marker_canonical` is null: unmapped rows are stored (#58/#155) and become a
    live series the moment the marker is promoted, so a duplicate that slips in unmapped
    would surface as a corrupted series long after the upload that caused it. Guarding the
    raw label closes that, rather than leaving it as a known gap."""
    return marker_canonical if marker_canonical else f"raw:{marker_name_raw}"


@router.post("/confirm", response_model=ConfirmResponse, status_code=status.HTTP_201_CREATED)
def confirm_lab_report(
    body: ExtractionResult,
    on_duplicate: str = "skip",
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """`on_duplicate` resolves a marker already present at this collection date:

      * `skip` (default) — the colliding ROW is not written; every other row is, and the
        report itself is still created because the document genuinely exists (#155
        retain-raw). One collision never fails the whole upload.
      * `keep_both` — write it anyway. For the case the operator knows is legitimate.

    `supersede` is NOT offered, deliberately. There is no supersede column on `LabResult`
    (#52 is explicit: compute-on-read, no supersede column), so the only mechanism available
    would be deleting the earlier row — which directly contradicts `#155`'s ratification of
    retain-raw. Superseding needs a `superseded_at`/`superseded_by` affordance so the
    original is retained but excluded from the series; that is a schema change and is not
    invented here. A correction is therefore resolved today by `keep_both` plus a follow-up,
    or by adding that column first.
    """
    if body.report.dates.collected is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="report.dates.collected is required — it is the timeline anchor and cannot be stored null",
        )

    unmapped: list[str] = []
    resolved: list[tuple[ResultItem, str | None, str | None]] = []
    canonical_map = _canonical_map(db)

    for r in body.results:
        entry = canonical_map.get(r.marker_name_raw)
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

    # ---------- series-integrity guard (#156) ----------
    # A marker already present for this user at this collection date would give
    # `marker_series` two same-draw rows at rn=1/rn=2, drop the true earlier prior, and
    # resolve both safety bands identically — returning band_change None. The safety arm
    # then never fires and the marker reads as flat and quiet. Detected here, at the only
    # point where the series can still be kept correct.
    collected_date = report.dates.collected.date()
    existing_at_date: dict[str, tuple[int, float | None]] = {}
    for canonical, raw, value_num, existing_report_id in (
        db.query(models.LabResult.marker_canonical, models.LabResult.marker_name_raw,
                 models.LabResult.value_num, models.LabResult.lab_report_id)
        .join(models.LabReport, models.LabReport.id == models.LabResult.lab_report_id)
        .filter(models.LabReport.user_id == current_user.id,            # #42
                models.LabReport.collected_date == collected_date)
        .all()
    ):
        existing_at_date.setdefault(_duplicate_key(canonical, raw), (existing_report_id, value_num))

    duplicates: list[DuplicateCollision] = []
    # Skip is decided per ROW INDEX, never per marker key. Keying the skip set by marker
    # meant an intra-batch repeat suppressed EVERY row carrying that marker — including the
    # first, which had nothing to collide with — so a marker appearing twice in one document
    # was dropped entirely rather than stored once. That is real loss (the value reaches no
    # row anywhere), as distinct from the DB-collision case where the value is already
    # stored and skipping it is the point. Row indices align with `resolved`.
    skip_indices: set[int] = set()
    seen_in_batch: set[str] = set()
    for idx, (r, canonical, _established_unit) in enumerate(resolved):
        key = _duplicate_key(canonical, r.marker_name_raw)
        prior = existing_at_date.get(key)
        if prior is None:
            if key not in seen_in_batch:
                seen_in_batch.add(key)
                continue          # first sighting of a marker not already stored — write it
            # the same marker twice inside ONE submission (two raw labels, one canonical);
            # the (lab_report_id, marker_name_raw) constraint does not catch this.
            prior = (0, None)
        seen_in_batch.add(key)
        existing_report_id, existing_value = prior
        if on_duplicate == "skip":
            skip_indices.add(idx)
        duplicates.append(DuplicateCollision(
            marker=canonical or r.marker_name_raw,
            marker_canonical=canonical,
            collected_date=collected_date,
            existing_lab_report_id=existing_report_id,
            existing_value_num=existing_value,
            incoming_value_num=r.value_num,
            action="skipped" if on_duplicate == "skip" else "written",
        ))

    # ---------- re-confirm shell dedupe (retain-raw #155, bounded) ----------
    # An all-collision re-confirm (every resolved row already stored at this date) otherwise
    # mints a fresh `all_markers_declined` shell on EVERY re-submission of the same document —
    # they accumulate without bound. Cap them at ONE per identified document: if a shell for
    # this (user, collected_date, source_doc_filename) already records the event, return it
    # rather than creating a second. The decline-history record (#155/#157) is preserved, its
    # unbounded growth is not.
    #
    # NULL-FILENAME GUARD. Without a filename the source document is unidentifiable, and folding
    # two file-less re-confirms into one would collapse genuinely-distinct uploads. So dedupe
    # only fires when the filename is present; a file-less re-confirm falls through and records
    # its own shell — retain-raw for the case we cannot identify.
    #
    # SCOPE. This is the all-markers-declined path only (`resolved` non-empty, every row
    # skipped). `no_values_extracted` (empty extraction) is a FAULT, never deduped — each
    # occurrence is its own event.
    source_doc_filename = report.source_doc.filename if report.source_doc else None
    reconfirm_all = bool(resolved) and len(skip_indices) == len(resolved)
    if reconfirm_all and source_doc_filename is not None:
        prior_shell = (
            db.query(models.LabReport)
            .filter(models.LabReport.user_id == current_user.id,
                    models.LabReport.collected_date == collected_date,
                    models.LabReport.source_doc_filename == source_doc_filename,
                    models.LabReport.zero_row_reason == "all_markers_declined")
            .order_by(models.LabReport.id)
            .first()
        )
        if prior_shell is not None:
            return ConfirmResponse(
                lab_report_id=prior_shell.id,
                result_count=0,
                unmapped=unmapped,
                duplicates=duplicates,
            )

    # Derive each row's confidence ONCE (min over its field_confidences, the per-row
    # rule), then reuse those same values for the row records AND the report's
    # overall_confidence. overall = min(row confidences): it propagates the worst row,
    # consistent with the per-row rule, and — because this gates a user-facing
    # confidence statement — a single bad row must not hide behind a mean. Derived at
    # confirm from stored inputs, not reported by the model (#146).
    row_confidences: list[tuple[ResultItem, str | None, float]] = []
    for r, canonical, _established_unit in resolved:
        # Drop not-expressed sub-fields BEFORE min(). `FieldConfidence` sub-fields are
        # Optional, and `min()` over a list mixing float and None raises TypeError — which
        # would convert the 422 this loosening removes into a 500, one layer deeper and
        # after the report row is built. The filter is load-bearing, not defensive.
        #
        # An all-None object filters to empty and falls to the same 1.0 as an ABSENT
        # object, which is deliberate: both mean "no confidence was expressed", and they
        # should not score differently. Non-empty stays min-over-expressed — §6's rule
        # that overall propagates the WORST expressed confidence, unchanged.
        confidences = (
            [v for v in r.field_confidence.model_dump().values() if v is not None]
            if r.field_confidence else None
        )
        row_confidences.append((r, canonical, min(confidences) if confidences else 1.0))

    # `skip_indices` indexes `resolved`; the write loop below indexes `row_confidences`.
    # They are built from the same source in the same order — asserted, not assumed, because
    # a silent misalignment would skip the wrong row and lose a result without erroring.
    assert len(row_confidences) == len(resolved), "row/confidence lists must stay aligned"
    # A document from which NOTHING could be extracted is a recorded event, not a 500. This
    # previously tripped `assert row_confidences`, which raised before `db.commit()` — so an
    # unparseable upload (a graph or chart PDF with no results table) left no trace whatever,
    # and could not afterwards be told apart from a correctly-declined repeat. It is now stored
    # with `zero_row_reason='no_values_extracted'` and surfaced as a fault.
    # `overall_confidence` is 0.0 in that case and is NOT ambiguous the way #146's silent 0.0
    # was: `zero_row_reason` states why, so an omitted field and a genuine zero are distinct.
    overall_confidence = min((conf for _, _, conf in row_confidences), default=0.0)

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
        source_doc_filename=source_doc_filename,
        page_count=report.source_doc.page_count if report.source_doc else None,
        overall_confidence=overall_confidence,
        extracted_at=report.extraction.extracted_at,
    )
    db.add(lab_report)
    db.flush()  # get lab_report.id before inserting results

    written = 0
    for idx, (r, canonical, confidence) in enumerate(row_confidences):
        if idx in skip_indices:
            continue  # collision reported in `duplicates`; the series stays single-valued
        written += 1
        db.add(models.LabResult(
            lab_report_id=lab_report.id,
            marker_name_raw=r.marker_name_raw,
            # marker_canonical is nullable (#58) — an unmapped marker stores no
            # placeholder; `unmapped` in the response is the actual signal for
            # "needs a human bind/declare".
            marker_canonical=canonical,
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

    # Persist WHY nothing landed, so the two zero-row cases stay distinguishable after the fact.
    # Without this the results list could only filter on row count, which would hide a fault
    # (nothing extractable) exactly as readily as a repeat (everything already stored).
    if written == 0:
        lab_report.zero_row_reason = (
            "all_markers_declined" if resolved else "no_values_extracted"
        )

    db.commit()

    return ConfirmResponse(
        lab_report_id=lab_report.id,
        result_count=written,          # rows WRITTEN, not submitted — a skipped collision differs
        unmapped=unmapped,
        duplicates=duplicates,
    )
