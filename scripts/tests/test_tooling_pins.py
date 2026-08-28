"""Tooling-manifest drift guard (PR-1 step 3).

The SessionStart hook installs the DB tooling from `.claude/requirements-tooling.txt`
instead of grepping backend/requirements.txt. That is only safe if the manifest cannot
silently drift from its source of truth — so this proves the guard both HOLDS on the
real tree and BITES on injected drift (version and membership, both directions).
"""
from pathlib import Path

import check_tooling_pins as C


# --- the live invariant: the committed manifest is in lockstep ------------------------------- #

def test_real_manifest_is_in_lockstep():
    """The tree as committed must pass — a red bar here means a real drift to fix."""
    assert C.check() == []


def test_manifest_covers_exactly_the_canonical_tooling_set():
    manifest = C._parse_pins(C.MANIFEST)
    assert set(manifest) == C.CANONICAL_TOOLING


# --- the guard bites: injected drift is caught ---------------------------------------------- #

def _point_at(monkeypatch, tmp_path, manifest_body: str, backend_body: str):
    man = tmp_path / "requirements-tooling.txt"
    back = tmp_path / "requirements.txt"
    man.write_text(manifest_body, encoding="utf-8")
    back.write_text(backend_body, encoding="utf-8")
    monkeypatch.setattr(C, "MANIFEST", man)
    monkeypatch.setattr(C, "BACKEND_REQS", back)


# A minimal backend that pins every canonical tooling package (plus an app-only one).
_BACKEND = (
    "sqlalchemy==2.0.50\n"
    "alembic==1.18.4\n"
    "psycopg2-binary==2.9.12\n"
    "python-dotenv==1.2.2\n"
    "pytest==9.1.1\n"
    "fastapi==0.136.3\n"
)
_MANIFEST_OK = (
    "# comment\n"
    "sqlalchemy==2.0.50\n"
    "alembic==1.18.4\n"
    "psycopg2-binary==2.9.12\n"
    "python-dotenv==1.2.2\n"
    "pytest==9.1.1\n"
)


def test_synthetic_lockstep_passes(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path, _MANIFEST_OK, _BACKEND)
    assert C.check() == []


def test_version_drift_is_caught(monkeypatch, tmp_path):
    """Bump the manifest's sqlalchemy pin away from the backend's — must be reported."""
    drifted = _MANIFEST_OK.replace("sqlalchemy==2.0.50", "sqlalchemy==2.0.49")
    _point_at(monkeypatch, tmp_path, drifted, _BACKEND)
    problems = C.check()
    assert any("sqlalchemy" in p and "2.0.49" in p for p in problems), problems


def test_dropped_package_is_caught(monkeypatch, tmp_path):
    """Drop pytest from the manifest — the hook would stop installing it."""
    dropped = _MANIFEST_OK.replace("pytest==9.1.1\n", "")
    _point_at(monkeypatch, tmp_path, dropped, _BACKEND)
    problems = C.check()
    assert any("pytest" in p and "absent" in p for p in problems), problems


def test_extra_non_tooling_package_is_caught(monkeypatch, tmp_path):
    """A package outside the canonical tooling set has no business in the manifest."""
    extra = _MANIFEST_OK + "fastapi==0.136.3\n"
    _point_at(monkeypatch, tmp_path, extra, _BACKEND)
    problems = C.check()
    assert any("fastapi" in p for p in problems), problems
