"""The per-user metabolic recompute cascade fired after any aerobic ingest.

ONE named per-user callable — `run_metabolic_cascade(db, user_id)` — invoked by
every aerobic ingest so that recompute-on-ingest is automatic, never a button:

  * `POST /integrations/polar/import-export` (Flow-export ZIP upload), and
  * `POST /integrations/polar/sync` (v4 live sync).

A third caller (the Phase-3 Polar webhook handler) is anticipated; it will reuse
this same callable rather than duplicating the sequence route-side.

The cascade is the two-level recompute in dependency order — the repo's standing
rule "recompute `load_events`, then `load_metrics`":

  1. metabolic transform  `aerobic_sessions` → `load_events`   (`metab-v1`)
  2. daily rollup         `load_events`      → `load_metrics`  (`metab-v1` / `banister-v1`,
                                                                the `metabolic` window)

Both steps are per-user and idempotent — each delete-and-reinserts only its own
(user, formula_version) rows — so the cascade is safe to re-fire and never touches
the strength (`tier0-v1`) series. It runs SYNCHRONOUSLY in-request: delete-and-
reinsert for a single user is cheap at current scale (the design default). Swap to
a framework background task only if a measured response-time concern appears.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from load_events_metabolic import FORMULA_VERSION_METABOLIC, compute_metabolic_load_events
from load_metrics import compute_load_metrics


def run_metabolic_cascade(db: Session, user_id: int) -> dict[str, Any]:
    """Recompute one user's metabolic load from source, then roll it up.

    Returns `{"transform": <transform summary>, "rollup": <rollup summary>}` — the
    per-user coverage counts from the metabolic transform and the daily-rollup
    accounting, suitable for surfacing in an ingest response.
    """
    transform = compute_metabolic_load_events(db, user_id)
    rollup = compute_load_metrics(db, user_id, formula_version=FORMULA_VERSION_METABOLIC)
    return {"transform": transform, "rollup": rollup}
