"""Injury clearance sweep — find every COPY of an injury outside the ledger (surfacing-only).

The injury ledger (`user_knowledge_entries`, type='injury') is the only authority on injury
state. Resolving a ledger row (`POST /knowledge/injuries/{id}/resolve`) retires the authority,
but the same injury may still be written in other stores that reach chat context and keep
re-imposing the constraint. This module finds those copies so the operator can clear them.

READ-ONLY BY CONSTRUCTION. Nothing here writes, and each hit carries the store's EXISTING action
(or `none`). Auto-editing copies would put the app in the clearing role (#133) and bypass the
operator. The route that serves this is `GET /knowledge/injuries/{id}/sweep`.

GRANULARITY. Free-text `user_knowledge` rows are ONE ROW PER CATEGORY with appended lines
(`chat.py`'s legacy write path), so a row holds facts about several injuries. Hits are therefore
per LINE (row id + line index) and the action is `edit`, never delete — deleting the row would
drop still-active facts with it.

SIDE. An entry's `side` is a signal, not a filter: a hit that names only the OPPOSITE side is
returned flagged (`opposite_side`), never dropped; a hit naming no side is returned unflagged.
Side detection is whole-word `left` / `right` only (no `L`/`R` abbreviations).
"""
from __future__ import annotations

import re
from typing import Any, Iterable

import models

# Restriction words too generic to identify an injury on their own ("heavy gripping" must not
# match every "heavy" in the store). Words of <= 3 letters are dropped as well.
_GENERIC_WORDS = frozenset({
    "heavy", "light", "static", "deep", "range", "tension", "loaded", "load", "unilateral",
    "bilateral", "short", "lever", "full", "speed", "with", "without", "from", "into", "over",
    "under", "avoid", "injury",
})
_SIDES = ("left", "right")
_SIDE_RE = re.compile(r"\b(left|right)\b", re.IGNORECASE)
_SNIPPET_MAX = 240

# The out-of-app stores the backend cannot search. ALWAYS returned, last, whatever the hits.
MANUAL_CHECKLIST: tuple[dict[str, str], ...] = (
    {"store": "project_knowledge_files",
     "where": "Claude project knowledge (orientation docs, e.g. Athlete_Profile, Clinical_Protocol)",
     "why": "Outside the app; the sweep cannot read them."},
    {"store": "claude_memory",
     "where": "Claude memory (chat and Code)",
     "why": "Outside the app; the sweep cannot read it."},
    {"store": "browser_chat_history",
     "where": "The in-app chat panel's saved conversation (browser localStorage)",
     "why": "Stored only in the browser and re-sent on every turn; the backend never sees it "
            "at rest. Clear or start a fresh conversation."},
    {"store": "hevy_workout_notes",
     "where": "Notes on logged Hevy workouts (recent workouts reach chat context)",
     "why": "Fetched live from Hevy per turn, not cached; edit them in Hevy."},
)


def _stem(word: str) -> str:
    """Crude prefix stem so `sprinting` also matches `sprint`/`sprints`, `striding` matches
    `stride`. Matching is prefix-bounded (`\\bstem`), so only the suffix needs stripping."""
    if word.endswith("ing") and len(word) - 3 >= 4:
        word = word[:-3]
        if len(word) >= 5 and word[-1] == word[-2]:  # gripping → gripp → grip
            word = word[:-1]
    return word


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", text.lower())
            if len(w) >= 4 and w not in _GENERIC_WORDS and w not in _SIDES]


def derive_terms(entry: models.UserKnowledgeEntry, extra: Iterable[str] = ()) -> list[str]:
    """Match terms for an injury entry: body_part (as a phrase and its words), the key's
    tokens, the words of `restrictions`, plus operator-supplied `extra` terms verbatim.
    Lower-cased, de-duplicated, order-preserving."""
    value = entry.value or {}
    terms: list[str] = []
    body_part = str(value.get("body_part") or "").strip().lower()
    if body_part:
        terms.append(body_part)
        terms.extend(_words(body_part))
    terms.extend(_words((entry.key or "").replace("_", " ")))
    for r in value.get("restrictions") or []:
        # A word already a term (the body part) is kept whole: "hamstring" is not an -ing verb.
        terms.extend(w if w in terms else _stem(w) for w in _words(str(r)))
    terms.extend(t.strip().lower() for t in extra if t and t.strip())
    seen: set[str] = set()
    return [t for t in terms if not (t in seen or seen.add(t))]


def term_regex(terms: list[str]) -> re.Pattern | None:
    if not terms:
        return None
    alts = sorted((r"\s+".join(map(re.escape, t.split())) for t in terms), key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(alts) + ")", re.IGNORECASE)


def _snippet(line: str, m: re.Match) -> str:
    line = line.strip()
    if len(line) <= _SNIPPET_MAX:
        return line
    start = max(0, m.start() - _SNIPPET_MAX // 3)
    return ("…" if start else "") + line[start:start + _SNIPPET_MAX].strip() + "…"


def _side_fields(line: str, own_side: str | None) -> dict[str, Any]:
    mentioned = sorted({s.lower() for s in _SIDE_RE.findall(line)})
    opposite = None
    if own_side in _SIDES:
        opposite = "right" if own_side == "left" else "left"
    return {
        "sides_mentioned": mentioned,
        "opposite_side": bool(opposite and opposite in mentioned and own_side not in mentioned),
    }


# A line that says it is history. Surfacing-only label: it separates a resolved-history line
# ("… RESOLVED Aug 2026") from a stale ORDER ("no sprinting") so the operator can tell which
# copies still instruct. Whole-word `resolved` / `historical` only — "cleared" is excluded
# because live clearance prose uses it ("all back movements cleared except …").
_HISTORY_RE = re.compile(r"\b(resolved|historical)\b", re.IGNORECASE)


def identity_terms(entry: models.UserKnowledgeEntry) -> list[str]:
    """What names an injury, as opposed to what it restricts: body_part (phrase + words) and
    key tokens only. Restriction words are left out on purpose — a lumbar row restricting
    "hamstring stretching" is not a hamstring injury, and matching on it would label every
    hamstring line as the lumbar row's."""
    value = entry.value or {}
    terms: list[str] = []
    body_part = str(value.get("body_part") or "").strip().lower()
    if body_part:
        terms.append(body_part)
        terms.extend(_words(body_part))
    terms.extend(_words((entry.key or "").replace("_", " ")))
    seen: set[str] = set()
    return [t for t in terms if not (t in seen or seen.add(t))]


def line_context(entry: models.UserKnowledgeEntry,
                 all_injuries: list[models.UserKnowledgeEntry]) -> dict[str, Any]:
    """Per-sweep context for labelling each hit line: the swept entry's side, and every OTHER
    injury (active or resolved) with a regex over its identity terms.

    Two exclusions keep the label about a DIFFERENT injury:
      * same body_part as the swept entry (the other-side hamstring) — the side flag already
        discriminates those, and labelling every hamstring line with its twin is noise;
      * superseded rows sharing a key collapse to ONE per key — the active row, else the
        highest id (the latest statement of that injury)."""
    own_body = str((entry.value or {}).get("body_part") or "").strip().lower()
    by_key: dict[str, models.UserKnowledgeEntry] = {}
    for o in all_injuries:
        if o.id == entry.id:
            continue
        if own_body and str((o.value or {}).get("body_part") or "").strip().lower() == own_body:
            continue
        cur = by_key.get(o.key)
        if cur is None or (o.active, o.id) > (cur.active, cur.id):
            by_key[o.key] = o
    others = []
    for o in sorted(by_key.values(), key=lambda r: r.id):
        rx = term_regex(identity_terms(o))
        if rx is not None:
            others.append({"entry_id": o.id, "key": o.key, "active": bool(o.active), "rx": rx})
    return {"own_side": (str((entry.value or {}).get("side") or "").lower() or None),
            "others": others}


def _line_fields(line: str, ctx: dict[str, Any]) -> dict[str, Any]:
    other_hits = []
    for o in ctx.get("others", []):
        found = sorted({m.group(0).lower() for m in o["rx"].finditer(line)})
        if found:
            other_hits.append({"entry_id": o["entry_id"], "key": o["key"],
                               "active": o["active"], "matched_terms": found})
    return {
        **_side_fields(line, ctx.get("own_side")),
        "marked_resolved": bool(_HISTORY_RE.search(line)),
        # The line also names another injury. `active` true = a line still in use by a live
        # injury: clearing it would drop that injury's copy too — edit, don't delete.
        "other_injuries": other_hits,
    }


def _line_hits(text: str, rx: re.Pattern, ctx: dict[str, Any]):
    """Yield (line_index, snippet, matched_terms, line_fields) for every matching line."""
    for idx, line in enumerate((text or "").split("\n")):
        found = list(rx.finditer(line))
        if not found:
            continue
        matched = sorted({m.group(0).lower() for m in found})
        yield idx, _snippet(line, found[0]), matched, _line_fields(line, ctx)


def _walk_strings(obj: Any, path: str):
    """Every string leaf in a JSON value, with a dotted path."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_strings(v, f"{path}[{i}]")


def _entry_reach(e: models.UserKnowledgeEntry, field: str) -> str:
    """Whether a structured entry's field reaches chat context, as verified on master.
    `yes`/`no` only where the render path was read; everything else is `unverified`."""
    if not e.active:
        return "no"  # current_state reads active=True only
    if e.type == "schedule_item":
        if field == "notes":
            # context_builder renders the first 40 chars of notes, and only for source=chat.
            return "yes" if e.source == "chat" else "no"
        return "yes"
    if e.type in ("load_context", "training_plan"):
        return "yes"
    return "unverified"


def _entry_action(e: models.UserKnowledgeEntry) -> tuple[str, str | None]:
    if e.type == "schedule_item" and e.active:
        return "resolve", f"POST /knowledge/schedule/{e.id}/resolve"
    return "none", None


# ── restriction audit — does anything drop out of context on resolve? ───────
#
# WHAT A RESTRICTION STRING DOES. Restriction strings are SURFACED, not gated: they render
# into chat context (`context_builder._section_schedule`, "avoid: …") and the MCP injury
# summary, and nothing else reads them — the engine's §8 filters (`selection.is_contraindicated`)
# gate on `body_part` + `signal_type` (+ side), with the one exception of the literal
# `ra_flare` token. So when an injury row is resolved its restrictions vanish from the only
# place they act: the coach's prompt. A restriction the resolution basis never addressed is
# an ORPHAN — still true (e.g. a neural limiter recorded on a tissue row) but about to go
# unsaid. The audit names each one so the operator can re-home it before resolving, or
# confirm it has been. It never writes.
#
# RE-HOMING HAS A TRAP. The destination row's `signal_type` changes what the engine does:
# a spinal (or body-part-less) row typed `neural`/`radicular` fires `_RADICULAR_BLOCKS` —
# a hinge/rotation/carry/gait stand-down — where the same words on a `mechanical` row are
# chat-only. The audit surfaces that as a warning on the destination; it never decides.

RESTRICTIONS_NOTE = (
    "Restriction strings are chat-rendered only (context_builder schedule section, MCP injury "
    "summary). The engine gates on body_part + signal_type (+ side, + the ra_flare token), "
    "never on restriction text."
)


def _distinguishing_stems(restriction: str, body_words: set[str]) -> list[str]:
    """The words that identify WHAT is restricted, stemmed. Body-part words are dropped
    ("static end-range hamstring stretching" → ["stretch"]) so a basis that merely names the
    body part does not read as addressing the restriction; if nothing is left, keep them."""
    words = _words(restriction)
    distinct = [w for w in words if w not in body_words]
    return [w if w in body_words else _stem(w) for w in (distinct or words)]


def _mentions_all(stems: list[str], text: str) -> bool:
    return bool(stems) and all(
        re.search(r"\b" + re.escape(s), text or "", re.IGNORECASE) for s in stems)


def _radicular_warning(dest: models.UserKnowledgeEntry) -> dict[str, Any] | None:
    from engine.selection import _RADICULAR_BLOCKS, _is_spinal  # the gate's own definitions
    val = dest.value or {}
    signal = str(val.get("signal_type", "mechanical")).lower()
    body = str(val.get("body_part") or "").lower()
    if signal in ("radicular", "neural") and _is_spinal(body):
        return {
            "signal_type": signal,
            "fires": sorted(_RADICULAR_BLOCKS),
            "message": (f"'{dest.key}' is a spinal row typed '{signal}': the engine hard-stops "
                        f"every region in _RADICULAR_BLOCKS while it is active. Type it "
                        f"'mechanical' if the restriction should be chat-only."),
        }
    return None


def audit_restrictions(entry: models.UserKnowledgeEntry,
                       other_injuries: list[models.UserKnowledgeEntry]) -> list[dict[str, Any]]:
    """One row per restriction on `entry`: is it addressed by the resolution basis, carried by
    another ACTIVE injury row (re-homed), or neither (orphan)? For an unresolved entry the basis
    is empty, so the audit reads as "what would orphan if resolved now"."""
    value = entry.value or {}
    basis = ((value.get("resolution") or {}).get("basis") or "")
    body_words = set(_words(str(value.get("body_part") or "")))
    out = []
    for r in value.get("restrictions") or []:
        r = str(r)
        stems = _distinguishing_stems(r, body_words)
        covered = _mentions_all(stems, basis)
        rehomed = []
        for dest in other_injuries:
            if dest.id == entry.id or not dest.active:
                continue
            if any(_mentions_all(stems, str(dr)) for dr in (dest.value or {}).get("restrictions") or []):
                rehomed.append({
                    "entry_id": dest.id, "key": dest.key,
                    "body_part": (dest.value or {}).get("body_part"),
                    "signal_type": str((dest.value or {}).get("signal_type", "mechanical")).lower(),
                    "radicular_warning": _radicular_warning(dest),
                })
        out.append({
            "restriction": r,
            "match_stems": stems,
            "covered_by_basis": covered,
            "rehomed_to": rehomed,
            "status": "rehomed" if rehomed else ("covered" if covered else "orphan"),
        })
    return out


def sweep_user_knowledge(rows, rx, ctx) -> list[dict[str, Any]]:
    hits = []
    for row in rows:
        for idx, snippet, matched, fields in _line_hits(row.content, rx, ctx):
            hits.append({
                "store": "user_knowledge", "row_id": row.id, "line_index": idx,
                "location": f"category: {row.category}", "snippet": snippet,
                "matched_terms": matched, **fields,
                # _section_knowledge renders every row, unfiltered, every turn.
                "reaches_context": "yes",
                "action": "edit", "action_route": f"PUT /knowledge/{row.id}",
            })
    return hits


def sweep_entries(entries, rx, ctx) -> list[dict[str, Any]]:
    hits = []
    for e in entries:
        fields = list(_walk_strings(e.value, "value")) + ([("notes", e.notes)] if e.notes else [])
        action, route = _entry_action(e)
        for path, text in fields:
            for idx, snippet, matched, fields in _line_hits(text, rx, ctx):
                hits.append({
                    "store": "user_knowledge_entries", "row_id": e.id, "line_index": idx,
                    "location": f"{e.type} {e.key} · {path}" + ("" if e.active else " (inactive)"),
                    "snippet": snippet, "matched_terms": matched, **fields,
                    "reaches_context": _entry_reach(e, path),
                    "action": action, "action_route": route,
                })
    return hits


def sweep_hevy_routines(routines, rx, ctx) -> list[dict[str, Any]]:
    hits = []
    for r in routines or []:
        rtitle = r.get("title") or "Untitled routine"
        fields = [(f"routine '{rtitle}' · notes", r.get("notes") or "")]
        for ex in r.get("exercises") or []:
            fields.append((f"routine '{rtitle}' · {ex.get('title') or 'exercise'} · notes",
                           ex.get("notes") or ""))
        for location, text in fields:
            for idx, snippet, matched, fields in _line_hits(text, rx, ctx):
                hits.append({
                    "store": "hevy_routines", "row_id": r.get("id"), "line_index": idx,
                    "location": location, "snippet": snippet, "matched_terms": matched, **fields,
                    # Full routine detail (notes included) renders only for the working-set
                    # folder; other routines appear by title only.
                    "reaches_context": "conditional",
                    "action": "none", "action_route": None,
                })
    return hits
