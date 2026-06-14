"""
Polar Accesslink v3 connector.

OAuth flow:
  1. Frontend fetches GET /integrations/polar/auth-url (with bearer token) → gets redirect URL
  2. User authorises at Polar
  3. Polar redirects to /integrations/polar/callback?code=...&state=user_id
  4. Backend exchanges code, registers user, stores token

Data pull:
  pull_exercise_sessions() uses the Accesslink transaction model:
    - POST /exercises/transactions  (204 = no new data)
    - GET each session URL
    - GET each session's heart-rate-zones
    - PUT /exercises/transactions/{id}  (commit — marks as retrieved)
"""
import os
import base64
import re
from datetime import datetime, timezone
from typing import Any

import httpx

POLAR_REDIRECT_URI = (
    "https://health-app-backend-production-760e.up.railway.app"
    "/integrations/polar/callback"
)
ACCESSLINK_BASE = "https://www.polaraccesslink.com/v3"
AUTHORIZE_URL = "https://flow.polar.com/oauth2/authorization"
TOKEN_URL = f"{ACCESSLINK_BASE}/oauth2/token"


def _basic_auth_header() -> str:
    client_id = os.getenv("POLAR_CLIENT_ID", "")
    client_secret = os.getenv("POLAR_CLIENT_SECRET", "")
    creds = f"{client_id}:{client_secret}"
    return "Basic " + base64.b64encode(creds.encode()).decode()


def parse_iso_duration(s: str | None) -> int | None:
    """Convert ISO 8601 duration string (PT1H30M45S) to total seconds."""
    if not s:
        return None
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", s)
    if not m:
        return None
    h = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    secs = float(m.group(3) or 0)
    return int(h * 3600 + mins * 60 + secs)


def _parse_polar_dt(s: str | None) -> datetime | None:
    """Parse Polar datetime string to UTC-aware datetime. Polar returns local time
    without tz offset in Accesslink v3; treat as UTC to avoid ambiguity."""
    if not s:
        return None
    try:
        raw = s[:19]  # strip sub-seconds and any trailing chars
        dt = datetime.fromisoformat(raw)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError, AttributeError):
        return None


def build_auth_url(user_id: int) -> str:
    client_id = os.getenv("POLAR_CLIENT_ID", "")
    return (
        f"{AUTHORIZE_URL}"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={POLAR_REDIRECT_URI}"
        f"&state={user_id}"
    )


def exchange_code_for_token(code: str) -> dict[str, Any]:
    with httpx.Client() as client:
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


class PolarClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def register_user(self, member_id: int) -> dict[str, Any]:
        """Must be called once after first OAuth. 409 = already registered (fine)."""
        with httpx.Client() as client:
            resp = client.post(
                f"{ACCESSLINK_BASE}/users",
                headers=self.headers,
                json={"member-id": str(member_id)},
            )
            if resp.status_code == 409:
                return {"already_registered": True}
            resp.raise_for_status()
            return resp.json()

    def get_polar_user_id(self) -> str | None:
        with httpx.Client() as client:
            resp = client.get(f"{ACCESSLINK_BASE}/users/me", headers=self.headers)
            resp.raise_for_status()
            return resp.json().get("polar-user-id")

    def pull_exercise_sessions(self) -> list[dict[str, Any]]:
        """
        Full Accesslink transaction flow. Returns [] when no new sessions.
        Must commit the transaction to mark sessions as retrieved — uncommitted
        sessions re-appear on next call.
        """
        with httpx.Client() as client:
            # Step 1: create transaction
            txn_resp = client.post(
                f"{ACCESSLINK_BASE}/exercises/transactions",
                headers=self.headers,
            )
            if txn_resp.status_code == 204:
                return []  # no new data
            txn_resp.raise_for_status()
            txn = txn_resp.json()
            txn_id = txn["transaction-id"]
            session_urls: list[str] = txn.get("exercises", [])

            sessions: list[dict[str, Any]] = []
            for url in session_urls:
                # Step 2: fetch session detail
                s_resp = client.get(url, headers=self.headers)
                s_resp.raise_for_status()
                raw = s_resp.json()

                # Step 3: fetch HR zones (optional — 404/no content is fine)
                zones = None
                z_resp = client.get(f"{url}/heart-rate-zones", headers=self.headers)
                if z_resp.status_code == 200:
                    zones = z_resp.json()

                sessions.append(self._parse_session(raw, zones))

            # Step 4: commit transaction — marks all sessions as retrieved
            commit_resp = client.put(
                f"{ACCESSLINK_BASE}/exercises/transactions/{txn_id}",
                headers=self.headers,
            )
            commit_resp.raise_for_status()

            return sessions

    def _parse_session(self, raw: dict[str, Any], zones: dict | None) -> dict[str, Any]:
        hr = raw.get("heart-rate") or {}
        return {
            "external_id": str(raw["id"]) if raw.get("id") is not None else None,
            "sport": raw.get("sport"),
            "start_time": _parse_polar_dt(raw.get("start-time")),
            "end_time": _parse_polar_dt(raw.get("stop-time")),
            "duration_seconds": parse_iso_duration(raw.get("exercise-duration")),
            "avg_hr": hr.get("average"),
            "max_hr": hr.get("maximum"),
            "distance_meters": raw.get("distance"),
            "calories": raw.get("calories"),
            "hr_zones": zones,
        }
