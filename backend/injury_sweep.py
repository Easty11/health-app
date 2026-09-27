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


def _line_hits(text: str, rx: re.Pattern, own_side: str | None):
    """Yield (line_index, snippet, matched_terms, side_fields) for every matching line."""
    for idx, line in enumerate((text or "").split("\n")):
        found = list(rx.finditer(line))
        if not found:
            continue
        matched = sorted({m.group(0).lower() for m in found})
        yield idx, _snippet(line, found[0]), matched, _side_fields(line, own_side)


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


def sweep_user_knowledge(rows, rx, own_side) -> list[dict[str, Any]]:
    hits = []
    for row in rows:
        for idx, snippet, matched, side in _line_hits(row.content, rx, own_side):
            hits.append({
                "store": "user_knowledge", "row_id": row.id, "line_index": idx,
                "location": f"category: {row.category}", "snippet": snippet,
                "matched_terms": matched, **side,
                # _section_knowledge renders every row, unfiltered, every turn.
                "reaches_context": "yes",
                "action": "edit", "action_route": f"PUT /knowledge/{row.id}",
            })
    return hits


def sweep_entries(entries, rx, own_side) -> list[dict[str, Any]]:
    hits = []
    for e in entries:
        fields = list(_walk_strings(e.value, "value")) + ([("notes", e.notes)] if e.notes else [])
        action, route = _entry_action(e)
        for path, text in fields:
            for idx, snippet, matched, side in _line_hits(text, rx, own_side):
                hits.append({
                    "store": "user_knowledge_entries", "row_id": e.id, "line_index": idx,
                    "location": f"{e.type} {e.key} · {path}" + ("" if e.active else " (inactive)"),
                    "snippet": snippet, "matched_terms": matched, **side,
                    "reaches_context": _entry_reach(e, path),
                    "action": action, "action_route": route,
                })
    return hits


def sweep_hevy_routines(routines, rx, own_side) -> list[dict[str, Any]]:
    hits = []
    for r in routines or []:
        rtitle = r.get("title") or "Untitled routine"
        fields = [(f"routine '{rtitle}' · notes", r.get("notes") or "")]
        for ex in r.get("exercises") or []:
            fields.append((f"routine '{rtitle}' · {ex.get('title') or 'exercise'} · notes",
                           ex.get("notes") or ""))
        for location, text in fields:
            for idx, snippet, matched, side in _line_hits(text, rx, own_side):
                hits.append({
                    "store": "hevy_routines", "row_id": r.get("id"), "line_index": idx,
                    "location": location, "snippet": snippet, "matched_terms": matched, **side,
                    # Full routine detail (notes included) renders only for the working-set
                    # folder; other routines appear by title only.
                    "reaches_context": "conditional",
                    "action": "none", "action_route": None,
                })
    return hits
