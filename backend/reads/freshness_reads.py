"""Data freshness, computed on read — no table, no migration, nothing written.

Two signals, because they fail differently:

* STREAMS, per (stream, writer): from `health_connect_record_sources` (every inbound Health
  Connect record keeps its writer package), plus the two writers that never pass through Health
  Connect — the Samsung scraper (`samsung_hrv_readings`) and the server-side Garmin HRV pull
  (`hrv_readings`, source 'garmin'). For each: the newest record time and the writer's USUAL
  GAP, and a stream is STALE when its newest record is older than STALE_GAP_MULTIPLE x that gap.
* PIPES, the last delivery of each route into the platform: the newest
  `health_connect_sync_events` row (Health Connect), the newest Polar session, the newest Garmin
  HRV night. Health Connect goes AMBER when its last delivery is older than HC_AMBER_AFTER (two
  background intervals of six hours, plus an hour of slack).

THE USUAL GAP IS MEASURED AT DAY GRAIN. A per-record median interval is minutes for a dense
stream such as heart rate, so "3 x the gap" would call it stale between every six-hourly delivery.
The gap here is the median number of days between days that have records, over the
GAP_WINDOW_DAYS ending at the writer's OWN last record (not at now: a writer that stopped a month
ago must still be judged against how it used to behave, or it would fall out of the window and read
"no history" instead of "stale"), never less than one day. Lateness inside a day is the delivery pipe's job
(HC_AMBER_AFTER), not a stream's. A stream with fewer than MIN_RECORD_DAYS record-days in the
window has no usual gap to be late against and reports `insufficient_history`, never stale.

SPARSE STREAMS ARE INFORMATION ONLY. A workout, a weigh-in or a mindfulness entry is irregular by
nature, so a long gap is a rest week and not a fault. They are reported (newest and age) with
status `info` and are never counted as stale. The Polar pipe is the same: it carries sessions,
and "no session for four days" cannot be told from a rest week.

A date-only record time ('2026-10-09', e.g. steps) is read as covering the whole AEST day, so it
is dated to that day's end and clamped to now: today's steps are not "23 hours old" at 23:00.

Read-side only. No ingest, aggregation or `load_metrics` change.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Any

import pytz
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import models
# Writer package -> friendly name, shared with the sleep read so the two never disagree.
from reads.snapshot_reads import SLEEP_SOURCE_BY_PACKAGE, SLEEP_WRITER_NAMES

_AEST = pytz.timezone("Australia/Brisbane")   # no DST; the same zone the day grain uses elsewhere

STALE_GAP_MULTIPLE = 3                          # operator brief 2026-10-09: "~3x its usual gap"
GAP_WINDOW_DAYS = 28                            # operator brief: median over 28 days
HC_AMBER_AFTER = timedelta(hours=13)            # operator brief: two background intervals (~13 h)
MIN_RECORD_DAYS = 4                             # fewer record-days than this: no usual gap yet
MIN_USUAL_GAP_DAYS = 1.0                        # day grain: see the module docstring
RETIRED_AFTER = timedelta(days=60)              # a writer silent this long is retired, not listed

# Health Connect record types whose arrival is irregular by nature (information only).
INFO_ONLY_STREAMS = frozenset({"exercise", "weight", "mindfulness"})

POLAR_SOURCES = ("polar_v4", "polar_flow_export")


def _utc(dt: datetime) -> datetime:
    """Aware UTC. SQLite hands TIMESTAMPTZ back naive; a naive value is read as UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _end_of_local_day(d: date) -> datetime:
    return _AEST.localize(datetime.combine(d + timedelta(days=1), datetime.min.time())).astimezone(timezone.utc)


def parse_record_time(text: str | None) -> datetime | None:
    """A `record_start` string as aware UTC, or None when it will not parse."""
    if not text:
        return None
    text = text.strip()
    try:
        if len(text) == 10:
            return _end_of_local_day(date.fromisoformat(text))
        return _utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def writer_name(package: str | None) -> str:
    key = SLEEP_SOURCE_BY_PACKAGE.get(package or "")
    if key:
        return SLEEP_WRITER_NAMES[key]
    return "unknown writer" if not package or package == "unknown" else package


def _age_hours(then: datetime, now: datetime) -> float:
    return round(max((now - then).total_seconds(), 0.0) / 3600.0, 1)


def _recent_days(days: list[date]) -> list[date]:
    """The record-days within GAP_WINDOW_DAYS of the writer's own newest record-day."""
    if not days:
        return []
    cutoff = max(days) - timedelta(days=GAP_WINDOW_DAYS)
    return sorted({d for d in days if d >= cutoff})


def usual_gap_days(days: list[date]) -> float | None:
    """Median whole days between consecutive record-days, at least one day; None when there are
    fewer than MIN_RECORD_DAYS days (in the window ending at the newest) to take a gap from."""
    ordered = _recent_days(days)
    if len(ordered) < MIN_RECORD_DAYS:
        return None
    gaps = [(b - a).days for a, b in zip(ordered, ordered[1:])]
    return max(float(median(gaps)), MIN_USUAL_GAP_DAYS)


def _stream(stream: str, writer: str, package: str | None, days: list[date], newest: datetime,
            now: datetime, *, info_only: bool) -> dict[str, Any]:
    """One (stream, writer) row. `days` are all the writer's record-days (the window is applied
    here, ending at its newest)."""
    gap = usual_gap_days(days)
    age_h = _age_hours(newest, now)
    if info_only:
        status = "info"
    elif gap is None:
        status = "insufficient_history"
    elif (now - newest) > timedelta(days=STALE_GAP_MULTIPLE * gap):
        status = "stale"
    else:
        status = "fresh"
    return {
        "stream": stream, "writer": writer, "package": package,
        "newest_at": newest.isoformat(), "age_hours": age_h,
        "usual_gap_days": gap, "record_days_28d": len(_recent_days(days)), "status": status,
    }


def _record_source_streams(db: Session, user_id: int, now: datetime) -> list[dict[str, Any]]:
    """Per (record_type, writer) rows from `health_connect_record_sources`. One grouped query:
    the database collapses each (type, writer, day) to its newest record, so the rows returned are
    a few per day of history, never one per record (heart rate alone is far too dense to read)."""
    day_col = func.substr(models.HealthConnectRecordSource.record_start, 1, 10)
    rows = db.execute(
        select(
            models.HealthConnectRecordSource.record_type,
            models.HealthConnectRecordSource.source_package,
            day_col.label("d"),
            func.max(models.HealthConnectRecordSource.record_start).label("newest"),
        )
        .where(models.HealthConnectRecordSource.user_id == user_id)
        .group_by(models.HealthConnectRecordSource.record_type,
                  models.HealthConnectRecordSource.source_package, day_col)
    ).all()

    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for rtype, pkg, d, newest_text in rows:
        newest = parse_record_time(newest_text)
        try:
            day = date.fromisoformat(d)
        except (TypeError, ValueError):
            continue
        if newest is None:
            continue
        g = groups.setdefault((rtype, pkg or "unknown"), {"days": [], "newest": newest})
        g["newest"] = max(g["newest"], newest)
        g["days"].append(day)

    out = []
    for (rtype, pkg), g in groups.items():
        if now - g["newest"] > RETIRED_AFTER:
            continue
        out.append(_stream(rtype, writer_name(pkg), pkg, g["days"], g["newest"], now,
                           info_only=rtype in INFO_ONLY_STREAMS))
    return out


def _nightly_streams(db: Session, user_id: int, now: datetime) -> list[dict[str, Any]]:
    """The Samsung scraper (sleep, hrv) and the server-side Garmin HRV pull: writers that do not
    pass through Health Connect, so `health_connect_record_sources` never sees them."""
    out = []

    scraper = [d for (d,) in db.execute(
        select(models.SamsungHRVReading.captured_at).where(
            models.SamsungHRVReading.user_id == user_id,
            models.SamsungHRVReading.context == "passive_overnight",
        )).all()]
    if scraper:
        newest = _end_of_local_day(max(scraper))
        if now - newest <= RETIRED_AFTER:
            out.append(_stream("sleep+hrv", "Samsung scraper", None,
                               scraper, min(newest, now), now,
                               info_only=False))

    garmin = [d for (d,) in db.execute(
        select(models.HrvReading.captured_at).where(
            models.HrvReading.user_id == user_id, models.HrvReading.source == "garmin",
        )).all()]
    if garmin:
        newest = _end_of_local_day(max(garmin))
        if now - newest <= RETIRED_AFTER:
            out.append(_stream("hrv", "Garmin (server pull)", None,
                               garmin, min(newest, now), now,
                               info_only=False))
    return out


def _pipes(db: Session, user_id: int, now: datetime, nightly: list[dict[str, Any]]) -> dict[str, Any]:
    hc_last = db.scalar(select(func.max(models.HealthConnectSyncEvent.synced_at)).where(
        models.HealthConnectSyncEvent.user_id == user_id))
    if hc_last is None:
        hc: dict[str, Any] = {"newest_at": None, "age_hours": None, "status": "never"}
    else:
        hc_last = _utc(hc_last)
        age = now - hc_last
        hc = {"newest_at": hc_last.isoformat(), "age_hours": _age_hours(hc_last, now),
              "status": "amber" if age > HC_AMBER_AFTER else "fresh"}
    hc["amber_after_hours"] = HC_AMBER_AFTER.total_seconds() / 3600.0

    p_start, p_day = db.execute(
        select(func.max(models.AerobicSession.start_time), func.max(models.AerobicSession.session_date))
        .where(models.AerobicSession.user_id == user_id,
               models.AerobicSession.source.in_(POLAR_SOURCES))
    ).one()
    polar_last = None
    if p_start is not None:
        polar_last = _utc(p_start)
    elif p_day is not None:
        polar_last = min(_end_of_local_day(p_day), now)
    polar = ({"newest_at": None, "age_hours": None, "status": "never"} if polar_last is None else
             {"newest_at": polar_last.isoformat(), "age_hours": _age_hours(polar_last, now),
              "status": "info"})

    g = next((s for s in nightly if s["writer"] == "Garmin (server pull)"), None)
    garmin = ({"newest_at": None, "age_hours": None, "status": "never"} if g is None else
              {"newest_at": g["newest_at"], "age_hours": g["age_hours"], "status": g["status"]})
    return {"health_connect": hc, "polar": polar, "garmin_hrv": garmin}


def freshness(db: Session, user_id: int, *, now: datetime | None = None) -> dict[str, Any]:
    """The whole freshness read for one user. `now` is injectable for tests."""
    now = _utc(now) if now is not None else datetime.now(timezone.utc)
    nightly = _nightly_streams(db, user_id, now)
    streams = _record_source_streams(db, user_id, now) + nightly
    streams.sort(key=lambda s: (s["stream"], s["writer"]))
    pipes = _pipes(db, user_id, now, nightly)

    # Pipes that feed the load number. Polar is information only (sessions are sparse), so the
    # one pipe with a threshold is Health Connect; the card dims on it alone.
    load_stale_pipes = [name for name in ("health_connect",) if pipes[name]["status"] == "amber"]
    arrivals = [datetime.fromisoformat(p["newest_at"]) for k, p in pipes.items()
                if k in ("health_connect", "polar") and p["newest_at"]]
    data_as_of = max(arrivals) if arrivals else None
    return {
        "generated_at": now.isoformat(),
        "streams": streams,
        "pipes": pipes,
        "data_as_of": ({"newest_at": data_as_of.isoformat(), "age_hours": _age_hours(data_as_of, now)}
                       if data_as_of else None),
        "load_inputs_stale": bool(load_stale_pipes),
        "load_stale_pipes": load_stale_pipes,
    }


def _ago(hours: float | None) -> str:
    if hours is None:
        return "never"
    if hours < 1:
        return f"{int(round(hours * 60))} min ago"
    if hours < 48:
        return f"{hours:.0f} h ago"
    return f"{hours / 24:.0f} d ago"


def freshness_snapshot_lines(f: dict[str, Any]) -> list[str]:
    """The short freshness block for `get_readiness_snapshot`."""
    pipes = f["pipes"]
    hc = pipes["health_connect"]
    flag = f" — AMBER, older than {hc['amber_after_hours']:.0f} h" if hc["status"] == "amber" else ""
    lines = ["Data freshness:",
             f"  Health Connect last delivery: {_ago(hc['age_hours'])}{flag}",
             f"  Polar last session: {_ago(pipes['polar']['age_hours'])} (information only)",
             f"  Garmin HRV last night: {_ago(pipes['garmin_hrv']['age_hours'])}"]
    stale = [s for s in f["streams"] if s["status"] == "stale"]
    for s in stale:
        lines.append(f"  STALE {s['stream']} · {s['writer']}: {_ago(s['age_hours'])} "
                     f"(usual gap {s['usual_gap_days']:.0f} d)")
    info = [f"{s['stream']} · {s['writer']} {_ago(s['age_hours'])}" for s in f["streams"]
            if s["status"] == "info"]
    if info:
        lines.append("  Irregular streams, information only: " + "; ".join(info))
    return lines
