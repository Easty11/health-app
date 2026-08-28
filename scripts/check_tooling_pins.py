#!/usr/bin/env python
"""Refuse to let the web-session tooling manifest drift from backend/requirements.txt.

`.claude/hooks/session-start.sh` used to `grep` its pins straight out of
backend/requirements.txt, so the hook could never install a version the source of
truth did not name. Retiring that grep for a committed manifest
(`.claude/requirements-tooling.txt`, DECISIONS_LOG) trades grep-fragility for a new
failure mode: the manifest and backend/requirements.txt can silently disagree. This
check closes it, and closes BOTH directions of drift:

  * VERSION drift  — a tooling pin is bumped in backend/requirements.txt (or the
    manifest) and the other side is not. The manifest would then install a version the
    backend no longer uses.
  * MEMBERSHIP drift — a package is dropped from (or spuriously added to) the manifest,
    so the hook installs the wrong SET. A dropped package reappears as a mid-session
    ModuleNotFoundError — exactly what the hook exists to prevent.

The canonical tooling set is named here, not derived, so the check has an opinion about
what the hook is supposed to install rather than trusting whatever the manifest happens
to list. It matches the historical grep alternation in the hook.

Exit 0 if the manifest is in lockstep; exit 1 with a per-line report otherwise. No
third-party imports — runs on the bare interpreter, same as the hook's environment.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# The DB tooling the SessionStart hook installs into the web container. Mirrors the
# alternation the hook used to grep (`sqlalchemy|alembic|psycopg2-binary|python-dotenv
# |pytest`). Add a package here and to the manifest in the same change.
CANONICAL_TOOLING = {
    "sqlalchemy",
    "alembic",
    "psycopg2-binary",
    "python-dotenv",
    "pytest",
}

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / ".claude" / "requirements-tooling.txt"
BACKEND_REQS = REPO_ROOT / "backend" / "requirements.txt"

# name==version, ignoring extras (`pydantic[email]`) and surrounding whitespace.
_PIN = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*==\s*([^\s#]+)\s*$")


def _parse_pins(path: Path) -> dict[str, str]:
    """Map lower-cased package name -> pinned version, skipping comments/blanks."""
    pins: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _PIN.match(line)
        if m:
            pins[m.group(1).lower()] = m.group(2)
    return pins


def check() -> list[str]:
    """Return a list of human-readable problems; empty means the manifest is clean."""
    problems: list[str] = []

    for path in (MANIFEST, BACKEND_REQS):
        if not path.is_file():
            problems.append(f"missing file: {path}")
    if problems:
        return problems

    manifest = _parse_pins(MANIFEST)
    backend = _parse_pins(BACKEND_REQS)

    manifest_names = set(manifest)

    missing = CANONICAL_TOOLING - manifest_names
    for name in sorted(missing):
        problems.append(
            f"{name}: in the canonical tooling set but absent from the manifest "
            f"({MANIFEST.name}). The hook would stop installing it → mid-session "
            f"ModuleNotFoundError."
        )

    extra = manifest_names - CANONICAL_TOOLING
    for name in sorted(extra):
        problems.append(
            f"{name}: pinned in the manifest but not in the canonical tooling set. "
            f"Add it to CANONICAL_TOOLING in {Path(__file__).name} if it is meant to "
            f"be tooling, or drop it from the manifest."
        )

    # Version lockstep, for every package the manifest and backend both name.
    for name in sorted(manifest_names & set(backend)):
        if manifest[name] != backend[name]:
            problems.append(
                f"{name}: manifest pins {manifest[name]} but backend/requirements.txt "
                f"pins {backend[name]}. Bring them into lockstep."
            )

    # A canonical tooling package that the backend does not pin at all is drift too:
    # the hook installs an unversioned floor the backend never chose.
    for name in sorted(CANONICAL_TOOLING & manifest_names):
        if name not in backend:
            problems.append(
                f"{name}: in the manifest but not pinned in backend/requirements.txt "
                f"(its source of truth)."
            )

    return problems


def main() -> int:
    problems = check()
    if problems:
        print(
            "tooling-pins: .claude/requirements-tooling.txt is out of lockstep with "
            "backend/requirements.txt:",
            file=sys.stderr,
        )
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print("tooling-pins: manifest in lockstep with backend/requirements.txt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
