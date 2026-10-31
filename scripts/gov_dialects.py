#!/usr/bin/env python3
"""Single source of truth for governance-store DIALECTS.

health-app and health-connect-app do NOT share store schemas. Both `gen_governance_view.py`
(human-readable markdown digest) and `gen_status_model.py` (append-only machine JSON) parse
those stores, so the heading/state grammar MUST live in exactly one place — otherwise the two
tools carry independent copies of the dialect knowledge and drift apart unnoticed. That drift
is not hypothetical: `gen_governance_view` matched a question's state as `**Status:**` while
health-app questions use `**State:**`, so every health-app question rendered with an empty
status and the existing count gates never saw it (heading counts still matched). See
DECISIONS_LOG #190 (extraction gate) and #191 (this module).

SCOPE — dialect grammar ONLY: heading regexes, state-line labels, vocabulary sets, and the
small extractors/classifiers over them. NOT fetch, NOT emit, NOT gates. Fetch and gate logic
stay in each tool so this module's blast radius is the grammar and nothing else.
"""

from __future__ import annotations

import re

OWNER = "Easty11"
REPOS = ("health-app", "health-connect-app")

MIDDOT = "·"  # ·  — HCA puts inline state after this on the heading line.

# --------------------------------------------------------------------------------------
# Heading grammar — one pattern each, spanning both dialects.
# --------------------------------------------------------------------------------------
# health-app '### 189. Title'        |  HCA '### #20 — Title  ·  active'
DECISION_HEADING = re.compile(r"^###\s+#?(\d+)\s*[.—–-]?\s*(.*)$")
# health-app '## Q88. Title'         |  HCA '### Q11 — Title  ·  OWED'
QUESTION_HEADING = re.compile(r"^#{2,3}\s+Q(\d+)\s*[.—–-]?\s*(.*)$")

# A body state line. Matching EITHER label is the fix for the #190 bug: health-app puts a
# question's state in '**State:**' and a decision's in '**Status:**'; an entry has one or the
# other, so accepting both is safe and loses neither.
STATE_LINE = re.compile(r"^\*\*(?:State|Status):\*\*\s*(.+)$")

# --------------------------------------------------------------------------------------
# Vocabularies — a token outside the RELEVANT set is OFF-VOCAB: tallied and reported, never
# coerced into a neighbour (DECISIONS_LOG #190). The shared question vocabulary is OPEN/OWED/
# DONE per the byte-identical shared block; a health-app question headed UNSTARTED/BLOCKED is
# work-item vocabulary bleeding in — store debt, flagged as drift, not a first-class dialect.
# HCA is the ONE exception, handled PER-REPO below (never in this shared tuple): it authors
# not-begun questions with UNSTARTED, so UNSTARTED is a recognised question state FOR HCA
# ONLY. Per-repo, so recognising HCA's dialect cannot silence health-app's drift signal.
# --------------------------------------------------------------------------------------
QUESTION_STATES = ("OPEN", "OWED", "DONE")            # health-app / default
WORK_ITEM_STATES = ("DONE", "BLOCKED", "OWED", "UNSTARTED")
# UNSTARTED already lives in WORK_ITEM_STATES, so ALL_STATES (which gates inline extraction)
# contains it regardless of the question tuple — an HCA '· UNSTARTED' inline is extracted, then
# classified against the PER-REPO vocab below (drift for health-app, clean for HCA).
ALL_STATES = tuple(sorted(set(QUESTION_STATES) | set(WORK_ITEM_STATES)))

# Per-repo question vocabularies (NOT a shared tuple). HCA recognises UNSTARTED (not-begun is a
# distinct authored state from in-flight OPEN — never aliased); health-app does not, so an
# UNSTARTED on a health-app question stays off-vocab drift (the store-debt signal above).
QUESTION_STATES_BY_REPO = {
    "health-app": ("OPEN", "OWED", "DONE"),
    "health-connect-app": ("OPEN", "OWED", "DONE", "UNSTARTED"),
}


def question_states(repo: str) -> tuple[str, ...]:
    """The question-state vocabulary for a repo — per-repo, never the shared tuple. UNSTARTED is
    a valid question state for HCA only; on a health-app question it stays off-vocab drift."""
    return QUESTION_STATES_BY_REPO.get(repo, QUESTION_STATES)

# HCA decisions carry state as a LOWERCASE inline '· <token>' segment on the heading — a
# dialect neither the caps vocab above nor the '**Status:**' body line (health-app decisions)
# covers. Enumerated empirically from all 35 HCA decisions at master (census 2026-08):
# 'active' ×34, 'held' ×1 — the only state tokens present. Lineage notes ('supersedes' /
# 'clarifies' / 'rider' / 'repair') also appear as '·' segments but are NOT state. A lowercase
# inline token outside this set is never coerced — it falls through to 'unstated' (surfaced,
# prompting re-enumeration). Kept separate from the caps vocab so it cannot leak into question
# parsing.
DECISION_INLINE_STATES = ("active", "held")

_LEADING_TOKEN = re.compile(r"[A-Z]+")


def canonical_token(raw: str) -> str:
    """The leading ALL-CAPS state word of a raw state string, after stripping markdown.

    '`DONE → #64` — superseded' -> 'DONE'   '**BLOCKED** — waiting' -> 'BLOCKED'
    'OPEN — the precondition'    -> 'OPEN'   'active'                -> ''  (lowercase)

    Anchored at the start (post-strip) so prose later in the line cannot masquerade as the
    state. Returns '' when the string does not lead with an all-caps token.
    """
    if not raw:
        return ""
    s = raw.lstrip("`*_ \t")
    m = _LEADING_TOKEN.match(s)
    return m.group(0) if m else ""


def classify(raw: str, vocab: tuple[str, ...]) -> tuple[str | None, bool]:
    """Return (token, off_vocab).

    - empty / no leading caps token -> (None, False): ABSENCE, distinct from off-vocab and
      caught separately by the extraction gate.
    - token in vocab                -> (token, False)
    - token not in vocab            -> (token, True): off-vocab, to be tallied not dropped.
    """
    tok = canonical_token(raw)
    if not tok:
        return None, False
    return tok, tok not in vocab


# --------------------------------------------------------------------------------------
# Extractors over the grammar above.
# --------------------------------------------------------------------------------------

def split_inline_state(rest: str) -> tuple[str, str]:
    """Split a heading remainder 'Title  ·  OWED' into ('Title', 'OWED').

    Only treats the trailing segment as state when it leads with a KNOWN state token, so a
    '·' inside a title cannot be misread as an inline state. Returns ('Title', '') otherwise.
    """
    if MIDDOT in rest:
        title, tail = rest.rsplit(MIDDOT, 1)
        if canonical_token(tail) in ALL_STATES:
            return title.strip(), tail.strip()
    return rest.strip(), ""


def state_from_body(lines: list[str], start: int, end: int) -> str:
    """First '**State:**'/'**Status:**' line in an entry body, flattened to its value."""
    for raw in lines[start:end]:
        m = STATE_LINE.match(raw)
        if m:
            return m.group(1).strip()
    return ""


def entry_state(lines: list[str], line_i: int, rest: str, end: int) -> str:
    """Raw state string for one entry, dialect-agnostic: inline (HCA) first, else the
    '**State:**'/'**Status:**' body line (health-app). '' when neither is present — which the
    extraction gate turns into a HALT if it holds across every entry in a store.

    NOTE: this is the QUESTION/caps path (split_inline_state gates on ALL_STATES). Decisions
    use decision_state below — a separate reader for the lowercase HCA decision dialect that
    must never leak into question parsing."""
    _title, inline = split_inline_state(rest)
    return inline or state_from_body(lines, line_i + 1, end)


def decision_inline_state(rest: str) -> str:
    """The lowercase inline decision-state token in a heading remainder, or '' if none.

    HCA decisions carry state as a lowercase '· <token>' segment (health-app decisions use a
    '**Status:**' body line instead). SCANS '·' segments for a DECISION_INLINE_STATES member,
    returned as-authored — not rsplit-last, because 6 of HCA's 35 carry a lineage note
    ('· supersedes #10') as the TRAILING segment, so the state is not always last. Distinct
    from split_inline_state (caps vocab) so the HCA decision dialect never leaks into questions."""
    if MIDDOT not in rest:
        return ""
    for seg in rest.split(MIDDOT)[1:]:
        words = seg.strip().split()
        if words and words[0].strip("`*").lower() in DECISION_INLINE_STATES:
            return words[0].strip("`*").lower()
    return ""


def decision_state(lines: list[str], line_i: int, rest: str, end: int) -> str:
    """Best-effort decision state, dialect-agnostic: HCA lowercase inline first, else the
    health-app '**Status:**' body line. '' means genuinely UNSTATED — a legitimate,
    optional-by-convention absence for decisions (intent-only / ledger-meta entries), NOT a
    parser miss, and NEVER extraction-gated. The caller presents '' as `unstated`."""
    return decision_inline_state(rest) or state_from_body(lines, line_i + 1, end)


def is_table_data_row(line: str) -> bool:
    """True for a pipe-table DATA row — excludes the header (first cell 'Branch') and the
    '|---|' separator. Dialect-agnostic: health-app backtick-quotes branch names, HCA does
    not, but both are '| Branch | ... |' tables, so row identity keys off the pipe structure,
    never the cell contents."""
    if not line.startswith("|"):
        return False
    if re.match(r"^\|[\s:|-]+\|?\s*$", line):          # separator
        return False
    if re.match(r"^\|\s*Branch\s*\|", line):           # header
        return False
    return True


def table_cells(line: str) -> list[str]:
    """Split a pipe-table row into trimmed cells, dropping the empty edges."""
    return [c.strip() for c in line.strip().strip("|").split("|")]
