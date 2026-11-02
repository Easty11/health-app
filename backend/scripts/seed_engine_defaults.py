"""Seed engine-tier DEFAULT PROPOSALS from active injuries — the operator-run half of "Engine blocks
are rows" (Q182, GH#539). Dry-run first; Code never runs it against production.

For each ACTIVE injury, `engine.engine_defaults` derives which regions the three in-code block maps
(`_ACUTE_TISSUE_BLOCKS`, `_RADICULAR_BLOCKS`, `_RA_FLARE_BLOCKS`) block for it, and this script
writes ONE proposal per (injury, region key):

    scope      {"tier": "engine", "region_keys": [<one key>], "side": <the injury's side, absent
                when bilateral>, "text": "<map name>: <body part> → <region label> (engine default)"}
    kind       "block"
    parent_key the injury's key;  exit {"with_parent": true}
    review_by  --review-by (required; an ISO date, today or later)
    status     "proposed";  asserted_by null;  source "system"

A PROPOSAL BLOCKS NOTHING (#342). The operator confirms each row on the Injuries page, or declines it
(`POST /knowledge/constraints/{id}/resolve` with a basis). Nothing is confirmed here and the
injury rows are never modified.

IDEMPOTENT on (parent_key, region key) across ALL engine constraint rows, active or not: an existing
cover is skipped with its reason, and a RESOLVED one — a declined default — is never re-proposed
(the #340 seed-resurrection lesson). A planned key already held by an active row of another shape is
a CONFLICT: reported, never written. The injury write path proposes the same rows for injuries it
writes; this script is for the rows that path never saw (written straight to the ORM, or before it
existed).

ADVISORY-CAP OVERLAP. A limit on a region still being trained is an advisory cap, never an engine
block (#344). Advisory rows carry no region keys, so an overlap cannot be computed — it is SURFACED:
beside each planned row, any active advisory `cap` row on the same injury (parent_key) or naming the
same body part is printed, for the operator to weigh at confirm time.

ONE TRANSACTION. `--confirm` stages every planned row through the validated write path
(`routers.knowledge._stage_upsert_entry`) and commits once; any failure rolls the whole set back.

Usage — INSIDE the backend container (cwd /app, the venv interpreter):
    /opt/venv/bin/python scripts/seed_engine_defaults.py <user_id> --review-by YYYY-MM-DD --dry-run
    /opt/venv/bin/python scripts/seed_engine_defaults.py <user_id> --review-by YYYY-MM-DD --confirm
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
from engine import engine_defaults  # noqa: E402
from load_metrics import _local_day  # noqa: E402  operator-local (AEST) day, Q42
from routers.knowledge import KnowledgeEntryIn, _stage_upsert_entry  # noqa: E402

SEED_NOTE = "engine default seeded for {parent} by scripts/seed_engine_defaults.py"


def advisory_cap_overlaps(db, user_id: int, injury_key: str, body_part: str) -> list[dict[str, Any]]:
    """Active advisory `cap` rows on this injury or naming its body part. Read-only; whole-word match
    on the body part so `knee` does not catch `kneeling`."""
    rows = db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id, type="constraint", active=True).all()
    word = re.compile(rf"\b{re.escape(body_part)}\b", re.I) if body_part else None
    out = []
    for r in rows:
        v = r.value or {}
        scope = v.get("scope") or {}
        if scope.get("tier") != "advisory" or v.get("kind") != "cap":
            continue
        same_parent = v.get("parent_key") == injury_key
        names_part = bool(word and word.search(str(scope.get("text") or "")))
        if same_parent or names_part:
            out.append({"key": r.key, "id": r.id, "text": scope.get("text"),
                        "why": "same injury" if same_parent else "names the body part"})
    return out


def plan_seed(db, user_id: int, review_by: date) -> dict[str, Any]:
    """Resolve every active injury into proposals. Writes nothing."""
    injuries = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=user_id, type="injury", active=True)
        .order_by(models.UserKnowledgeEntry.id)
        .all()
    )
    cover = engine_defaults._existing_engine_cover(db, user_id)
    active_keys = engine_defaults._active_keys(db, user_id)

    per_injury, planned, skipped, conflicts = [], [], [], []
    for inj in injuries:
        val = inj.value or {}
        sub = engine_defaults.plan_engine_defaults(
            db, user_id, inj.key, val, review_by, cover=cover, active_keys=active_keys,
        )
        norm = engine_defaults._norm(val)
        per_injury.append({
            "entry_id": inj.id, "key": inj.key, "body_part": norm["body_part"], "side": norm["side"],
            "signal_type": norm["signal_type"], "ra_flare": norm["ra_flare"],
            "planned": len(sub["planned"]), "skipped": len(sub["skipped"]),
        })
        overlaps = advisory_cap_overlaps(db, user_id, inj.key, norm["body_part"]) if sub["planned"] else []
        for p in sub["planned"]:
            p["advisory_cap_overlaps"] = overlaps
            planned.append(p)
        skipped.extend(sub["skipped"])
        conflicts.extend(sub["conflicts"])
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
        print(f"  #{inj['entry_id']} {inj['key']}: {inj['body_part'] or '(no body part)'} / "
              f"{inj['side']} / {inj['signal_type']}{' / ra_flare' if inj['ra_flare'] else ''}"
              f" — {inj['planned']} planned, {inj['skipped']} already covered")
    print(f"PLANNED ({len(plan['planned'])}) — engine / block / with_parent / proposed / asserted_by null:")
    for p in plan["planned"]:
        replaces = f"   (supersedes stale-sided proposal #{p['replaces']})" if p.get("replaces") else ""
        print(f"  {p['parent_key']} → {p['region_key']}, {p['side'] or 'bilateral'}   [{' + '.join(p['maps'])}]{replaces}")
        for o in p["advisory_cap_overlaps"]:
            print(f"      NOTE advisory cap ({o['why']}): {o['key']} — {o['text']}")
    print(f"SKIPPED ({len(plan['skipped'])}):")
    for s in plan["skipped"]:
        print(f"  {s['parent_key']} → {s['region_key']} — {s['why']}")
    print(f"CONFLICTS ({len(plan['conflicts'])}) — never written:")
    for c in plan["conflicts"]:
        print(f"  {c['key']} is held by active row #{c['held_by']} ({c['parent_key']} → {c['region_key']})")


def main(argv: list[str], db_factory=None) -> int:
    usage = ("usage: scripts/seed_engine_defaults.py <user_id> --review-by YYYY-MM-DD "
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
        print(f"WROTE {len(ids)} proposal(s): {ids}")
        print(f"constraint rows after: {count_constraints(db, uid)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
