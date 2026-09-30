"""
Garmin Connect HRV connector — server-side pull of the metrics Garmin WITHHOLDS
from Health Connect (HRV now; Body Battery / training readiness optional later).

Why server-side, not Health Connect: Garmin does not publish HRV, Body Battery, or
training readiness to Android Health Connect by design (confirmed empirically — a
first Garmin→HC sync landed HR + sleep + steps with `hrv_rmssd` null every day, no
HRV record type; corroborated by Garmin's published HC data list). The HC path is
structurally incapable of carrying it. So HRV comes via the unofficial
`python-garminconnect` library (curl_cffi OAuth + MFA) — the Garmin analogue of the
Samsung accessibility scraper.

Scope is the WITHHELD metrics only. Garmin sleep / steps / HR are NOT pulled here —
they already arrive via the official Garmin→HC feed into `health_connect_syncs`.
Concentrating those commodity signals behind a fragile unofficial auth is the
opposite of resilient: the unofficial auth lane breaks on Garmin auth changes, so keep
it carrying ONLY what the official channel refuses, and an outage then costs HRV, not
everything.

Credentials: the platform stores only the garminconnect token blob (Fernet-encrypted, in
`UserIntegration(provider="garmin")`), never the Garmin password. Interactive login
with MFA is out-of-band (`scripts/garmin_login.py`); this connector authenticates
from the token blob alone. The refresh token IS persistent account access — a secret.

Library mechanism (garminconnect 0.3.11, curl_cffi-era, read from source):
  * `Garmin().login(tokenstore)` — an inline JSON tokenstore string is loaded inline via
    `client.loads` (no path, no password). It proactively refreshes the DI token if it is
    expiring, so the blob we hold back may be newer than the one we loaded — hence the
    refresh-writeback contract (see `dump_token`).
  * `get_hrv_data(cdate)` — ONE day. 0.3.11 also exposes `get_hrv_data_range`, but this
    connector keeps the per-day loop so each night is normalised / bounds-checked and
    empty days dropped individually (see `get_hrv_range`); the range call is not adopted
    here — deliberately, not for want of an endpoint.
  * `client.dumps()` — serialise the (possibly refreshed) token blob for writeback.
  * A dead/expired token with no password raises `GarminConnectAuthenticationError`
    (login falls through to the credentials branch and finds none) — surfaced here as
    `GarminReconnectError`, mapped to 424 upstream, never a 500. A dead refresh token
    is expected steady-state, not a crash.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

logger = logging.getLogger(__name__)


# RMSSD is valid 1–400 ms; anything outside is corrupt at source, not signal
# (mirrors the samsung_hrv ingest guard). An out-of-range value is nulled/skipped and
# logged; the rest of the night's data is kept. All HRV fields here are RMSSD-domain.
_RMSSD_MIN = 1.0
_RMSSD_MAX = 400.0


# The account-identity call: `garminconnect` itself fetches this endpoint at login to learn the
# display name. The profile-id key name is not documented by the library, so candidates are tried
# in order; if none is present the id is UNRESOLVABLE, which the attach guard treats as a refusal
# (fail closed), never as "no conflict". Shared with `scripts/garmin_identity.py` on purpose: one
# implementation of "which Garmin account is this token".
SOCIAL_PROFILE_PATH = "/userprofile-service/socialProfile"
PROFILE_ID_KEYS = ("profileId", "id", "userProfileId", "userProfilePk")


class GarminProfileUnresolvable(Exception):
    """The social-profile response carried no usable profile id (shape changed, or empty).

    Deliberately distinct from `GarminReconnectError`: the token authenticated, but we cannot say
    WHICH Garmin account it belongs to, so the attach guard cannot do its job and must refuse."""


def extract_profile_id(prof: Any) -> Optional[str]:
    """The profile id from a social-profile response, as a string, or None if absent/unusable."""
    if not isinstance(prof, dict):
        return None
    for key in PROFILE_ID_KEYS:
        value = prof.get(key)
        if value is not None and str(value).strip() != "":
            return str(value)
    return None


def account_fingerprint(profile_id: str) -> str:
    """SHA-256 of the Garmin profile id (namespaced). Equality is all the guard needs, so the raw
    identifier is never stored."""
    return hashlib.sha256(f"garmin:{profile_id}".encode("utf-8")).hexdigest()


class GarminReconnectError(Exception):
    """Auth is dead or MFA is required — the operator must re-run garmin_login.py.

    Distinct from a transient API/network failure: this one means the stored token
    can no longer authenticate. Upstream maps it to 424 (a clean "reconnect Garmin"
    state), never a 500 — a dead refresh token is expected steady-state.
    """


def _bounded_rmssd(value: Any, *, cdate: str, field: str) -> Optional[float]:
    """Return the RMSSD value as a float if in [1, 400] ms, else None (logged).

    Non-numeric or missing values return None silently (absent data, not corrupt)."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not (_RMSSD_MIN <= v <= _RMSSD_MAX):
        logger.warning(
            "garmin hrv ingest: rejected out-of-range %s=%s (valid %s–%s ms) for %s; nulled/skipped",
            field, v, _RMSSD_MIN, _RMSSD_MAX, cdate,
        )
        return None
    return v


def _parse_reading_time(s: Optional[str]) -> Optional[datetime]:
    """Parse a Garmin reading timestamp; attach UTC if naive. Garmin sends
    `readingTimeGMT` like '2026-08-15T05:00:00.0' (no offset — it IS GMT)."""
    if not s:
        return None
    try:
        raw = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (ValueError, AttributeError):
        return None


def _parse_calendar_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def normalize_hrv_day(raw: Optional[dict], cdate: str) -> Optional[dict]:
    """Map one `/hrv-service/hrv/{date}` response to storage shape, or None to skip.

    Returns ``{"captured_at": date, "reading": {...fields...}, "samples": [{...}]}``.
    ``cdate`` (the queried 'YYYY-MM-DD') is the fallback night when the payload omits
    ``hrvSummary.calendarDate``. A day with neither a summary nor any readings is
    skipped (returns None) — there is nothing to store.

    Bounds: every RMSSD-domain field is guarded (nightly avg, weekly avg, baseline
    band, each 5-min sample). An out-of-range field is nulled / that sample skipped,
    and the rest of the night is kept — never the whole night dropped.
    """
    if not isinstance(raw, dict):
        return None

    summary = raw.get("hrvSummary") or {}
    readings = raw.get("hrvReadings") or []

    if not summary and not readings:
        return None

    captured_at = _parse_calendar_date(summary.get("calendarDate")) or _parse_calendar_date(cdate)
    if captured_at is None:
        logger.warning("garmin hrv ingest: unparseable date for %s; skipping day", cdate)
        return None

    baseline = summary.get("baseline") or {}
    reading = {
        "rmssd_ms": _bounded_rmssd(summary.get("lastNightAvg"), cdate=cdate, field="lastNightAvg"),
        "status": summary.get("status"),
        "baseline_low": _bounded_rmssd(baseline.get("balancedLow"), cdate=cdate, field="baseline.balancedLow"),
        "baseline_high": _bounded_rmssd(baseline.get("balancedUpper"), cdate=cdate, field="baseline.balancedUpper"),
        "weekly_avg": _bounded_rmssd(summary.get("weeklyAvg"), cdate=cdate, field="weeklyAvg"),
    }

    samples = []
    for r in readings:
        if not isinstance(r, dict):
            continue
        rt = _parse_reading_time(r.get("readingTimeGMT") or r.get("readingTimeLocal"))
        if rt is None:
            continue
        val = _bounded_rmssd(r.get("hrvValue"), cdate=cdate, field="hrvReadings.hrvValue")
        if val is None:
            continue  # skip the out-of-range/empty sample, keep the rest
        samples.append({"reading_time": rt, "rmssd_ms": val})

    return {"captured_at": captured_at, "reading": reading, "samples": samples}


class GarminClient:
    """Thin wrapper over a `garminconnect.Garmin` authenticated from a token blob.

    Constructed with an already-built garmin object (so tests inject a fake and never
    touch the network); `from_token` builds the real one from an inline token blob.
    """

    def __init__(self, garmin: Garmin) -> None:
        self._garmin = garmin

    @classmethod
    def from_token(cls, token_json: str) -> "GarminClient":
        """Authenticate from an inline garminconnect token blob (no password).

        A blob that can no longer authenticate raises GarminReconnectError; a
        transient connection/rate-limit failure is re-raised as-is for a 502/503 path.
        """
        garmin = Garmin()
        try:
            garmin.login(token_json)
        except (GarminConnectAuthenticationError, GarminConnectTooManyRequestsError) as exc:
            # Auth dead / MFA needed / rate-limited-into-reauth — operator must reconnect.
            raise GarminReconnectError(f"Garmin token can no longer authenticate: {exc}") from exc
        return cls(garmin)

    def profile_id(self) -> str:
        """The Garmin profile id behind this token (one social-profile call).

        Raises GarminProfileUnresolvable when the response has no usable id: an ERROR is logged with
        the response's KEY NAMES only (never values), so a shape change is diagnosable and alerts."""
        try:
            prof = self._garmin.client.connectapi(SOCIAL_PROFILE_PATH)
        except (GarminConnectAuthenticationError, GarminConnectTooManyRequestsError) as exc:
            raise GarminReconnectError(f"Garmin auth lost fetching the profile: {exc}") from exc
        pid = extract_profile_id(prof)
        if pid is None:
            keys = sorted(prof) if isinstance(prof, dict) else type(prof).__name__
            logger.error(
                "garmin profile id UNRESOLVABLE: none of %s in the socialProfile response (keys: %s); "
                "attach guard cannot verify the account, so attaches are refused until this is fixed",
                PROFILE_ID_KEYS, keys,
            )
            raise GarminProfileUnresolvable("no profile id in the Garmin social-profile response")
        return pid

    def dump_token(self) -> str:
        """The current (possibly refreshed) token blob, for re-encryption + writeback."""
        return self._garmin.client.dumps()

    def get_hrv_day(self, cdate: str) -> Optional[dict]:
        """Raw HRV payload for one 'YYYY-MM-DD', or None if Garmin has no data."""
        try:
            return self._garmin.get_hrv_data(cdate)
        except (GarminConnectAuthenticationError, GarminConnectTooManyRequestsError) as exc:
            raise GarminReconnectError(f"Garmin auth lost mid-pull: {exc}") from exc

    def get_hrv_range(self, start: date, end: date) -> list[dict]:
        """Normalised HRV for each day in [start, end] inclusive that has data.

        Per-day loop (deliberate): 0.3.11 exposes `get_hrv_data_range`, but looping keeps
        per-day normalisation / bounds and lets days Garmin has no HRV for be silently
        absent from the result (not an error), rather than adopting the range call.
        """
        out: list[dict] = []
        cur = start
        while cur <= end:
            cdate = cur.isoformat()
            normalized = normalize_hrv_day(self.get_hrv_day(cdate), cdate)
            if normalized is not None:
                out.append(normalized)
            cur += timedelta(days=1)
        return out
