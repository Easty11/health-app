"""Service layer for the Garmin Personal API: credentials -> client, token write-back, lane runner.

  * `personal_client(db, user_id)` yields a `PersonalClient` built from the user's `garmin_personal`
    integration row (Fernet-decrypted key, cached bearer token if it still decrypts), or None when the user
    has no such row. On exit the possibly re-exchanged token is written back ENCRYPTED and committed. A cached
    token that fails to decrypt (e.g. after a key rotation) is a cache miss: the client re-exchanges.
  * `record_failure` / `run_lane` turn a Personal API failure into an `integration_lane_status` row, and an
    auth failure also into the `personal_token` lane (the key is dead or expired: the operator must act).

Nothing here logs or returns the key or token; reasons are exception class names plus HTTP status text.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterator, Optional

import httpx
from cryptography.fernet import InvalidToken

import garmin_raw
import models
from connectors import garmin_personal as gp
from encryption import decrypt, encrypt

logger = logging.getLogger(__name__)

PROVIDER = "garmin_personal"


def get_row(db, user_id: int) -> Optional[models.UserIntegration]:
    return db.query(models.UserIntegration).filter_by(user_id=user_id, provider=PROVIDER).first()


PACE_S = 2.0   # min gap between data requests on the real host (12 requests 2 s apart: all 200; a burst: 429)


def build_client(row: models.UserIntegration, *, transport: Optional[httpx.BaseTransport] = None,
                 min_interval_s: Optional[float] = None) -> gp.PersonalClient:
    """The real host is paced at `PACE_S`; a client over an injected transport (a test double) is not."""
    if min_interval_s is None:
        min_interval_s = 0.0 if transport is not None else PACE_S
    token = expires = None
    if row.access_token_encrypted and row.access_token_expires_at is not None:
        try:
            token, expires = decrypt(row.access_token_encrypted), row.access_token_expires_at
        except (InvalidToken, ValueError, TypeError):
            token = expires = None                     # a cache miss, not an error
    return gp.PersonalClient(decrypt(row.api_key_encrypted), access_token=token, token_expires_at=expires,
                             transport=transport, min_interval_s=min_interval_s)


def persist_token(db, row: models.UserIntegration, client: gp.PersonalClient) -> None:
    """Write the client's token back (encrypted) when it differs from what the row holds. Best effort."""
    token, expires = client.token_state()
    if token is None or expires is None:
        return
    try:
        held = None
        if row.access_token_encrypted:
            try:
                held = decrypt(row.access_token_encrypted)
            except (InvalidToken, ValueError, TypeError):
                held = None
        if held != token:
            row.access_token_encrypted = encrypt(token)
            row.access_token_expires_at = expires
            db.commit()
    except Exception as exc:  # noqa: BLE001 -- losing a cache write costs one re-exchange, never a sync
        db.rollback()
        logger.warning("garmin personal: token cache not written for user %s: %s", row.user_id, type(exc).__name__)


@contextmanager
def personal_client(db, user_id: int, *, transport: Optional[httpx.BaseTransport] = None
                    ) -> Iterator[Optional[gp.PersonalClient]]:
    row = get_row(db, user_id)
    if row is None:
        yield None
        return
    client = build_client(row, transport=transport)
    try:
        yield client
    finally:
        persist_token(db, row, client)
        client.close()


class NoPersonalKey(Exception):
    """The user has no `garmin_personal` key, so the Personal API cannot serve them. Since PR-B (#449) there is
    no DI fallback for HRV or self-evaluation: the caller maps this to its own 'not connected' state."""


def failure_outcome(exc: BaseException) -> str:
    if isinstance(exc, gp.PersonalAuthError):
        return garmin_raw.AUTH_FAILED
    if isinstance(exc, gp.PersonalRateLimited):
        return garmin_raw.RATE_LIMITED
    return garmin_raw.ERROR


def record_failure(db, user_id: int, lane: str, exc: BaseException, *, now: Optional[datetime] = None) -> None:
    """Record a lane failure (and the token lane too when the key itself was refused)."""
    reason = f"{type(exc).__name__}: {exc}"
    garmin_raw.record_lane(db, user_id, lane, failure_outcome(exc), reason, now=now)
    if isinstance(exc, gp.PersonalAuthError):
        garmin_raw.record_lane(db, user_id, garmin_raw.LANE_PERSONAL_TOKEN, garmin_raw.AUTH_FAILED, reason, now=now)


def record_success(db, user_id: int, lane: str, *, empty: bool = False, now: Optional[datetime] = None) -> None:
    garmin_raw.record_lane(db, user_id, lane, garmin_raw.EMPTY if empty else garmin_raw.OK, now=now)
    garmin_raw.record_lane(db, user_id, garmin_raw.LANE_PERSONAL_TOKEN, garmin_raw.OK, now=now)


def run_lane(db, user_id: int, lane: str, fn: Callable[[gp.PersonalClient], dict], *,
             transport: Optional[httpx.BaseTransport] = None, now: Optional[datetime] = None) -> dict[str, Any]:
    """Run `fn(client)` for one user on one lane; never raises. Returns `fn`'s counts, or
    `{"error": ..., "counts": ...}`, or `{"skipped": "no_personal_key"}`. Records the lane status either way."""
    try:
        with personal_client(db, user_id, transport=transport) as client:
            if client is None:
                return {"skipped": "no_personal_key"}
            out = fn(client)
    except gp.PersonalApiError as exc:
        db.rollback()
        record_failure(db, user_id, lane, exc, now=now)
        logger.warning("garmin personal: user %s lane %s failed: %s", user_id, lane, type(exc).__name__)
        return {"error": f"{type(exc).__name__}: {exc}", "counts": getattr(exc, "counts", None)}
    except Exception as exc:  # noqa: BLE001 -- the class is the whole report
        db.rollback()
        garmin_raw.record_lane(db, user_id, lane, garmin_raw.ERROR, type(exc).__name__, now=now)
        logger.warning("garmin personal: user %s lane %s crashed: %s", user_id, lane, type(exc).__name__)
        return {"error": type(exc).__name__, "counts": None}
    if out.get("errors"):                         # a lane that swallowed per-item errors is not a success
        garmin_raw.record_lane(db, user_id, lane, garmin_raw.ERROR, f"errors={out['errors']}", now=now)
        return out
    record_success(db, user_id, lane, empty=not any(v for k, v in out.items() if k not in ("days", "empty")), now=now)
    return out


# -- attach (S1) -------------------------------------------------------------------------------------

class AttachError(Exception):
    """An attach the guard refuses. `code` is one of: empty_key, bad_expiry, refused, unverified, conflict,
    own_mismatch. The message names no other user and never carries the key."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


ATTACH_CONFLICT = "This Garmin account is already connected to a different user."
ATTACH_UNVERIFIED = ("Could not verify which Garmin account this key belongs to, so it was not saved. "
                     "Please retry in a few minutes.")
ATTACH_OWN_MISMATCH = ("This key belongs to a different Garmin account than the one already connected for "
                       "this user, so it was not saved.")
_PK_PROBE_DAYS = 7          # how far back to look for a payload that carries userProfilePk


def resolve_profile_pk(client: gp.PersonalClient, today: date) -> Optional[str]:
    """`userProfilePk` from the most recent HRV (then sleep) payload within `_PK_PROBE_DAYS`. The HRV payload
    carries it (chat probe, 24 Oct 2026). None when no recent payload does: the guard then FAILS CLOSED."""

    for reader in (client.hrv_day, client.sleep_day):
        for back in range(_PK_PROBE_DAYS):
            pk = gp.extract_user_profile_pk(reader((today - timedelta(days=back)).isoformat()))
            if pk is not None:
                return pk
    return None


def attach_key(db, user_id: int, api_key: str, key_expires_on: date, *, today: date,
               transport: Optional[httpx.BaseTransport] = None) -> dict[str, Any]:
    """Verify and store a Personal API key for `user_id`. The platform's same-account guard, on `userProfilePk`:

      * the key is exchanged, and the account it belongs to resolved (a refused key -> `refused`; any
        inability to resolve -> `unverified`, nothing stored: FAILS CLOSED);
      * refused (`conflict`) when that account is connected to a DIFFERENT user on either Garmin provider;
      * refused (`own_mismatch`, ruling R6) when this user's own DI connection is a different account, since
        HRV and SpO2 would then describe two people. A DI row with no recorded fingerprint does not block.
    The access token obtained for the check is cached (encrypted) on the row. Commits."""
    from sqlalchemy.exc import IntegrityError

    from connectors.garmin import account_fingerprint

    key = (api_key or "").strip()
    if not key:
        raise AttachError("empty_key", "api_key must not be empty")
    if key_expires_on <= today:
        raise AttachError("bad_expiry", "key_expires_on must be a future date (the expiry shown when the key was created)")

    client = gp.PersonalClient(key, transport=transport)
    try:
        try:
            pk = resolve_profile_pk(client, today)
        except gp.PersonalAuthError as exc:
            raise AttachError("refused", f"Garmin refused this key: {exc}") from None
        except gp.PersonalApiError:
            logger.exception("garmin personal attach BLOCKED for user %s: could not verify the account", user_id)
            raise AttachError("unverified", ATTACH_UNVERIFIED) from None
        if pk is None:
            logger.error("garmin personal profile pk UNRESOLVABLE for user %s: no userProfilePk in any recent "
                         "HRV or sleep payload; attaches are refused until this is fixed", user_id)
            raise AttachError("unverified", ATTACH_UNVERIFIED)
        fingerprint = account_fingerprint(pk)
        token, expires = client.token_state()
    finally:
        client.close()

    elsewhere = (db.query(models.UserIntegration.id).filter(
        models.UserIntegration.provider.in_(("garmin", PROVIDER)),
        models.UserIntegration.account_fingerprint == fingerprint,
        models.UserIntegration.user_id != user_id).first())
    if elsewhere is not None:
        logger.warning("garmin personal attach REFUSED for user %s: account already connected to another user", user_id)
        raise AttachError("conflict", ATTACH_CONFLICT)
    own_di = db.query(models.UserIntegration).filter_by(user_id=user_id, provider="garmin").first()
    if own_di is not None and own_di.account_fingerprint is not None and own_di.account_fingerprint != fingerprint:
        logger.warning("garmin personal attach REFUSED for user %s: key is a different account from the DI row", user_id)
        raise AttachError("own_mismatch", ATTACH_OWN_MISMATCH)

    row = get_row(db, user_id)
    if row is None:
        row = models.UserIntegration(user_id=user_id, provider=PROVIDER, api_key_encrypted=encrypt(key))
        db.add(row)
    else:
        row.api_key_encrypted = encrypt(key)
    row.account_fingerprint = fingerprint
    row.key_expires_on = key_expires_on
    row.access_token_encrypted = encrypt(token) if token else None
    row.access_token_expires_at = expires if token else None
    try:
        db.commit()
    except IntegrityError:                  # a concurrent attach won the unique index
        db.rollback()
        raise AttachError("conflict", ATTACH_CONFLICT) from None
    garmin_raw.record_lane(db, user_id, garmin_raw.LANE_PERSONAL_TOKEN, garmin_raw.OK)
    return {"key_expires_on": key_expires_on.isoformat(), "days_to_expiry": (key_expires_on - today).days}
