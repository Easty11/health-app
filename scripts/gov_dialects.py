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
# coerced into a neighbour (DECISIONS_LOG #190). Questions carry OPEN/OWED/DONE per the
# byte-identical shared block; a question headed UNSTARTED/BLOCKED is work-item vocabulary
# bleeding in — store debt, flagged as drift, not a first-class dialect.
# --------------------------------------------------------------------------------------
QUESTION_STATES = ("OPEN", "OWED", "DONE")
WORK_ITEM_STATES = ("DONE", "BLOCKED", "OWED", "UNSTARTED")
ALL_STATES = tuple(sorted(set(QUESTION_STATES) | set(WORK_ITEM_STATES)))

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
    extraction gate turns into a HALT if it holds across every entry in a store."""
    _title, inline = split_inline_state(rest)
    return inline or state_from_body(lines, line_i + 1, end)


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
