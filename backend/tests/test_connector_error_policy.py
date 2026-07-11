"""Connector failures decouple from session auth (DECISIONS_LOG #66).

The choke point `_hevy_error_to_http` remaps connector-auth failure 401->424, and
the three read handlers now route `httpx.HTTPStatusError` through it (clean 502,
not an unhandled 500 that would strip CORS headers). Polar token-refresh failure
likewise returns 424, not 401.

All faked — no live Hevy/Polar call. The Hevy read handlers construct their client
via module-level `_hevy_client`, so a fake is installed by monkeypatching that.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import HTTPException, status

import models
from connectors.hevy import HevyAuthError, HevyForbiddenError
from cors_errors import add_cors_error_handler
from encryption import encrypt
from routers import integrations, polar


class _FakeUser:
    def __init__(self, id_):
        self.id = id_


def _hevy_status_error() -> httpx.HTTPStatusError:
    """The exact shape `_check` raises on a Hevy 4xx/5xx (e.g. pageSize over ceiling)."""
    req = httpx.Request("GET", "https://api.hevyapp.com/v1/workouts")
    resp = httpx.Response(400, request=req, text="pageSize exceeds maximum")
    return httpx.HTTPStatusError(
        "Hevy API error 400: pageSize exceeds maximum", request=req, response=resp
    )


def _install_fake_hevy_client(monkeypatch, *, raises: Exception):
    class FakeHevyClient:
        async def get_workout_count(self):
            raise raises

        async def get_workouts(self, page=1, page_size=10):
            raise raises

        async def get_all_workouts(self, page_size=10):
            raise raises

        async def get_routines(self, page=1, page_size=10):
            raise raises

    monkeypatch.setattr(integrations, "_hevy_client", lambda user, db: FakeHevyClient())


# Every read handler, each invoked with its own signature. Includes the /workouts/all
# aggregator so its error routing (424/502) is covered like the rest.
_READ_HANDLERS = {
    "workout_count": lambda u, db: integrations.hevy_workout_count(current_user=u, db=db),
    "workouts": lambda u, db: integrations.hevy_workouts(page=1, page_size=10, current_user=u, db=db),
    "workouts_all": lambda u, db: integrations.hevy_workouts_all(current_user=u, db=db),
    "routines": lambda u, db: integrations.hevy_get_routines(page=1, page_size=10, current_user=u, db=db),
}


# ---------- choke point: direct mapping ----------
def test_choke_point_maps_auth_error_to_424():
    assert integrations._hevy_error_to_http(HevyAuthError("revoked")).status_code == 424


def test_choke_point_maps_http_status_error_to_502():
    assert integrations._hevy_error_to_http(_hevy_status_error()).status_code == 502


def test_choke_point_forbidden_unchanged_403():
    # Regression guard: the 403 branch must be untouched by the 401->424 remap.
    assert integrations._hevy_error_to_http(HevyForbiddenError("plan")).status_code == 403


# ---------- read handlers: auth failure -> 424 (was 401) ----------
@pytest.mark.parametrize("name", list(_READ_HANDLERS))
def test_read_handler_auth_error_returns_424(db_session, monkeypatch, name):
    _install_fake_hevy_client(monkeypatch, raises=HevyAuthError("revoked key"))
    with pytest.raises(HTTPException) as ei:
        asyncio.run(_READ_HANDLERS[name](_FakeUser(1), db_session))
    assert ei.value.status_code == status.HTTP_424_FAILED_DEPENDENCY
    assert ei.value.status_code != status.HTTP_401_UNAUTHORIZED


# ---------- read handlers: Hevy HTTP error -> 502, NOT an unhandled 500 ----------
@pytest.mark.parametrize("name", list(_READ_HANDLERS))
def test_read_handler_http_status_error_returns_502(db_session, monkeypatch, name):
    _install_fake_hevy_client(monkeypatch, raises=_hevy_status_error())
    with pytest.raises(HTTPException) as ei:
        asyncio.run(_READ_HANDLERS[name](_FakeUser(1), db_session))
    assert ei.value.status_code == status.HTTP_502_BAD_GATEWAY
    assert ei.value.status_code != 500  # the fake-CORS class: never leak a raw 500


# ---------- Polar token-refresh failure -> 424 (was 401) ----------
def test_polar_refresh_failure_returns_424(db_session, monkeypatch):
    user_id = 1
    expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    payload = json.dumps({
        "access_token": "old", "refresh_token": "refresh-me",
        "expires_at": expired, "scope": None, "token_type": "bearer",
    })
    db_session.add(models.UserIntegration(
        user_id=user_id, provider="polar", api_key_encrypted=encrypt(payload),
    ))
    db_session.commit()

    def _boom(refresh_token):
        raise RuntimeError("Polar refresh endpoint returned 400")

    monkeypatch.setattr(polar, "refresh_access_token", _boom)

    with pytest.raises(HTTPException) as ei:
        polar._valid_client(user_id, db_session)
    assert ei.value.status_code == status.HTTP_424_FAILED_DEPENDENCY
    assert ei.value.status_code != status.HTTP_401_UNAUTHORIZED


# ---------- Step 4: forced 500 carries CORS headers (the fake-CORS class) ----------
def _boom_app():
    """A minimal app wired exactly like main: CORSMiddleware + the global 500 guard.

    Built standalone (no `import main`) so the suite never runs create_all against
    the live DATABASE_URL; the handler under test is the real one from cors_errors.
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    allowed = ["https://health-app-production-e0ff.up.railway.app"]
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware, allow_origins=allowed, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )
    add_cors_error_handler(app, allowed)

    @app.get("/_boom")
    async def _boom():
        raise RuntimeError("intentional unhandled error")

    return app, allowed[0]


def test_unhandled_500_carries_cors_for_allowed_origin():
    from starlette.testclient import TestClient

    app, origin = _boom_app()
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/_boom", headers={"Origin": origin})
    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") == origin
    assert r.headers.get("access-control-allow-credentials") == "true"


def test_unhandled_500_does_not_echo_disallowed_origin():
    from starlette.testclient import TestClient

    app, _ = _boom_app()
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/_boom", headers={"Origin": "https://evil.example.com"})
    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") is None
