"""Metabolic (aerobic) load transform — `aerobic_sessions` → `load_events` (S1).

The Metabolic sibling of the Tier-0 strength transform (`backend/load_events.py`):
the same source-neutral `load_events` store, a different source table and formula.
Design authority: `docs/load-governor-trajectory-design.md` §3.1 (ledger gap), §10 S1,
INV-2 (unit-lock), INV-6 (ratio-free criterion), INV-7 (fail-closed coverage).

Reads one row per `aerobic_sessions` session and emits one Metabolic `load_events` row
per QUALIFYING session, in the window-native unit of a zone-weighted TRIMP. The daily
`load_metrics` + Banister rollup (gate 3) already provisions the `metabolic` window (τ=4)
and lights up the moment these rows exist — no rollup change.

Formula — Edwards (1993) zone-weighted TRIMP, a REASONED PRIOR (#32), literature-standard
and requiring no individual physiological constants::

    trimp = Σ_z (zone_z_seconds / 60) × weight_z ,   weight = {z1:1, z2:2, z3:3, z4:4, z5:5}

Per D-B the computed history is a RECOMPUTE, never a migration: the formula is tagged with
`FORMULA_VERSION_METABOLIC`; a correction bumps the version and re-derives from source. The
orchestrator is delete-and-reinsert scoped to (user, `FORMULA_VERSION_METABOLIC`) ONLY — it
never touches the strength transform's `tier0-v1` rows — and is idempotent on the natural
key `uq_load_event_session_window_version`.

Fail-closed (INV-7): a session with no usable zone data (every `z*_seconds` NULL, or the
zone-sum is zero) emits NO row and increments a coverage counter. There is NO Banister-TRIMP
(HR-based) fallback in v1 — mixing formulas inside one window's series would break
within-window comparability (INV-2). Polar's proprietary `cardio_load` is NEVER the load
input (device-locked, non-recomputable — violates #32 provenance discipline); it is used
only for a convergent-sanity correlation in the summary.

Windows are ORTHOGONAL: a session captured by both Hevy (→ Mechanical / Neuromuscular) and
Polar (→ Metabolic) deposits into DIFFERENT windows — this is the four-window design
functioning, not double-counting.

Re-runnable CLI::

    python backend/load_events_metabolic.py            # recompute every user with aerobic sessions
    python backend/load_events_metabolic.py --user 1   # one user
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any, Mapping

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# REASONED-PRIOR constants (provenance-labelled #32; tagged by FORMULA_VERSION_METABOLIC)
# ---------------------------------------------------------------------------

FORMULA_VERSION_METABOLIC = "metab-v1"

WINDOW_METABOLIC = "metabolic"        # lowercase — matches the load_metrics τ allowlist key
UNIT_METABOLIC = "trimp_edw_au"       # Edwards zone-weighted TRIMP, arbitrary units (INV-2 unit-lock)

# Edwards (1993) zone-weighted TRIMP: minutes in HR zone z, weighted by z. A reasoned prior
# (literature-standard), NOT an individual physiological constant — so it needs no per-athlete
# calibration and is recomputable from stored zone seconds alone.
ZONES = (1, 2, 3, 4, 5)
EDWARDS_WEIGHTS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}


# ---------------------------------------------------------------------------
# Per-session load (pure)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetabolicLoad:
    """One aerobic session's Edwards TRIMP and its qualifying verdict.

    `qualifying` is False for a fail-closed (INV-7) session — every zone NULL, or a
    zone-sum of zero — which emits no row. `zone_seconds` carries only the non-NULL zones
    (diagnostic, for provenance)."""
    trimp: float
    qualifying: bool
    zone_seconds: dict[int, int]


def edwards_trimp(zone_seconds: Mapping[int, int | None]) -> float:
    """Σ (zone_z_seconds / 60) × weight_z over zones 1..5. A NULL zone contributes nothing
    (treated as zero minutes), NOT imputed. Pure and deterministic."""
    total = 0.0
    for z in ZONES:
        secs = zone_seconds.get(z)
        if secs is None:
            continue
        total += (float(secs) / 60.0) * EDWARDS_WEIGHTS[z]
    return total


def compute_metabolic_load(zone_seconds: Mapping[int, int | None]) -> MetabolicLoad:
    """Score one session's zone seconds into an Edwards TRIMP + qualifying verdict.

    Qualifying (INV-7) = at least one `z*_seconds` non-NULL AND the zone-sum > 0. An
    all-NULL session and an all-zero session both fail closed → no row emitted."""
    present = {z: zone_seconds.get(z) for z in ZONES}
    any_non_null = any(present[z] is not None for z in ZONES)
    trimp = edwards_trimp(present)
    qualifying = any_non_null and trimp > 0.0
    return MetabolicLoad(
        trimp=round(trimp, 6),
        qualifying=qualifying,
        zone_seconds={z: int(present[z]) for z in ZONES if present[z] is not None},
    )


def _occurred_at(row: Any) -> datetime:
    """The instant the load_events row is anchored to. Prefer the session's `start_time`;
    fall back to UTC-midnight of the always-present `session_date` so EVERY qualifying
    session feeds the rollup (which drops NULL-`occurred_at` rows). UTC-midnight of day D
    converts to 10:00 AEST on the SAME day D, so `load_metrics._local_day` buckets it
    correctly."""
    if row.start_time is not None:
        return row.start_time
    return datetime.combine(row.session_date, time.min, tzinfo=timezone.utc)


def _pearson(pairs: list[tuple[float, float]]) -> float | None:
    """Pearson r over (trimp, cardio_load) pairs; None if fewer than two pairs or either
    series is constant. Convergent-sanity diagnostic only — never a gate, never a load
    input."""
    n = len(pairs)
    if n < 2:
        return None
    sx = sum(x for x, _ in pairs)
    sy = sum(y for _, y in pairs)
    mx, my = sx / n, sy / n
    cov = sum((x - mx) * (y - my) for x, y in pairs)
    vx = sum((x - mx) ** 2 for x, _ in pairs)
    vy = sum((y - my) ** 2 for _, y in pairs)
    if vx <= 0.0 or vy <= 0.0:
        return None
    return cov / math.sqrt(vx * vy)


# ---------------------------------------------------------------------------
# Orchestrator (DB): recompute a user's Metabolic load_events from source
# ---------------------------------------------------------------------------

def compute_metabolic_load_events(
    db: Session,
    user_id: int,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Recompute all Metabolic `load_events` for one user from `aerobic_sessions`.

    REPLACES the user's rows for `FORMULA_VERSION_METABOLIC` (delete-then-insert —
    idempotent recompute, D-B); the strength transform's `tier0-v1` rows are untouched.
    Rows are sourced through read-time cross-source arbitration (#260/Q127): a row emits
    only if it is BOTH canonical (the winning row of its same-bout cluster) and qualifying
    (INV-7). Non-canonical rows are counted in `sessions_skipped_non_canonical`;
    non-qualifying rows in `sessions_skipped_no_zones`. Returns per-user coverage counts
    plus a convergent-sanity TRIMP-vs-`cardio_load` correlation (`cardio_load` is NOT a
    load input)."""
    now = now or datetime.now(timezone.utc)

    # Source rows through read-time cross-source arbitration (#260/Q127) rather
    # than a raw select: each row carries a derived `.canonical` flag, and the
    # emit loop below emits ONLY the canonical row of each same-bout cluster, so
    # single-emission of the metabolic series is a guaranteed property, not the
    # accidental side effect of the fail-closed skip (INV-7) landing on a zoneless
    # v4 twin. Lazy import — aerobic_reads imports compute_metabolic_load from this
    # module, so a top-level import here would be circular. `arbitrated_sessions`
    # with no since/limit returns the user's FULL session set (arbitration sees
    # every session, never a window) ordered session_date desc.
    from reads.aerobic_reads import arbitrated_sessions

    rows = arbitrated_sessions(user_id, db)

    # Replace this version's rows for the user (idempotent recompute; tier0-v1 untouched).
    db.execute(
        delete(models.LoadEvent).where(
            models.LoadEvent.user_id == user_id,
            models.LoadEvent.formula_version == FORMULA_VERSION_METABOLIC,
        )
    )

    events_written = 0
    sessions_skipped_no_zones = 0
    sessions_skipped_non_canonical = 0
    corr_pairs: list[tuple[float, float]] = []
    for row in rows:
        # Emit only from the canonical row of each same-bout cluster (#260/Q127).
        # A non-canonical row is a cross-source duplicate of a bout emitted from
        # its richer twin; skipping it here makes single-emission guaranteed. The
        # richer twin always outranks (aerobic_reads._SOURCE_RANK: flow_export >
        # v4 > health_connect), so the canonical row is the zoned one.
        if not row.canonical:
            sessions_skipped_non_canonical += 1
            continue
        ml = compute_metabolic_load({
            1: row.z1_seconds, 2: row.z2_seconds, 3: row.z3_seconds,
            4: row.z4_seconds, 5: row.z5_seconds,
        })
        if not ml.qualifying:
            sessions_skipped_no_zones += 1
            continue
        db.add(models.LoadEvent(
            user_id=user_id,
            source="aerobic_sessions",
            source_ref=str(row.id),           # stable internal id; source_session_id is nullable
            load_window=WINDOW_METABOLIC,
            occurred_at=_occurred_at(row),
            load=ml.trimp,
            unit=UNIT_METABOLIC,
            formula_version=FORMULA_VERSION_METABOLIC,
            provenance={
                "zone_seconds": ml.zone_seconds,
                "zone_source": row.source,     # 'polar_flow_export' | 'health_connect'
                "sport_name": row.sport_name,
                "duration_minutes": row.duration_minutes,
                "had_hr_avg": row.hr_avg is not None,
            },
            computed_at=now,
        ))
        events_written += 1
        if row.cardio_load is not None:
            corr_pairs.append((ml.trimp, float(row.cardio_load)))

    db.commit()
    return {
        "formula_version": FORMULA_VERSION_METABOLIC,
        "sessions": len(rows),
        "events_written": events_written,
        "sessions_skipped_no_zones": sessions_skipped_no_zones,
        "sessions_skipped_non_canonical": sessions_skipped_non_canonical,
        "cardio_load_pairs": len(corr_pairs),
        "trimp_cardio_load_pearson_r": _pearson(corr_pairs),
    }


def _users_with_aerobic_sessions(db: Session) -> list[int]:
    """Distinct user ids that have at least one `aerobic_sessions` row."""
    rows = db.execute(
        select(models.AerobicSession.user_id).distinct()
    ).scalars().all()
    return sorted(rows)


def compute_all_users_metabolic(
    db: Session, *, only_user_id: int | None = None
) -> dict[str, Any]:
    """Recompute Metabolic load_events for one user or every user with aerobic sessions."""
    if only_user_id is not None:
        return {"users": 1, "per_user": {only_user_id: compute_metabolic_load_events(db, only_user_id)}}
    per_user: dict[int, Any] = {}
    for uid in _users_with_aerobic_sessions(db):
        per_user[uid] = compute_metabolic_load_events(db, uid)
    return {"users": len(per_user), "per_user": per_user}


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Recompute Metabolic (Edwards TRIMP) load_events from aerobic_sessions."
    )
    parser.add_argument("--user", type=int, default=None, help="only this user id")
    args = parser.parse_args()

    from database import SessionLocal

    _db = SessionLocal()
    try:
        _result = compute_all_users_metabolic(_db, only_user_id=args.user)
        print(_result)
    finally:
        _db.close()
