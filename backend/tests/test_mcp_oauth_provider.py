"""The persisted MCP OAuth provider (Q196).

Replaces `test_mcp_provider_really_persists_nothing`, which pinned the in-memory behaviour. Gates:
G1 restart survival, G2 hash only, G3 lifecycle (expiry, refresh, revoke, cascade, garbage). The
last block drives the SDK's real token / revoke endpoints through Starlette, because the SDK -- not
the provider -- decides what a refresh and a revoke look like on the wire.
"""
from __future__ import annotations

import asyncio
import base64
import functools
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from mcp.server.auth.provider import AccessToken, AuthorizationParams, RefreshToken, TokenError
from mcp.server.auth.routes import create_auth_routes
from mcp.server.auth.settings import ClientRegistrationOptions, RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyHttpUrl, AnyUrl
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.applications import Starlette
from starlette.testclient import TestClient

import database
import models
import oauth_provider as op
from oauth_provider import PersonalOAuthProvider, hash_token

REDIRECT = "https://client.example/callback"


def sync(fn):
    """Run an async test body with asyncio.run -- the repo has no async pytest plugin; its async
    tests call asyncio.run directly. functools.wraps keeps the fixture signature visible."""
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        return asyncio.run(fn(*a, **kw))
    return wrapper


def _fk_on(dbapi_connection, _record):
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


@pytest.fixture()
def factory():
    """One in-memory SQLite shared by every provider instance a test builds -- the stand-in for
    'the same database after a restart'. FK enforcement ON, as in conftest.db_session."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    event.listen(engine, "connect", _fk_on)
    database.Base.metadata.create_all(engine)
    yield sessionmaker(autoflush=False, bind=engine)
    engine.dispose()


@pytest.fixture()
def provider(factory):
    return PersonalOAuthProvider(session_factory=factory)


@pytest.fixture()
def clock(monkeypatch):
    """A movable UTC clock for oauth_provider (expiry, sliding refresh, touch throttle)."""
    state = {"now": datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(op, "_utcnow", lambda: state["now"])
    return state


def _add_user(factory, email="a@example.test") -> int:
    with factory() as s:
        u = models.User(email=email, hashed_password="x")
        s.add(u)
        s.commit()
        return u.id


def _client(client_id="client-1") -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id=client_id,
        client_secret="dcr-client-secret",
        redirect_uris=[AnyUrl(REDIRECT)],
        token_endpoint_auth_method="client_secret_post",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp",
    )


async def _connect(provider, user_id, client=None, scopes=("mcp",)):
    """The full sign-in: register, authorize, log in as user_id, exchange the code."""
    client = client or _client()
    await provider.register_client(client)
    url = await provider.authorize(client, AuthorizationParams(
        state="st", scopes=list(scopes), code_challenge="chal",
        redirect_uri=AnyUrl(REDIRECT), redirect_uri_provided_explicitly=True, resource=None,
    ))
    ticket = parse_qs(urlparse(url).query)["ticket"][0]
    redirect = provider.complete_login(ticket, user_id)
    code = parse_qs(urlparse(redirect).query)["code"][0]
    code_obj = await provider.load_authorization_code(client, code)
    return client, await provider.exchange_authorization_code(client, code_obj)


# --- G1: restart survival ----------------------------------------------------------------------

@sync
async def test_mcp_tokens_survive_restart(factory):
    uid = _add_user(factory)
    first = PersonalOAuthProvider(session_factory=factory)
    client, tok = await _connect(first, uid)

    second = PersonalOAuthProvider(session_factory=factory)   # a restart: new instance, same DB

    assert (await second.get_client(client.client_id)).client_id == client.client_id
    assert second.get_user_id(tok.access_token) == uid
    loaded = await second.load_access_token(tok.access_token)
    assert loaded is not None and loaded.client_id == client.client_id and loaded.scopes == ["mcp"]
    rt = await second.load_refresh_token(client, tok.refresh_token)
    assert rt is not None and rt.client_id == client.client_id
    refreshed = await second.exchange_refresh_token(client, rt, rt.scopes)
    assert second.get_user_id(refreshed.access_token) == uid


@sync
async def test_authorization_codes_and_pending_logins_are_not_persisted(factory):
    """Stamped decision: both stay in memory; a restart mid-login means signing in again."""
    uid = _add_user(factory)
    first = PersonalOAuthProvider(session_factory=factory)
    client = _client()
    await first.register_client(client)
    url = await first.authorize(client, AuthorizationParams(
        state=None, scopes=["mcp"], code_challenge="c", redirect_uri=AnyUrl(REDIRECT),
        redirect_uri_provided_explicitly=True, resource=None,
    ))
    ticket = parse_qs(urlparse(url).query)["ticket"][0]
    second = PersonalOAuthProvider(session_factory=factory)
    assert second.get_pending_login(ticket) is None
    assert second.complete_login(ticket, uid) is None


# --- G2: hash only -----------------------------------------------------------------------------

@sync
async def test_no_raw_token_is_stored_or_logged(factory, provider, caplog):
    caplog.set_level(logging.DEBUG)
    uid = _add_user(factory)
    client, tok = await _connect(provider, uid)
    rt = await provider.load_refresh_token(client, tok.refresh_token)
    refreshed = await provider.exchange_refresh_token(client, rt, rt.scopes)
    await provider.load_access_token(tok.access_token)
    raws = [tok.access_token, tok.refresh_token, refreshed.access_token]

    with factory() as s:
        cells = []
        for table in ("mcp_oauth_clients", "mcp_oauth_tokens"):
            for row in s.execute(text(f"SELECT * FROM {table}")).all():
                cells.extend(str(c) for c in row)
    assert cells, "expected rows to scan"
    # Messages below deliberately name no token value.
    for i, raw in enumerate(raws):
        assert not any(raw in c for c in cells), f"raw token #{i} appears in a stored column"
        assert not any(raw in r.getMessage() for r in caplog.records), f"raw token #{i} appears in a log line"

    with factory() as s:
        hashes = {r.token_hash for r in s.query(models.McpOAuthToken).all()}
    assert hashes == {hash_token(t) for t in raws}
    assert all(len(h) == 64 and h == h.lower() for h in hashes)
    assert hash_token(tok.access_token) == hashlib.sha256(tok.access_token.encode()).hexdigest()


# --- G3: lifecycle -----------------------------------------------------------------------------

@sync
async def test_token_response_carries_the_access_lifetime(factory, provider):
    _, tok = await _connect(provider, _add_user(factory))
    assert tok.expires_in == op.ACCESS_TTL_DEFAULT_SECONDS == 3600
    assert tok.token_type == "Bearer" and tok.refresh_token


@sync
async def test_expired_access_token_is_refused_and_refresh_mints_a_new_one(factory, provider, clock):
    uid = _add_user(factory)
    client, tok = await _connect(provider, uid)
    assert provider.get_user_id(tok.access_token) == uid

    clock["now"] += timedelta(seconds=3601)                     # past the 1 h access life
    assert await provider.load_access_token(tok.access_token) is None
    assert provider.get_user_id(tok.access_token) is None

    rt = await provider.load_refresh_token(client, tok.refresh_token)
    assert rt is not None                                       # the refresh outlives it
    fresh = await provider.exchange_refresh_token(client, rt, rt.scopes)
    assert fresh.access_token != tok.access_token
    assert fresh.refresh_token == tok.refresh_token             # F2: no rotation
    assert provider.get_user_id(fresh.access_token) == uid


@sync
async def test_an_access_token_minted_by_a_refresh_also_expires(factory, provider, clock):
    """Every access token carries an expiry, whichever path minted it (the SDK's bearer check
    and the 401-then-refresh loop both depend on it)."""
    uid = _add_user(factory)
    client, tok = await _connect(provider, uid)
    rt = await provider.load_refresh_token(client, tok.refresh_token)
    fresh = await provider.exchange_refresh_token(client, rt, rt.scopes)
    assert fresh.expires_in == 3600
    loaded = await provider.load_access_token(fresh.access_token)
    assert loaded.expires_at == int((clock["now"] + timedelta(seconds=3600)).timestamp())
    clock["now"] += timedelta(seconds=3601)
    assert provider.get_user_id(fresh.access_token) is None


@sync
async def test_access_token_is_live_just_inside_its_expiry(factory, provider, clock):
    uid = _add_user(factory)
    _, tok = await _connect(provider, uid)
    clock["now"] += timedelta(seconds=3599)
    assert provider.get_user_id(tok.access_token) == uid


@sync
async def test_refresh_token_expires_at_ninety_days_and_slides_on_use(factory, provider, clock):
    uid = _add_user(factory)
    client, tok = await _connect(provider, uid)

    clock["now"] += timedelta(days=60)
    rt = await provider.load_refresh_token(client, tok.refresh_token)
    assert rt is not None
    await provider.exchange_refresh_token(client, rt, rt.scopes)   # slides to day 60 + 90

    clock["now"] += timedelta(days=60)                          # day 120: dead without the slide
    assert await provider.load_refresh_token(client, tok.refresh_token) is not None

    clock["now"] += timedelta(days=31)                          # 91 days since the last use
    assert await provider.load_refresh_token(client, tok.refresh_token) is None


@sync
async def test_expired_refresh_cannot_be_exchanged_even_if_loaded_earlier(factory, provider, clock):
    uid = _add_user(factory)
    client, tok = await _connect(provider, uid)
    rt = await provider.load_refresh_token(client, tok.refresh_token)
    clock["now"] += timedelta(days=91)
    with pytest.raises(TokenError):
        await provider.exchange_refresh_token(client, rt, rt.scopes)


@sync
async def test_revoking_the_refresh_token_kills_its_access_tokens(factory, provider):
    uid = _add_user(factory)
    client, tok = await _connect(provider, uid)
    rt = await provider.load_refresh_token(client, tok.refresh_token)
    second = await provider.exchange_refresh_token(client, rt, rt.scopes)
    assert provider.get_user_id(tok.access_token) == uid
    assert provider.get_user_id(second.access_token) == uid

    await provider.revoke_token(rt)

    assert provider.get_user_id(tok.access_token) is None
    assert provider.get_user_id(second.access_token) is None
    assert await provider.load_access_token(second.access_token) is None
    assert await provider.load_refresh_token(client, tok.refresh_token) is None
    with pytest.raises(TokenError):
        await provider.exchange_refresh_token(client, rt, rt.scopes)


@sync
async def test_revoking_an_access_token_kills_only_that_token(factory, provider):
    uid = _add_user(factory)
    client, tok = await _connect(provider, uid)
    rt = await provider.load_refresh_token(client, tok.refresh_token)
    other = await provider.exchange_refresh_token(client, rt, rt.scopes)

    at = await provider.load_access_token(tok.access_token)
    await provider.revoke_token(at)

    assert provider.get_user_id(tok.access_token) is None
    assert provider.get_user_id(other.access_token) == uid
    assert await provider.load_refresh_token(client, tok.refresh_token) is not None


@sync
async def test_revoke_is_idempotent_and_ignores_unknown_tokens(factory, provider):
    uid = _add_user(factory)
    client, tok = await _connect(provider, uid)
    at = await provider.load_access_token(tok.access_token)
    await provider.revoke_token(at)
    with factory() as s:
        first = s.get(models.McpOAuthToken, hash_token(tok.access_token)).revoked_at
    await provider.revoke_token(at)
    with factory() as s:
        assert s.get(models.McpOAuthToken, hash_token(tok.access_token)).revoked_at == first
    await provider.revoke_token(AccessToken(token="never-issued", client_id="x", scopes=[]))


@sync
async def test_deleting_the_user_cascades_and_get_user_id_returns_none(factory, provider):
    uid = _add_user(factory)
    keeper = _add_user(factory, "b@example.test")
    client, tok = await _connect(provider, uid)
    _, other = await _connect(provider, keeper, client=_client("client-2"))
    assert provider.get_user_id(tok.access_token) == uid

    with factory() as s:
        s.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
        s.commit()

    assert provider.get_user_id(tok.access_token) is None
    assert await provider.load_access_token(tok.access_token) is None
    assert await provider.load_refresh_token(client, tok.refresh_token) is None
    with factory() as s:
        assert s.query(models.McpOAuthToken).filter_by(user_id=uid).count() == 0
    assert provider.get_user_id(other.access_token) == keeper   # another user's tokens untouched


@sync
async def test_garbage_and_cross_kind_tokens_resolve_to_nothing(factory, provider):
    uid = _add_user(factory)
    client, tok = await _connect(provider, uid)
    for junk in ("", "not-a-token", "A" * 43, hash_token(tok.access_token)):
        assert provider.get_user_id(junk) is None
        assert await provider.load_access_token(junk) is None
        assert await provider.load_refresh_token(client, junk) is None
    # A refresh token is not a bearer credential, and an access token is not a refresh token.
    assert provider.get_user_id(tok.refresh_token) is None
    assert await provider.load_access_token(tok.refresh_token) is None
    assert await provider.load_refresh_token(client, tok.access_token) is None


@sync
async def test_refresh_token_is_bound_to_its_client(factory, provider):
    uid = _add_user(factory)
    client, tok = await _connect(provider, uid)
    other = _client("client-2")
    await provider.register_client(other)
    assert await provider.load_refresh_token(other, tok.refresh_token) is None
    rt = await provider.load_refresh_token(client, tok.refresh_token)
    with pytest.raises(TokenError):
        await provider.exchange_refresh_token(other, rt, rt.scopes)


@sync
async def test_each_token_resolves_to_exactly_its_own_user(factory, provider):
    a, b = _add_user(factory), _add_user(factory, "b@example.test")
    client_a, tok_a = await _connect(provider, a, client=_client("client-a"))
    client_b, tok_b = await _connect(provider, b, client=_client("client-b"))
    assert provider.get_user_id(tok_a.access_token) == a
    assert provider.get_user_id(tok_b.access_token) == b
    rt_b = await provider.load_refresh_token(client_b, tok_b.refresh_token)
    assert provider.get_user_id((await provider.exchange_refresh_token(client_b, rt_b, rt_b.scopes)).access_token) == b


@sync
async def test_a_code_with_no_bound_user_still_refuses_to_issue(provider):
    from mcp.server.auth.provider import AuthorizationCode
    client = _client()
    await provider.register_client(client)
    orphan = AuthorizationCode(
        code="c", scopes=["mcp"], expires_at=9e12, client_id=client.client_id,
        code_challenge="x", redirect_uri=AnyUrl(REDIRECT), redirect_uri_provided_explicitly=True,
    )
    provider._auth_codes["c"] = orphan
    with pytest.raises(ValueError, match="no bound user"):
        await provider.exchange_authorization_code(client, orphan)


@sync
async def test_last_used_at_is_throttled_to_once_a_minute(factory, provider, clock):
    uid = _add_user(factory)
    _, tok = await _connect(provider, uid)
    h = hash_token(tok.access_token)

    def last_used():
        with factory() as s:
            return _aware_utc(s.get(models.McpOAuthToken, h).last_used_at)

    assert last_used() is None
    await provider.load_access_token(tok.access_token)
    t0 = clock["now"]
    assert last_used() == t0
    clock["now"] = t0 + timedelta(seconds=30)
    await provider.load_access_token(tok.access_token)
    assert last_used() == t0                                   # inside the window: no write
    clock["now"] = t0 + timedelta(seconds=61)
    await provider.load_access_token(tok.access_token)
    assert last_used() == t0 + timedelta(seconds=61)


def _aware_utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


@pytest.mark.parametrize("raw,expected", [
    (None, 3600), ("", 3600), ("120", 120), ("abc", 3600), ("0", 3600), ("-5", 3600),
])
def test_access_ttl_env_override(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("MCP_ACCESS_TOKEN_TTL_SECONDS", raising=False)
    else:
        monkeypatch.setenv("MCP_ACCESS_TOKEN_TTL_SECONDS", raw)
    assert op.access_ttl_seconds() == expected


@sync
async def test_short_ttl_env_override_applies_to_new_tokens(factory, provider, clock, monkeypatch):
    """The G4 knob: a 2-minute access TTL, set by env, with no code change."""
    monkeypatch.setenv("MCP_ACCESS_TOKEN_TTL_SECONDS", "120")
    uid = _add_user(factory)
    _, tok = await _connect(provider, uid)
    assert tok.expires_in == 120
    clock["now"] += timedelta(seconds=121)
    assert provider.get_user_id(tok.access_token) is None


# --- the caller's contract ---------------------------------------------------------------------

def test_current_user_id_raises_without_a_bound_user(factory, provider, monkeypatch):
    import mcp_server
    monkeypatch.setattr(mcp_server, "_oauth_provider", provider)
    monkeypatch.setattr(mcp_server, "get_access_token", lambda: None)
    with pytest.raises(ValueError, match="No authenticated"):
        mcp_server._current_user_id()
    monkeypatch.setattr(
        mcp_server, "get_access_token",
        lambda: AccessToken(token="valid-looking-but-unknown", client_id="c", scopes=[]),
    )
    with pytest.raises(ValueError, match="not bound to a user"):
        mcp_server._current_user_id()


@sync
async def test_current_user_id_resolves_a_persisted_token(factory, provider, monkeypatch):
    import mcp_server
    uid = _add_user(factory)
    _, tok = await _connect(provider, uid)
    monkeypatch.setattr(mcp_server, "_oauth_provider", provider)
    monkeypatch.setattr(
        mcp_server, "get_access_token",
        lambda: AccessToken(token=tok.access_token, client_id="client-1", scopes=["mcp"]),
    )
    assert mcp_server._current_user_id() == uid


# --- the SDK's real endpoints (token + revoke) over the provider -------------------------------

def _app(provider):
    routes = create_auth_routes(
        provider, AnyHttpUrl("https://issuer.example"),
        client_registration_options=ClientRegistrationOptions(enabled=True),
        revocation_options=RevocationOptions(enabled=True),
    )
    return Starlette(routes=routes)


def _pkce():
    verifier = "v" * 64
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def _sign_in_over_http(http, provider, user_id):
    reg = http.post("/register", json={
        "redirect_uris": [REDIRECT], "token_endpoint_auth_method": "client_secret_post",
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        "scope": "mcp",
    })
    assert reg.status_code == 201, reg.text
    cid, secret = reg.json()["client_id"], reg.json()["client_secret"]
    verifier, challenge = _pkce()
    auth = http.get("/authorize", params={
        "client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "scope": "mcp",
        "code_challenge": challenge, "code_challenge_method": "S256", "state": "s",
    }, follow_redirects=False)
    assert auth.status_code == 302, auth.text
    ticket = parse_qs(urlparse(auth.headers["location"]).query)["ticket"][0]
    code = parse_qs(urlparse(provider.complete_login(ticket, user_id)).query)["code"][0]
    tok = http.post("/token", data={
        "grant_type": "authorization_code", "client_id": cid, "client_secret": secret,
        "code": code, "redirect_uri": REDIRECT, "code_verifier": verifier,
    })
    assert tok.status_code == 200, tok.text
    return cid, secret, tok.json()


def test_sdk_endpoints_refresh_and_revoke_over_the_persisted_provider(factory, clock):
    uid = _add_user(factory)
    first = PersonalOAuthProvider(session_factory=factory)
    cid, secret, body = _sign_in_over_http(TestClient(_app(first), base_url="https://issuer.example"), first, uid)
    assert body["expires_in"] == 3600 and body["refresh_token"]

    # A restart between sign-in and refresh: a new provider behind a new app.
    second = PersonalOAuthProvider(session_factory=factory)
    http = TestClient(_app(second), base_url="https://issuer.example")
    clock["now"] += timedelta(hours=2)                           # the first access token is dead
    assert second.get_user_id(body["access_token"]) is None

    ref = http.post("/token", data={
        "grant_type": "refresh_token", "client_id": cid, "client_secret": secret,
        "refresh_token": body["refresh_token"],
    })
    assert ref.status_code == 200, ref.text
    assert ref.json()["refresh_token"] == body["refresh_token"] and ref.json()["expires_in"] == 3600
    assert second.get_user_id(ref.json()["access_token"]) == uid

    # Revoking by the refresh token (the SDK tries load_access_token first, then the refresh loader).
    rev = http.post("/revoke", data={
        "client_id": cid, "client_secret": secret, "token": body["refresh_token"],
        "token_type_hint": "refresh_token",
    })
    assert rev.status_code == 200
    assert second.get_user_id(ref.json()["access_token"]) is None
    again = http.post("/token", data={
        "grant_type": "refresh_token", "client_id": cid, "client_secret": secret,
        "refresh_token": body["refresh_token"],
    })
    assert again.status_code == 400 and again.json()["error"] == "invalid_grant"


def test_sdk_refresh_endpoint_rejects_an_expired_refresh_token(factory, clock):
    uid = _add_user(factory)
    provider = PersonalOAuthProvider(session_factory=factory)
    http = TestClient(_app(provider), base_url="https://issuer.example")
    cid, secret, body = _sign_in_over_http(http, provider, uid)
    clock["now"] += timedelta(days=91)
    r = http.post("/token", data={
        "grant_type": "refresh_token", "client_id": cid, "client_secret": secret,
        "refresh_token": body["refresh_token"],
    })
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


# --- the identity a tool call sees (G4 finding, 8 Oct 2026) ------------------------------------
#
# The SDK's get_access_token() is a contextvar tool handlers inherit from the task that started
# the MCP session, i.e. the FIRST request. A client that refreshes keeps its Mcp-Session-Id and
# sends the new token: the middleware accepts it (HTTP 200) but the handler still saw the token
# that created the session. With non-expiring tokens that was invisible; once access tokens expire
# it surfaced as the tool error "MCP token is not bound to a user" instead of a working call.

def _mcp_over_http(provider, monkeypatch):
    """A real FastMCP streamable-HTTP app over `provider`, whose one tool reports what the app's
    own _current_user_id() resolves and what the SDK's contextvar still holds."""
    import mcp_server
    from mcp.server.auth.middleware.auth_context import get_access_token
    from mcp.server.fastmcp import FastMCP
    from mcp.server.auth.settings import AuthSettings
    from mcp.server.transport_security import TransportSecuritySettings

    monkeypatch.setattr(mcp_server, "_oauth_provider", provider)
    # _current_user_id reads the request via the module-level `mcp`; point it at this server.
    server = FastMCP(
        "t", auth_server_provider=provider,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl("https://t.example"),
            client_registration_options=ClientRegistrationOptions(enabled=True),
            resource_server_url=AnyHttpUrl("https://t.example/mcp"),
        ),
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    monkeypatch.setattr(mcp_server, "mcp", server)

    @server.tool()
    def whoami() -> dict:
        sdk = get_access_token()
        try:
            uid = mcp_server._current_user_id()
        except ValueError as e:
            uid = f"ERROR: {e}"
        return {"user": uid, "sdk_context_is_session_token": bool(sdk), "sdk_hash": hash_token(sdk.token) if sdk else None}

    return server.streamable_http_app()


def _headers(token, sid=None):
    h = {"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream",
         "Content-Type": "application/json"}
    if sid:
        h["mcp-session-id"] = sid
    return h


def _rpc(http, token, sid, method, params=None, id_=None):
    import json
    body = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        body["params"] = params
    if id_ is not None:
        body["id"] = id_
    return http.post("/mcp", headers=_headers(token, sid), content=json.dumps(body))


def _payload(resp):
    import json
    for line in resp.text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:])
    return resp.json()


def _open_session(http, token):
    r = _rpc(http, token, None, "initialize", {
        "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}, 1)
    assert r.status_code == 200, r.text
    sid = r.headers["mcp-session-id"]
    _rpc(http, token, sid, "notifications/initialized")
    return sid


def _whoami(http, token, sid, id_=2):
    r = _rpc(http, token, sid, "tools/call", {"name": "whoami", "arguments": {}}, id_)
    assert r.status_code == 200, r.text
    import json
    return json.loads(_payload(r)["result"]["content"][0]["text"])


@pytest.mark.parametrize("how", ["expired", "revoked"])
def test_a_refreshed_token_on_a_long_lived_session_resolves_its_own_user(factory, provider, monkeypatch, how):
    """The session was opened with token A. A then expires (or is revoked), the client refreshes
    to B and keeps the session. The tool must resolve B's user, not fail on A."""
    uid = _add_user(factory)
    client, first = asyncio.run(_connect(provider, uid))
    app = _mcp_over_http(provider, monkeypatch)
    with TestClient(app, base_url="https://t.example") as http:
        sid = _open_session(http, first.access_token)
        fresh = _whoami(http, first.access_token, sid)
        assert fresh["user"] == uid                                  # control: before any expiry

        with factory() as s:                                         # A dies; the session does not
            row = s.get(models.McpOAuthToken, hash_token(first.access_token))
            if how == "expired":
                row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
            else:
                row.revoked_at = datetime.now(timezone.utc)
            s.commit()
        assert provider.get_user_id(first.access_token) is None

        rt = asyncio.run(provider.load_refresh_token(client, first.refresh_token))
        second = asyncio.run(provider.exchange_refresh_token(client, rt, rt.scopes))
        out = _whoami(http, second.access_token, sid, id_=3)

    assert out["user"] == uid, f"tool did not resolve the refreshed token's user: {out['user']}"
    # Identity control: the SDK's own contextvar really is still the session-creating token A, so
    # this test would fail on the old code rather than pass for the wrong reason.
    assert out["sdk_hash"] == hash_token(first.access_token)
    assert out["sdk_hash"] != hash_token(second.access_token)


def test_a_session_cannot_borrow_another_users_identity_via_a_later_token(factory, provider, monkeypatch):
    """Identity binding is unchanged: the user a tool resolves is the one bound to the token on
    THAT request, never the session creator's. (The SDK separately rejects a different client's
    credential on an existing session, which is what stops a cross-client replay.)"""
    a, b = _add_user(factory), _add_user(factory, "b@example.test")
    client, tok_a = asyncio.run(_connect(provider, a))
    # Same client, second user: sign in again as b through the same registered client.
    url = asyncio.run(provider.authorize(client, AuthorizationParams(
        state=None, scopes=["mcp"], code_challenge="c", redirect_uri=AnyUrl(REDIRECT),
        redirect_uri_provided_explicitly=True, resource=None)))
    ticket = parse_qs(urlparse(url).query)["ticket"][0]
    code = parse_qs(urlparse(provider.complete_login(ticket, b)).query)["code"][0]
    tok_b = asyncio.run(provider.exchange_authorization_code(
        client, asyncio.run(provider.load_authorization_code(client, code))))
    app = _mcp_over_http(provider, monkeypatch)
    with TestClient(app, base_url="https://t.example") as http:
        sid = _open_session(http, tok_a.access_token)
        assert _whoami(http, tok_a.access_token, sid)["user"] == a
        assert _whoami(http, tok_b.access_token, sid, id_=3)["user"] == b


def test_request_token_falls_back_to_the_contextvar_outside_a_request(provider, monkeypatch):
    """No request context (a direct call, not over HTTP): the contextvar is the only source."""
    import mcp_server
    sentinel = AccessToken(token="outside-request", client_id="c", scopes=[])
    monkeypatch.setattr(mcp_server, "get_access_token", lambda: sentinel)
    assert mcp_server._request_access_token() is sentinel
