"""
latest_lab_results(user_id, db) -> list[LabRow]

Shared partition query for both lab reads (current_state's context-builder
feed, and any future GET /labs/results consumer): one row per real-world
marker, keyed by COALESCE(marker_canonical, marker_name_raw) — latest by
collected_date, then id, wins.

Query-only, no schema. Canonicalisation happens once, at /labs/confirm write
time (#58) plus the backfill rider for vocab bumps — this helper trusts the
stored marker_canonical and never re-resolves raw names (that would duplicate
canonicalisation and drift from stored state).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

import models


@dataclass
class LabRow:
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
    computed_flag: str | None
    is_derived: bool
    collected_date: date


def latest_lab_results(user_id: int, db: Session) -> list[LabRow]:
    marker_key = func.coalesce(models.LabResult.marker_canonical, models.LabResult.marker_name_raw)

    ranked = (
        db.query(
            models.LabResult,
            models.LabReport.collected_date.label("collected_date"),
            func.row_number()
            .over(
                partition_by=marker_key,
                order_by=(models.LabReport.collected_date.desc(), models.LabResult.id.desc()),
            )
            .label("rn"),
        )
        .join(models.LabReport, models.LabReport.id == models.LabResult.lab_report_id)
        .filter(models.LabReport.user_id == user_id)
        .subquery()
    )

    LatestResult = aliased(models.LabResult, ranked)
    rows = (
        db.query(LatestResult, ranked.c.collected_date)
        .filter(ranked.c.rn == 1)
        .order_by(LatestResult.marker_canonical.is_(None), LatestResult.marker_name_raw)
        .all()
    )

    return [
        LabRow(
            marker_name_raw=lr.marker_name_raw,
            marker_canonical=lr.marker_canonical,
            value_num=lr.value_num,
            value_operator=lr.value_operator,
            value_qualitative=lr.value_qualitative,
            unit_canonical=lr.unit_canonical,
            ref_low=lr.ref_low,
            ref_high=lr.ref_high,
            ref_low_exclusive=lr.ref_low_exclusive,
            ref_high_exclusive=lr.ref_high_exclusive,
            lab_flag=lr.lab_flag,
            computed_flag=lr.computed_flag,
            is_derived=lr.is_derived,
            collected_date=collected_date,
        )
        for lr, collected_date in rows
    ]


@dataclass
class MarkerPair:
    """Newest + the one before it, for a single marker. `prior` is None on a
    first-ever observation — the interpretation producer emits `delta: null`
    there rather than inventing a comparison."""
    current: LabRow
    prior: LabRow | None


def _to_lab_row(lr, collected_date: date) -> LabRow:
    return LabRow(
        marker_name_raw=lr.marker_name_raw,
        marker_canonical=lr.marker_canonical,
        value_num=lr.value_num,
        value_operator=lr.value_operator,
        value_qualitative=lr.value_qualitative,
        unit_canonical=lr.unit_canonical,
        ref_low=lr.ref_low,
        ref_high=lr.ref_high,
        ref_low_exclusive=lr.ref_low_exclusive,
        ref_high_exclusive=lr.ref_high_exclusive,
        lab_flag=lr.lab_flag,
        computed_flag=lr.computed_flag,
        is_derived=lr.is_derived,
        collected_date=collected_date,
    )


def marker_series(user_id: int, db: Session) -> dict[str, MarkerPair]:
    """Newest + prior per marker, keyed by COALESCE(marker_canonical,
    marker_name_raw) — the interpretation producer's read seam.

    Same partition as `latest_lab_results`, widened to `rn <= 2`.
    `latest_lab_results` is deliberately left untouched: it feeds the
    context_builder path guarded by the #43/#80 parity assertion, and this
    read wants two rows where that one wants exactly one. The partition
    expression is therefore duplicated rather than extracted — if the ordering
    rule ever changes, BOTH must move together.
    """
    marker_key = func.coalesce(models.LabResult.marker_canonical, models.LabResult.marker_name_raw)

    ranked = (
        db.query(
            models.LabResult,
            models.LabReport.collected_date.label("collected_date"),
            marker_key.label("marker_key"),
            func.row_number()
            .over(
                partition_by=marker_key,
                order_by=(models.LabReport.collected_date.desc(), models.LabResult.id.desc()),
            )
            .label("rn"),
        )
        .join(models.LabReport, models.LabReport.id == models.LabResult.lab_report_id)
        .filter(models.LabReport.user_id == user_id)
        .subquery()
    )

    RankedResult = aliased(models.LabResult, ranked)
    rows = (
        db.query(RankedResult, ranked.c.collected_date, ranked.c.marker_key, ranked.c.rn)
        .filter(ranked.c.rn <= 2)
        .order_by(ranked.c.marker_key, ranked.c.rn)
        .all()
    )

    series: dict[str, MarkerPair] = {}
    for lr, collected_date, key, rn in rows:
        row = _to_lab_row(lr, collected_date)
        if rn == 1:
            series[key] = MarkerPair(current=row, prior=None)
        elif key in series:
            series[key].prior = row
    return series


def find_marker(labs: list[LabRow], message: str) -> LabRow | None:
    """Explicit single-marker on-ask detection (#60): does `message` name a
    marker the user already has on file? Operates on an already-fetched `labs`
    list (chat.py already computed `state.labs` this request via
    `latest_lab_results` — no need for a second DB round-trip).

    Word-boundary, case-insensitive match against the report's own raw name
    (what a user would actually type, e.g. "testosterone") or the canonical id
    with underscores read as spaces. First match wins — a small heuristic for
    "the user named a marker", not a general NLU intent parser.
    """
    msg_lower = message.lower()
    for row in labs:
        candidates = {row.marker_name_raw.lower()}
        if row.marker_canonical:
            candidates.add(row.marker_canonical.replace("_", " "))
        for phrase in candidates:
            if re.search(rf"\b{re.escape(phrase)}\b", msg_lower):
                return row
    return None
