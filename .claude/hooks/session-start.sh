#!/bin/bash
# SessionStart hook — install the SQLAlchemy/Alembic tooling so migrations and
# the DB-backed test suite work in Claude Code on the web.
#
# The web container is ephemeral: it is cloned fresh each session with no Python
# packages installed. Without this, `alembic upgrade head` (the Procfile/Railway
# start command) and any code importing `sqlalchemy`/`models` fail with
# ModuleNotFoundError.
#
# Scoped deliberately to the DB tooling — sqlalchemy, alembic, its psycopg2
# driver, python-dotenv (read by database.py / migrations/env.py) and pytest.
# Installing the full backend/requirements.txt is avoided because it drags in
# distro-managed packages (python-jose -> PyJWT) that pip cannot cleanly replace
# in this image. Versions are grep'd out of backend/requirements.txt so the pins
# here never drift from the single source of truth.
#
# Synchronous by design: the tooling is guaranteed present before the agent loop
# runs a migration or a test. Switch to async mode (emit
# `{"async": true, "asyncTimeout": 300000}` as the first line of stdout) if
# faster session startup is preferred over that guarantee.
set -euo pipefail

# Only run in the remote (Claude Code on the web) environment; local machines
# manage their own venvs.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

REQ="${CLAUDE_PROJECT_DIR:-.}/backend/requirements.txt"
if [ ! -f "$REQ" ]; then
  echo "session-start: $REQ not found; skipping tooling install" >&2
  exit 0
fi

# Pull the exact pins from requirements.txt so this hook stays in lockstep with it.
PKGS=$(grep -iE '^(sqlalchemy|alembic|psycopg2-binary|python-dotenv|pytest)==' "$REQ" || true)
if [ -z "$PKGS" ]; then
  echo "session-start: no sqlalchemy/alembic tooling pins found in $REQ" >&2
  exit 0
fi

# pip install is idempotent — a fast no-op once satisfied, and the post-hook
# container cache holds the installed packages for the session.
python -m pip install --quiet --disable-pip-version-check $PKGS

echo "session-start: sqlalchemy/alembic tooling installed:" >&2
echo "$PKGS" | sed 's/^/  /' >&2
