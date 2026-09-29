"""The appointment brief (#345) — a document the OPERATOR reads from in the room.

It is an agenda of asks, not a clinical synthesis: what the operator needs to know about the
injuries this appointment is about, and what they need to leave with. The brief is DERIVED on
every read from one `type="appointment"` row plus the ledger, and never stored.

KIND-DRIVEN (Amendment 1). There is no single brief format. The row's `kind` picks a default,
ordered list of section modules and an audience; the row may add or drop modules. Every module is a
pure function over the same `BriefContext`, so each is tested alone and the kind only picks and
orders them. `audience` sets heading voice and the tick boxes on the page — never the content.

SCOPE IS ONE HOP. In scope: the injury rows named by `scope.parent_keys`, and the constraints and
findings whose `parent_key` names one of them. A row parented to an in-scope constraint or finding
(a grandchild) is NOT read in v1. Nothing outside scope renders, including other active injuries.

HARD EXCLUSIONS, inherited from the lifts (`typed_entries`) and re-applied to history rows here:
  * a `proposed` constraint or finding never renders;
  * a finding whose `derived_from_labs` is not explicitly `False` never renders — not even as a
    count (labs are out of v1; the #60 firewall applies anyway);
  * free-text `user_knowledge` is never read (being retired, Q181) — this module takes no session,
    so it cannot read any table; the loader reads `user_knowledge_entries` (and the user's
    `full_name`, for the print subtitle) only.

PURE. `build_appointment_brief` takes loaded rows and returns a JSON-safe dict: no queries, no
clock. `load_appointment_brief` is the one loader (one ledger query, plus the user's name) the API
route and the MCP tool both call, so the two surfaces return the same object.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session

import models
import typed_entries
from current_state import CurrentState
from engine.taxonomy import by_key as region_by_key
from routers.knowledge import (
    APPOINTMENT_DEFAULT_AUDIENCE,
    APPOINTMENT_DEFAULT_SECTIONS,
)

# Section B: the authored asks the operator leaves with — all of them up to this many, else the
# first this many by priority. Each is a one-line pointer to its ask (first sentence, capped near
# this many characters); the full text and the tick box live only under Asks.
LEAVE_WITH_MAX = 5
LEAVE_WITH_SHORT_CHARS = 90
# Derived ask (i): a row whose review falls due within this many days after the appointment (or has
# already passed) is worth settling in the room.
REVIEW_HORIZON_DAYS = 30
# Derived ask (iii): an open finding whose provocation marker is not yet settled.
UNSETTLED_MARKERS = ("provocative", "untested")
# No statement cap here: the 280-char cap belongs to the chat context builder. The brief is read in
# the room and renders every statement in full.

LIMITS = (
    "Scope is one hop: the injuries named by the appointment and the constraints and findings "
    "parented directly to them. Rows parented to those (grandchildren) are not read.",
    "Labs are out of scope: lab-derived findings are not read here.",
)


# ── inputs ────────────────────────────────────────────────────────────────────

def _v(row: Any) -> dict[str, Any]:
    return getattr(row, "value", None) or {}


def _iso(d: Any) -> str | None:
    return None if d is None else str(d)


def _human(token: Any) -> str:
    """A stored token as words: `cervical_spine` → `cervical spine`."""
    return " ".join(str(token or "").replace("_", " ").split())


def _injury_label(value: dict[str, Any]) -> str:
    """The human label for an injury everywhere in the brief: "right shoulder", "cervical spine" —
    never the raw `body_part` token."""
    side = _human(value.get("side")).lower()
    part = _human(value.get("body_part")) or "injury"
    return f"{side} {part}" if side and side not in ("bilateral", "both") else part


_SENTENCE_END = re.compile(r"(?<=[.?!])\s+(?=[A-Z0-9\"'(])")


def _short(text: Any) -> str:
    """An ask's first sentence, cut at a word boundary near `LEAVE_WITH_SHORT_CHARS` with "…"."""
    s = " ".join(str(text or "").split())
    m = _SENTENCE_END.search(s)
    first = s[:m.start()] if m else s
    if len(first) <= LEAVE_WITH_SHORT_CHARS:
        return first
    cut = first[:LEAVE_WITH_SHORT_CHARS]
    space = cut.rfind(" ")
    if space > LEAVE_WITH_SHORT_CHARS // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:-—") + "…"


def _resolved_on(value: dict[str, Any]) -> date | None:
    return typed_entries.parse_date((value.get("resolution") or {}).get("resolved_on"))


def _predecessors(current: Any, rows: list[Any]) -> list[Any]:
    """The supersession chain behind `current`, newest first — each row whose `superseded_by`
    names the one after it."""
    by_successor = {getattr(r, "superseded_by", None): r for r in rows if getattr(r, "superseded_by", None)}
    chain, cur = [], current
    while getattr(cur, "id", None) in by_successor:
        cur = by_successor[cur.id]
        chain.append(cur)
    return chain


@dataclass
class BriefContext:
    """Everything a module reads, computed once from the inputs. Modules never see the raw ledger."""
    key: str
    value: dict[str, Any]
    kind: str
    audience: str
    at: datetime
    since: date | None
    parent_keys: list[str]
    sections: list[str] = field(default_factory=list)                     # resolved module order
    # Per parent key in scope: {"key", "row", "history": [older rows, newest first]}.
    injuries: list[dict[str, Any]] = field(default_factory=list)
    missing_parent_keys: list[str] = field(default_factory=list)
    parent_labels: dict[str, str] = field(default_factory=dict)          # in-scope injury key → label
    constraints: list[dict[str, Any]] = field(default_factory=list)       # active, confirmed
    findings: list[dict[str, Any]] = field(default_factory=list)          # open/confirmed, visible
    resolved_constraints: list[Any] = field(default_factory=list)        # inactive, confirmed, resolved
    finding_history: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # key → older, newest first
    derived_asks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def appointment_date(self) -> date:
        return self.at.date()


def _visible_history_finding(row: Any) -> bool:
    """A superseded finding renders as history only if it was never a proposal and is explicitly
    not lab-derived. Supersession overwrites the stored status with `superseded`, so "was never a
    proposal" is read from its authority: a chat proposal carries `asserted_by: null`, and an
    `open`/`confirmed` finding cannot (validator)."""
    v = _v(row)
    return v.get("derived_from_labs") is False and v.get("asserted_by") is not None


def scope_context(appointment: dict[str, Any], current_state: CurrentState, ledger: list[Any]) -> BriefContext:
    """Compute the in-scope rows once. `appointment` is `{"key", "value"}`; `current_state` supplies
    the ACTIVE typed rows through the shared lifts (`constraints`, `findings["visible"]`); `ledger`
    is the user's injury, constraint and finding rows, active and inactive (history)."""
    value = appointment["value"]
    kind = value["kind"]
    pks = list(value["scope"]["parent_keys"])
    pk_set = set(pks)
    ctx = BriefContext(
        key=appointment["key"],
        value=value,
        kind=kind,
        audience=value.get("audience") or APPOINTMENT_DEFAULT_AUDIENCE[kind],
        at=datetime.fromisoformat(value["at"]),
        since=typed_entries.parse_date(value.get("since")),
        parent_keys=pks,
        sections=resolve_sections(value),
    )

    for pk in pks:
        rows = [r for r in ledger if r.type == "injury" and r.key == pk]
        active = [r for r in rows if r.active]
        resolved = sorted((r for r in rows if not r.active and _resolved_on(_v(r)) is not None),
                          key=lambda r: r.id or 0, reverse=True)
        current = active[0] if active else (resolved[0] if resolved else None)
        if current is None:
            ctx.missing_parent_keys.append(pk)
            continue
        ctx.injuries.append({"key": pk, "row": current, "history": _predecessors(current, rows)})
        ctx.parent_labels[pk] = _injury_label(_v(current))

    ctx.constraints = [c for c in current_state.constraints if c.get("parent_key") in pk_set]
    ctx.findings = [f for f in (current_state.findings or {}).get("visible", [])
                    if f.get("parent_key") in pk_set]
    ctx.resolved_constraints = [
        r for r in ledger
        if r.type == "constraint" and not r.active and _v(r).get("parent_key") in pk_set
        and _v(r).get("status") == "confirmed" and _resolved_on(_v(r)) is not None
    ]
    finding_rows = [r for r in ledger if r.type == "finding"]
    for f in ctx.findings:
        current = next((r for r in finding_rows if r.id == f["id"]), None)
        if current is None:
            continue
        older = _predecessors(current, [r for r in finding_rows if r.key == f["key"]])
        ctx.finding_history[f["key"]] = [
            {"statement": _v(r).get("statement"), "as_of": _v(r).get("as_of"), "id": r.id,
             "asserted_by": _v(r).get("asserted_by"),
             "authority": typed_entries.AUTHORITY_LABELS.get(_v(r).get("asserted_by"))}
            for r in older if _visible_history_finding(r)
        ]
    ctx.derived_asks = _derived_asks(ctx)
    return ctx


# ── row summaries ─────────────────────────────────────────────────────────────
#
# `text` / `exit` are the shared chat phrasing (`typed_entries`) and stay as they are. The print
# document (#350) reads the plain fields beside them: `restriction`, `exit_label`, `parent_label` —
# the same row in words, with no stored tokens and no tier boilerplate.

def _parent_label(key: Any, labels: dict[str, str]) -> str | None:
    return None if not key else labels.get(key) or _human(key)


def _restriction(c: dict[str, Any]) -> str:
    """A constraint as the restriction itself. Advisory: its own text, verbatim. Engine: its kind
    and regions (taxonomy labels) and side, in words — never the "engine-enforced" boilerplate."""
    scope = c.get("scope") or {}
    if scope.get("tier") != "engine":
        return str(scope.get("text") or "")
    regions = ", ".join(getattr(region_by_key(k), "label", None) or _human(k)
                        for k in scope.get("region_keys") or [])
    side = scope.get("side") or "bilateral"
    side_str = "" if side == "bilateral" else f", {side} side only"
    kind = _human(c.get("kind")).capitalize()
    return f"{kind}: {regions}{side_str}" if kind else f"{regions}{side_str}"


def _exit_label(c: dict[str, Any], labels: dict[str, str]) -> str:
    """`constraint_exits` with the parent key replaced by the injury's label."""
    exit_ = c.get("exit") or {}
    parent = c.get("parent_key")
    if exit_.get("with_parent") is True and parent:
        return typed_entries.constraint_exits(
            {**c, "parent_key": _parent_label(parent, labels)})
    return typed_entries.constraint_exits(c)


def _constraint_summary(c: dict[str, Any], labels: dict[str, str] | None = None) -> dict[str, Any]:
    scope = c.get("scope") or {}
    labels = labels or {}
    return {
        "key": c.get("key"), "type": "constraint",
        "tier": scope.get("tier"), "kind": c.get("kind"),
        "text": typed_entries.constraint_what(c),
        "restriction": _restriction(c),
        "exit": typed_entries.constraint_exits(c),
        "exit_label": _exit_label(c, labels),
        "parent_key": c.get("parent_key"),
        "parent_label": _parent_label(c.get("parent_key"), labels),
        "review_by": c.get("review_by"),
        "asserted_by": c.get("asserted_by"),
        "authority": typed_entries.AUTHORITY_LABELS.get(c.get("asserted_by")),
        "detail": c.get("detail"),
    }


def _finding_summary(f: dict[str, Any], labels: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "key": f.get("key"), "type": "finding",
        "text": f.get("statement"),
        "parent_key": f.get("parent_key"),
        "parent_label": _parent_label(f.get("parent_key"), labels or {}),
        "as_of": f.get("as_of"), "status": f.get("status"),
        "marker_status": f.get("marker_status"),
        "review_by": f.get("review_by"),
        "asserted_by": f.get("asserted_by"),
        "authority": typed_entries.AUTHORITY_LABELS.get(f.get("asserted_by")),
    }


def _injury_summary(inj: dict[str, Any]) -> dict[str, Any]:
    row = inj["row"]
    v = _v(row)
    resolved = _resolved_on(v)
    return {
        "key": inj["key"], "type": "injury",
        "text": _injury_label(v),
        "status": "active" if row.active else "resolved",
        "recorded_on": _iso(getattr(row, "added_at", None)),
        "resolved_on": _iso(resolved),
        "detail": v.get("detail"),
        "restrictions": list(v.get("restrictions") or []),
    }


def _row_in_scope(ctx: BriefContext, key: str | None) -> dict[str, Any] | None:
    if not key:
        return None
    for c in ctx.constraints:
        if c.get("key") == key:
            return _constraint_summary(c, ctx.parent_labels)
    for f in ctx.findings:
        if f.get("key") == key:
            return _finding_summary(f, ctx.parent_labels)
    for inj in ctx.injuries:
        if inj["key"] == key:
            return _injury_summary(inj)
    return None


# ── derived asks (computed, never stored) ─────────────────────────────────────
#
# NEUTRAL FRAMING (#349, operator ruling). A brief presents facts and asks open questions; it
# never presumes a clinical answer, a gate or a requirement. The templates below are questions
# about the row, never instructions to set, date or rule on it — a row may be the operator's own
# precaution, and phrasing it as something the clinician must settle reads it as a clinical order.

REVIEW_QUESTION = "Is this still appropriate?"
CONDITION_QUESTION = "Does this condition still apply?"
MARKER_QUESTION = "What does this mean?"

def _derived_asks(ctx: BriefContext) -> list[dict[str, Any]]:
    horizon = ctx.appointment_date + timedelta(days=REVIEW_HORIZON_DAYS)
    out: list[dict[str, Any]] = []

    def add(rule: str, row: dict[str, Any], question: str, subject: str) -> None:
        # `question` is the template alone (the print document shows it beside the row it names);
        # `text` is the question with its subject, as the screen and the chat read it.
        out.append({"rule": rule, "entry_key": row["key"], "question": question,
                    "text": f"{question} {subject}", "row": row, "source": "ledger"})

    for c in ctx.constraints:
        s = _constraint_summary(c, ctx.parent_labels)
        review_by = typed_entries.parse_date(c.get("review_by"))
        if review_by is not None and review_by <= horizon:
            add("review_due", s, REVIEW_QUESTION, s["text"])
        exit_ = c.get("exit") or {}
        # "Only exit is on_condition": a condition with no date and no parent to end with.
        if exit_.get("on_condition") and not exit_.get("on_date") and exit_.get("with_parent") is not True:
            add("undated_exit", s, CONDITION_QUESTION, exit_["on_condition"])
    for f in ctx.findings:
        s = _finding_summary(f, ctx.parent_labels)
        review_by = typed_entries.parse_date(f.get("review_by"))
        if review_by is not None and review_by <= horizon:
            add("review_due", s, REVIEW_QUESTION, s["text"])
        if f.get("status") == "open" and f.get("marker_status") in UNSETTLED_MARKERS:
            add("unsettled_marker", s, MARKER_QUESTION, s["text"])
    return out


def _authored_asks(ctx: BriefContext) -> list[dict[str, Any]]:
    """Authored asks by priority ascending (ties keep written order), each with its `resolves` row
    looked up IN SCOPE and the derived asks folded into it."""
    asks = sorted(enumerate(ctx.value.get("asks") or []), key=lambda p: (p[1]["priority"], p[0]))
    out = []
    for _, a in asks:
        entry_key = (a.get("resolves") or {}).get("entry_key")
        row = _row_in_scope(ctx, entry_key)
        out.append({
            "id": a["id"], "text": a["text"], "priority": a["priority"],
            "resolves": {
                "entry_key": entry_key,
                "note": (a.get("resolves") or {}).get("note"),
                # None when unset, or when the key is not an in-scope row a reader may see.
                "row": row,
                # The ask names a row the brief cannot show (missing, proposed, inactive or out of
                # scope): the page says so under the ask rather than dropping the link silently.
                "unresolved": bool(entry_key) and row is None,
            },
            "folded": [d for d in ctx.derived_asks if entry_key and d["entry_key"] == entry_key],
        })
    return out


# ── section modules ───────────────────────────────────────────────────────────
#
# Each returns a dict (the section) or None (renders nothing — no placeholder). Every section carries
# its `module` name; the page supplies the heading for the audience.

def module_header(ctx: BriefContext) -> dict[str, Any]:
    v = ctx.value
    return {
        "clinician": v["clinician"], "practice": v.get("practice"),
        "at": v["at"], "date": ctx.at.date().isoformat(), "time": ctx.at.strftime("%H:%M"),
        "status": v["status"], "kind": ctx.kind, "audience": ctx.audience,
        "detail": v.get("detail"),
    }


def module_leave_with(ctx: BriefContext) -> dict[str, Any]:
    """A compact pointer list: each item is its ask's first sentence (`short`), linked by `id` to the
    full ask under Asks. The full text is not repeated here."""
    asks = _authored_asks(ctx)
    return {
        "items": [{"id": a["id"], "short": _short(a["text"]), "priority": a["priority"]}
                  for a in asks[:LEAVE_WITH_MAX]],
        "total": len(asks),
    }


def module_asks(ctx: BriefContext) -> dict[str, Any]:
    folded = {d["entry_key"] for a in _authored_asks(ctx) for d in a["folded"]}
    return {
        "authored": _authored_asks(ctx),
        "derived": [d for d in ctx.derived_asks if d["entry_key"] not in folded],
    }


def module_options_prep(ctx: BriefContext) -> dict[str, Any] | None:
    items = [
        {"ask_id": a["id"], "text": a["text"],
         "options": [{"option": o["option"], "implication": o["implication"]} for o in a["options"]]}
        for a in sorted(ctx.value.get("asks") or [], key=lambda a: a["priority"])
        if a.get("options")
    ]
    return {"items": items} if items else None


def _since_missing() -> dict[str, Any]:
    return {"since": None, "note": "This appointment has no `since` date, so nothing is compared."}


def module_since(ctx: BriefContext) -> dict[str, Any] | None:
    """What happened since the last visit, each row ONCE, in the most specific module present.
    When `changes_vs_history` is in the brief it owns the findings and the injury status changes
    (resolved, rewritten), so this keeps only what it does not carry: constraints confirmed or
    resolved, and injury rows newly recorded. A constraint an ask already names (a derived ask, when
    Asks is in the brief) is not repeated as "confirmed" here; Current constraints is its home.
    Nothing left → None (renders nothing)."""
    history_owns = "changes_vs_history" in ctx.sections
    if ctx.since is None:
        # changes_vs_history already carries the same note.
        return None if history_owns else _since_missing()
    since = ctx.since
    asked = ({d["entry_key"] for d in ctx.derived_asks if d["row"]["type"] == "constraint"}
             if "asks" in ctx.sections else set())
    injuries = []
    for inj in ctx.injuries:
        row, v = inj["row"], _v(inj["row"])
        resolved = _resolved_on(v)
        if not row.active and resolved is not None and resolved >= since:
            if not history_owns:
                injuries.append({"key": inj["key"], "text": _injury_label(v), "change": "resolved",
                                 "on": resolved.isoformat(),
                                 "basis": (v.get("resolution") or {}).get("basis")})
        elif row.active and getattr(row, "added_at", None) is not None and row.added_at >= since:
            if inj["history"] and history_owns:
                continue
            injuries.append({"key": inj["key"], "text": _injury_label(v),
                             "change": "updated" if inj["history"] else "recorded",
                             "on": _iso(row.added_at)})
    findings = [] if history_owns else [
        _finding_summary(f, ctx.parent_labels) for f in ctx.findings
        if (d := typed_entries.parse_date(f.get("as_of"))) is not None and d >= since]
    constraints = []
    for c in ctx.constraints:
        if c.get("key") in asked:
            continue
        on = typed_entries.parse_date(c.get("confirmed_on")) or c.get("added_at")
        if on is not None and on >= since:
            constraints.append({**_constraint_summary(c, ctx.parent_labels), "change": "confirmed", "on": _iso(on)})
    for r in ctx.resolved_constraints:
        resolved = _resolved_on(_v(r))
        if resolved >= since:
            constraints.append({**_constraint_summary({"key": r.key, **_v(r)}, ctx.parent_labels),
                                "change": "resolved",
                                "on": resolved.isoformat(),
                                "basis": (_v(r).get("resolution") or {}).get("basis")})
    if not (injuries or findings or constraints):
        return None
    return {"since": since.isoformat(), "injuries": injuries, "findings": findings,
            "constraints": constraints}


def module_changes_vs_history(ctx: BriefContext) -> dict[str, Any]:
    """The "flag against history" module: each new finding beside the statement(s) it replaced, and
    each in-scope injury whose status changed since, before → after."""
    if ctx.since is None:
        return _since_missing()
    since = ctx.since
    findings = []
    for f in ctx.findings:
        as_of = typed_entries.parse_date(f.get("as_of"))
        if as_of is None or as_of < since:
            continue
        findings.append({**_finding_summary(f, ctx.parent_labels), "previous": ctx.finding_history.get(f["key"], [])})
    injuries = []
    for inj in ctx.injuries:
        row, v = inj["row"], _v(inj["row"])
        resolved = _resolved_on(v)
        if not row.active and resolved is not None and resolved >= since:
            injuries.append({"key": inj["key"], "text": _injury_label(v),
                             "before": "active", "after": f"resolved {resolved.isoformat()}",
                             "on": resolved.isoformat()})
        elif row.active and inj["history"] and row.added_at is not None and row.added_at >= since:
            prev = _v(inj["history"][0])
            injuries.append({"key": inj["key"], "text": _injury_label(v),
                             "before": prev.get("detail") or ", ".join(prev.get("restrictions") or []),
                             "after": v.get("detail") or ", ".join(v.get("restrictions") or []),
                             "on": _iso(row.added_at)})
    return {"since": since.isoformat(), "findings": findings, "injuries": injuries}


def module_current_constraints(ctx: BriefContext) -> dict[str, Any]:
    return {"items": [_constraint_summary(c, ctx.parent_labels) for c in ctx.constraints]}


def module_background(ctx: BriefContext) -> dict[str, Any]:
    """v1 background: the in-scope injury rows and the CONFIRMED in-scope findings, nothing else.
    Durable history (mechanism, prior imaging narrative) still lives in free-text `user_knowledge`,
    which new code must not read; full background waits on the Q181 migration."""
    return {
        "injuries": [_injury_summary(inj) for inj in ctx.injuries],
        "findings": [_finding_summary(f, ctx.parent_labels) for f in ctx.findings if f.get("status") == "confirmed"],
        "note": "Background is the injury ledger and confirmed findings only; fuller history waits on Q181.",
    }


def module_imaging_timeline(ctx: BriefContext) -> dict[str, Any]:
    """Evidence refs on the `document` door among in-scope findings, oldest first by the citing
    finding's `as_of`. The `document` door resolves to nothing (no store behind it — a ref is free
    text), so refs render as written, undated and untitled."""
    items = []
    for f in sorted(ctx.findings, key=lambda f: str(f.get("as_of") or "")):
        for ev in ((f.get("basis") or {}).get("evidence") or []):
            if ev.get("door") == "document":
                items.append({"ref": ev.get("ref"), "finding_key": f.get("key"), "as_of": f.get("as_of")})
    return {"items": items, "note": "Document refs as written; they do not resolve to a dated, titled record yet."}


def module_request(ctx: BriefContext) -> dict[str, Any] | None:
    req = ctx.value.get("request")
    if not req:
        return None
    return {"ask": req["ask"], "justification": req["justification"],
            "evidence": [{"door": e["door"], "ref": e["ref"]} for e in req.get("evidence") or []],
            "alternatives": list(req.get("alternatives") or [])}


def module_logistics(ctx: BriefContext) -> dict[str, Any]:
    return {"items": list(ctx.value.get("logistics") or [])}


MODULES: dict[str, Callable[[BriefContext], dict[str, Any] | None]] = {
    "header": module_header,
    "leave_with": module_leave_with,
    "asks": module_asks,
    "options_prep": module_options_prep,
    "since": module_since,
    "changes_vs_history": module_changes_vs_history,
    "current_constraints": module_current_constraints,
    "background": module_background,
    "imaging_timeline": module_imaging_timeline,
    "request": module_request,
    "logistics": module_logistics,
}


def resolve_sections(value: dict[str, Any]) -> list[str]:
    """The kind's default list, minus `sections.drop`, plus `sections.add` (appended in the order
    given; a module already in the list stays where it is)."""
    sec = value.get("sections") or {}
    drop = set(sec.get("drop") or [])
    out = [m for m in APPOINTMENT_DEFAULT_SECTIONS[value["kind"]] if m not in drop]
    for m in sec.get("add") or []:
        if m not in out:
            out.append(m)
    return out


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def build_appointment_brief(
    appointment: dict[str, Any], current_state: CurrentState, ledger: list[Any],
    patient_name: str | None = None,
) -> dict[str, Any]:
    """Assemble the brief: pure, JSON-safe. See the module docstring for scope and exclusions.
    `patient_name` is the user's `full_name` (None if unset) — the print document's subtitle."""
    ctx = scope_context(appointment, current_state, ledger)
    sections = []
    for name in resolve_sections(ctx.value):
        body = MODULES[name](ctx)
        if body is not None:
            sections.append({"module": name, **body})
    return _json_safe({
        "key": ctx.key,
        "kind": ctx.kind,
        "audience": ctx.audience,
        "status": ctx.value["status"],
        "patient": {"name": patient_name or None},
        "scope": {"parent_keys": ctx.parent_keys, "missing_parent_keys": ctx.missing_parent_keys,
                  "hops": 1},
        "sections": sections,
        "limits": list(LIMITS),
    })


# ── the one loader (API route and MCP tool) ───────────────────────────────────

BRIEF_ROW_TYPES = ("appointment", "injury", "constraint", "finding")


def load_appointment_brief(db: Session, user_id: int, key: str) -> dict[str, Any] | None:
    """ONE query of the user's appointment / injury / constraint / finding rows (active and
    inactive), lifted through `typed_entries` exactly as `current_state` lifts them, then assembled.
    None when no active appointment has this key. Does not run the whole `current_state()` (HRV,
    resolver, labs) — the brief reads none of it (the `_typed_entries_read` precedent)."""
    rows = (
        db.query(models.UserKnowledgeEntry)
        .filter(models.UserKnowledgeEntry.user_id == user_id,
                models.UserKnowledgeEntry.type.in_(BRIEF_ROW_TYPES))
        .order_by(models.UserKnowledgeEntry.added_at.desc(), models.UserKnowledgeEntry.id.desc())
        .all()
    )
    appt = next((r for r in rows if r.type == "appointment" and r.key == key and r.active), None)
    if appt is None:
        return None
    active = [r for r in rows if r.active]
    state = CurrentState(
        knowledge_entries=active,
        constraints=typed_entries.lift_constraints(active),
        findings=typed_entries.lift_findings(active),
        live_keys=typed_entries.active_keys(active),
    )
    ledger = [r for r in rows if r.type != "appointment"]
    name = db.query(models.User.full_name).filter(models.User.id == user_id).scalar()
    return build_appointment_brief({"key": appt.key, "value": appt.value}, state, ledger, name)


def list_appointments(db: Session, user_id: int, status: str | None = None) -> list[dict[str, Any]]:
    """Active appointment rows (optionally one status), soonest first — the hub doorway's read."""
    rows = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=user_id, type="appointment", active=True)
        .all()
    )
    out = [
        {"key": r.key, "clinician": _v(r).get("clinician"), "practice": _v(r).get("practice"),
         "at": _v(r).get("at"), "kind": _v(r).get("kind"), "status": _v(r).get("status")}
        for r in rows if status is None or _v(r).get("status") == status
    ]
    return sorted(out, key=lambda a: str(a["at"] or ""))
