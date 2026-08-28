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
# in this image; for the full stack on demand, use the isolated venv path in
# .claude/scripts/install-full-stack.sh (not wired here — it must not tax cold start).
#
# Pins come from the committed manifest .claude/requirements-tooling.txt, kept in
# lockstep with backend/requirements.txt by scripts/check_tooling_pins.py. (This
# replaced grepping requirements.txt at run time: the manifest is reviewable and
# cannot pick up a package requirements.txt happens to add.)
#
# Fail loud (set -euo pipefail): a missing manifest or a failed pip line exits the
# hook non-zero so session start aborts visibly, rather than proceeding into a
# mid-task ModuleNotFoundError from a half-install.
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

MANIFEST="${CLAUDE_PROJECT_DIR:-.}/.claude/requirements-tooling.txt"
if [ ! -f "$MANIFEST" ]; then
  echo "session-start: tooling manifest $MANIFEST not found — cannot install DB tooling" >&2
  exit 1
fi

# pip install is idempotent — a fast no-op once satisfied, and the post-hook
# container cache holds the installed packages for the session. A non-zero exit
# here propagates under set -e and aborts session start.
python -m pip install --quiet --disable-pip-version-check -r "$MANIFEST"

echo "session-start: sqlalchemy/alembic tooling installed from $MANIFEST:" >&2
# Informational echo of the installed pins — must never fail the hook (pipefail),
# so tolerate grep's exit 1 on a hypothetical all-comment manifest.
{ grep -vE '^\s*(#|$)' "$MANIFEST" || true; } | sed 's/^/  /' >&2
