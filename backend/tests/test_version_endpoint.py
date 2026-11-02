"""`GET /version`: the commit this instance was built from, for the post-deploy check (#433).

Public and read-only like /health, one value. `commit` is null (never an empty string, never a guess) when
Railway's `RAILWAY_GIT_COMMIT_SHA` is absent, so the check reads a missing variable as a FAILURE. It is
registered before the `/` mount, or the MCP app answers it.
"""
from fastapi.testclient import TestClient

from main import app

SHA = "0123456789abcdef0123456789abcdef01234567"


def test_version_reports_the_railway_commit(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", SHA)
    r = TestClient(app).get("/version")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    assert r.json() == {"service": "health-app-backend", "commit": SHA}


def test_version_is_null_when_the_variable_is_absent_or_empty(monkeypatch):
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    assert TestClient(app).get("/version").json()["commit"] is None
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "")
    assert TestClient(app).get("/version").json()["commit"] is None


def test_version_needs_no_login_and_exposes_nothing_else(monkeypatch):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", SHA)
    monkeypatch.setenv("SECRET_KEY", "must-not-appear")
    r = TestClient(app).get("/version")
    assert r.status_code == 200 and set(r.json()) == {"service", "commit"}
    assert "must-not-appear" not in r.text


def test_version_is_served_by_the_app_not_swallowed_by_the_mcp_mount():
    paths = [getattr(r, "path", None) for r in app.routes]
    assert paths.index("/version") < paths.index("") if "" in paths else "/version" in paths
    assert TestClient(app).get("/version").json()["service"] == "health-app-backend"
