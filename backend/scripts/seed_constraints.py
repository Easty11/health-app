"""Seed typed `constraint` rows from active injuries' `restrictions[]` — S6 of the typed-entries
brief (#342). Operator-run; dry-run first; Code never runs it against production.

For each ACTIVE injury, each `restrictions[]` string becomes ONE advisory constraint:

    scope      {"tier": "advisory", "text": <the restriction, verbatim>}
    kind       "block"
    parent_key the injury's key;  exit {"with_parent": true}   (it ends when the injury resolves)
    review_by  --review-by (required; an ISO date, today or later)
    status     "confirmed";  asserted_by "user"   (the operator running this IS the confirmation)

ENGINE-TIER ROWS ARE NEVER SEEDED. Restriction strings are prose; an engine constraint comes only
from an explicit operator write. `injury.restrictions[]` is READ, never modified.

IDEMPOTENT on (parent_key, scope.text) across ALL constraint rows, active or not: an existing
match is skipped, and a RESOLVED match is never re-created (the #340 seed-resurrection lesson —
a row the operator retired stays retired). Also skipped and reported: the literal `ra_flare` token,
which is an engine signal on the injury (`selection.gather_active_injuries`), not an instruction;
and any planned key already held by an active row of another shape (reported as a conflict,
never written).

ONE TRANSACTION. `--confirm` stages every planned row through the validated write path
(`routers.knowledge._stage_upsert_entry`) and commits once; any failure rolls the whole set back.

Usage — INSIDE the backend container (cwd /app, the venv interpreter):
    /opt/venv/bin/python scripts/seed_constraints.py <user_id> --review-by YYYY-MM-DD --dry-run
    /opt/venv/bin/python scripts/seed_constraints.py <user_id> --review-by YYYY-MM-DD --confirm
Exactly one of --dry-run / --confirm; there is no default write.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models  # noqa: E402
from load_metrics import _local_day  # noqa: E402  operator-local (AEST) day, Q42
from routers.knowledge import KnowledgeEntryIn, _stage_upsert_entry  # noqa: E402

ENGINE_TOKENS = ("ra_flare",)
SEED_NOTE = "seeded from {parent}.restrictions by scripts/seed_constraints.py"


def _slug(text: str) -> str:
    return "_".join(re.findall(r"[a-z0-9]+", text.lower()))[:60].rstrip("_") or "restriction"


def plan_seed(db, user_id: int, review_by: date) -> dict[str, Any]:
    """Resolve every active injury's restrictions into a plan. Writes nothing."""
    injuries = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=user_id, type="injury", active=True)
        .order_by(models.UserKnowledgeEntry.id)
        .all()
    )
    existing = db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id, type="constraint").all()
    seen = {((e.value or {}).get("parent_key"), ((e.value or {}).get("scope") or {}).get("text")):
            ("active" if e.active else "resolved/superseded", e.id) for e in existing}
    active_keys = {e.key: e for e in
                   db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id, active=True).all()}

    per_injury, planned, skipped, conflicts = [], [], [], []
    used_keys: set[str] = set()
    for inj in injuries:
        restrictions = [str(r) for r in (inj.value or {}).get("restrictions") or []]
        per_injury.append({"entry_id": inj.id, "key": inj.key, "restrictions": restrictions})
        for text in restrictions:
            if text.strip() in ENGINE_TOKENS:
                skipped.append({"parent_key": inj.key, "text": text, "why": "engine token, not an instruction"})
                continue
            hit = seen.get((inj.key, text))
            if hit is not None:
                skipped.append({"parent_key": inj.key, "text": text,
                                "why": f"already seeded ({hit[0]}, id {hit[1]})"})
                continue
            base = f"constraint_{inj.key}_{_slug(text)}"
            key, n = base, 2
            while key in used_keys:
                key, n = f"{base}_{n}", n + 1
            if key in active_keys:
                conflicts.append({"key": key, "held_by": active_keys[key].id,
                                  "parent_key": inj.key, "text": text})
                continue
            used_keys.add(key)
            planned.append({
                "key": key,
                "parent_key": inj.key,
                "value": {
                    "scope": {"tier": "advisory", "text": text},
                    "kind": "block",
                    "parent_key": inj.key,
                    "exit": {"with_parent": True},
                    "review_by": review_by.isoformat(),
                    "status": "confirmed",
                    "asserted_by": "user",
                },
            })
    return {"user_id": user_id, "review_by": review_by.isoformat(), "injuries": per_injury,
            "planned": planned, "skipped": skipped, "conflicts": conflicts}


def apply_seed(db, plan: dict[str, Any]) -> list[int]:
    """Write the plan in ONE transaction through the validated write path. Returns new ids."""
    ids: list[int] = []
    try:
        for p in plan["planned"]:
            row = _stage_upsert_entry(plan["user_id"], KnowledgeEntryIn(
                type="constraint", key=p["key"], value=p["value"], source="system",
                notes=SEED_NOTE.format(parent=p["parent_key"]),
            ), db)
            ids.append(row.id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ids


def count_constraints(db, user_id: int) -> dict[str, int]:
    rows = db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id, type="constraint").all()
    return {"active": sum(1 for r in rows if r.active), "total": len(rows)}


def print_plan(plan: dict[str, Any]) -> None:
    print(f"user {plan['user_id']} — review_by {plan['review_by']}")
    print(f"active injuries: {len(plan['injuries'])}")
    for inj in plan["injuries"]:
        print(f"  #{inj['entry_id']} {inj['key']}: {len(inj['restrictions'])} restriction(s)")
        for r in inj["restrictions"]:
            print(f"      - {r}")
    print(f"PLANNED ({len(plan['planned'])}) — advisory / block / with_parent / confirmed / user:")
    for p in plan["planned"]:
        print(f"  {p['key']}  <- {p['parent_key']}: {p['value']['scope']['text']}")
    print(f"SKIPPED ({len(plan['skipped'])}):")
    for s in plan["skipped"]:
        print(f"  {s['parent_key']}: {s['text']} — {s['why']}")
    print(f"CONFLICTS ({len(plan['conflicts'])}) — never written:")
    for c in plan["conflicts"]:
        print(f"  {c['key']} is held by active row #{c['held_by']} ({c['parent_key']}: {c['text']})")


def main(argv: list[str], db_factory=None) -> int:
    usage = ("usage: scripts/seed_constraints.py <user_id> --review-by YYYY-MM-DD "
             "(--dry-run | --confirm)")
    args = list(argv)
    try:
        uid = int(args.pop(0))
        review_raw = args[args.index("--review-by") + 1]
    except (IndexError, ValueError):
        print(usage)
        return 2
    do_dry, do_confirm = "--dry-run" in args, "--confirm" in args
    if do_dry == do_confirm:
        print("exactly one of --dry-run / --confirm is required — there is no default write\n" + usage)
        return 2
    try:
        review_by = date.fromisoformat(review_raw)
    except ValueError:
        print(f"--review-by must be an ISO date (YYYY-MM-DD), got {review_raw!r}")
        return 2
    if review_by < _local_day():
        print(f"--review-by {review_by} is in the past — every seeded row would be due for review at once")
        return 2

    if db_factory is None:
        from database import SessionLocal
        db_factory = SessionLocal
    db = db_factory()
    try:
        plan = plan_seed(db, uid, review_by)
        print_plan(plan)
        before = count_constraints(db, uid)
        print(f"constraint rows before: {before}")
        if do_dry:
            print("DRY RUN — nothing written.")
            return 0
        ids = apply_seed(db, plan)
        print(f"WROTE {len(ids)} row(s): {ids}")
        print(f"constraint rows after: {count_constraints(db, uid)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
