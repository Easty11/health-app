"""
Polar AccessLink Dynamic API v4 connector.

Why v4 (not v3): the v3 exercise-transactions pipeline only exposes sessions
recorded *on a Polar device*. Sessions recorded with the Polar Flow phone app
(product.modelName = "Polar Flow app") — which is how this user records H10
sessions — are silently excluded (transactions return 204). v4's
training-sessions/list is date-range based and returns app-recorded sessions.

OAuth flow (authorization_code):
  1. Frontend GET /integrations/polar/auth-url (bearer) → {url}
  2. User authorises at https://auth.polar.com/oauth/authorize
  3. Polar redirects to /integrations/polar/callback?code=...&state=user_id
  4. Backend exchanges code at https://auth.polar.com/oauth/token (Basic auth)
     → access_token (12h), refresh_token, expires_in
  5. No user registration step in v4 — call data endpoints directly with the token.

Data:
  GET https://www.polaraccesslink.com/v4/data/training-sessions/list?from=&to=
"""
import os
import base64
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

AUTHORIZE_URL = "https://auth.polar.com/oauth/authorize"
TOKEN_URL = "https://auth.polar.com/oauth/token"
DATA_BASE = "https://www.polaraccesslink.com/v4/data"

POLAR_REDIRECT_URI = (
    "https://health-app-backend-production-760e.up.railway.app"
    "/integrations/polar/callback"
)

# Requested at authorization. Space-delimited per v4 spec.
SCOPES = "training_sessions:read ppi_data:read nightly_recharge:read sleep:read"


def _basic_auth_header() -> str:
    client_id = os.getenv("POLAR_CLIENT_ID", "")
    client_secret = os.getenv("POLAR_CLIENT_SECRET", "")
    creds = f"{client_id}:{client_secret}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


def parse_iso_duration(s: str | None) -> int | None:
    """ISO 8601 duration (PT1H30M45S) → total seconds."""
    if not s:
        return None
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", s)
    if not m:
        return None
    h = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    secs = float(m.group(3) or 0)
    return int(h * 3600 + mins * 60 + secs)


def _parse_dt(s: str | None) -> datetime | None:
    """Parse an ISO datetime; attach UTC if naive."""
    if not s:
        return None
    try:
        raw = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError, AttributeError):
        return None


def _dig(obj: Any, *paths: str) -> Any:
    """Return the first present value among dotted paths. Defensive against the
    v4 schema's exact nesting, which the public docs don't fully enumerate."""
    for path in paths:
        cur = obj
        ok = True
        for key in path.split("."):
            if isinstance(cur, dict) and key in cur and cur[key] is not None:
                cur = cur[key]
            else:
                ok = False
                break
        if ok:
            return cur
    return None


# ── OAuth ────────────────────────────────────────────────────────────────────

def build_auth_url(user_id: int) -> str:
    from urllib.parse import quote, urlencode
    params = {
        "response_type": "code",
        "client_id": os.getenv("POLAR_CLIENT_ID", ""),
        "redirect_uri": POLAR_REDIRECT_URI,
        "scope": SCOPES,
        "state": str(user_id),
    }
    # quote_via=quote so spaces in scope become %20 (not +) and colons survive
    return f"{AUTHORIZE_URL}?{urlencode(params, quote_via=quote)}"


def exchange_code_for_token(code: str) -> dict[str, Any]:
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            TOKEN_URL,
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": POLAR_REDIRECT_URI,
            },
        )
        resp.raise_for_status()
        return resp.json()


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            TOKEN_URL,
            headers={
                "Authorization": _basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        resp.raise_for_status()
        return resp.json()


# ── data client ──────────────────────────────────────────────────────────────

class PolarV4Client:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    # v4 rejects date windows beyond ~a quarter (108d → 400; 90d ok).
    MAX_WINDOW_DAYS = 90

    def list_training_sessions(self, from_dt: str, to_dt: str) -> list[dict[str, Any]]:
        """GET /training-sessions/list for a single window. `from`/`to` are ISO
        *datetimes without a timezone* (e.g. 2026-06-01T00:00:00); a trailing 'Z'
        is rejected (400). Returns the list under the 'trainingSessions' key."""
        params = {"from": from_dt, "to": to_dt}
        with httpx.Client(timeout=60) as client:
            resp = client.get(
                f"{DATA_BASE}/training-sessions/list", headers=self.headers, params=params
            )
            if resp.status_code == 204:
                return []
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, dict):
            return data.get("trainingSessions") or []
        return data if isinstance(data, list) else []

    def list_training_sessions_chunked(self, start, end) -> list[dict[str, Any]]:
        """List sessions across an arbitrary range by splitting into windows the
        API will accept. `start`/`end` are date objects."""
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        cur = start
        while cur < end:
            window_end = min(cur + timedelta(days=self.MAX_WINDOW_DAYS), end)
            for s in self.list_training_sessions(f"{cur}T00:00:00", f"{window_end}T00:00:00"):
                sid = (s.get("identifier") or {}).get("id")
                if sid and sid in seen:
                    continue
                if sid:
                    seen.add(sid)
                out.append(s)
            cur = window_end
        return out

    @staticmethod
    def parse_session(raw: dict[str, Any]) -> dict[str, Any] | None:
        """Map a v4 training session to aerobic_sessions fields.

        The v4 session schema is identical to the Polar Flow ZIP-export session
        JSON, so we reuse import_polar._parse_session for byte-for-byte parity
        between live-sync and ZIP-import data. The only difference is source.
        (The v4 *list* endpoint omits trainingLoadReport/zones, so cardio_load,
        muscle_load and z*_seconds come back null — those remain ZIP-only.)"""
        from import_polar import _parse_session
        fields = _parse_session(raw)
        if fields is None:
            return None
        fields["source"] = "polar_v4"
        return fields
