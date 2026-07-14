"""Seed exercise_region_tags + laterality from the proposal reference
(DECISIONS_LOG #NEXT).

Mirrors the labs extract -> confirm -> canonicalise flow: `reference/
exercise_region_tags_v0.json` is the LLM-PROPOSED map; a human confirms it, then
this seeder resolves each title to a Hevy template id and upserts the tags.

Fail-closed (G1): a region_key with no matching taxonomy Region aborts the run —
an orphan is NEVER written. Idempotent: re-running upserts the same rows.

Re-runnable CLI:
    python backend/seed_exercise_region_tags.py <user_id>            # seed as llm_proposed
    python backend/seed_exercise_region_tags.py <user_id> --confirm  # stamp human_confirmed + confirmed_at
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

import models
from engine import taxonomy
from hevy_templates import resolve_exercise

logger = logging.getLogger(__name__)

_PROPOSAL_PATH = Path(__file__).resolve().parent / "reference" / "exercise_region_tags_v0.json"


class OrphanRegionKeyError(Exception):
    """A proposed region_key does not resolve to a taxonomy Region — fail closed."""


def load_proposal(path: Path = _PROPOSAL_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _validate_fail_closed(proposal: dict) -> None:
    """G1: every region_key must resolve to a Region in engine/taxonomy.py."""
    orphans = []
    for entry in proposal.get("tags", []):
        for r in entry.get("regions", []):
            if taxonomy.by_key(r["key"]) is None:
                orphans.append((entry["title"], r["key"]))
    if orphans:
        raise OrphanRegionKeyError(
            f"Refusing to seed — {len(orphans)} orphan region_key(s): {orphans}"
        )


def seed_tags(
    db: Session,
    user_id: int,
    *,
    proposal: dict | None = None,
    confirm: bool = False,
) -> dict:
    """Upsert tags + laterality for one user's resolved templates.

    `confirm=True` overrides the per-row `source` to 'human_confirmed' and stamps
    `confirmed_at` — the authoritative-confirmation step. Otherwise the proposal's
    `source` (default 'llm_proposed') is written with confirmed_at NULL.
    """
    proposal = proposal or load_proposal()
    _validate_fail_closed(proposal)
    default_source = proposal.get("_meta", {}).get("source", "llm_proposed")
    now = datetime.now(timezone.utc)

    resolved = written = unresolved = no_pattern = 0
    unresolved_titles: list[str] = []

    def _apply_template_meta(tid: str, laterality) -> None:
        """Laterality + three-state adjudication live on the template — never
        assigned by `_upsert_template`, so a resync preserves them. adjudicated_at
        is stamped ONLY on --confirm: adjudicated_at NOT NULL ⟺ human-confirmed
        adjudication (DECISIONS_LOG #76)."""
        tmpl = db.get(models.HevyExerciseTemplate, tid)
        if tmpl is None:
            return
        if laterality is not None:
            tmpl.laterality = laterality
        if confirm:
            tmpl.adjudicated_at = now

    # Tagged entries: write region rows + stamp template meta.
    for entry in proposal.get("tags", []):
        title = entry["title"]
        tid = resolve_exercise(db, title, user_id)
        if tid is None:
            unresolved += 1
            unresolved_titles.append(title)
            continue
        resolved += 1
        _apply_template_meta(tid, entry.get("laterality"))

        for r in entry.get("regions", []):
            row = db.get(models.ExerciseRegionTag, (tid, r["key"]))
            if row is None:
                row = models.ExerciseRegionTag(
                    hevy_exercise_template_id=tid, region_key=r["key"]
                )
                db.add(row)
            row.role = r.get("role", "primary")
            row.taxonomy_version = taxonomy.TAXONOMY_VERSION
            row.source = "human_confirmed" if confirm else default_source
            row.confirmed_at = now if confirm else None
            written += 1

    # No-pattern entries: adjudicated with ZERO region rows (the movement
    # demonstrates no screenable taxonomy region). Only meaningful once
    # human-confirmed, so they persist only on --confirm.
    for entry in proposal.get("no_pattern", []):
        title = entry["title"]
        tid = resolve_exercise(db, title, user_id)
        if tid is None:
            unresolved += 1
            unresolved_titles.append(title)
            continue
        resolved += 1
        if confirm:
            _apply_template_meta(tid, entry.get("laterality"))
            no_pattern += 1

    db.commit()
    summary = {
        "user_id": user_id,
        "titles_resolved": resolved,
        "titles_unresolved": unresolved,
        "tags_written": written,
        "no_pattern_adjudicated": no_pattern,
        "confirmed": confirm,
        "unresolved_titles": unresolved_titles,
    }
    logger.info("seed_exercise_region_tags: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print("usage: python backend/seed_exercise_region_tags.py <user_id> [--confirm]")
        raise SystemExit(2)
    uid = int(sys.argv[1])
    do_confirm = "--confirm" in sys.argv[2:]

    from database import SessionLocal

    _db = SessionLocal()
    try:
        print(seed_tags(_db, uid, confirm=do_confirm))
    finally:
        _db.close()
