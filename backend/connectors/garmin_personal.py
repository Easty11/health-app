"""Garmin Personal API client (host personal.connectapi.garmin.com) -- the official lane.

Hand-rolled on `httpx` (already a dependency) instead of depending on `garmin/connect-personal-api-python`:
that library caches the bearer token in a file under ~/.config that cannot be switched off, which is wrong
for a multi-user server where the cache must be Fernet-encrypted in the database (DECISIONS_LOG #449).
Its endpoint map and exchange protocol are what this follows.

  * The key is exchanged for a bearer JWT: `POST /personalapitoken-service/personal-api/personal-api-key/token`,
    header `Authorization: ApiKey <key>`, no body, the response BODY is the JWT as plain text. TTL 24 h, no
    refresh token (so none of the DI lane's rotate-and-write-back problem). The expiry is read from the JWT
    `exp` claim without verifying it.
  * A token with more than `REUSE_MARGIN` left is reused; otherwise a new one is exchanged. A 401 on a data
    call forces ONE re-exchange and a retry; a second 401 is an auth failure.
  * Nothing here logs the key or the token, and no exception message carries either: failures are raised as
    this module's own classes, whose text is a status code or a class name only.

The caller owns persistence: `token_state()` returns the (token, expiry) the client currently holds so the
service layer can write it back encrypted; the client itself never touches the database.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timedelta, timezone
import time
from typing import Any, Callable, Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"
TIMEOUT_S = 30.0
REUSE_MARGIN = timedelta(hours=1)

# Paths (from the official client's endpoint map). One place, so a path change is one edit.
HRV_PATH = "/hrv-service/hrv/{date}"
SLEEP_PATH = "/sleep-service/sleep/dailySleep"
HEART_RATE_PATH = "/wellness-service/wellness/dailyHeartRate"
SPO2_HOURLY_PATH = "/wellness-service/wellness/daily/spo2acclimation/{date}"
BODY_BATTERY_PATH = "/wellness-service/wellness/bodyBattery/reports/daily"
STRESS_PATH = "/usersummary-service/stats/stress/daily/{start}/{end}"
HR_ZONES_PATH = "/biometric-service/heartRateZones/v2"
ACTIVITY_LIST_PATH = "/activitylist-service/activities/search/activities"
ACTIVITY_PATH = "/activity-service/activity"


class PersonalApiError(Exception):
    """Base class. The text is a status code or a class name; never a key, token, URL query or body."""


class PersonalAuthError(PersonalApiError):
    """The key was refused (exchange 401/403), or the token was refused twice. The operator must act:
    the key expired, was revoked, or is wrong."""


class PersonalRateLimited(PersonalApiError):
    """429. Back off; never retried in-line."""


class PersonalNotFound(PersonalApiError):
    """404: Garmin has nothing for that request. The lane treats it as an empty day."""


class PersonalTransientError(PersonalApiError):
    """A network failure, a timeout, a 5xx or a malformed token. Retry on the next run."""


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def jwt_expiry(token: str) -> datetime:
    """The `exp` claim of a JWT as an aware UTC datetime. The signature is NOT verified (we only schedule a
    re-exchange from it). Raises PersonalTransientError for anything that is not a JWT with a numeric `exp`."""
    try:
        payload_b64 = token.split(".")[1]
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4)))
        exp = payload["exp"]
        if isinstance(exp, bool) or not isinstance(exp, (int, float)):
            raise TypeError
        return datetime.fromtimestamp(exp, tz=timezone.utc)
    except Exception as exc:  # noqa: BLE001 -- the class is the whole report; the token must not be echoed
        raise PersonalTransientError("malformed bearer token") from None


class PersonalClient:
    """One user's Personal API session: the key, and a cached bearer token."""

    def __init__(
        self,
        api_key: str,
        *,
        access_token: Optional[str] = None,
        token_expires_at: Optional[datetime] = None,
        transport: Optional[httpx.BaseTransport] = None,
        base_url: str = BASE_URL,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        min_interval_s: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not api_key or not api_key.strip():
            raise PersonalAuthError("empty api key")
        self._key = api_key.strip()
        self._token = access_token
        self._expires_at = _aware(token_expires_at) if token_expires_at is not None else None
        self._now = now
        # Minimum gap between DATA requests (the first is never delayed). 0 disables it.
        self._min_interval = max(0.0, min_interval_s)
        self._sleep, self._monotonic = sleep, monotonic
        self._last_request_at: Optional[float] = None
        self.requests = 0                       # HTTP calls made (exchanges + data), for per-trigger budget reports
        self._http = httpx.Client(base_url=base_url.rstrip("/"), timeout=TIMEOUT_S, transport=transport)

    # -- lifecycle ----------------------------------------------------------------------------------
    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "PersonalClient":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    # -- token --------------------------------------------------------------------------------------
    def token_state(self) -> tuple[Optional[str], Optional[datetime]]:
        """The (token, expiry) currently held, for the caller to persist."""
        return self._token, self._expires_at

    def _token_usable(self) -> bool:
        return (self._token is not None and self._expires_at is not None
                and self._expires_at - _aware(self._now()) > REUSE_MARGIN)

    def exchange(self) -> str:
        """Exchange the key for a fresh bearer token (always hits the network)."""
        self.requests += 1
        try:
            resp = self._http.post(TOKEN_PATH, headers={"Authorization": f"ApiKey {self._key}", "Accept": "*/*"})
        except httpx.HTTPError as exc:
            raise PersonalTransientError(f"token exchange: {type(exc).__name__}") from None
        if resp.status_code in (401, 403):
            raise PersonalAuthError(f"token exchange refused: HTTP {resp.status_code}")
        if resp.status_code == 429:
            raise PersonalRateLimited("token exchange: HTTP 429")
        if resp.status_code != 200:
            raise PersonalTransientError(f"token exchange: HTTP {resp.status_code}")
        token = resp.text.strip()
        self._expires_at = jwt_expiry(token)
        self._token = token
        return token

    def _bearer(self, *, force: bool = False) -> str:
        if force or not self._token_usable():
            return self.exchange()
        assert self._token is not None
        return self._token

    # -- data ---------------------------------------------------------------------------------------
    def _pace(self) -> None:
        """Keep at least `min_interval_s` between data requests. The host answers 429 to a burst (observed
        25 Oct 2026: about six back-to-back calls per day of backfill) and sends no Retry-After or limit
        header, while 12 requests two seconds apart all returned 200."""
        if self._min_interval and self._last_request_at is not None:
            wait = self._min_interval - (self._monotonic() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._monotonic()

    def get(self, path: str, params: Optional[dict[str, str]] = None) -> Any:
        """GET `path` with the bearer token; decoded JSON, or None for an empty body. ProbeSource-shaped, so
        the existing self-evaluation code can read through it unchanged."""
        for attempt in (0, 1):
            token = self._bearer(force=attempt == 1)
            self._pace()
            self.requests += 1
            try:
                resp = self._http.get(path, params=params, headers={"Authorization": f"Bearer {token}"})
            except httpx.HTTPError as exc:
                raise PersonalTransientError(f"GET: {type(exc).__name__}") from None
            if resp.status_code == 401 and attempt == 0:
                continue                       # the cached token was refused: re-exchange once
            break
        if resp.status_code == 401:
            raise PersonalAuthError("token refused twice: HTTP 401")
        if resp.status_code == 403:
            raise PersonalAuthError("forbidden: HTTP 403")
        if resp.status_code == 404:
            raise PersonalNotFound("HTTP 404")
        if resp.status_code == 429:
            raise PersonalRateLimited("HTTP 429")
        if resp.status_code >= 400:
            raise PersonalTransientError(f"HTTP {resp.status_code}")
        if not resp.content or not resp.content.strip():
            return None
        try:
            return resp.json()
        except ValueError:
            raise PersonalTransientError("response was not JSON") from None

    def get_or_none(self, path: str, params: Optional[dict[str, str]] = None) -> Any:
        """As `get`, but a 404 is an empty day (None), not an error."""
        try:
            return self.get(path, params)
        except PersonalNotFound:
            return None

    # -- the named reads (one line each so the path map stays in this module) ---------------------
    def hrv_day(self, d: str) -> Any:
        return self.get_or_none(HRV_PATH.format(date=d))

    def sleep_day(self, d: str) -> Any:
        return self.get_or_none(SLEEP_PATH, {"date": d})

    def heart_rate_day(self, d: str) -> Any:
        return self.get_or_none(HEART_RATE_PATH, {"date": d})

    def spo2_hourly_day(self, d: str) -> Any:
        return self.get_or_none(SPO2_HOURLY_PATH.format(date=d))

    def body_battery_day(self, d: str) -> Any:
        return self.get_or_none(BODY_BATTERY_PATH, {"startDate": d, "endDate": d})

    def stress_day(self, d: str) -> Any:
        return self.get_or_none(STRESS_PATH.format(start=d, end=d))

    def hr_zones(self) -> Any:
        return self.get_or_none(HR_ZONES_PATH)


def extract_user_profile_pk(payload: Any) -> Optional[str]:
    """`userProfilePk` from a Personal API payload (HRV carries it; some payloads spell it `userProfilePK`),
    as a string, or None. The account fingerprint source (S0): `account_fingerprint(pk)`."""
    if not isinstance(payload, dict):
        return None
    for holder in (payload, payload.get("dailySleepDTO")):       # the sleep payload nests it one level down
        if not isinstance(holder, dict):
            continue
        for key in ("userProfilePk", "userProfilePK"):
            value = holder.get(key)
            if value is not None and not isinstance(value, bool) and str(value).strip() != "":
                return str(value)
    return None
