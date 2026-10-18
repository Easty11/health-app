"""Seed exercise_region_tags + laterality from the proposal reference
(DECISIONS_LOG #74).

Mirrors the labs extract -> confirm -> canonicalise flow: `reference/
exercise_region_tags_v0.json` is the LLM-PROPOSED map; a human confirms it, then
this seeder resolves each entry to a Hevy template id and upserts the tags.

Three entry forms (#337):
  * title-keyed  — `{"title": ...}` resolved via `resolve_exercise` (catalogue title, #79).
  * id-keyed     — `{"template_id": ..., "title": <label only>}`: the id IS the key; the
                   title is never resolved. Must be visible to the user (`_visible_to`).
  * sided variant — `sided_variants[]`: `{"template_id", "title", "parent_template_id"}`
                   and NO regions. A custom L/R template gets a new id and so loses its
                   parent's tags; it inherits them through this EXPLICIT, operator-confirmed
                   mapping — never by stripping " L"/" R" off titles at runtime (titles drift,
                   #79). The variant mirrors its parent exactly: tagged -> same regions+roles
                   (rows the parent lacks are removed), no-pattern -> no-pattern.

Side (Q27 v1): any `tags[]` or `sided_variants[]` entry may carry `"side": "left" | "right"`. It is
written to `exercise_region_tags.side` on every row that entry plans (a variant stamps the rows it
inherits from its parent). Side is NEVER derived from a title; it is the declared value only. An
entry without `side` leaves the column untouched - the seeder never clears it. `--dry-run` lists the
rows whose side would change as `pending_side_updates`.

Fail-closed (G1): a region_key with no matching taxonomy Region aborts the run —
an orphan is NEVER written. So does a malformed variant (regions on it, a missing
parent id, or a variant-of-a-variant) and a template id claimed by two entries.
Idempotent: re-running upserts the same rows.

Plan, then write: every entry is resolved into one plan first; `--dry-run` prints
that plan (resolved ids, regions, inheritance source) and writes NOTHING. A plain
run is NOT a dry run — it writes `llm_proposed` rows, and Rule 1 counts them.

Preflight (#338), reported on every run and printed by --dry-run:
  * `near_twins` — a catalogue id sharing the first 8 characters of an id the reference
    names (Q145's `b4bab549-…4166…` vs `…4186…`), so a typo'd-but-live twin is surfaced,
    never silently mapped.
  * `unconfirmed_existing` — tag rows already in the table that are NOT human-confirmed
    (a plain run writes `llm_proposed`, and Rule 1 counts them). `--confirm` re-stamps the
    ones this run plans; `--prune-unconfirmed` (only with `--confirm`) DELETES the rest
    (`prune` lists them). Opt-in: which to do is an operator ruling (Q179).

Re-runnable CLI:
    python backend/seed_exercise_region_tags.py <user_id> --dry-run  # resolve + print, no writes
    python backend/seed_exercise_region_tags.py <user_id>            # seed as llm_proposed
    python backend/seed_exercise_region_tags.py <user_id> --confirm  # stamp human_confirmed + confirmed_at
    python backend/seed_exercise_region_tags.py <user_id> --confirm --prune-unconfirmed
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

import models
from engine import taxonomy
from hevy_templates import _visible_to, resolve_exercise

logger = logging.getLogger(__name__)

SIDES = ("left", "right")

_PROPOSAL_PATH = Path(__file__).resolve().parent / "reference" / "exercise_region_tags_v0.json"


class OrphanRegionKeyError(Exception):
    """A proposed region_key does not resolve to a taxonomy Region — fail closed."""


class MalformedProposalError(Exception):
    """A structurally invalid proposal (bad sided variant, duplicate template id) —
    fail closed before anything is resolved or written."""


class EmptyTemplateStoreError(Exception):
    """`hevy_exercise_templates` is empty — a PRECONDITION failure, not a data
    problem (DECISIONS_LOG #77). Every title would resolve to None and the seed
    would report "N unresolved" and exit 0, masking an unpopulated substrate.
    Run `sync_hevy_templates.py` first."""


def load_proposal(path: Path = _PROPOSAL_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _label(entry: dict) -> str:
    return entry.get("title") or entry.get("template_id") or "<unnamed>"


def _validate_fail_closed(proposal: dict) -> None:
    """G1: every region_key must resolve to a Region in engine/taxonomy.py; sided
    variants carry a parent id and no regions of their own, and never chain."""
    orphans = []
    for entry in proposal.get("tags", []):
        for r in entry.get("regions", []):
            if taxonomy.by_key(r["key"]) is None:
                orphans.append((_label(entry), r["key"]))
    if orphans:
        raise OrphanRegionKeyError(
            f"Refusing to seed — {len(orphans)} orphan region_key(s): {orphans}"
        )

    problems = []
    bad_sides = [(_label(e), e["side"]) for key in ("tags", "sided_variants")
                 for e in proposal.get(key, []) if "side" in e and e["side"] not in SIDES]
    if bad_sides:
        problems.append(f"side must be one of {list(SIDES)}: {bad_sides}")
    variants = proposal.get("sided_variants", [])
    variant_ids = {v.get("template_id") for v in variants}
    for v in variants:
        if not v.get("template_id"):
            problems.append(f"sided variant {_label(v)!r} has no template_id")
        if not v.get("parent_template_id"):
            problems.append(f"sided variant {_label(v)!r} has no parent_template_id")
        if v.get("regions"):
            problems.append(f"sided variant {_label(v)!r} carries its own regions — it inherits")
        if v.get("parent_template_id") in variant_ids:
            problems.append(f"sided variant {_label(v)!r} names another variant as parent")
    ids = [e["template_id"] for key in ("tags", "no_pattern", "sided_variants")
           for e in proposal.get(key, []) if e.get("template_id")]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        problems.append(f"template_id(s) claimed by more than one entry: {dupes}")
    if problems:
        raise MalformedProposalError("Refusing to seed — " + "; ".join(problems))


def _resolve_entry(db: Session, entry: dict, user_id: int) -> str | None:
    """id-keyed entries resolve by id (visible to this user); title-keyed by catalogue title."""
    tid = entry.get("template_id")
    if tid:
        Template = models.HevyExerciseTemplate
        found = (
            db.query(Template.id)
            .filter(Template.id == tid)
            .filter(_visible_to(user_id))
            .first()
        )
        return found[0] if found else None
    return resolve_exercise(db, entry["title"], user_id)


def _db_state(db: Session, tid: str) -> tuple[str, list[dict]] | None:
    """A template's CURRENT adjudicated state: ('tagged'|'no_pattern', regions), or None
    if it is not human-adjudicated (an unconfirmed parent is not a source to inherit)."""
    tmpl = db.get(models.HevyExerciseTemplate, tid)
    if tmpl is None or tmpl.adjudicated_at is None:
        return None
    rows = db.query(models.ExerciseRegionTag).filter_by(hevy_exercise_template_id=tid).all()
    regions = [{"key": r.region_key, "role": r.role} for r in rows]
    return ("tagged" if regions else "no_pattern"), regions


def build_plan(db: Session, user_id: int, proposal: dict) -> dict:
    """Resolve every entry into `{tid: {...}}` without writing. Direct entries first, then
    sided variants against the plan (a parent set in this same run) or, failing that, the
    parent's current adjudicated DB state."""
    plan: dict[str, dict] = {}
    unresolved: list[str] = []

    def _direct(entry: dict, kind: str) -> None:
        tid = _resolve_entry(db, entry, user_id)
        if tid is None:
            unresolved.append(_label(entry))
            return
        if tid in plan:
            raise MalformedProposalError(
                f"Refusing to seed — {tid} is resolved by both {plan[tid]['label']!r} "
                f"and {_label(entry)!r}"
            )
        plan[tid] = {
            "label": _label(entry), "kind": kind, "via": None,
            "regions": [{"key": r["key"], "role": r.get("role", "primary")}
                        for r in entry.get("regions", [])] if kind == "tagged" else [],
            "laterality": entry.get("laterality"),
            "side": entry.get("side"),
        }

    for entry in proposal.get("tags", []):
        _direct(entry, "tagged")
    for entry in proposal.get("no_pattern", []):
        _direct(entry, "no_pattern")

    for v in proposal.get("sided_variants", []):
        tid = _resolve_entry(db, v, user_id)
        if tid is None:
            unresolved.append(_label(v))
            continue
        if tid in plan:
            raise MalformedProposalError(
                f"Refusing to seed — {tid} is both a sided variant and a direct entry"
            )
        parent = v["parent_template_id"]
        if parent in plan:
            kind, regions = plan[parent]["kind"], plan[parent]["regions"]
        else:
            state = _db_state(db, parent)
            if state is None:
                unresolved.append(f"{_label(v)} (parent {parent} not adjudicated)")
                continue
            kind, regions = state
        plan[tid] = {
            "label": _label(v), "kind": kind, "via": parent,
            "regions": [dict(r) for r in regions], "laterality": v.get("laterality"),
            "side": v.get("side"),
        }

    return {"plan": plan, "unresolved": unresolved}


def _near_twins(db: Session, proposal: dict) -> list[dict]:
    """Catalogue ids that share an 8-char prefix with a referenced id but are not it."""
    refs = {e[k] for key in ("tags", "no_pattern", "sided_variants")
            for e in proposal.get(key, [])
            for k in ("template_id", "parent_template_id") if e.get(k)}
    Template = models.HevyExerciseTemplate
    out = []
    for ref in sorted(refs):
        if len(ref) < 9:          # 8-char Hevy default ids have no room for a twin
            continue
        for tid, title in (db.query(Template.id, Template.title)
                           .filter(Template.id.like(ref[:8] + "%"), Template.id != ref).all()):
            out.append({"referenced": ref, "twin": tid, "twin_title": title})
    return out


def _unconfirmed_rows(db: Session) -> list[dict]:
    """Every tag row not human-confirmed, with its template title (for the report)."""
    Tag, Template = models.ExerciseRegionTag, models.HevyExerciseTemplate
    rows = (
        db.query(Tag, Template.title)
        .outerjoin(Template, Template.id == Tag.hevy_exercise_template_id)
        .filter((Tag.source != "human_confirmed") | (Tag.confirmed_at.is_(None)))
        .all()
    )
    return [{"template_id": t.hevy_exercise_template_id, "title": title,
             "region_key": t.region_key, "role": t.role, "source": t.source}
            for t, title in rows]


def _validate_plan_keys(plan: dict) -> None:
    """Every region_key the PLAN would write must resolve. `_validate_fail_closed` covers the
    reference; this covers a sided variant that inherits a parent's current DB state, which can
    carry a key the taxonomy has since retired (Q27 v1: `shoulder_er_ir`)."""
    orphans = sorted({(p["label"], r["key"]) for p in plan.values() for r in p["regions"]
                      if taxonomy.by_key(r["key"]) is None})
    if orphans:
        raise OrphanRegionKeyError(
            f"Refusing to seed — the plan would write {len(orphans)} unresolved region_key(s): {orphans}"
        )


def _pending_deletions(db: Session, plan: dict) -> list[dict]:
    """Tag rows on a PLANNED template whose region_key the plan does not carry. The reference is
    authoritative for the templates it names: with `--confirm` these are deleted (a template
    retagged from key A to key B ends with only B). Any `source`: a row's `human_confirmed`
    stamp does not protect it, because the writer of every row is this seeder (checked: no
    other code path inserts `exercise_region_tags`)."""
    Tag = models.ExerciseRegionTag
    out = []
    for tid, p in plan.items():
        keep = {r["key"] for r in p["regions"]}
        for row in db.query(Tag).filter_by(hevy_exercise_template_id=tid).all():
            if row.region_key not in keep:
                out.append({"template_id": tid, "label": p["label"], "region_key": row.region_key,
                            "role": row.role, "source": row.source, "via": p["via"]})
    return out


def _pending_side_updates(db: Session, plan: dict) -> list[dict]:
    """Rows whose `side` the plan would set to a different value. A planned entry with no `side`
    contributes nothing (the column is left as it is). A row not yet in the table counts as a change
    from None, since the seed would create it carrying the side."""
    out = []
    for tid, p in plan.items():
        if p.get("side") is None or p["kind"] != "tagged":
            continue
        for r in p["regions"]:
            row = db.get(models.ExerciseRegionTag, (tid, r["key"]))
            current = row.side if row is not None else None
            if current != p["side"]:
                out.append({"template_id": tid, "label": p["label"], "region_key": r["key"],
                            "from": current, "to": p["side"], "row_exists": row is not None})
    return out


def seed_tags(
    db: Session,
    user_id: int,
    *,
    proposal: dict | None = None,
    confirm: bool = False,
    dry_run: bool = False,
    prune_unconfirmed: bool = False,
) -> dict:
    """Upsert tags + laterality for one user's resolved templates.

    `confirm=True` overrides the per-row `source` to 'human_confirmed' and stamps
    `confirmed_at` — the authoritative-confirmation step. Otherwise the proposal's
    `source` (default 'llm_proposed') is written with confirmed_at NULL.
    `dry_run=True` resolves and returns the plan, writing nothing.
    `prune_unconfirmed=True` (requires `confirm`, or `dry_run` to preview) deletes every
    non-confirmed tag row this run does not plan — after it, no unconfirmed row remains.

    The reference is AUTHORITATIVE for the templates it names (Q27 v1): on `--confirm`, every
    PLANNED template, parent or variant, loses the tag rows whose region_key the plan does not
    carry, whatever their `source`. `--dry-run` lists them as `pending_deletions`. (A plain run
    still deletes only for sided variants, as before.) A planned region_key that the taxonomy
    does not resolve is refused.
    """
    if prune_unconfirmed and not (confirm or dry_run):
        raise ValueError("--prune-unconfirmed requires --confirm (or --dry-run to preview)")
    proposal = proposal or load_proposal()
    _validate_fail_closed(proposal)

    # Prod-precondition gate (#77): refuse loudly on an empty substrate rather
    # than reporting "N unresolved" and exiting 0 — that reads like a data
    # problem when it is an unpopulated-table precondition failure.
    if db.query(models.HevyExerciseTemplate).count() == 0:
        raise EmptyTemplateStoreError(
            "hevy_exercise_templates is EMPTY — run `python backend/sync_hevy_templates.py` "
            "first, verify a non-zero row count, THEN seed. Refusing to seed."
        )

    built = build_plan(db, user_id, proposal)
    plan, unresolved_titles = built["plan"], built["unresolved"]
    _validate_plan_keys(plan)
    pending = _pending_deletions(db, plan)
    pending_sides = _pending_side_updates(db, plan)
    near_twins = _near_twins(db, proposal)
    unconfirmed = _unconfirmed_rows(db)
    planned_pairs = {(tid, r["key"]) for tid, p in plan.items() for r in p["regions"]}
    prune = [u for u in unconfirmed if (u["template_id"], u["region_key"]) not in planned_pairs]

    default_source = proposal.get("_meta", {}).get("source", "llm_proposed")
    now = datetime.now(timezone.utc)
    written = no_pattern = inherited = 0

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

    for tid, p in plan.items():
        if p["via"] is not None:
            inherited += 1
        if p["kind"] == "no_pattern":
            # Adjudicated with ZERO region rows. Only meaningful once human-confirmed,
            # so it persists only on --confirm.
            if confirm:
                no_pattern += 1
                if not dry_run:
                    _apply_template_meta(tid, p["laterality"])
                    # A variant mirrors its parent exactly; a direct entry is authoritative.
                    db.query(models.ExerciseRegionTag).filter_by(
                        hevy_exercise_template_id=tid).delete()
            continue

        written += len(p["regions"])
        if dry_run:
            continue
        _apply_template_meta(tid, p["laterality"])
        if p["via"] is not None or confirm:   # drop rows the plan no longer carries
            keep = {r["key"] for r in p["regions"]}
            for row in db.query(models.ExerciseRegionTag).filter_by(
                    hevy_exercise_template_id=tid).all():
                if row.region_key not in keep:
                    db.delete(row)
        for r in p["regions"]:
            row = db.get(models.ExerciseRegionTag, (tid, r["key"]))
            if row is None:
                row = models.ExerciseRegionTag(
                    hevy_exercise_template_id=tid, region_key=r["key"]
                )
                db.add(row)
            row.role = r["role"]
            row.taxonomy_version = taxonomy.TAXONOMY_VERSION
            row.source = "human_confirmed" if confirm else default_source
            row.confirmed_at = now if confirm else None
            if p.get("side") is not None:
                row.side = p["side"]

    if prune_unconfirmed and not dry_run:
        for u in prune:
            row = db.get(models.ExerciseRegionTag, (u["template_id"], u["region_key"]))
            if row is not None:
                db.delete(row)

    if dry_run:
        db.rollback()
    else:
        db.commit()
    summary = {
        "user_id": user_id,
        "dry_run": dry_run,
        "titles_resolved": len(plan),
        "titles_unresolved": len(unresolved_titles),
        "tags_written": 0 if dry_run else written,
        "tags_planned": written,
        "inherited_variants": inherited,
        "no_pattern_adjudicated": 0 if dry_run else no_pattern,
        "confirmed": confirm,
        "unresolved_titles": unresolved_titles,
        "near_twins": near_twins,
        "unconfirmed_existing": unconfirmed,
        "prune": prune,
        "pending_deletions": pending,
        "pending_side_updates": pending_sides,
        "deleted": 0 if dry_run else sum(
            1 for d in pending if confirm or d["via"] is not None),
        "pruned": 0 if (dry_run or not prune_unconfirmed) else len(prune),
        "plan": {tid: {k: p[k] for k in ("label", "kind", "via", "regions", "side")}
                 for tid, p in plan.items()},
    }
    logger.info("seed_exercise_region_tags: %s",
                {k: v for k, v in summary.items()
                 if k not in ("plan", "unconfirmed_existing", "prune", "pending_deletions",
                             "pending_side_updates")})
    return summary


def _print_plan(summary: dict) -> None:
    for tid, p in sorted(summary["plan"].items(), key=lambda kv: kv[1]["label"]):
        regions = ", ".join(f"{r['key']}({r['role']})" for r in p["regions"]) or "NO-PATTERN"
        via = f"  <- inherits {p['via']}" if p["via"] else ""
        print(f"  {tid:<38} {p['label'][:44]:<44} {regions}{via}")
    for title in summary["unresolved_titles"]:
        print(f"  UNRESOLVED  {title}")
    for t in summary["near_twins"]:
        print(f"  NEAR-TWIN   {t['twin']} ({t['twin_title']}) shares a prefix with "
              f"referenced {t['referenced']} - rule on it, never map it silently")
    print(f"  pre-existing unconfirmed tag rows: {len(summary['unconfirmed_existing'])} "
          f"({len(summary['prune'])} not re-planned -> what --prune-unconfirmed would delete)")
    print(f"  pending deletions (rows on planned templates the reference does not carry; "
          f"--confirm deletes them): {len(summary['pending_deletions'])}")
    print(f"  pending side updates (rows whose side the reference sets; --confirm writes them): "
          f"{len(summary['pending_side_updates'])}")
    for s in summary["pending_side_updates"]:
        print(f"    SIDE   {s['template_id']:<38} {str(s['label'])[:34]:<34} "
              f"{s['region_key']} {s['from']} -> {s['to']}")
    for d in summary["pending_deletions"]:
        print(f"    DELETE {d['template_id']:<38} {str(d['label'])[:34]:<34} "
              f"{d['region_key']}({d['role']}) [{d['source']}]")
    for u in summary["unconfirmed_existing"]:
        fate = "PRUNE" if u in summary["prune"] else "re-stamped by --confirm"
        print(f"    {u['template_id']:<38} {str(u['title'])[:34]:<34} "
              f"{u['region_key']}({u['role']}) [{u['source']}] -> {fate}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print("usage: python backend/seed_exercise_region_tags.py <user_id> "
              "[--dry-run | --confirm] [--prune-unconfirmed]")
        raise SystemExit(2)
    uid = int(sys.argv[1])
    flags = sys.argv[2:]
    do_confirm = "--confirm" in flags
    do_dry = "--dry-run" in flags
    do_prune = "--prune-unconfirmed" in flags
    if do_confirm and do_dry:
        print("--dry-run and --confirm are exclusive")
        raise SystemExit(2)
    if do_prune and not (do_confirm or do_dry):
        print("--prune-unconfirmed requires --confirm (or --dry-run to preview)")
        raise SystemExit(2)

    from database import SessionLocal

    _db = SessionLocal()
    try:
        result = seed_tags(_db, uid, confirm=do_confirm, dry_run=do_dry,
                           prune_unconfirmed=do_prune)
        if do_dry:
            _print_plan(result)
        print({k: v for k, v in result.items()
               if k not in ("plan", "unconfirmed_existing", "prune", "pending_deletions",
                            "pending_side_updates")})
    except (EmptyTemplateStoreError, OrphanRegionKeyError, MalformedProposalError) as exc:
        logging.error("%s", exc)
        raise SystemExit(1)
    finally:
        _db.close()
