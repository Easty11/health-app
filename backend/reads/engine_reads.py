"""Engine reads for the MCP door — injuries, constraints and the probe queue.

READ-ONLY, one definition each. These are what Code (and chat) read to answer "what is the state of the
injury ledger, which engine blocks exist and what is pending, and which regions will Probe actually offer
and why not the rest" without a psql session. Prod reads reach Code only as MCP tools added by PR (operator
ruling, 2 Nov 2026); psql and any raw DB session stay operator-only.

THE SAME LIFTS THE CHAT READS. Constraints are rendered through `typed_entries` (`constraint_what`,
`constraint_exits`, `constraint_due_tags`), so this door cannot say something the chat section and the
review sweep do not. Unlike the standing chat section, which lists only CONFIRMED rows, `constraints_read`
also lists PROPOSALS and RESOLUTIONS: the operator's pending count and a declined default's basis are the
point of the read.

NOTHING HERE INTERPRETS. An injury is listed as written; a block is listed with its authority, exit and
review date; a region left out of the probe queue is listed with the string the engine itself returned.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

import models
import typed_entries
from engine import profile as profile_mod
from engine import selection

CONSTRAINT_STATUS_FILTERS = ("confirmed", "proposed", "resolved")


# ── injuries ──────────────────────────────────────────────────────────────────

def injuries_read(db: Session, user_id: int, *, include_resolved: bool = False) -> list[dict[str, Any]]:
    """The user's injury rows, newest first, each with the engine-tier rows parented to it.

    Active rows by default. `include_resolved` adds the retired ones (resolved or superseded) so the
    history is inspectable; a resolved row carries its `resolution` block. `engine_rows` counts the
    constraint rows parented to the injury by state — a proposal is not a block."""
    q = db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id, type="injury")
    if not include_resolved:
        q = q.filter_by(active=True)
    injuries = q.order_by(models.UserKnowledgeEntry.added_at.desc(), models.UserKnowledgeEntry.id.desc()).all()

    children: dict[str, dict[str, int]] = {}
    for c in db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id, type="constraint").all():
        v = c.value or {}
        parent = v.get("parent_key")
        if not parent:
            continue
        state = ("resolved" if not c.active else str(v.get("status") or "unknown"))
        bucket = children.setdefault(parent, {})
        bucket[state] = bucket.get(state, 0) + 1

    out = []
    for r in injuries:
        v = r.value or {}
        out.append({
            "id": r.id, "key": r.key, "active": bool(r.active), "superseded_by": r.superseded_by,
            "body_part": v.get("body_part"), "side": v.get("side"), "signal_type": v.get("signal_type"),
            "ra_flare": bool(v.get("ra_flare", False)) or "ra_flare" in (v.get("restrictions") or []),
            "restrictions": list(v.get("restrictions") or []), "detail": v.get("detail"),
            "added_at": r.added_at.isoformat() if r.added_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "source": r.source, "resolution": v.get("resolution"),
            "engine_rows": dict(children.get(r.key, {})),
        })
    return out


def format_injuries(rows: list[dict[str, Any]], *, include_resolved: bool) -> str:
    if not rows:
        return "No injuries recorded." if include_resolved else "No active injuries."
    active = [r for r in rows if r["active"]]
    head = f"Injuries ({len(active)} active" + (f", {len(rows) - len(active)} retired" if include_resolved else "") + "), newest first:"
    lines = [head]
    for r in rows:
        side = r["side"] or "bilateral"
        tag = "" if r["active"] else (" [resolved]" if r["resolution"] else " [superseded]")
        lines.append(f"- #{r['id']} {r['key']}{tag} — {r['body_part'] or 'no body part'} / {side} / "
                     f"{r['signal_type'] or 'mechanical'}" + (" / RA flare" if r["ra_flare"] else ""))
        if r["restrictions"]:
            lines.append(f"    restrictions (chat-rendered, gate nothing): {'; '.join(r['restrictions'])}")
        if r["detail"]:
            lines.append(f"    detail: {r['detail']}")
        meta = [f"on record since {r['added_at']}"]
        if r["expires_at"]:
            meta.append(f"expires {r['expires_at']}")
        meta.append(f"source {r['source']}")
        lines.append("    " + " · ".join(meta))
        if r["engine_rows"]:
            counts = ", ".join(f"{n} {state}" for state, n in sorted(r["engine_rows"].items()))
            lines.append(f"    constraint rows parented to it: {counts}")
        if r["resolution"]:
            res = r["resolution"]
            lines.append(f"    resolved {res.get('resolved_on')} by {res.get('resolved_by')}: {res.get('basis')}")
    return "\n".join(lines)


# ── constraints ───────────────────────────────────────────────────────────────

def constraints_read(
    db: Session, user_id: int, *, status: str | None = None, today: date,
) -> dict[str, Any]:
    """The user's constraint rows with status, proposals and resolutions, and the pending count.

        summary — confirmed / proposed (PENDING) / resolved (declined + retired) / due, plus the
                  finding proposals awaiting confirmation (the Injuries page lists both kinds)
        items   — the rows asked for, newest first

    `status` None: every ACTIVE row (confirmed and proposed). `confirmed` / `proposed` narrow to that
    status among active rows; `resolved` is the retired ones (declined proposals and ended blocks),
    never a superseded row (its successor carries the content)."""
    if status is not None and status not in CONSTRAINT_STATUS_FILTERS:
        raise ValueError(f"unknown status {status!r} — one of {', '.join(CONSTRAINT_STATUS_FILTERS)}")
    all_rows = (
        db.query(models.UserKnowledgeEntry).filter_by(user_id=user_id)
        .order_by(models.UserKnowledgeEntry.added_at.desc(), models.UserKnowledgeEntry.id.desc()).all()
    )
    active_rows = [r for r in all_rows if r.active]
    live = typed_entries.active_keys(active_rows)
    constraints = [r for r in all_rows if r.type == "constraint"]

    def _state(r) -> str:
        if r.active:
            return str((r.value or {}).get("status") or "unknown")
        return "resolved" if r.superseded_by is None and (r.value or {}).get("resolution") else "superseded"

    summary = {
        "confirmed": sum(1 for r in constraints if _state(r) == "confirmed"),
        "proposed": sum(1 for r in constraints if _state(r) == "proposed"),
        "resolved": sum(1 for r in constraints if _state(r) == "resolved"),
        "due": 0,
        "finding_proposals_pending": sum(
            1 for r in active_rows
            if r.type == "finding" and (r.value or {}).get("status") == "proposed"
            and (r.value or {}).get("derived_from_labs") is False),
    }
    wanted = {"confirmed": {"confirmed"}, "proposed": {"proposed"}, "resolved": {"resolved"}}.get(
        status, {"confirmed", "proposed"})
    items = []
    for r in constraints:
        state = _state(r)
        v = r.value or {}
        flat = {"id": r.id, "key": r.key, **v}
        tags = typed_entries.constraint_due_tags(flat, live, today) if state == "confirmed" else []
        if state == "confirmed" and tags:
            summary["due"] += 1
        if state not in wanted:
            continue
        resolution = v.get("resolution") or None
        items.append({
            "id": r.id, "key": r.key, "state": state,
            "outcome": (("declined" if v.get("status") == "proposed" else "retired") if state == "resolved" else None),
            "what": typed_entries.constraint_what(flat), "exits": typed_entries.constraint_exits(flat),
            "parent_key": v.get("parent_key"), "review_by": v.get("review_by"),
            "asserted_by": v.get("asserted_by"), "confirmed_on": v.get("confirmed_on"),
            "kind": v.get("kind"), "tier": (v.get("scope") or {}).get("tier"),
            "region_keys": list((v.get("scope") or {}).get("region_keys") or []),
            "side": (v.get("scope") or {}).get("side"), "detail": v.get("detail"),
            "tags": tags, "resolution": resolution, "source": r.source,
        })
    return {"summary": summary, "items": items, "status": status}


def format_constraints(data: dict[str, Any]) -> str:
    s = data["summary"]
    lines = [
        f"Constraints: {s['confirmed']} confirmed, {s['proposed']} PENDING proposal(s), "
        f"{s['resolved']} resolved, {s['due']} confirmed row(s) due for review/exit.",
        f"Finding proposals pending confirmation: {s['finding_proposals_pending']}.",
    ]
    items = data["items"]
    label = {None: "active (confirmed and proposed)"}.get(data["status"], data["status"])
    if not items:
        lines.append(f"No {label} constraint rows.")
        return "\n".join(lines)
    lines.append(f"{len(items)} {label} row(s), newest first:")
    for i in items:
        if i["state"] == "resolved":
            res = i["resolution"] or {}
            head = f"[{i['outcome']} {res.get('resolved_on')} by {res.get('resolved_by')}]"
            tail = f" — basis: {res.get('basis')}"
        elif i["state"] == "proposed":
            head, tail = "[proposed — PENDING, blocks nothing]", ""
        else:
            auth = typed_entries.AUTHORITY_LABELS.get(i["asserted_by"], f"asserted by {i['asserted_by']}")
            head, tail = f"[confirmed {i['confirmed_on'] or 'on an unrecorded date'}]", f" — {auth}"
        line = (f"- #{i['id']} {head} {i['what']} — ends {i['exits']} — review by {i['review_by']}"
                f"{tail} [{i['key']}]")
        if i["parent_key"]:
            line += f" (re: {i['parent_key']})"
        if i["tags"]:
            line += " [" + ", ".join(i["tags"]).upper() + "]"
        lines.append(line)
    return "\n".join(lines)


# ── the probe queue ───────────────────────────────────────────────────────────

def probe_queue_read(db: Session, user_id: int, *, loaded_region_keys: set[str]) -> dict[str, Any]:
    """The probe queue and its exclusions for this user: `selection.probe_queue_detail` over the
    user's profile and confirmed engine-tier rows. `loaded_region_keys` is the caller's (best-effort)
    Hevy read, as `/engine/next` takes it."""
    detail = selection.probe_queue_detail(
        db, user_id, profile=profile_mod.get_profile(db, user_id), loaded_region_keys=loaded_region_keys)
    detail["loaded_region_keys"] = sorted(loaded_region_keys)
    detail["active_constraints"] = selection.gather_active_constraints(db, user_id)
    return detail


def _cell(c: dict[str, Any]) -> str:
    return f"{c['region_key']} ({c['side']})"


def format_probe_queue(detail: dict[str, Any]) -> str:
    queue, excluded = detail["queue"], detail["excluded"]
    blocked = [e for e in excluded if e["kind"] == "contraindicated"]
    lines = [
        f"Probe queue: {len(queue)} (region, side) cells probeable, {len(excluded)} excluded "
        f"({len(blocked)} contraindicated).",
        "This is the list /engine/next draws its Probe from; its due-slot capacity, readiness and phase "
        "filters then narrow it, so the first entry here is not necessarily the one it suggests.",
        "Loaded in recent Hevy workouts (best-effort; empty when Hevy is not connected or the fetch failed): "
        + (", ".join(detail["loaded_region_keys"]) or "none"),
        "",
        "Probeable, in the engine's rank order:",
    ]
    lines += [f"{n}. {_cell(c)} — {c['label']} · {c['capacity']}" + (" · probe priority" if c["probe_priority"] else "")
              for n, c in enumerate(queue, 1)] or ["(none)"]
    lines += ["", "Excluded by a block (contraindicated):"]
    lines += [f"- {_cell(e)} — {e['reason']}" for e in blocked] or [
        "- none (no confirmed engine-tier constraint row or profile hard-stop covers an untested region)"]
    for kind, title in (("recently_loaded", "Excluded: recently loaded"), ("already_tested", "Excluded: already tested"),
                        ("not_relevant", "Excluded: not relevant"),
                        ("not_queue_eligible", "Excluded: ungrounded axes (not sampled)")):
        group = [e for e in excluded if e["kind"] == kind]
        if group:
            lines += ["", f"{title} ({len(group)}): " + ", ".join(_cell(e) for e in group)]
    return "\n".join(lines)
