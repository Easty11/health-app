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

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, null
from sqlalchemy.orm import Session

import models
from hr_zones import PLAUSIBLE_BPM, REASONS, entry_from_row, hrmax_in_force, zone_session
from reads.aerobic_reads import HEALTH_CONNECT, arbitrated_sessions, twins_by_canonical


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


def over_ceiling_prompts(db: Session, user_id: int) -> list[dict[str, Any]]:
    """One prompt per BOUT whose health_connect row(s) hold a plausible same-writer sample above the HRmax in
    force. The over-ceiling test is `enrich_user`'s `over_ceiling_rows` (every raw row), read from the
    stored samples instead of from a chain run (nothing persists a run's report): one aggregate query,
    READ-ONLY, so the freshness read can carry it. Same definition as `zone_session`: samples inside
    [start, stop] from the row's own writer, inside the plausibility bounds, `top > hrmax` (equal is not
    over); a row with no usable interval or no HRmax in force is never over.

    A bout two writers recorded (a Polar row and the Garmin row inside it) is one ride, so it earns one
    prompt: the over-ceiling rows are grouped with the SAME arbitration the session lists use
    (`arbitrated_sessions`, `twins_by_canonical`). The prompt sits on the canonical row when that row is
    itself over the ceiling, else on the lowest-id over-ceiling twin, so a sample held only by a suppressed
    twin still prompts. A Hevy mirror is outside the arbitration and keeps its own prompt. The chain report
    still lists every raw row (each is zoned on its own), so prompts equal the chain's rows only when no
    two rows are twins; otherwise they are a subset. Each item: `{id, date, sport, hr_max, hrmax_in_force}`,
    `id` an `aerobic_sessions` row id. It never touches `user_hrmax`: restating is the operator's call (#383)."""
    hrmax_rows = [entry_from_row(h)
                  for h in db.query(models.UserHrmax).filter(models.UserHrmax.user_id == user_id).all()]
    lo, hi = PLAUSIBLE_BPM
    A, H = models.AerobicSession, models.HrSample
    tops = (db.query(A.id, A.session_date, A.sport_name, func.max(H.bpm))
            .join(H, and_(H.user_id == A.user_id, H.source == HEALTH_CONNECT,
                          H.source_package == func.coalesce(A.source_package, "unknown"),
                          H.sample_time >= A.start_time, H.sample_time <= A.stop_time,
                          H.bpm >= lo, H.bpm <= hi))
            .filter(A.user_id == user_id, A.source == HEALTH_CONNECT, A.stop_time > A.start_time)
            .group_by(A.id, A.session_date, A.sport_name)
            .order_by(A.session_date, A.id)
            .all())
    over = []
    for row_id, day, sport, top in tops:
        hrmax = hrmax_in_force(hrmax_rows, day)
        if hrmax is not None and top > hrmax:
            over.append({"id": row_id, "date": day.isoformat(), "sport": sport,
                         "hr_max": top, "hrmax_in_force": hrmax, "_day": day})
    if len(over) < 2:                      # one bout cannot be duplicated by itself: skip the arbitration read
        return [{k: v for k, v in o.items() if k != "_day"} for o in over]

    # One prompt per ARBITRATED bout (the same `arbitrate` the session lists use): a bout two writers
    # recorded is one ride, so it earns one prompt, not one per raw row. The prompt is attributed to the
    # canonical row when that row is itself over the ceiling, else to the lowest-id over-ceiling twin, so a
    # sample held only by a suppressed twin still prompts. Hevy mirrors are outside the arbitration and
    # keep their own prompt.
    rows = arbitrated_sessions(user_id, db, since=min(o["_day"] for o in over) - timedelta(days=1))
    by_id = {r.id: r for r in rows}
    winner_of = {t.id: w for w, twins in twins_by_canonical(rows).items() for t in twins}
    groups: dict[int, list[dict[str, Any]]] = {}
    for o in over:
        r = by_id.get(o["id"])
        key = o["id"] if r is None or getattr(r, "hevy_mirror", False) else winner_of.get(o["id"], o["id"])
        groups.setdefault(key, []).append(o)
    out = []
    for key, members in groups.items():
        pick = next((m for m in members if m["id"] == key), None) or min(members, key=lambda m: m["id"])
        out.append(pick)
    out.sort(key=lambda m: (m["_day"], m["id"]))
    return [{k: v for k, v in m.items() if k != "_day"} for m in out]
