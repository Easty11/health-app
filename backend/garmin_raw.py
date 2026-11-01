"""Append-only raw landing of Garmin Personal API payloads (S3), and the per-user lane status writer (S5).

`land` stores one response in `garmin_raw_payloads`, idempotent on (user, endpoint, ref, payload hash):

  * The payload is scrubbed of identity keys FIRST (`IDENTITY_KEYS`, ruling R3), and the hash is taken over
    the scrubbed payload, so the profile pk, display name and device ids are never stored (the same rule
    `garmin_spo2` applies to its payload) and an identity-only difference never mints a row.
  * The hash is SHA-256 of the canonical JSON (sorted keys, compact separators, UTF-8 with `ensure_ascii`
    off), so emoji in activity names hash and round-trip as the characters they are.
  * An unchanged re-fetch is a no-op; a changed payload (e.g. a day that was still filling) appends a row.
    The CURRENT payload of a key is its row with the greatest `fetched_at` (then id).

`land` flushes but does not commit: the caller commits once per unit of work.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import models

logger = logging.getLogger(__name__)

# Lower-cased key names removed (at any depth) before a payload is hashed or stored. A closed list on
# purpose: an unknown key is kept as sent, so a new field is never silently lost.
IDENTITY_KEYS = frozenset({
    "userprofilepk", "userprofileid", "profileid", "userid", "displayname", "fullname",
    "ownerid", "ownerdisplayname", "ownerfullname", "deviceid", "userprofilefullname",
})
_IDENTITY_PREFIXES = ("ownerprofileimage", "profileimage")


def _is_identity_key(key: Any) -> bool:
    k = str(key).lower()
    return k in IDENTITY_KEYS or k.startswith(_IDENTITY_PREFIXES)


def scrub(obj: Any) -> Any:
    """`obj` without any identity key at any depth (a copy; the input is untouched)."""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items() if not _is_identity_key(k)}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


def payload_sha256(scrubbed: Any) -> str:
    canonical = json.dumps(scrubbed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Landed:
    sha256: str
    inserted: bool
    payload: Any          # the scrubbed payload: what mappers read


def land(db, user_id: int, endpoint: str, ref: str, payload: Any, *, now: Optional[datetime] = None) -> Landed:
    """Land one payload. Idempotent. Flushes; the caller commits."""
    scrubbed = scrub(payload)
    sha = payload_sha256(scrubbed)
    exists = db.scalar(select(models.GarminRawPayload.id).where(
        models.GarminRawPayload.user_id == user_id, models.GarminRawPayload.endpoint == endpoint,
        models.GarminRawPayload.ref == ref, models.GarminRawPayload.payload_sha256 == sha))
    if exists is not None:
        return Landed(sha, False, scrubbed)
    try:
        with db.begin_nested():
            db.add(models.GarminRawPayload(
                user_id=user_id, endpoint=endpoint, ref=str(ref), payload_sha256=sha, payload=scrubbed,
                fetched_at=now or datetime.now(timezone.utc)))
    except IntegrityError:                 # a concurrent writer landed the identical payload first
        return Landed(sha, False, scrubbed)
    return Landed(sha, True, scrubbed)


def latest_payload(db, user_id: int, endpoint: str, ref: str) -> Any:
    """The current landed payload of a key, or None."""
    return db.scalar(
        select(models.GarminRawPayload.payload).where(
            models.GarminRawPayload.user_id == user_id, models.GarminRawPayload.endpoint == endpoint,
            models.GarminRawPayload.ref == str(ref))
        .order_by(models.GarminRawPayload.fetched_at.desc(), models.GarminRawPayload.id.desc()).limit(1))


# -- lane status (S5) -------------------------------------------------------------------------------

OK, EMPTY, AUTH_FAILED, RATE_LIMITED, ERROR, SKIPPED_NEEDS_REFRESH = (
    "ok", "empty", "auth_failed", "rate_limited", "error", "skipped_needs_refresh")
_SUCCESS = frozenset({OK, EMPTY})

LANE_PERSONAL_TOKEN = "personal_token"
LANE_PERSONAL_HRV = "personal_hrv"
LANE_PERSONAL_WELLNESS = "personal_wellness"
LANE_PERSONAL_SELFEVAL = "personal_selfeval"
LANE_DI_SPO2 = "di_spo2"
LANE_WAKE_DAY = "wake_day_fetch"   # the wake-day capture attempt itself (check-in / Recovery / Refresh / 10:00 backstop)


def record_lane(db, user_id: int, lane: str, outcome: str, reason: Optional[str] = None,
                *, now: Optional[datetime] = None) -> None:
    """Upsert the (user, lane) status row and COMMIT. `reason` is a class name / short code, truncated; it
    must never carry a payload, key or token. Never raises: status bookkeeping must not cost a sync."""
    now = now or datetime.now(timezone.utc)
    try:
        row = db.query(models.IntegrationLaneStatus).filter_by(user_id=user_id, lane=lane).first()
        if row is None:
            row = models.IntegrationLaneStatus(user_id=user_id, lane=lane, last_attempt_at=now, outcome=outcome)
            db.add(row)
        row.last_attempt_at = now
        row.outcome = outcome
        row.reason = (reason or None) and reason[:200]
        if outcome in _SUCCESS:
            row.last_success_at = now
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("lane status not recorded for user %s lane %s: %s", user_id, lane, type(exc).__name__)
