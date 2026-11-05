"""Garmin activity metrics on sessions: placed by read-time window overlap, shown vendor-labelled.

`garmin_activity_metrics` keeps no link to an `aerobic_sessions` row (ruling R1). A metrics row is placed
on a session the way an RPE observation is (`reads.srpe_reads._place`): the one session its window
overlaps most, among those it is the same bout as (`OVERLAP_THRESHOLD` of the shorter). Callers pass the
rows they show (canonical rows), so a ride recorded by a Polar strap and a Garmin watch carries Garmin's
numbers on the one row the list shows, labelled as Garmin's.

DISPLAY ONLY. Training Effect and Garmin load are vendor composites. Nothing in the load or readiness path
imports this module or reads the table (`tests/test_garmin_activity_metrics_guard.py`).
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

import models
from reads.srpe_reads import _place, _utc, aerobic_bout

VENDOR = "Garmin"
# The display fields, in tile order. The API carries all of them; the card shows the first four.
DISPLAY_FIELDS = ("calories", "te_aerobic", "te_anaerobic", "training_load", "te_label",
                  "resp_avg", "intensity_min_moderate", "intensity_min_vigorous", "recovery_hr")


def _window(m: models.GarminActivityMetric) -> Optional[SimpleNamespace]:
    start = _utc(m.start_time_gmt)
    if start is None or m.duration_s is None or m.duration_s <= 0:
        return None
    return SimpleNamespace(start_time=start, stop_time=start + timedelta(seconds=float(m.duration_s)))


def metrics_payload(m: models.GarminActivityMetric) -> dict[str, Any]:
    """The vendor-labelled dict the sessions API and the MCP line carry."""
    out: dict[str, Any] = {"vendor": VENDOR, "garmin_activity_id": int(m.garmin_activity_id)}
    for f in DISPLAY_FIELDS:
        out[f] = getattr(m, f)
    return out


def garmin_metrics_by_session(db: Session, user_id: int, rows: Iterable[Any]) -> dict[int, dict[str, Any]]:
    """`{aerobic_sessions.id: metrics dict}` for the given rows. A metrics row with no usable window, or
    one that overlaps none of the rows, is placed nowhere. When two Garmin activities land on one row,
    the one with the larger overlap wins (`_place`'s order), so a row carries at most one."""
    rows = [r for r in rows if getattr(r, "start_time", None) is not None and getattr(r, "stop_time", None) is not None]
    if not rows:
        return {}
    bouts = [aerobic_bout(r) for r in rows]
    lo = min(b.start for b in bouts) - timedelta(days=1)
    hi = max(b.stop for b in bouts) + timedelta(days=1)
    cands = (db.query(models.GarminActivityMetric)
             .filter(models.GarminActivityMetric.user_id == user_id,
                     models.GarminActivityMetric.start_time_gmt >= lo,
                     models.GarminActivityMetric.start_time_gmt <= hi)
             .all())
    placed: dict[int, tuple[float, dict[str, Any]]] = {}
    for m in cands:
        w = _window(m)
        if w is None:
            continue
        b = _place(w, bouts)
        if b is None:
            continue
        ov = (min(w.stop_time, b.stop) - max(w.start_time, b.start)).total_seconds()
        if b.key[1] not in placed or ov > placed[b.key[1]][0]:
            placed[b.key[1]] = (ov, metrics_payload(m))
    return {k: v for k, (_, v) in placed.items()}
