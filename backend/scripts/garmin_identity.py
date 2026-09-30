"""Whose Garmin (and Hevy) account is behind these users? -- a READ-ONLY identity check.

    /opt/venv/bin/python -m scripts.garmin_identity --user-ids 1 4

Built to answer "two users' Garmin HRV is identical every night: whose account is it?"
before anything is changed. Per user it reports:

  * a 12-char SHA-256 digest of each stored credential (Garmin token blob, Hevy API key),
    and which users' digests match. A MATCH means the same stored credential (a copy). A
    MISMATCH proves nothing about the account: two logins to one Garmin account mint different
    token blobs, and a rotating refresh token makes a once-identical copy diverge. So the
    identity evidence is the next line, not the digest;
  * Garmin only: the account's display name (first 3 characters, rest masked) and the last 4
    digits of its profile id, fetched from Garmin's social-profile endpoint with the stored
    token. Nothing else from the profile is read or printed. A fetch failure prints the error
    class only. Hevy is digest-only: the Hevy API is never called.

Read-only, and that is enforced rather than promised:
  * No database write of any kind (one SELECT; the connection is rolled back on close).
  * The Garmin token is NEVER refreshed. The client normally refreshes its access token when it
    is within 15 minutes of expiry, and again on a 401, and a refresh may rotate the refresh
    token; not persisting that would strand the stored credential of a real account. So the
    client's `_refresh_session` is replaced on the instance with one that raises: neither
    path can refresh. An expiring token is reported as "needs a refresh", with the workaround
    (open the app's Garmin card, which refreshes AND saves, then re-run). Loaded from the blob
    with `client.loads`, never `Garmin.login` (which refreshes proactively).
  * No credential, token content or full name is printed or logged; output is pure ASCII
    (PowerShell mojibake, FEEDBACK section 30). The real-user guard of `retire_user` does not
    apply: this reads, never deletes.

`socialProfile` is the endpoint `garminconnect` itself calls at login to learn the display name
(`Garmin._load_profile_and_settings`, 0.3.11). The profile-id key name is not documented by the
library, so several candidate keys are tried and, if none is present, the report says so rather
than guessing.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from typing import Any, Callable, Protocol

from sqlalchemy import text

from connectors.garmin import PROFILE_ID_KEYS as _PROFILE_ID_KEYS  # one implementation of "which account"
from connectors.garmin import SOCIAL_PROFILE_PATH as _SOCIAL_PROFILE_PATH
from connectors.garmin import extract_profile_id

_PROVIDERS = ("garmin", "hevy")


class RefreshWouldBeNeeded(Exception):
    """Raised in place of a token refresh. Nothing was sent to Garmin's token endpoint."""


class IdentitySource(Protocol):
    def social_profile(self) -> dict[str, Any]: ...


class LibrarySource:
    """A `garminconnect` client loaded from a token blob that CANNOT refresh."""

    def __init__(self, blob: str, *, session: Any = None) -> None:
        from garminconnect import Garmin

        client = Garmin().client
        client.loads(blob)  # sets the tokens; performs no request
        client._refresh_session = self._refuse_refresh  # instance override: closes both refresh paths
        if session is not None:  # transport-layer seam for tests
            client._api_session = session
        self._client = client
        self._before = (client.di_token, client.di_refresh_token)

    @staticmethod
    def _refuse_refresh(*_a: Any, **_k: Any) -> None:
        raise RefreshWouldBeNeeded()

    def social_profile(self) -> dict[str, Any]:
        prof = self._client.connectapi(_SOCIAL_PROFILE_PATH)
        # Belt and braces: the override above should make this unreachable.
        if (self._client.di_token, self._client.di_refresh_token) != self._before:
            raise RuntimeError("token changed in memory during an identity fetch")
        return prof if isinstance(prof, dict) else {}


SourceFactory = Callable[[str], IdentitySource]


def digest12(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


def _ascii(s: str) -> str:
    return s.encode("ascii", "backslashreplace").decode("ascii")


def mask_display_name(name: Any) -> str:
    """First 3 characters, then a fixed mask (a fixed width leaks nothing about the length)."""
    s = str(name or "")
    return f"{_ascii(s[:3])}***" if s else "(none)"


def profile_id_tail(prof: dict[str, Any]) -> str:
    """Last 4 DIGITS of the profile id, or a statement that no id key was present."""
    pid = extract_profile_id(prof)
    if pid is None:
        return "(no id key in response)"
    digits = re.sub(r"\D", "", pid)
    return f"...{digits[-4:]}" if digits else "(no digits)"


def _garmin_identity(blob: str, factory: SourceFactory) -> dict[str, str]:
    try:
        prof = factory(blob).social_profile()
    except RefreshWouldBeNeeded:
        return {"status": "needs_refresh"}
    except Exception as exc:  # noqa: BLE001 -- the error CLASS is the whole report
        return {"status": "failed", "error": type(exc).__name__}
    return {
        "status": "ok",
        "display": mask_display_name(prof.get("displayName")),
        "profile_id": profile_id_tail(prof),
    }


def gather(conn, user_ids: list[int], factory: SourceFactory) -> dict[int, dict[str, Any]]:
    """{user_id: {provider: {digest, identity?}}} for every requested user. One SELECT."""
    from encryption import decrypt

    out: dict[int, dict[str, Any]] = {uid: {} for uid in user_ids}
    rows = conn.execute(
        text("SELECT user_id, provider, api_key_encrypted FROM user_integrations"
             " WHERE provider IN ('garmin', 'hevy') ORDER BY user_id, provider")
    ).mappings()
    for r in rows:
        uid = int(r["user_id"])
        if uid not in out:
            continue
        secret = decrypt(r["api_key_encrypted"])  # in memory only; hashed, then used once
        entry: dict[str, Any] = {"digest": digest12(secret)}
        if r["provider"] == "garmin":
            entry["identity"] = _garmin_identity(secret, factory)
        out[uid][r["provider"]] = entry
        del secret
    return out


def _matches(data: dict[int, dict[str, Any]], provider: str) -> list[list[int]]:
    groups: dict[str, list[int]] = {}
    for uid, provs in data.items():
        if provider in provs:
            groups.setdefault(provs[provider]["digest"], []).append(uid)
    return [sorted(g) for g in groups.values() if len(g) > 1]


def format_report(data: dict[int, dict[str, Any]], target: str) -> str:
    out: list[str] = [f"Target database: {target}", ""]
    for uid in sorted(data):
        out.append(f"user {uid}")
        for provider in _PROVIDERS:
            e = data[uid].get(provider)
            if e is None:
                out.append(f"  {provider:<7} not connected")
                continue
            line = f"  {provider:<7} credential digest {e['digest']}"
            ident = e.get("identity")
            if ident is not None:
                if ident["status"] == "ok":
                    line += f"   display {ident['display']}   profile id {ident['profile_id']}"
                elif ident["status"] == "needs_refresh":
                    line += ("   identity SKIPPED: token needs a refresh, and a fetch would refresh it"
                             " (and may rotate the stored token). Open the app's Garmin card (it"
                             " refreshes and saves), then re-run.")
                else:
                    line += f"   identity fetch failed: {ident['error']}"
            out.append(line)
    out.append("")
    for provider in _PROVIDERS:
        groups = _matches(data, provider)
        if groups:
            for g in groups:
                out.append(f"{provider}: users {', '.join(map(str, g))} hold the IDENTICAL stored credential.")
        else:
            out.append(f"{provider}: no two of these users hold an identical stored credential"
                       " (a mismatch is NOT evidence of different accounts).")
    ok = {u: d["garmin"]["identity"] for u, d in data.items()
          if "garmin" in d and d["garmin"]["identity"]["status"] == "ok"}
    for a in sorted(ok):
        for b in sorted(ok):
            if a < b:
                same_name = ok[a]["display"] == ok[b]["display"]
                same_id = ok[a]["profile_id"] == ok[b]["profile_id"] and "..." in ok[a]["profile_id"]
                out.append(
                    f"garmin identity, users {a} and {b}: display name {'MATCHES' if same_name else 'differs'},"
                    f" profile id last-4 {'MATCHES' if same_id else 'differs'}"
                    + ("  -> consistent with ONE Garmin account (last-4 is not proof)" if same_name and same_id else "")
                )
    out.append("")
    out.append("READ-ONLY: nothing was written, no token was refreshed, and no Hevy call was made.")
    return "\n".join(out)


def main(argv: list[str] | None = None, *, factory: SourceFactory | None = None) -> int:
    p = argparse.ArgumentParser(description="Read-only Garmin/Hevy credential identity check.")
    p.add_argument("--user-ids", type=int, nargs="+", required=True)
    args = p.parse_args(argv)

    import database

    engine = database.engine
    with engine.connect() as conn:  # SELECT only; rolls back on close
        data = gather(conn, sorted(set(args.user_ids)), factory or LibrarySource)
    url = engine.url
    target = (f"sqlite file={url.database}" if engine.dialect.name == "sqlite"
              else f"{engine.dialect.name} host={url.host} port={url.port} db={url.database}")
    print(format_report(data, target).encode("ascii", "backslashreplace").decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
