#!/usr/bin/env python
"""Refuse to let an unresolved governance placeholder reach master.

Number-at-merge says a new entry is headed `### #NEXT` on a branch and claims its
integer when the governance commit fast-forwards. Nothing enforced the second half. The
placeholder rode master for three sessions: `feat/hub-shell` merged with its heading
still reading `#NEXT`, #163 and #164 were then minted on top of it, and #162 became a
hole in the canonical store. The fix kept being written on branches that did not merge.

WHY A REF CHECK AND NOT A `git land` GUARD. The merge that finally healed it was done by
hand — `git checkout master && git merge --ff-only && git push` — not through the `land`
alias. A guard living only in that alias would not have fired for it, which is the whole
failure mode: the placeholder reaches master by whichever path is convenient that day.
So the check runs against the ref being pushed, and the alias calls the same script.

Exit 0 = clean. Exit 1 = a placeholder would reach master. Exit 2 = the check itself
could not run (missing file, bad ref) — never silently pass, because a check that cannot
run is not a check that passed.

Usage:
    python scripts/check_governance_placeholders.py              # working tree
    python scripts/check_governance_placeholders.py --ref HEAD   # a commit
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Anchored, never a bare substring (#113): a corrected entry legitimately QUOTES the
# token it superseded, and several do. Anchoring on the heading form means prose about
# the convention — CLAUDE.md's own rule text, #148's entry, historical BRANCHES rows —
# is not a false positive, and the matches are printed so they are read, not counted.
#
# HEADING LEVEL IS TOLERATED, HEADING FORM IS NOT. This script is one implementation of
# one rule across every repo in the project, so it must match each repo's grammar. The
# two stores do not agree on level: `health-app/OPEN_QUESTIONS.md` heads a question `##
# Q77.` while `health-connect-app/OPEN_QUESTIONS.md` heads it `### Q8 — …  ·  OWED`
# (verified against both trees 2026-08-04). A `^## Q#NEXT`-only pattern therefore reads
# HCA as permanently clean — installed, green, and blind, which is worse than absent
# because the next session stops checking by hand. `{2,3}` covers both without loosening
# the anchor: the token must still open a heading. Decision headings are `### ` in both
# repos today; the level is generalised there too so the two arms cannot drift apart.
CHECKS = [
    ("DECISIONS_LOG.md", re.compile(r"^#{2,3} #NEXT\b.*$", re.M), "a #NEXT decision heading"),
    ("OPEN_QUESTIONS.md", re.compile(r"^#{2,3} Q#NEXT\b.*$", re.M), "a Q#NEXT question heading"),
]


def read(path: str, ref: str | None) -> str:
    if ref is None:
        p = Path(path)
        if not p.exists():
            print(f"check-placeholders: cannot read {path}", file=sys.stderr)
            sys.exit(2)
        return p.read_text(encoding="utf-8")
    r = subprocess.run(["git", "show", f"{ref}:{path}"],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(f"check-placeholders: cannot read {path} at {ref}: "
              f"{r.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return r.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=None,
                    help="git ref to check; omit to check the working tree")
    args = ap.parse_args()

    offences: list[str] = []
    for path, pattern, label in CHECKS:
        text = read(path, args.ref)
        for m in pattern.finditer(text):
            line_no = text.count("\n", 0, m.start()) + 1
            offences.append(f"  {path}:{line_no}  {m.group(0)[:100]}")

    if not offences:
        return 0

    where = args.ref or "the working tree"
    print(f"\nREFUSED: unresolved governance placeholder in {where}.\n",
          file=sys.stderr)
    print("\n".join(offences), file=sys.stderr)
    print(
        "\nNumber-at-merge: claim the integer ON THE BRANCH, before the fast-forward,"
        "\nre-reading master's max at that instant. Resolve every token the branch"
        "\nintroduced (#148 — classified, not counted) and leave every token it did not."
        "\n\nAudit after resolving:"
        "\n  python scripts/check_governance_placeholders.py"
        "\n\nThis check exists because the placeholder reached master three sessions"
        "\nrunning and left a permanent hole at #162.\n",
        file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
