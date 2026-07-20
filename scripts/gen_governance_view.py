#!/usr/bin/env python3
"""Generate CONSOLIDATED_GOVERNANCE_VIEW.md from both repos' governance stores.

Reads the four canonical stores from each of health-app and health-connect-app at
**master**, via raw.githubusercontent.com — never from a local working tree, which may be
dirty or behind. This also sidesteps the single-repo rule: it reads health-connect-app and
never writes it.

Emits a **digest**, not a verbatim dump (DECISIONS_LOG #94). Every digest line carries a
line-anchored GitHub URL, so the view says what exists and where, and master gives detail.

Output is gitignored. A derived artifact is not committed — a committed derivative is a
second thing that goes stale, which is the failure this script exists to remove.

Usage:
    python scripts/gen_governance_view.py [-o build/CONSOLIDATED_GOVERNANCE_VIEW.md]
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

OWNER = "Easty11"
REPOS = ("health-app", "health-connect-app")
STORES = ("DECISIONS_LOG", "OPEN_QUESTIONS", "FEEDBACK", "ROADMAP")

RAW = "https://raw.githubusercontent.com/{owner}/{repo}/{sha}/{store}.md"
BLOB = "https://github.com/{owner}/{repo}/blob/{sha}/{store}.md#L{line}"

BANNER = "═" * 60          # ═
RULE = "─" * 3             # ───
MIDDOT = "·"               # ·
ENDASH = "–"               # –

# A store smaller than this is assumed to be a fetch failure, not a small store.
# The smallest real store at time of writing is health-app/ROADMAP.md at ~5 KB.
MIN_STORE_BYTES = 500


class GenError(RuntimeError):
    """Raised when a gate fails. Never degrade silently — a quiet pass is the bug."""


@dataclass
class Entry:
    """One digest row: its label, title, status, and the line it starts on."""
    label: str
    title: str
    status: str
    line: int


# --------------------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------------------

def resolve_master_sha(repo: str) -> str:
    """Resolve <repo>'s master to a full SHA via git ls-remote.

    Uses ls-remote rather than the GitHub API: no auth, no 60/hr rate limit, and it is the
    same mechanism the branch-disposition rules already rely on.
    """
    url = f"https://github.com/{OWNER}/{repo}.git"
    out = subprocess.run(
        ["git", "ls-remote", url, "refs/heads/master"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if not out:
        raise GenError(f"{repo}: ls-remote returned nothing for refs/heads/master")
    sha = out.split()[0]
    if len(sha) != 40:
        raise GenError(f"{repo}: implausible SHA {sha!r}")
    return sha


def fetch(repo: str, sha: str, store: str) -> str:
    """Fetch one store at a pinned SHA, asserting it is non-empty and plausibly sized.

    The assertion is the point. An extraction that fails silently and yields an empty
    string will compare equal to another empty string and report PASS — the expected
    answer, arrived at by measuring nothing (FEEDBACK §14, occurrence 4).
    """
    url = RAW.format(owner=OWNER, repo=repo, sha=sha, store=store)
    with urllib.request.urlopen(url, timeout=30) as resp:
        if resp.status != 200:
            raise GenError(f"{url} returned HTTP {resp.status}")
        text = resp.read().decode("utf-8")
    if len(text.encode("utf-8")) < MIN_STORE_BYTES:
        raise GenError(
            f"{repo}/{store}.md is {len(text)} bytes — under the {MIN_STORE_BYTES}-byte "
            f"floor. Treating as a fetch failure rather than a small store."
        )
    return text


# --------------------------------------------------------------------------------------
# Parse
#
# The two repos do NOT share store schemas. Every parser below accepts both forms and
# asserts it matched something, because a regex that fits one repo and silently returns
# nothing for the other is the exact failure mode this script is meant to make loud.
# --------------------------------------------------------------------------------------

def _split_inline_status(rest: str) -> tuple[str, str]:
    """Split 'Title  ·  STATUS' into (title, status). HCA puts status inline; health-app
    puts it in a **Status:** line in the body."""
    parts = re.split(r"\s+" + re.escape(MIDDOT) + r"\s+", rest, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return rest.strip(), ""


def _status_from_body(lines: list[str], start: int, end: int) -> str:
    """Pull the first **Status:** line from an entry body and flatten it to one line."""
    for raw in lines[start:end]:
        m = re.match(r"^\*\*Status:\*\*\s*(.+)$", raw)
        if m:
            return m.group(1).strip()
    return ""


def _first_body_line(lines: list[str], start: int, end: int) -> str:
    for raw in lines[start:end]:
        s = raw.strip()
        if s and not s.startswith("#"):
            return s
    return ""


def _parse_headed(text: str, pattern: re.Pattern, store: str, repo: str,
                  status_mode: str) -> list[Entry]:
    """Generic heading-driven parser shared by DECISIONS_LOG / OPEN_QUESTIONS / FEEDBACK.

    status_mode: 'entry'  -> inline '·' status, else **Status:** from the body
                 'first'  -> first non-empty body line (FEEDBACK has no status field)
    """
    lines = text.splitlines()
    hits: list[tuple[int, str, str]] = []
    for i, raw in enumerate(lines):
        m = pattern.match(raw)
        if m:
            hits.append((i, m.group(1), m.group(2) if m.lastindex >= 2 else ""))

    if not hits:
        raise GenError(
            f"{repo}/{store}.md: heading pattern {pattern.pattern!r} matched ZERO entries. "
            f"The store's schema has changed, or the pattern is wrong for this repo. "
            f"Refusing to emit an empty section that would read as 'nothing here'."
        )

    entries: list[Entry] = []
    for idx, (line_i, label, rest) in enumerate(hits):
        end = hits[idx + 1][0] if idx + 1 < len(hits) else len(lines)
        title, inline = _split_inline_status(rest)
        if status_mode == "first":
            status = _first_body_line(lines, line_i + 1, end)
        else:
            status = inline or _status_from_body(lines, line_i + 1, end)
        entries.append(Entry(label=label, title=title, status=status, line=line_i + 1))
    return entries


def parse_decisions(text: str, repo: str) -> list[Entry]:
    # health-app '### 93. Title' | health-connect-app '### #20 — Title  ·  active'
    pat = re.compile(r"^###\s+#?(\d+)\s*[.—-]?\s*(.*)$")
    entries = _parse_headed(text, pat, "DECISIONS_LOG", repo, "entry")

    # Free gap check: for an append-only, sequentially-numbered store, the highest number
    # should equal the entry count. A mismatch means a gap or a duplicate — surface it.
    nums = [int(e.label) for e in entries]
    if max(nums) != len(nums):
        print(
            f"  ! {repo}/DECISIONS_LOG.md: highest #{max(nums)} but {len(nums)} entries "
            f"— gap or duplicate in the sequence.",
            file=sys.stderr,
        )
    return entries


def parse_questions(text: str, repo: str) -> list[Entry]:
    # health-app '## Q33. Title' | health-connect-app '### Q11 — Title  ·  OWED'
    pat = re.compile(r"^#{2,3}\s+Q(\d+)\s*[.—-]?\s*(.*)$")
    return _parse_headed(text, pat, "OPEN_QUESTIONS", repo, "entry")


def parse_feedback(text: str, repo: str) -> list[Entry]:
    """health-app '## 15. Title' | health-connect-app '### 2026-07-20 — title  [tag]'.

    The heading LEVEL is load-bearing and differs per repo, so this cannot be a lenient
    '#{2,3}' match. health-app nests subsections as '### 1.1', '### 2.6' under each
    top-level '## N.' section; a lenient pattern sweeps those in and reports 52 entries
    for a store that has 15. HCA's dated entries sit at '###' with no subsections, and its
    '### YYYY-MM-DD — short title  [tag]' format template is excluded by requiring digits.
    """
    pat = re.compile(r"^(?:##\s+(\d+)\.|###\s+(\d{4}-\d{2}-\d{2})\s*[—-])\s*(.*)$")

    lines = text.splitlines()
    hits: list[tuple[int, str, str]] = []
    for i, raw in enumerate(lines):
        m = pat.match(raw)
        if m:
            hits.append((i, m.group(1) or m.group(2), m.group(3)))
    if not hits:
        raise GenError(
            f"{repo}/FEEDBACK.md: matched ZERO entries. Schema changed, or the pattern is "
            f"wrong for this repo. Refusing to emit an empty section."
        )

    entries: list[Entry] = []
    for idx, (line_i, label, rest) in enumerate(hits):
        end = hits[idx + 1][0] if idx + 1 < len(hits) else len(lines)
        title, _ = _split_inline_status(rest)
        entries.append(Entry(label=label, title=title,
                             status=_first_body_line(lines, line_i + 1, end),
                             line=line_i + 1))
    return entries


def parse_roadmap(text: str, repo: str) -> list[tuple[str, list[tuple[str, int]]]]:
    """Return [(section heading, [(table row, line), ...]), ...].

    Emits EVERY top-level section rather than filtering to NOW/NEXT/LATER. health-app uses
    those names; health-connect-app uses 'Now' / 'Work queue' / 'Phase 2' / 'UI debt' and
    others. A three-name filter would emit an empty HCA roadmap and look like it worked.

    Captures BOTH table rows and bullet items, because the row format differs per repo the
    same way the section names do: health-app's roadmap is '| Item | Notes |' tables,
    health-connect-app's is bullet lists. A table-only parser returns 4 rows for HCA — all
    of them from an unrelated stats table — and silently drops its entire work queue.
    """
    lines = text.splitlines()
    sections: list[tuple[str, list[tuple[str, int]]]] = []
    current: str | None = None
    rows: list[tuple[str, int]] = []

    for i, raw in enumerate(lines):
        if re.match(r"^##\s+\S", raw):
            if current is not None:
                sections.append((current, rows))
            current = raw.lstrip("# ").strip()
            rows = []
        elif current is not None and raw.startswith("|"):
            if re.match(r"^\|[\s|:-]+\|?\s*$", raw):   # separator row
                continue
            cells = [c.strip() for c in raw.strip().strip("|").split("|")]
            if cells and cells[0].lower() in ("item", "store", "branch", "task"):
                continue                                # header row
            if any(cells):
                rows.append((raw.strip(), i + 1))
        elif current is not None and re.match(r"^[-*]\s+\S", raw):
            rows.append((raw.strip(), i + 1))

    if current is not None:
        sections.append((current, rows))
    if not sections:
        raise GenError(f"{repo}/ROADMAP.md: no '## ' sections found — schema changed?")
    return sections


# --------------------------------------------------------------------------------------
# Emit
# --------------------------------------------------------------------------------------

def anchor(repo: str, sha: str, store: str, line: int) -> str:
    return BLOB.format(owner=OWNER, repo=repo, sha=sha, store=store, line=line)


def truncate(s: str, n: int = 160) -> str:
    """Flatten to one line and cap. Digest lines must stay one-per-entry."""
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def store_separator(repo: str, store: str, paren: str = "") -> str:
    label = f"STORE: {repo} / {store}.md"
    if paren:
        label += f"  ({paren})"
    return f"{RULE} {label} {RULE}"


def repo_banner(repo: str, sha: str, dmax: int) -> list[str]:
    """Banner block: one blank line before, three after (format spec).

    Emits no leading blank of its own — the caller normalises whatever precedes it to
    exactly one, so the gap does not depend on whether the previous section happened to
    end with a blank line.
    """
    label = (f"REPO: {repo}   {MIDDOT}   master {sha[:7]}   {MIDDOT}   "
             f"DECISIONS_LOG #{dmax}")
    return [BANNER, label, BANNER, "", "", ""]


def append_banner(out: list[str], block: list[str]) -> None:
    """Append a banner block preceded by exactly one blank line."""
    while out and out[-1] == "":
        out.pop()
    out.append("")
    out += block


def build(data: dict, generated: str) -> tuple[list[str], dict]:
    out: list[str] = []
    counts: dict[str, tuple[int, int]] = {}   # store key -> (entries parsed, lines emitted)

    # Em dash in the title; ENDASH is reserved for numeric ranges, per the format spec.
    out.append("# CONSOLIDATED GOVERNANCE VIEW — health-app + health-connect-app")
    out.append("")
    out.append("> **READ-ONLY. Do not edit this file.** It is *generated* by")
    out.append("> `scripts/gen_governance_view.py` in health-app, from both repos' stores")
    out.append("> read at **master**. Edits here are overwritten on the next run and never")
    out.append("> reach a repo. This is a **digest with anchors**, not a copy: it tells you")
    out.append("> what exists and where. Master is canonical for detail — follow a link.")
    out.append("> Regenerate: `python scripts/gen_governance_view.py`")
    out.append("")
    out.append("## Provenance")
    out.append("")
    out.append("| Repo | Source ref | Stores | Highest decision | As of |")
    out.append("|------|-----------|--------|------------------|-------|")
    for repo in REPOS:
        d = data[repo]
        out.append(
            f"| `{repo}` | `master` @ `{d['sha'][:7]}` | {len(STORES)} "
            f"| #{d['dmax']} | {generated} |"
        )
    out.append("")
    out.append("## Numbering is PER-REPO and native")
    out.append("")
    out.append("Each repo numbers its own decisions and questions from #1. "
               "`health-app #20` and")
    out.append("`health-connect-app #20` are **different decisions**. Numbers here are "
               "native to their")
    out.append("repo and are never renumbered into a shared sequence — always cite "
               "them repo-qualified.")
    out.append("")

    for repo in REPOS:
        d = data[repo]
        sha = d["sha"]
        append_banner(out, repo_banner(repo, sha, d["dmax"]))

        # DECISIONS_LOG
        ents = d["DECISIONS_LOG"]
        rng = f"native #{min(int(e.label) for e in ents)}{ENDASH}#{max(int(e.label) for e in ents)}"
        out.append(store_separator(repo, "DECISIONS_LOG", rng))
        out.append("")
        n = 0
        for e in ents:
            link = anchor(repo, sha, "DECISIONS_LOG", e.line)
            status = f" {MIDDOT} {truncate(e.status, 90)}" if e.status else ""
            out.append(f"- [`#{e.label}`]({link}) {MIDDOT} {truncate(e.title)}{status}")
            n += 1
        counts[f"{repo}/DECISIONS_LOG"] = (len(ents), n)
        out.append("")

        # OPEN_QUESTIONS
        ents = d["OPEN_QUESTIONS"]
        paren = ""
        if repo == "health-connect-app":
            qs = sorted(int(e.label) for e in ents)
            paren = f"Q{qs[0]}{ENDASH}Q{qs[-1]}"
        out.append(store_separator(repo, "OPEN_QUESTIONS", paren))
        out.append("")
        n = 0
        for e in ents:
            link = anchor(repo, sha, "OPEN_QUESTIONS", e.line)
            status = f" {MIDDOT} {truncate(e.status, 110)}" if e.status else ""
            out.append(f"- [`Q{e.label}`]({link}) {MIDDOT} {truncate(e.title)}{status}")
            n += 1
        counts[f"{repo}/OPEN_QUESTIONS"] = (len(ents), n)
        out.append("")

        # FEEDBACK
        ents = d["FEEDBACK"]
        out.append(store_separator(repo, "FEEDBACK"))
        out.append("")
        n = 0
        for e in ents:
            link = anchor(repo, sha, "FEEDBACK", e.line)
            head = truncate(e.title) if e.title else truncate(e.status)
            tail = f" {MIDDOT} {truncate(e.status, 110)}" if e.title and e.status else ""
            out.append(f"- [`{e.label}`]({link}) {MIDDOT} {head}{tail}")
            n += 1
        counts[f"{repo}/FEEDBACK"] = (len(ents), n)
        out.append("")

        # ROADMAP
        out.append(store_separator(repo, "ROADMAP"))
        out.append("")
        n = 0
        for heading, rows in d["ROADMAP"]:
            out.append(f"**{heading}**")
            out.append("")
            for row, line in rows:
                link = anchor(repo, sha, "ROADMAP", line)
                if row.startswith("|"):
                    cells = [c.strip() for c in row.strip().strip("|").split("|")]
                    item = truncate(cells[0], 90) if cells else ""
                    note = truncate(cells[1], 110) if len(cells) > 1 else ""
                else:
                    # Bullet form (health-connect-app). Strip the marker so it does not
                    # end up inside the link text and break the emitted markdown.
                    item, note = truncate(re.sub(r"^[-*]\s+", "", row), 140), ""
                sep = f" {MIDDOT} {note}" if note else ""
                out.append(f"- [{item}]({link}){sep}")
                n += 1
            out.append("")
        counts[f"{repo}/ROADMAP"] = (sum(len(r) for _, r in d["ROADMAP"]), n)

    append_banner(out, [
        BANNER,
        f"END CONSOLIDATED GOVERNANCE VIEW   {MIDDOT}   generated {generated}",
        BANNER,
        "",
    ])
    return out, counts


# --------------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--out", default="build/CONSOLIDATED_GOVERNANCE_VIEW.md")
    args = ap.parse_args()

    parsers = {
        "DECISIONS_LOG": parse_decisions,
        "OPEN_QUESTIONS": parse_questions,
        "FEEDBACK": parse_feedback,
        "ROADMAP": parse_roadmap,
    }

    data: dict = {}
    for repo in REPOS:
        sha = resolve_master_sha(repo)
        print(f"  {repo}: master @ {sha[:7]}", file=sys.stderr)
        d: dict = {"sha": sha}
        for store in STORES:
            text = fetch(repo, sha, store)
            d[store] = parsers[store](text, repo)
            got = (sum(len(r) for _, r in d[store]) if store == "ROADMAP"
                   else len(d[store]))
            print(f"    {store}.md: {len(text):>7} B -> {got} entries", file=sys.stderr)
        d["dmax"] = max(int(e.label) for e in d["DECISIONS_LOG"])
        data[repo] = d

    # Offset-explicit, not name-dependent: Windows renders %Z as "E. Australia Standard
    # Time", and Git Bash silently ignores TZ and mislabels UTC as local. A numeric offset
    # cannot be misread by either.
    generated = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %z")
    lines, counts = build(data, generated)

    # Gate: every digest section emitted exactly one line per parsed entry.
    for key, (parsed, emitted) in sorted(counts.items()):
        if parsed != emitted:
            raise GenError(f"{key}: parsed {parsed} entries but emitted {emitted} lines")
    if len(counts) != len(REPOS) * len(STORES):
        raise GenError(
            f"expected {len(REPOS) * len(STORES)} store sections, got {len(counts)}"
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # UTF-8 + LF explicitly: the box-drawing characters are load-bearing and mangle under
    # CP1252, which is the Windows default this repo runs on.
    with out_path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))

    print(f"\n  wrote {out_path} — {len(lines)} lines", file=sys.stderr)
    for key, (parsed, emitted) in sorted(counts.items()):
        print(f"    {key:<38} {parsed:>4} entries = {emitted:>4} lines", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GenError as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        sys.exit(1)
