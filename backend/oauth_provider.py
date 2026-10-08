"""
OAuth 2.0 provider binding each issued token to a real app user. Client registrations and
access/refresh tokens are PERSISTED (tables mcp_oauth_clients / mcp_oauth_tokens, Q196),
so a backend restart or redeploy no longer drops a connected MCP client.

authorize() does not auto-approve -- it parks the request and sends the browser to /mcp/login
(routers/mcp_auth.py) for an email/password check against the same `users` table backend/auth.py
already authenticates against.

What is stored, and how:
  * Tokens are stored as sha256(token) hex, never raw. They are 256-bit `token_urlsafe(32)`
    values, so a fast hash needs no salt or KDF. The raw value is returned to the client once.
    No raw token is logged or placed in an error message.
  * Access tokens expire (default 1 h); refresh tokens expire (default 90 days) and slide: each
    refresh extends it. Both are overridable by env (MCP_ACCESS_TOKEN_TTL_SECONDS,
    MCP_REFRESH_TOKEN_TTL_SECONDS) so the access TTL can be changed without a code edit.
    Refresh tokens are NOT rotated: a refresh returns the same refresh token.
  * `mcp_oauth_tokens.user_id` is ON DELETE CASCADE, so a deleted user's tokens vanish and
    get_user_id() returns None for them. Revoking a refresh token revokes the access tokens it
    minted. `revoked_at` is set, never cleared.
  * Identity binding is unchanged: every token resolves to exactly one user_id, and the caller
    (mcp_server._current_user_id) still raises when there isn't one.

What is NOT stored: authorization codes (5-minute life) and pending logins stay in memory;
losing one mid-login just means signing in again.

DB access is one short-lived session per call from the `database` session factory (resolved at
call time, so tests can point it elsewhere); there is no global session.
"""
import hashlib
import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

import database
import models
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

# F1 (Q196): 1 h access, 90 d sliding refresh. The access TTL is the knob the G4 real-client check
# turns (a short value on a test deploy); a fallback to a long TTL is an env change, not a code edit.
ACCESS_TTL_DEFAULT_SECONDS = 3600
REFRESH_TTL_DEFAULT_SECONDS = 90 * 24 * 3600
# last_used_at is touched at most once per this many seconds per token, so a tool call is not a write.
TOUCH_INTERVAL_SECONDS = 60


def _ttl_seconds(env_name: str, default: int) -> int:
    raw = os.getenv(env_name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def access_ttl_seconds() -> int:
    return _ttl_seconds("MCP_ACCESS_TOKEN_TTL_SECONDS", ACCESS_TTL_DEFAULT_SECONDS)


def refresh_ttl_seconds() -> int:
    return _ttl_seconds("MCP_REFRESH_TOKEN_TTL_SECONDS", REFRESH_TTL_DEFAULT_SECONDS)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite hands timestamptz columns back naive; the values written here are always UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _usable(row: "models.McpOAuthToken | None", kind: str, now: datetime) -> bool:
    """A row is usable only if it exists, is the wanted kind, is not revoked and has not expired."""
    if row is None or row.kind != kind or row.revoked_at is not None:
        return False
    expires = _aware(row.expires_at)
    return expires is None or expires > now


@dataclass
class _PendingLogin:
    client_id: str
    scopes: list[str]
    code_challenge: str | None
    redirect_uri: object
    redirect_uri_provided_explicitly: bool
    resource: str | None
    state: str | None


class PersonalOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        # None -> database.SessionLocal, looked up at call time.
        self._session_factory = session_factory
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._pending_logins: dict[str, _PendingLogin] = {}
        self._auth_code_user_id: dict[str, int] = {}
        self._last_touch: dict[str, datetime] = {}

    def _session(self) -> Session:
        return (self._session_factory or database.SessionLocal)()

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with self._session() as s:
            row = s.get(models.McpOAuthClient, client_id)
            if row is None:
                return None
            return OAuthClientInformationFull.model_validate(row.client_info)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        with self._session() as s:
            s.merge(models.McpOAuthClient(
                client_id=client_info.client_id,
                client_info=client_info.model_dump(mode="json"),
            ))
            s.commit()

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        # Park the request behind a login gate — no code is minted, and no
        # redirect to the client happens, until a real user authenticates.
        ticket = secrets.token_urlsafe(32)
        self._pending_logins[ticket] = _PendingLogin(
            client_id=client.client_id,
            scopes=params.scopes or [],
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            state=params.state,
        )
        from mcp_server import _SERVER_ROOT
        return f"{_SERVER_ROOT}/mcp/login?ticket={ticket}"

    def get_pending_login(self, ticket: str) -> _PendingLogin | None:
        return self._pending_logins.get(ticket)

    def complete_login(self, ticket: str, user_id: int) -> str | None:
        """Mint the authorization code for a ticket that just passed a real
        login check, bind it to user_id, and return the client redirect URL.
        Returns None if the ticket is unknown/already used."""
        pending = self._pending_logins.pop(ticket, None)
        if pending is None:
            return None
        code = secrets.token_urlsafe(32)
        self._auth_codes[code] = AuthorizationCode(
            code=code,
            scopes=pending.scopes,
            expires_at=time.time() + 300,
            client_id=pending.client_id,
            code_challenge=pending.code_challenge,
            redirect_uri=pending.redirect_uri,
            redirect_uri_provided_explicitly=pending.redirect_uri_provided_explicitly,
            resource=pending.resource,
        )
        self._auth_code_user_id[code] = user_id
        return construct_redirect_uri(
            str(pending.redirect_uri),
            code=code,
            state=pending.state,
        )

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code_obj = self._auth_codes.get(authorization_code)
        if code_obj and code_obj.client_id == client.client_id and code_obj.expires_at > time.time():
            return code_obj
        return None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        del self._auth_codes[authorization_code.code]
        user_id = self._auth_code_user_id.pop(authorization_code.code, None)
        if user_id is None:
            # Should be unreachable — every code minted by complete_login()
            # carries a user_id. Refuse rather than issue an unbound token.
            raise ValueError("Authorization code has no bound user; refusing to issue a token")

        now = _utcnow()
        access_token = secrets.token_urlsafe(32)
        refresh_token_str = secrets.token_urlsafe(32)
        refresh_hash = hash_token(refresh_token_str)
        access_ttl = access_ttl_seconds()
        scopes = list(authorization_code.scopes)

        with self._session() as s:
            s.add(models.McpOAuthToken(
                token_hash=refresh_hash, kind="refresh", user_id=user_id, client_id=client.client_id,
                scopes=scopes, expires_at=now + timedelta(seconds=refresh_ttl_seconds()),
            ))
            s.add(models.McpOAuthToken(
                token_hash=hash_token(access_token), kind="access", user_id=user_id,
                client_id=client.client_id, scopes=scopes,
                expires_at=now + timedelta(seconds=access_ttl), refresh_hash=refresh_hash,
            ))
            s.commit()

        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=access_ttl,
            refresh_token=refresh_token_str,
            scope=" ".join(scopes) if scopes else None,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        with self._session() as s:
            row = s.get(models.McpOAuthToken, hash_token(refresh_token))
            if not _usable(row, "refresh", _utcnow()) or row.client_id != client.client_id:
                return None
            expires = _aware(row.expires_at)
            return RefreshToken(
                token=refresh_token,
                client_id=row.client_id,
                scopes=list(row.scopes),
                expires_at=int(expires.timestamp()) if expires else None,
            )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        now = _utcnow()
        refresh_hash = hash_token(refresh_token.token)
        access_token = secrets.token_urlsafe(32)
        access_ttl = access_ttl_seconds()
        with self._session() as s:
            row = s.get(models.McpOAuthToken, refresh_hash)
            if not _usable(row, "refresh", now) or row.client_id != client.client_id:
                # Revoked, expired or its user deleted between load_refresh_token and here.
                raise TokenError("invalid_grant", "refresh token is no longer valid")
            s.add(models.McpOAuthToken(
                token_hash=hash_token(access_token), kind="access", user_id=row.user_id,
                client_id=client.client_id, scopes=list(refresh_token.scopes),
                expires_at=now + timedelta(seconds=access_ttl), refresh_hash=refresh_hash,
            ))
            # Sliding: each refresh extends the refresh token's life. Same token, no rotation (F2).
            row.expires_at = now + timedelta(seconds=refresh_ttl_seconds())
            row.last_used_at = now
            s.commit()
        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            expires_in=access_ttl,
            refresh_token=refresh_token.token,
            scope=" ".join(refresh_token.scopes) if refresh_token.scopes else None,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        now = _utcnow()
        token_hash = hash_token(token)
        with self._session() as s:
            row = s.get(models.McpOAuthToken, token_hash)
            if not _usable(row, "access", now):
                return None
            last = self._last_touch.get(token_hash)
            if last is None or (now - last).total_seconds() >= TOUCH_INTERVAL_SECONDS:
                row.last_used_at = now
                s.commit()
                self._last_touch[token_hash] = now
            expires = _aware(row.expires_at)
            return AccessToken(
                token=token,
                client_id=row.client_id,
                scopes=list(row.scopes),
                expires_at=int(expires.timestamp()) if expires else None,
            )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        now = _utcnow()
        token_hash = hash_token(token.token)
        with self._session() as s:
            row = s.get(models.McpOAuthToken, token_hash)
            if row is None:
                return
            if row.kind == "refresh":
                # The refresh token and every access token it minted.
                s.execute(
                    update(models.McpOAuthToken)
                    .where(
                        (models.McpOAuthToken.token_hash == token_hash)
                        | (models.McpOAuthToken.refresh_hash == token_hash),
                        models.McpOAuthToken.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
            elif row.revoked_at is None:
                row.revoked_at = now
            s.commit()

    def get_user_id(self, token: str) -> int | None:
        """The user an ACCESS token is bound to, or None (unknown, garbage, a refresh token,
        revoked, expired, or its user was deleted and the row cascaded away)."""
        with self._session() as s:
            row = s.get(models.McpOAuthToken, hash_token(token))
            if not _usable(row, "access", _utcnow()):
                return None
            return row.user_id
