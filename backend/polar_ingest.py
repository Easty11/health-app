"""
Polar AccessLink v4 ingest core — per-user, request-free (Q154).

sync_user(db, user_id, *, days, run_cascade=True) -> dict

The fetch+persist body of `POST /integrations/polar/sync`, extracted so the load chain
(`scripts/refresh_load.run_user_chain`, step `polar_sync`) can pull new Polar sessions
into `aerobic_sessions` without a request, a `current_user`, or a manual Sync press.
The router (`routers/polar.py::sync_polar_sessions`) delegates here and keeps its
response contract; this module never raises `HTTPException` — it raises the plain
exceptions below, and each caller maps them (router → HTTP status, chain → soft-fail
step outcome).

Token storage lives here too (the OAuth callback in the router reuses `store_tokens`),
so a batch caller can read and refresh a user's token from
`UserIntegration(provider="polar")` outside any request.
"""
import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

import models
from connectors.polar import PolarV4Client, refresh_access_token
from encryption import decrypt, encrypt
from load_events_metabolic import compute_metabolic_load
from metabolic_cascade import run_metabolic_cascade


class PolarIngestError(Exception):
    """Base for every failure `sync_user` raises."""


class NotConnected(PolarIngestError):
    """The user has no `UserIntegration(provider="polar")` row. Router → 404."""


class TokenRefreshFailed(PolarIngestError):
    """The stored token was expired and the refresh call failed. Router → 424 (a connector
    failure, not session death — never 401, so the frontend never logs the user out)."""


class PolarApiError(PolarIngestError):
    """A v4 data call (summary list or zone-feature fetch) failed. Router → 502."""


# ── token storage ────────────────────────────────────────────────────────────

def get_polar_row(user_id: int, db: Session) -> models.UserIntegration | None:
    return (
        db.query(models.UserIntegration)
        .filter_by(user_id=user_id, provider="polar")
        .first()
    )


def load_tokens(user_id: int, db: Session) -> dict:
    row = get_polar_row(user_id, db)
    if not row:
        raise NotConnected("Polar not connected")
    return json.loads(decrypt(row.api_key_encrypted))


def store_tokens(user_id: int, token_data: dict, db: Session) -> None:
    """Persist a token response, computing an absolute expiry."""
    expires_in = token_data.get("expires_in", 43199)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    payload = json.dumps({
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": expires_at,
        "scope": token_data.get("scope"),
        "token_type": token_data.get("token_type"),
    })
    row = get_polar_row(user_id, db)
    if row:
        row.api_key_encrypted = encrypt(payload)
    else:
        db.add(models.UserIntegration(
            user_id=user_id, provider="polar", api_key_encrypted=encrypt(payload),
        ))
    db.commit()


def valid_client(user_id: int, db: Session) -> PolarV4Client:
    """Return a client with a non-expired access token, refreshing if needed."""
    tokens = load_tokens(user_id, db)
    expires_at = tokens.get("expires_at")
    needs_refresh = True
    if expires_at:
        try:
            needs_refresh = datetime.fromisoformat(expires_at) <= datetime.now(timezone.utc) + timedelta(seconds=60)
        except ValueError:
            needs_refresh = True

    if needs_refresh and tokens.get("refresh_token"):
        try:
            new_tokens = refresh_access_token(tokens["refresh_token"])
            # refresh response may omit refresh_token — keep the old one if so
            new_tokens.setdefault("refresh_token", tokens["refresh_token"])
            store_tokens(user_id, new_tokens, db)
            tokens = load_tokens(user_id, db)
        except Exception as exc:
            raise TokenRefreshFailed(f"Polar token refresh failed: {exc}") from exc

    return PolarV4Client(tokens["access_token"])


# ── ingest ───────────────────────────────────────────────────────────────────

def sync_user(db: Session, user_id: int, *, days: int, run_cascade: bool = True) -> dict:
    """Pull v4 training sessions over the last `days`, upsert into aerobic_sessions,
    ENRICH the zoneless v4 rows in the window with per-exercise HR zones, then (when
    `run_cascade`) fire the per-user metabolic cascade (transform + rollup).

    Two-pass ingest:
      1. Summary list/upsert (`list_training_sessions_chunked`) — the v4 summary
         transport omits the HR-zone split (#255/Q123), so these rows land zoneless.
      2. Zone enrichment — the v4 *feature* mode DOES surface zones
         (`features='zones'`, one-day window cap; DECISIONS_LOG — v4 zone-enrichment),
         in the same schema the ZIP export carries. For exactly the dates that have a
         zoneless polar_v4 row in the window, fetch zones and merge `z*_seconds` onto
         those rows by `source_session_id`.

    Aerobic ingest is recompute-triggering: the on-ingest cascade then recomputes
    metab-v1 with the newly-qualifying bouts — no manual recompute, no formula bump.
    Enriching a v4 twin never flips a dual-lane bout's canonical source: flow_export
    outranks v4 (#260), so its richer row stays canonical and the bout still emits once.

    `run_cascade=False` is for the load chain, whose own `load_events_metabolic` /
    `load_metrics_metab` steps recompute after this one — so the cascade never runs twice.

    Scope: enrichment covers the SYNC WINDOW only. Zoneless v4 rows older than `days`
    stay zoneless until a wider sync touches them — a one-time wide-window sync backfills
    history; ongoing syncs keep it current.

    Returns `{"synced", "enriched", "available"}` plus `"cascade"` when `run_cascade`.
    Raises NotConnected / TokenRefreshFailed / PolarApiError.
    """
    client = valid_client(user_id, db)
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days)
    end = today + timedelta(days=1)

    try:
        raw_sessions = client.list_training_sessions_chunked(start, end)
    except Exception as exc:
        raise PolarApiError(f"Polar v4 API error: {exc}") from exc

    stored = 0
    for raw in raw_sessions:
        fields = PolarV4Client.parse_session(raw)
        if not fields or not fields.get("source_session_id"):
            continue
        # Dedup across sources: a session already imported from the ZIP
        # (polar_flow_export, which carries cardio_load + zones) takes precedence,
        # so v4 only adds sessions not already present.
        exists = (
            db.query(models.AerobicSession)
            .filter(
                models.AerobicSession.user_id == user_id,
                models.AerobicSession.source_session_id == fields["source_session_id"],
                models.AerobicSession.source.in_(["polar_flow_export", "polar_v4"]),
            )
            .first()
        )
        if exists:
            continue
        db.add(models.AerobicSession(user_id=user_id, **fields))
        stored += 1

    db.commit()

    enriched = _enrich_v4_zones(client, user_id, start, db)

    result = {
        "synced": stored,
        "enriched": enriched,
        "available": len(raw_sessions),
    }
    if run_cascade:
        result["cascade"] = run_metabolic_cascade(db, user_id)
    return result


def _row_zone_seconds(row) -> dict[int, int | None]:
    return {i: getattr(row, f"z{i}_seconds") for i in range(1, 6)}


def _enrich_v4_zones(client, user_id: int, window_start: date, db: Session) -> int:
    """Backfill `z*_seconds` on this user's zoneless `polar_v4` rows dated on/after
    `window_start`, using the v4 zone-feature fetch. Returns the number of rows enriched.

    "Zoneless" is the transform's own INV-7 predicate — NOT qualifying (every zone
    NULL/0, so the zone-sum is 0) — because a summary-synced v4 row stores `z*_seconds`
    as 0 (the column default), never NULL. The fetch is scoped to exactly the dates
    those rows fall on, so a sync where every v4 row already carries zones makes no extra
    API calls. A row is overwritten only when its fetched session carries a QUALIFYING
    zone split (positive sum); once enriched it is no longer a target, so re-syncs are
    idempotent. `polar_flow_export` rows are never touched; a v4 twin enriched here stays
    non-canonical behind its flow_export twin (#260), so single-emission holds."""
    v4_rows = (
        db.query(models.AerobicSession)
        .filter(
            models.AerobicSession.user_id == user_id,
            models.AerobicSession.source == "polar_v4",
            models.AerobicSession.session_date >= window_start,
        )
        .all()
    )
    targets = [r for r in v4_rows if not compute_metabolic_load(_row_zone_seconds(r)).qualifying]
    if not targets:
        return 0

    days = sorted({r.session_date for r in targets})
    try:
        zoned_raw = client.list_zoned_sessions(days)
    except Exception as exc:
        raise PolarApiError(f"Polar v4 zone fetch error: {exc}") from exc

    # Map source_session_id → z*_seconds, but only for sessions whose fetched split is
    # itself qualifying (skips a fetch that came back with no usable zones — leaves the
    # row as-is rather than writing zeros over zeros).
    z_by_sid: dict[str, list] = {}
    for raw in zoned_raw:
        fields = PolarV4Client.parse_session(raw)
        sid = (fields or {}).get("source_session_id")
        if not sid:
            continue
        zsecs = [fields.get(f"z{i}_seconds") for i in range(1, 6)]
        if compute_metabolic_load(dict(zip(range(1, 6), zsecs))).qualifying:
            z_by_sid[sid] = zsecs

    enriched = 0
    for row in targets:
        zsecs = z_by_sid.get(row.source_session_id)
        if not zsecs:
            continue
        row.z1_seconds, row.z2_seconds, row.z3_seconds, row.z4_seconds, row.z5_seconds = zsecs
        enriched += 1

    if enriched:
        db.commit()
    return enriched
