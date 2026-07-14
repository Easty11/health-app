"""Audit exercise-tag coverage over a user's recent Hevy history (DECISIONS_LOG #79).

READ-ONLY. This script never writes: no db.add, no db.commit. It measures, it
does not repair.

The metric is the FALLBACK HIT-RATE — the share of distinct movements in the
window whose templates are untagged and never adjudicated, so
`infer_loaded_regions` falls through to the legacy `_LOADED_KEYWORDS` matcher
(which is wrong on live data: see selection.py). Target: zero.

Keyed on `exercise_template_id`, NEVER on title (DECISIONS_LOG #79). A Hevy
workout carries a snapshot of the title as it was WHEN LOGGED, and Hevy renames
its default templates, so logged titles drift from catalogue titles. A
title-keyed audit reports coverage that the id-keyed join in
`infer_loaded_regions` does not actually deliver — in either direction. The
classification itself is imported from `engine.selection`, not restated here.

    python backend/audit_exercise_tag_coverage.py <user_id> [--days 28] [--strict]

Exit 0 by default (diagnostic). `--strict` exits 1 when any UNTAGGED movement
remains, so this can gate a pipeline later.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

import models
from connectors.hevy import HevyClient
from engine import selection
from hevy_templates import catalogue_titles_by_id, user_hevy_key

logger = logging.getLogger(__name__)

DEFAULT_DAYS = 28


class MissingHevyKeyError(Exception):
    """No Hevy key for this user — a PRECONDITION failure, not a coverage
    result. Without it every window is empty and the audit would report a
    perfect 0% fallback rate over zero movements, which is a lie."""


def _workout_start(w: dict[str, Any]) -> datetime | None:
    """Mirrors context_builder.py:170 — `start_time`, falling back to `created_at`."""
    raw = w.get("start_time") or w.get("created_at") or ""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        logger.warning("unparseable workout timestamp %r — excluding from window", raw)
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def workouts_in_window(workouts: list[dict[str, Any]], days: int,
                       *, now: datetime | None = None) -> list[dict[str, Any]]:
    """The `days`-day trailing window. A workout with no parseable timestamp is
    EXCLUDED — it cannot be shown to fall inside the window."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    kept = []
    for w in workouts or []:
        start = _workout_start(w)
        if start is not None and start >= cutoff:
            kept.append(w)
    return kept


def logged_titles_by_template(workouts: list[dict[str, Any]]) -> dict[str, set[str]]:
    """template_id -> every distinct title it was LOGGED under in the window.

    A set, not a scalar: the same template can appear under several historical
    titles across a window, which is the drift this audit exists to surface.
    """
    out: dict[str, set[str]] = {}
    for w in workouts or []:
        for ex in (w.get("exercises", []) or []):
            tid = ex.get("exercise_template_id")
            if not tid:
                continue
            out.setdefault(tid, set())
            if title := (ex.get("title") or ""):
                out[tid].add(title)
    return out


def audit_coverage(db: Session, workouts: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify every distinct template in `workouts` against the three-state
    coverage rule. Read-only.

    The classification is `selection.classify_coverage` — the SAME function the
    read path uses — so this measures the behaviour rather than a parallel model
    of it.
    """
    logged = logged_titles_by_template(workouts)
    template_ids = set(logged)
    _, classes = selection.classify_coverage(db, template_ids)
    catalogue = catalogue_titles_by_id(db, template_ids)

    movements: dict[str, list[dict[str, Any]]] = {
        selection.COVERAGE_TAGGED: [],
        selection.COVERAGE_ADJUDICATED_NO_PATTERN: [],
        selection.COVERAGE_UNTAGGED: [],
    }
    for tid in sorted(template_ids):
        cat_title = catalogue.get(tid)
        movements[classes[tid]].append({
            "template_id": tid,
            "catalogue_title": cat_title,  # None => template absent from the local catalogue
            "logged_titles": sorted(logged[tid]),
            "title_drift": bool(cat_title) and logged[tid] != {cat_title} and bool(logged[tid]),
        })

    total = len(template_ids)
    untagged = len(movements[selection.COVERAGE_UNTAGGED])
    return {
        "distinct_movements": total,
        "counts": {cls: len(items) for cls, items in movements.items()},
        "movements": movements,
        # Rate over DISTINCT movements, matching the coverage claim. 0.0 on an
        # empty window is vacuous, not clean — the caller reports the count too.
        "fallback_hit_rate": (untagged / total) if total else 0.0,
    }


def _fmt_movement(m: dict[str, Any]) -> str:
    cat = m["catalogue_title"] or "<NOT IN LOCAL CATALOGUE>"
    line = f"    {m['template_id']}  {cat}"
    if m["title_drift"]:
        line += f"\n        logged as: {', '.join(m['logged_titles'])}"
    elif not m["logged_titles"]:
        line += "\n        logged as: <no title on the logged exercise>"
    return line


def render(report: dict[str, Any], *, days: int) -> str:
    counts = report["counts"]
    lines = [
        "",
        f"Exercise-tag coverage — trailing {days} days, keyed on exercise_template_id",
        "=" * 72,
        f"  TAGGED                  {counts[selection.COVERAGE_TAGGED]:>4}",
        f"  ADJUDICATED NO-PATTERN  {counts[selection.COVERAGE_ADJUDICATED_NO_PATTERN]:>4}   (deliberate; not a gap)",
        f"  UNTAGGED                {counts[selection.COVERAGE_UNTAGGED]:>4}   (keyword fallback fires)",
        "-" * 72,
        f"  distinct movements      {report['distinct_movements']:>4}",
        f"  FALLBACK HIT-RATE      {report['fallback_hit_rate'] * 100:>5.1f}%   (target 0)",
        "",
    ]
    if not report["distinct_movements"]:
        lines += ["  No movements in the window — a 0% rate here is vacuous, not clean.", ""]
        return "\n".join(lines)

    titles = {
        selection.COVERAGE_UNTAGGED: "UNTAGGED — keyword fallback fires (the gap)",
        selection.COVERAGE_ADJUDICATED_NO_PATTERN: "ADJUDICATED NO-PATTERN — covered by decision",
        selection.COVERAGE_TAGGED: "TAGGED — authoritative",
    }
    for cls, heading in titles.items():
        items = report["movements"][cls]
        if not items:
            continue
        lines += [f"  {heading}  [{len(items)}]"]
        lines += [_fmt_movement(m) for m in items]
        lines += [""]
    return "\n".join(lines)


async def _fetch_workouts(api_key: str) -> list[dict[str, Any]]:
    return (await HevyClient(api_key).get_all_workouts()).get("workouts", [])


def run(db: Session, user_id: int, *, days: int = DEFAULT_DAYS) -> dict[str, Any]:
    api_key = user_hevy_key(db, user_id)
    if not api_key:
        raise MissingHevyKeyError(
            f"No Hevy API key stored for user {user_id} — cannot audit an empty window."
        )
    workouts = asyncio.run(_fetch_workouts(api_key))
    window = workouts_in_window(workouts, days)
    logger.info(
        "audit_exercise_tag_coverage: %d/%d workouts inside the %d-day window",
        len(window), len(workouts), days,
    )
    return audit_coverage(db, window)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        print("usage: python backend/audit_exercise_tag_coverage.py <user_id> [--days 28] [--strict]")
        raise SystemExit(2)
    uid = int(argv[0])
    strict = "--strict" in argv
    _days = DEFAULT_DAYS
    if "--days" in argv:
        _days = int(argv[argv.index("--days") + 1])

    from database import SessionLocal

    _db = SessionLocal()
    try:
        _report = run(_db, uid, days=_days)
        print(render(_report, days=_days))
    except MissingHevyKeyError as exc:
        logging.error("%s", exc)
        raise SystemExit(1)
    finally:
        _db.close()

    if strict and _report["counts"][selection.COVERAGE_UNTAGGED] > 0:
        logging.error(
            "--strict: %d untagged movement(s) in the window — fallback still fires.",
            _report["counts"][selection.COVERAGE_UNTAGGED],
        )
        raise SystemExit(1)
