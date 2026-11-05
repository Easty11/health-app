"""HR-zone enrichment — fills session zones from raw samples under the per-class model (Q159 stage 2; design 0010).

The DB-facing half of the zoning. `hr_zones.zone_session` is pure; this module selects its
inputs and writes its outputs:

* every `aerobic_sessions` row of the user (ALL of them on every run, not a window: an anchor with
  a past effective date must reflow history, and the row count is small);
* the zone spec in force on the row's local session date: the basis from the row's raw
  `sport_name` (`sport_classes.zone_basis_for`, Q164) and the anchors in force (`user_hrmax`,
  `user_hr_anchors`; append-only, dated; `hr_zones.resolve_zone_spec`);
* the samples inside the row's [start_time, stop_time]:
  - a `health_connect` row reads `hr_samples` written by the SAME writer as the row
    (`source_package` equal) — a ring's HR inside a Garmin bout is never used for it;
  - a Polar row (`polar_v4`, `polar_flow_export`) reads the H10 trace of the same bout where it
    already lives: `hr_samples` written through Health Connect by `POLAR_SAMPLE_WRITERS`
    (`fi.polar.polarflow`, the Polar Flow app). Polar's own per-second samples are not stored
    (0005 appendix; the native ingest is a `build` issue), so this is the R2 "samples exist" branch.

Recompute from samples on every run, so late HR and a changed anchor both reflow. A `health_connect`
row that now zones is written (z1-z5, hr_avg, hr_max); one that is withheld goes back to its stage-1
state (z*, hr_avg, hr_max NULL — INV-7 fail-closed). A Polar row that zones is written the same way;
one that is withheld KEEPS what it holds — Polar's own zones, the flagged fallback (R2) — and is never
NULLed. The per-row basis is not stored: `reads.zone_reads.row_zoning` derives it on read from the
same inputs. It is a DATA FILL, not a formula change: no `formula_version` bump here (#356 precedent;
the model change itself is `metab-v2`, `load_events_metabolic`). It writes only `aerobic_sessions`
z*/hr_avg/hr_max and nothing else — never arbitration inputs (`source`, `source_package`, times).

Soft-fail in the chain (`scripts.refresh_load.SOFT_STEPS`): a failure leaves rows in their prior
state, so it can only withhold information, never corrupt a computed value.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, null
from sqlalchemy.orm import Session

import models
from hr_zones import PLAUSIBLE_BPM, REASONS, ZoneSpec, entry_from_row, hrmax_in_force, resolve_zone_spec, zone_session
from reads.aerobic_reads import HEALTH_CONNECT, arbitrated_sessions, twins_by_canonical
from sport_classes import zone_basis_for

# The Health Connect writers whose samples are the trace of a POLAR-recorded bout (design 0010 row 1).
# Empty tuple = pure vendor fallback for every Polar row (the reverse-by).
POLAR_SAMPLE_WRITERS: tuple[str, ...] = ("fi.polar.polarflow",)
POLAR_SOURCES = ("polar_v4", "polar_flow_export")


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Aware-UTC view of a stored instant. SQLite hands timestamps back naive; Postgres hands
    them back aware (FEEDBACK §49) — the zoning maths needs one shape."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def sample_writers_for(row: models.AerobicSession) -> tuple[str, ...]:
    """The `hr_samples.source_package` values a row may be zoned from: its own writer for a
    health_connect row; `POLAR_SAMPLE_WRITERS` for a Polar row; nothing for any other source."""
    if row.source == HEALTH_CONNECT:
        return (row.source_package or "unknown",)
    if row.source in POLAR_SOURCES:
        return POLAR_SAMPLE_WRITERS
    return ()


def _row_samples(db: Session, user_id: int, row: models.AerobicSession,
                 start: datetime, stop: datetime) -> list[tuple[datetime, int]]:
    writers = sample_writers_for(row)
    if not writers:
        return []
    q = (db.query(models.HrSample.sample_time, models.HrSample.bpm)
         .filter(models.HrSample.user_id == user_id,
                 models.HrSample.source == HEALTH_CONNECT,
                 models.HrSample.source_package.in_(writers),
                 models.HrSample.sample_time >= start,
                 models.HrSample.sample_time <= stop))
    return [(_utc(t), b) for t, b in q.all()]


def anchor_entries(db: Session, user_id: int) -> dict[str, list]:
    """`{"hrmax": [...], "lthr": [...], "rhr": [...]}` as resolver entries, from both anchor tables."""
    out: dict[str, list] = {
        "hrmax": [entry_from_row(h) for h in
                  db.query(models.UserHrmax).filter(models.UserHrmax.user_id == user_id).all()],
        "lthr": [], "rhr": [],
    }
    for a in db.query(models.UserHrAnchor).filter(models.UserHrAnchor.user_id == user_id).all():
        out[a.kind].append(entry_from_row(a))
    return out


def spec_for(row: models.AerobicSession, anchors: dict[str, list]) -> Optional[ZoneSpec]:
    """The `ZoneSpec` in force for a row (its sport class on its session date), or None."""
    return resolve_zone_spec(zone_basis_for(row.sport_name), row.session_date,
                             hrmax_entries=anchors["hrmax"], lthr_entries=anchors["lthr"],
                             rhr_entries=anchors["rhr"])


def enrich_user(db: Session, user_id: int) -> dict[str, Any]:
    """Zone every `aerobic_sessions` row of `user_id` from the samples it may use; commit once.

    Returns the chain-report dict: `rows` evaluated, `zoned`, `reasons` (the closed set from
    `hr_zones.REASONS`, every key always present), `skipped_no_interval` (rows with no usable
    [start, stop] — not evaluable, not a reason), `changed` (rows whose stored values moved),
    `over_ceiling` (rows holding a plausible sample above the HRmax in force — counted and listed,
    HRmax never auto-raised), `dropped_implausible` (samples outside the plausibility bounds),
    `polar_rezoned` (Polar rows zoned on this model) and `polar_vendor_fallback` (Polar rows that
    kept Polar's own zones), `by_basis` (zoned rows per basis)."""
    anchors = anchor_entries(db, user_id)
    rows = (db.query(models.AerobicSession)
            .filter(models.AerobicSession.user_id == user_id)
            .order_by(models.AerobicSession.id)
            .all())

    out: dict[str, Any] = {
        "rows": len(rows), "zoned": 0, "reasons": {r: 0 for r in REASONS},
        "skipped_no_interval": 0, "changed": 0, "over_ceiling": 0, "over_ceiling_rows": [],
        "dropped_implausible": 0, "polar_rezoned": 0, "polar_vendor_fallback": 0,
        "by_basis": {"lthr": 0, "hrr": 0},
    }
    for row in rows:
        start, stop = _utc(row.start_time), _utc(row.stop_time)
        is_polar = row.source in POLAR_SOURCES
        if start is None or stop is None or stop <= start:
            out["skipped_no_interval"] += 1
            if is_polar:
                out["polar_vendor_fallback"] += 1
            continue
        spec = spec_for(row, anchors)
        samples = _row_samples(db, user_id, row, start, stop) if spec is not None else []
        res = zone_session(samples, start, stop, spec)

        out["reasons"][res.reason] += 1
        out["dropped_implausible"] += res.dropped_implausible
        if res.over_ceiling:
            out["over_ceiling"] += 1
            out["over_ceiling_rows"].append({"id": row.id, "date": row.session_date.isoformat(),
                                             "hr_max": max((b for _, b in samples if PLAUSIBLE_BPM[0] <= b <= PLAUSIBLE_BPM[1]), default=None),
                                             "hrmax_in_force": spec.hrmax if spec else None})

        if res.zones is not None:
            new = (*res.zones, res.hr_avg, res.hr_max)
            out["zoned"] += 1
            out["by_basis"][spec.basis] += 1
            if is_polar:
                out["polar_rezoned"] += 1
        elif is_polar:
            out["polar_vendor_fallback"] += 1     # the flagged fallback: Polar's own zones stay as they are
            continue
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
    over); a row with no usable interval or no HRmax in force is never over. The ceiling is HRmax under
    either zoning basis.

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
