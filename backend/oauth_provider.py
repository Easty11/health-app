"""
In-memory OAuth 2.0 provider binding each issued token to a real app user.
authorize() no longer auto-approves — it parks the request and sends the
browser to /mcp/login (routers/mcp_auth.py) for an email/password check
against the same `users` table backend/auth.py already authenticates against.
Tokens are stored in memory and reset on server restart (re-auth needed after redeploy).
"""
import secrets
import time
from dataclasses import dataclass

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


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
    def __init__(self) -> None:
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}
        self._pending_logins: dict[str, _PendingLogin] = {}
        self._auth_code_user_id: dict[str, int] = {}
        self._token_user_id: dict[str, int] = {}

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._clients[client_info.client_id] = client_info

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

        access_token = secrets.token_urlsafe(32)
        refresh_token_str = secrets.token_urlsafe(32)

        self._access_tokens[access_token] = AccessToken(
            token=access_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=None,
        )
        self._token_user_id[access_token] = user_id
        self._refresh_tokens[refresh_token_str] = RefreshToken(
            token=refresh_token_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=None,
        )
        self._token_user_id[refresh_token_str] = user_id

        return OAuthToken(
            access_token=access_token,
            token_type="Bearer",
            refresh_token=refresh_token_str,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        rt = self._refresh_tokens.get(refresh_token)
        if rt and rt.client_id == client.client_id:
            return rt
        return None

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        user_id = self._token_user_id.get(refresh_token.token)
        if user_id is None:
            raise ValueError("Refresh token has no bound user; refusing to issue a token")
        new_access = secrets.token_urlsafe(32)
        self._access_tokens[new_access] = AccessToken(
            token=new_access,
            client_id=client.client_id,
            scopes=refresh_token.scopes,
            expires_at=None,
        )
        self._token_user_id[new_access] = user_id
        return OAuthToken(
            access_token=new_access,
            token_type="Bearer",
            refresh_token=refresh_token.token,
            scope=" ".join(refresh_token.scopes) if refresh_token.scopes else None,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        return self._access_tokens.get(token)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self._access_tokens.pop(getattr(token, "token", ""), None)
        self._refresh_tokens.pop(getattr(token, "token", ""), None)
        self._token_user_id.pop(getattr(token, "token", ""), None)

    def get_user_id(self, token: str) -> int | None:
        return self._token_user_id.get(token)
