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

    def list_training_sessions(
        self, from_date: str, to_date: str, features: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """GET /training-sessions/list. from inclusive, to exclusive (ISO dates)."""
        params: dict[str, Any] = {"from": from_date, "to": to_date}
        if features:
            params["features"] = features
        with httpx.Client(timeout=60) as client:
            resp = client.get(
                f"{DATA_BASE}/training-sessions/list", headers=self.headers, params=params
            )
            if resp.status_code == 204:
                return []
            resp.raise_for_status()
            data = resp.json()
        # response may be a bare list or wrapped — handle both
        if isinstance(data, dict):
            for key in ("data", "trainingSessions", "training_sessions", "items", "sessions"):
                if isinstance(data.get(key), list):
                    return data[key]
            return [data]
        return data if isinstance(data, list) else []

    @staticmethod
    def parse_session(raw: dict[str, Any]) -> dict[str, Any]:
        """Map a v4 training session to aerobic_sessions fields. Defensive about
        nested key names — the public v4 docs don't fully enumerate the schema,
        so each value tries several plausible paths."""
        start = _parse_dt(_dig(raw, "startTime", "start_time", "start"))
        dur_s = parse_iso_duration(_dig(raw, "duration"))
        if dur_s is None:
            dur_ms = _dig(raw, "durationMillis", "duration_millis")
            dur_s = int(dur_ms / 1000) if dur_ms else None
        stop = None
        if start and dur_s:
            stop = start + timedelta(seconds=dur_s)

        hr_avg = _dig(raw, "statistics.heartRate.average", "statistics.heartRate.avg",
                      "heartRate.average", "hrAvg", "statistics.avgHeartRate")
        hr_max = _dig(raw, "statistics.heartRate.maximum", "statistics.heartRate.max",
                      "heartRate.maximum", "hrMax", "statistics.maxHeartRate")
        calories = _dig(raw, "statistics.calories", "kiloCalories", "calories")
        cardio_load = _dig(raw, "trainingLoadData.cardioLoad", "trainingLoad.cardioLoad",
                           "cardioLoad")
        muscle_load = _dig(raw, "trainingLoadData.muscleLoad", "trainingLoad.muscleLoad",
                           "muscleLoad")
        recovery_h = None
        rec_ms = _dig(raw, "recoveryTimeMillis", "recoveryTime")
        if rec_ms:
            try:
                recovery_h = round(float(rec_ms) / 3_600_000, 1)
            except (TypeError, ValueError):
                recovery_h = None

        sport_name = _dig(raw, "sport.name", "sportName", "sport.translatedName")
        sport_id = _dig(raw, "sport.id", "sportId", "sport")
        if isinstance(sport_id, dict):
            sport_id = sport_id.get("id")

        zones = PolarV4Client._parse_zones(raw)

        return {
            "external_id": str(_dig(raw, "id", "identifier.id") or "") or None,
            "session_date": start.date() if start else None,
            "start_time": start,
            "stop_time": stop,
            "sport_id": str(sport_id) if sport_id is not None else None,
            "sport_name": sport_name or (str(sport_id) if sport_id is not None else None),
            "duration_minutes": round(dur_s / 60, 2) if dur_s else None,
            "hr_avg": int(hr_avg) if hr_avg is not None else None,
            "hr_max": int(hr_max) if hr_max is not None else None,
            "calories": int(calories) if calories is not None else None,
            "cardio_load": float(cardio_load) if cardio_load is not None else None,
            "muscle_load": float(muscle_load) if muscle_load is not None and muscle_load >= 0 else None,
            "recovery_hours": recovery_h,
            **zones,
        }

    @staticmethod
    def _parse_zones(raw: dict[str, Any]) -> dict[str, int]:
        out = {f"z{i}_seconds": 0 for i in range(1, 6)}
        zones = _dig(raw, "zones.heartRate", "heartRateZones", "zones")
        if not isinstance(zones, list):
            return out
        for idx, z in enumerate(zones[:5], start=1):
            if not isinstance(z, dict):
                continue
            secs = parse_iso_duration(_dig(z, "inZone", "duration", "time"))
            if secs is None:
                ms = _dig(z, "inZoneMillis", "durationMillis")
                secs = int(ms / 1000) if ms else 0
            out[f"z{idx}_seconds"] = secs or 0
        return out
