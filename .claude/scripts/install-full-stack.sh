#!/bin/bash
# On-demand FULL app-stack install for Claude Code on the web — NOT wired into
# SessionStart.
#
# WHY THIS IS SEPARATE FROM THE SESSION-START HOOK. The hook installs only the DB
# tooling (sqlalchemy/alembic/psycopg2-binary/python-dotenv/pytest) into the container's
# system Python, fast, on every session. Installing the full backend/requirements.txt
# there was rejected in #122: it drags in python-jose[cryptography], whose PyJWT
# dependency pip cannot cleanly replace over the distro-managed one in the system image,
# and it taxes every cold start whether or not the session touches the app stack.
#
# THE FIX: a throwaway venv. A fresh venv is isolated from the distro site-packages, so
# the python-jose/PyJWT conflict simply does not arise — the full requirements install
# clean. Design call (PR-1, DECISIONS_LOG): tooling fast-and-always in system Python;
# full stack on request, isolated in a venv. Proven, not assumed — this exact path was
# exercised (full install clean; pytz/app-stack test that failed cold in #122 now
# collects and runs 9/9 green under the venv).
#
# WHEN YOU NEED IT: importing the FastAPI app, jose/jwt, pytz, resend, openpyxl, mcp,
# etc. — anything beyond the five tooling packages — e.g. running the full backend test
# suite or booting the app locally in a web session.
#
# USAGE:
#   bash .claude/scripts/install-full-stack.sh
#   .venv/bin/python -m pytest backend/tests            # run against the full stack
#   .venv/bin/python -c "import fastapi, jose, pytz"     # or import the app stack
#
# The venv lives at <repo>/.venv (already in .gitignore) and is rebuilt from scratch each
# run so it can never carry a stale pin. It is ephemeral with the container.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REQ="$ROOT/backend/requirements.txt"
VENV="$ROOT/.venv"

if [ ! -f "$REQ" ]; then
  echo "install-full-stack: $REQ not found" >&2
  exit 1
fi

echo "install-full-stack: (re)building venv at $VENV" >&2
rm -rf "$VENV"
python -m venv "$VENV"

"$VENV/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install --quiet --disable-pip-version-check -r "$REQ"

echo "install-full-stack: full backend stack installed into $VENV" >&2
echo "install-full-stack: run tests with  $VENV/bin/python -m pytest backend/tests" >&2
