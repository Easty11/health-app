"""Shared read-model for the nightly sleep and HRV-continuity lines.

Read-side only: nothing here ingests, aggregates or writes. Two consumers share it so the
two surfaces cannot drift (FEEDBACK §55): the card's `/health/summary` (`latest_sleep`) and
the MCP `get_readiness_snapshot`.

SLEEP WRITER RULE (operator ruling 2026-10-09; see DECISIONS_LOG): the snapshot's night
comes from ONE writer, named on every value, by fixed priority

    Garmin (com.garmin.android.apps.connectmobile)
      > Samsung Health relay (com.sec.android.app.shealth)
      > Samsung scraper (samsung_hrv_readings)

and stages are never mixed across writers. The night chosen is the newest wake-date across
{Health Connect aggregate, Samsung scraper}; on a tie Health Connect wins (it outranks the
scraper), and inside Health Connect the writer is read from `health_connect_record_sources`.

WHAT THIS CANNOT DO: `health_connect_syncs` holds ONE aggregate per night, built as a union
over every writer's sessions (`_aggregate_day`, #254/#256). Where a night has two or more real
writers the aggregate is a blend that cannot be split back per writer here (no per-writer
stage minutes are stored). Such a night is returned `blended=True`, labelled with its writers,
and a caller that must not mix stages (the snapshot) withholds the stage split. Splitting it
needs per-writer aggregates at ingest, which is a schema change and so a separate decision.

STAGE TRUST: the only stage-confidence logic (`deepSleepConfidence.js`, companion DECISIONS #3)
runs on the phone, is held back from the readiness model (#4), and its verdict is not sent to or
stored by this backend. There is nothing to reuse here, so no confidence is claimed.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

import models

# Health Connect writer package → friendly source, as the packages actually arrive in
# health_connect_record_sources.source_package. Withings is a real HC sleep writer historically
# (Q83) even though it is disabled on live nights, so a Samsung+Withings night is recognised as
# multi-source rather than misattributed to Samsung.
SLEEP_SOURCE_BY_PACKAGE = {
    "com.garmin.android.apps.connectmobile": "garmin",
    "com.sec.android.app.shealth": "samsung",
    "com.withings.wiscale2": "withings",
}
SLEEP_SOURCE_LABELS = {"garmin": "Garmin", "samsung": "Samsung", "withings": "Withings"}
# Names for the value itself. The Samsung Health relay and the Samsung scraper are different
# writers with different data, so the snapshot never calls either of them just "Samsung".
SLEEP_WRITER_NAMES = {"garmin": "Garmin", "samsung": "Samsung Health", "withings": "Withings"}
SCRAPER_WRITER_NAME = "Samsung scraper"
# Writer priority, highest first, for the sources this module can name. The scraper is not an
# HC writer; it sits below every HC writer by the ruling above.
SLEEP_WRITER_PRIORITY = ("garmin", "samsung", "withings")


def hc_sleep_writers(db: Session, user_id: int, night: date) -> set[str]:
    """The distinct REAL writer packages of a Health Connect sleep night.

    JOIN WINDOW: a sleep session's `record_start` is its START timestamp, whose local date is
    normally the calendar day BEFORE the wake-date `health_connect_syncs` is keyed on, so match
    `record_start` on {night, night-1}. The 'unknown' pre-cutover sentinel is not a source."""
    days = [night.isoformat(), (night - timedelta(days=1)).isoformat()]
    rows = db.execute(
        select(models.HealthConnectRecordSource.source_package)
        .where(
            models.HealthConnectRecordSource.user_id == user_id,
            models.HealthConnectRecordSource.record_type == "sleep",
            func.substr(models.HealthConnectRecordSource.record_start, 1, 10).in_(days),
        )
        .distinct()
    ).all()
    return {pkg for (pkg,) in rows if pkg and pkg != "unknown"}


def resolve_hc_sleep_source(db: Session, user_id: int, night: date) -> tuple[str, str]:
    """(source_key, display_label) for a Health-Connect sleep night.

    Two or more real packages → the aggregate is a blend: 'Health Connect (multiple)', never
    misattributed to one device (Decision B), even when only one of them has a friendly name.
    Exactly one real package → its chip if known, else generic 'Health Connect'. None or only
    'unknown' → generic 'Health Connect'."""
    packages = hc_sleep_writers(db, user_id, night)
    if len(packages) >= 2:
        return "multiple", "Health Connect (multiple)"
    if len(packages) == 1:
        key = SLEEP_SOURCE_BY_PACKAGE.get(next(iter(packages)))
        if key:
            return key, SLEEP_SOURCE_LABELS[key]
    return "health_connect", "Health Connect"


def _writer_names(packages: set[str]) -> list[str]:
    """Friendly writer names, in priority order; an unmapped real package shows as itself."""
    keys = [SLEEP_SOURCE_BY_PACKAGE.get(p) for p in packages]
    named = sorted({k for k in keys if k}, key=SLEEP_WRITER_PRIORITY.index)
    other = sorted(p for p, k in zip(packages, keys) if not k)
    return [SLEEP_WRITER_NAMES[k] for k in named] + other


def latest_sleep_night(db: Session, user_id: int) -> dict[str, Any] | None:
    """Freshest staged sleep night across the Samsung scraper table and the Health Connect
    aggregate, source-labelled and dated. Newest wake-date wins; a same-night tie prefers the
    HC aggregate (it outranks the scraper in the writer priority above).

    Fields the winning source does not carry are None — never another night's or another
    writer's value under the same header. The HC aggregate stores only the asleep-union stages
    (deep/rem/light, summing to duration) plus a score, so efficiency %, awake/WASO, respiratory
    rate, sleep HR, SpO2 and bedtime/wake are genuinely absent for an HC night.

    Extra keys over the card's original shape: `writers` (friendly names behind the value, a
    list) and `blended` (True when an HC night spans two or more real writers, so its stage
    split mixes writers)."""
    hc = (
        db.query(models.HealthConnectSync)
        .filter(
            models.HealthConnectSync.user_id == user_id,
            models.HealthConnectSync.sleep_duration_minutes.isnot(None),
        )
        .order_by(models.HealthConnectSync.date.desc())
        .first()
    )
    samsung = (
        db.query(models.SamsungHRVReading)
        .filter(
            models.SamsungHRVReading.user_id == user_id,
            models.SamsungHRVReading.context != "session",
            or_(
                models.SamsungHRVReading.total_sleep_time_minutes.isnot(None),
                models.SamsungHRVReading.actual_sleep_time_minutes.isnot(None),
            ),
        )
        .order_by(models.SamsungHRVReading.captured_at.desc())
        .first()
    )

    hc_night = hc.date if hc else None
    samsung_night = samsung.captured_at if samsung else None

    if hc_night is not None and (samsung_night is None or hc_night >= samsung_night):
        packages = hc_sleep_writers(db, user_id, hc_night)
        source, label = resolve_hc_sleep_source(db, user_id, hc_night)
        return {
            "night": hc_night.isoformat(),
            "source": source,
            "source_label": label,
            "writers": _writer_names(packages),
            "blended": len(packages) >= 2,
            "duration_min": hc.sleep_duration_minutes,
            "deep_min": hc.deep_sleep_minutes,
            "rem_min": hc.rem_sleep_minutes,
            "light_min": hc.light_sleep_minutes,
            "score": hc.sleep_score,
            "efficiency_pct": None,
            "awake_min": None,
            "resp_rate": None,
            "sleep_hr_bpm": None,
            "spo2_pct": None,
            "bedtime": None,
            "wake_time": None,
        }
    if samsung_night is not None:
        return {
            "night": samsung_night.isoformat(),
            "source": "samsung",
            "source_label": "Samsung",
            "writers": [SCRAPER_WRITER_NAME],
            "blended": False,
            "duration_min": (
                samsung.total_sleep_time_minutes
                if samsung.total_sleep_time_minutes is not None
                else samsung.actual_sleep_time_minutes
            ),
            "deep_min": samsung.deep_minutes,
            "rem_min": samsung.rem_minutes,
            "light_min": samsung.light_minutes,
            "score": None,
            "efficiency_pct": samsung.sleep_efficiency_pct,
            "awake_min": samsung.awake_minutes,
            "resp_rate": samsung.respiratory_rate,
            "sleep_hr_bpm": samsung.sleep_hr_bpm,
            "spo2_pct": samsung.spo2_average_pct,
            "bedtime": samsung.bedtime,
            "wake_time": samsung.wake_time,
        }
    return None


def format_duration(minutes: float) -> str:
    """6 h 17 m — whole minutes, never a bare decimal."""
    total = int(round(minutes))
    return f"{total // 60} h {total % 60:02d} m" if total >= 60 else f"{total} m"


def sleep_snapshot_lines(sleep: dict[str, Any] | None) -> list[str]:
    """The snapshot's sleep lines: duration WITH its writer, then the stage split of that
    one writer. A blended night (two or more writers) withholds the split rather than present
    mixed stages under one name. Fields the writer did not stage print '—'."""
    if sleep is None:
        return ["  Sleep: — (no staged night found)"]
    who = sleep["writers"][0] if len(sleep["writers"]) == 1 else sleep["source_label"]
    lines = [f"  Sleep {format_duration(sleep['duration_min'])} · {who} (night of {sleep['night']})"]
    if sleep["blended"]:
        lines.append(f"  Sleep stages: withheld — the night spans {' + '.join(sleep['writers'])} "
                     f"and cannot be split per writer")
    elif None not in (sleep["deep_min"], sleep["rem_min"]):
        lines.append(f"  Deep: {sleep['deep_min']:.0f} min  REM: {sleep['rem_min']:.0f} min · {who}")
    else:
        lines.append("  Sleep stages: —")
    if sleep["efficiency_pct"] is not None:
        lines.append(f"  Sleep efficiency: {sleep['efficiency_pct']:.0f}% · {who}")
    if sleep["spo2_pct"] is not None:
        lines.append(f"  SpO2: {sleep['spo2_pct']:.1f}% · {who}")
    if sleep["resp_rate"] is not None:
        lines.append(f"  Resp rate: {sleep['resp_rate']:.1f} br/min · {who}")
    if sleep["sleep_hr_bpm"] is not None:
        lines.append(f"  Resting HR: {sleep['sleep_hr_bpm']:.0f} bpm · {who}")
    return lines


def hrv_continuity(db: Session, user_id: int, wake_day: date, days: int = 7) -> dict[str, Any]:
    """HRV nights present in the `days` ending on `wake_day` (inclusive), over EVERY source
    that feeds HRV: `hrv_readings` (Garmin, plus the scraper's mirrored nights) and the Samsung
    scraper's own rows (history the mirror backfill has not copied). Returns
    {"nights": distinct nights with any reading, "days": days, "by_source": {source: nights}}.
    A night two sources both measured counts once in `nights` and once in each source."""
    start = wake_day - timedelta(days=days - 1)
    by_source: dict[str, set[date]] = {}
    for src, night in db.execute(
        select(models.HrvReading.source, models.HrvReading.captured_at).where(
            models.HrvReading.user_id == user_id,
            models.HrvReading.captured_at >= start,
            models.HrvReading.captured_at <= wake_day,
            models.HrvReading.rmssd_ms.isnot(None),
        )
    ).all():
        by_source.setdefault(src, set()).add(night)
    for (night,) in db.execute(
        select(models.SamsungHRVReading.captured_at).where(
            models.SamsungHRVReading.user_id == user_id,
            models.SamsungHRVReading.captured_at >= start,
            models.SamsungHRVReading.captured_at <= wake_day,
            models.SamsungHRVReading.context == "passive_overnight",
            models.SamsungHRVReading.hrv_ms.isnot(None),
        )
    ).all():
        by_source.setdefault("samsung", set()).add(night)
    return {
        "nights": len(set().union(*by_source.values())) if by_source else 0,
        "days": days,
        "by_source": {s: len(n) for s, n in sorted(by_source.items())},
    }


def hrv_continuity_line(c: dict[str, Any]) -> str:
    per = ", ".join(f"{s} {n}" for s, n in c["by_source"].items()) or "no source"
    return f"  HRV data continuity: {c['nights']}/{c['days']} nights in the last week ({per})"
