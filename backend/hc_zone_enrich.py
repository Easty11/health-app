"""Health Connect HR-zone enrichment — fills the stage-1 zoneless rows from raw samples (Q159 stage 2).

The DB-facing half of the zoning. `hr_zones.zone_session` is pure; this module selects its
inputs and writes its outputs:

* every `health_connect` row of the user (ALL of them on every run, not a window: a new HRmax with
  a past effective date must reflow history, and the row count is small);
* samples from `hr_samples` inside the row's [start_time, stop_time] written by the SAME writer as
  the row (`source_package` equal) — a ring's HR inside a Garmin bout is never used for it;
* the HRmax in force on the row's local session date (`user_hrmax`, append-only, dated).

Recompute from samples on every run, so late HR and a changed HRmax both reflow. A row that now
zones is written (z1-z5, hr_avg, hr_max); a row that is withheld goes back to its stage-1 state
(z*, hr_avg, hr_max NULL — INV-7 fail-closed). It is a DATA FILL, not a formula change: no
`formula_version` bump (#356 precedent). It writes only health_connect rows' z*/hr_avg/hr_max and
nothing else — never arbitration inputs (`source`, `source_package`, times), never Polar rows.

Soft-fail in the chain (`scripts.refresh_load.SOFT_STEPS`): a failure leaves rows in the stage-1
state, so it can only withhold information, never corrupt a computed value.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import null
from sqlalchemy.orm import Session

import models
from hr_zones import PLAUSIBLE_BPM, REASONS, entry_from_row, hrmax_in_force, zone_session
from reads.aerobic_reads import HEALTH_CONNECT


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Aware-UTC view of a stored instant. SQLite hands timestamps back naive; Postgres hands
    them back aware (FEEDBACK §49) — the zoning maths needs one shape."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _row_samples(db: Session, user_id: int, row: models.AerobicSession,
                 start: datetime, stop: datetime) -> list[tuple[datetime, int]]:
    pkg = row.source_package or "unknown"
    q = (db.query(models.HrSample.sample_time, models.HrSample.bpm)
         .filter(models.HrSample.user_id == user_id,
                 models.HrSample.source == HEALTH_CONNECT,
                 models.HrSample.source_package == pkg,
                 models.HrSample.sample_time >= start,
                 models.HrSample.sample_time <= stop))
    return [(_utc(t), b) for t, b in q.all()]


def enrich_user(db: Session, user_id: int) -> dict[str, Any]:
    """Zone every health_connect row of `user_id` from its same-writer samples; commit once.

    Returns the chain-report dict: `rows` evaluated, `zoned`, `reasons` (the closed set from
    `hr_zones.REASONS`, every key always present), `skipped_no_interval` (rows with no usable
    [start, stop] — not evaluable, not a reason), `changed` (rows whose stored values moved),
    `over_ceiling` (rows holding a plausible sample above the HRmax in force — counted and listed,
    HRmax never auto-raised), `dropped_implausible` (samples outside the plausibility bounds)."""
    hrmax_rows = [entry_from_row(h)
                  for h in db.query(models.UserHrmax).filter(models.UserHrmax.user_id == user_id).all()]
    rows = (db.query(models.AerobicSession)
            .filter(models.AerobicSession.user_id == user_id,
                    models.AerobicSession.source == HEALTH_CONNECT)
            .order_by(models.AerobicSession.id)
            .all())

    out: dict[str, Any] = {
        "rows": len(rows), "zoned": 0, "reasons": {r: 0 for r in REASONS},
        "skipped_no_interval": 0, "changed": 0, "over_ceiling": 0, "over_ceiling_rows": [],
        "dropped_implausible": 0,
    }
    for row in rows:
        start, stop = _utc(row.start_time), _utc(row.stop_time)
        if start is None or stop is None or stop <= start:
            out["skipped_no_interval"] += 1
            continue
        hrmax = hrmax_in_force(hrmax_rows, row.session_date)
        samples = _row_samples(db, user_id, row, start, stop) if hrmax is not None else []
        res = zone_session(samples, start, stop, hrmax)

        out["reasons"][res.reason] += 1
        out["dropped_implausible"] += res.dropped_implausible
        if res.over_ceiling:
            out["over_ceiling"] += 1
            out["over_ceiling_rows"].append({"id": row.id, "date": row.session_date.isoformat(),
                                             "hr_max": max((b for _, b in samples if PLAUSIBLE_BPM[0] <= b <= PLAUSIBLE_BPM[1]), default=None),
                                             "hrmax_in_force": hrmax})

        if res.zones is not None:
            new = (*res.zones, res.hr_avg, res.hr_max)
            out["zoned"] += 1
        else:
            new = (None, None, None, None, None, None, None)
        old = (row.z1_seconds, row.z2_seconds, row.z3_seconds, row.z4_seconds, row.z5_seconds,
               row.hr_avg, row.hr_max)
        if old != new:
            out["changed"] += 1
            row.z1_seconds, row.z2_seconds, row.z3_seconds, row.z4_seconds, row.z5_seconds = (
                (v if v is not None else null()) for v in new[:5])
            row.hr_avg, row.hr_max = new[5], new[6]
    db.commit()
    return out
