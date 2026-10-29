"""Shared read-model for the nightly sleep and HRV-continuity lines.

Read-side only: nothing here ingests, aggregates or writes. Two consumers share it so the
two surfaces cannot drift (FEEDBACK §55): the card's `/health/summary` (`latest_sleep`) and
the MCP `get_readiness_snapshot`.

PER-FIELD RESOLUTION. The night is the newest wake-date with a sleep duration; every figure on it
is resolved on its own through `recovery_night` (the same candidates and rank tables as the MCP
`get_recovery_metrics`), so the two cannot disagree and a source that lacks a field no longer
blanks it: a Personal API night has its own efficiency, awake minutes and respiratory rate, and
SpO2 comes from the epoch lane when it has the night. Each figure keeps the source that supplied
it (`field_sources`), and the snapshot lines tag every figure with its own.

SLEEP WRITER RULE (operator ruling 2026-10-09; see DECISIONS_LOG) still governs the duration and
the stage split, which come from ONE source, named on every value, and are never mixed across
writers. The order is now (Q243, DECISIONS_LOG)

    Garmin Personal API
      > Garmin (com.garmin.android.apps.connectmobile) via Health Connect
      > Samsung Health relay (com.sec.android.app.shealth)
      > Samsung scraper (samsung_hrv_readings)

WHAT THIS CANNOT DO: `health_connect_syncs` holds ONE aggregate per night, built as a union
over every writer's sessions (`_aggregate_day`, #254/#256). Where a night has two or more real
writers the aggregate is a blend that cannot be split back per writer here (no per-writer
stage minutes are stored). Such a night is returned `blended=True`, labelled with its writers,
and a caller that must not mix stages (the snapshot) withholds the stage split. Splitting it
needs per-writer aggregates at ingest, which is a schema change and so a separate decision.
A night that cannot be one night (`hc_sleep.night_implausibility`) is withheld, not read.

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
from reads.hc_sleep import (  # noqa: F401  (re-exported: callers and tests import these from here)
    SCRAPER_WRITER_NAME, SLEEP_SOURCE_BY_PACKAGE, SLEEP_SOURCE_LABELS, SLEEP_WRITER_NAMES,
    SLEEP_WRITER_PRIORITY, hc_sleep_writers,
)
from reads.recovery_night import (
    DERIVED, GARMIN_API, GARMIN_DI, HC_BLENDED, HC_UNNAMED, SCRAPER, SOURCE_LABELS, load_candidates,
    load_device_windows, load_diary, partial_detail, partial_note, resolve_night,
)

# Names for a figure's source in the snapshot lines (the writer, not the rank key). A figure from
# the same source as the duration is tagged with the duration's own name instead.
FIELD_SOURCE_NAMES = {
    GARMIN_API: "Garmin (Personal API)",
    "garmin_hc": "Garmin (Health Connect)",
    GARMIN_DI: "Garmin (epoch SpO2 lane)",
    "samsung_hc": SLEEP_WRITER_NAMES["samsung"],
    "withings_hc": SLEEP_WRITER_NAMES["withings"],
    HC_BLENDED: "Health Connect (multiple)",
    HC_UNNAMED: "Health Connect",
    "hc_utc_day": "Health Connect (UTC-day)",
    SCRAPER: SCRAPER_WRITER_NAME,
}

# How far behind the newest sleep night the card looks for a night that survives the plausibility
# guard. A newest night that is withheld falls back to the previous one inside this window.
LATEST_NIGHT_LOOKBACK_DAYS = 7


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


def _newest_sleep_night(db: Session, user_id: int) -> date | None:
    """Wake-date of the newest night any sleep store holds, filtered as `load_candidates` reads."""
    newest = [
        db.query(func.max(models.SleepNight.captured_at)).filter(
            models.SleepNight.user_id == user_id, models.SleepNight.source == "garmin",
            models.SleepNight.sleep_time_s.isnot(None)).scalar(),
        db.query(func.max(models.HealthConnectSync.date)).filter(
            models.HealthConnectSync.user_id == user_id,
            models.HealthConnectSync.sleep_duration_minutes.isnot(None)).scalar(),
        db.query(func.max(models.SamsungHRVReading.captured_at)).filter(
            models.SamsungHRVReading.user_id == user_id,
            models.SamsungHRVReading.context == "passive_overnight",
            or_(models.SamsungHRVReading.total_sleep_time_minutes.isnot(None),
                models.SamsungHRVReading.actual_sleep_time_minutes.isnot(None))).scalar(),
    ]
    return max((d for d in newest if d is not None), default=None)


def _field(r: dict[str, Any], field: str, key: str | None = None) -> Any:
    hit = r[field]
    return hit["value"][key or field] if hit else None


def latest_sleep_night(db: Session, user_id: int) -> dict[str, Any] | None:
    """Freshest sleep night across the Personal API, the Health Connect aggregate and the Samsung
    scraper, every figure resolved on its own and dated. The newest wake-date with a duration wins;
    on a tie the duration's source follows `recovery_night.TST_RANK` (Personal API, then the HC
    writers, then the scraper).

    Fields no source carries are None — never another night's value under the same header. A
    figure from a different source than the duration is named in `field_sources`; the stage split
    and the duration are always one source.

    Keys over the card's original shape: `writers` (friendly names behind the duration, a list),
    `blended` (True when an HC night spans two or more real writers, so its stage split mixes
    writers), `transport` ('personal_api', 'health_connect' or 'scraper'), `field_sources`
    ({field: label}), `efficiency_derived` (True when the efficiency is sleep time over the
    device's own start-to-end window, which has no pre-sleep time in bed and so reads higher than
    the diary SE), `resting_hr_bpm` (the daily resting rate, or None) `withheld` (nights the
    plausibility guard refused, newest first) and `diary_note` (the night's diary TST beside the device figure,
    flagged when the device is 60 min or more below it; None when the diary is not logged, Q247)."""
    newest = _newest_sleep_night(db, user_id)
    if newest is None:
        return None
    cands = load_candidates(db, user_id, newest - timedelta(days=LATEST_NIGHT_LOOKBACK_DAYS))
    withheld: list[dict[str, str]] = []
    for night in sorted(cands, reverse=True):
        r = resolve_night(night, cands[night])
        withheld += [{"night": night.isoformat(), "source": SOURCE_LABELS.get(s, s), "reason": why}
                     for s, why in r["withheld"].items()]
        if r["tst"] is not None:
            return _night_dict(db, user_id, night, r, cands[night], withheld)
    return None


def _night_dict(db: Session, user_id: int, night: date, r: dict[str, Any], cand: dict[str, Any],
                withheld: list[dict[str, str]]) -> dict[str, Any]:
    tst_src = r["tst"]["source"]
    stages = r["stages"]["value"] if r["stages"] else {}
    if tst_src == HC_BLENDED:
        # The resolver withholds a blend's split; the card has always shown it, labelled blended.
        stages = {k: cand[HC_BLENDED].get(k) for k in ("deep", "rem", "light")}
    score, bedtime, wake_time = None, None, None
    if tst_src == SCRAPER:
        source, label, writers, transport = "samsung", "Samsung", [SCRAPER_WRITER_NAME], "scraper"
        scraper = db.query(models.SamsungHRVReading).filter_by(
            user_id=user_id, captured_at=night, context="passive_overnight").first()
        bedtime, wake_time = (scraper.bedtime, scraper.wake_time) if scraper else (None, None)
    elif tst_src == GARMIN_API:
        source, label, writers, transport = "garmin", SLEEP_SOURCE_LABELS["garmin"], \
            [SLEEP_WRITER_NAMES["garmin"]], "personal_api"
    else:
        packages = hc_sleep_writers(db, user_id, night)
        source, label = resolve_hc_sleep_source(db, user_id, night)
        writers, transport = _writer_names(packages), "health_connect"
        hc = db.query(models.HealthConnectSync).filter_by(user_id=user_id, date=night).first()
        score = hc.sleep_score if hc else None
    diary_note = partial_note(
        _field(r, "tst"), tst_src, load_diary(db, user_id, night).get(night),
        load_device_windows(db, user_id, night).get(night))
    field_sources = {f: FIELD_SOURCE_NAMES.get(r[f]["source"], r[f]["source"])
                     for f in ("tst", "stages", "efficiency", "spo2", "rr", "sleep_hr", "daily_rhr") if r[f]}
    return {
        "night": night.isoformat(),
        "source": source,
        "source_label": label,
        "writers": writers,
        "blended": tst_src == HC_BLENDED,
        "transport": transport,
        "duration_min": _field(r, "tst"),
        "deep_min": stages.get("deep"),
        "rem_min": stages.get("rem"),
        "light_min": stages.get("light"),
        "score": score,
        "efficiency_pct": _field(r, "efficiency"),
        "efficiency_derived": bool(r["efficiency"]) and ("efficiency", r["efficiency"]["source"]) in DERIVED,
        "awake_min": stages.get("awake"),
        "resp_rate": _field(r, "rr"),
        "sleep_hr_bpm": _field(r, "sleep_hr"),
        "spo2_pct": _field(r, "spo2"),
        "resting_hr_bpm": _field(r, "daily_rhr"),
        "field_sources": field_sources,
        "withheld": withheld,
        "bedtime": bedtime,
        "wake_time": wake_time,
        "diary_note": diary_note,
    }


def format_duration(minutes: float) -> str:
    """6 h 17 m — whole minutes, never a bare decimal."""
    total = int(round(minutes))
    return f"{total // 60} h {total % 60:02d} m" if total >= 60 else f"{total} m"


# A heart-rate figure on the snapshot carries no date of its own (it rides on the night's line), so a
# night that is not recent would put an old number under "Resting HR" beside today's biometrics. Past
# this age the figure is withheld and the reason printed. Measured in whole wake-days (`days * 24`),
# because the stores key a figure to its wake-date and not to a clock time.
HR_MAX_AGE_HOURS = 48


def hr_figures_stale(night: str, today: date | None) -> int | None:
    """Days between the sleep night's wake-date and `today` when that age exceeds `HR_MAX_AGE_HOURS`,
    else None. None whenever `today` is not given (callers that do not gate) or the night is unparseable
    (never a crash, never a silent withhold)."""
    if today is None:
        return None
    try:
        age_days = (today - date.fromisoformat(str(night)[:10])).days
    except ValueError:
        return None
    return age_days if age_days * 24 > HR_MAX_AGE_HOURS else None


def sleep_snapshot_lines(sleep: dict[str, Any] | None, today: date | None = None) -> list[str]:
    """The snapshot's sleep lines: duration WITH its source, then the stage split of that one
    source, then each other figure tagged with the source that supplied it. A blended night (two
    or more writers) withholds the split rather than present mixed stages under one name. Fields
    no source carried print '—' where the line has a name to hold (stages, resting HR).

    "Resting HR" is the daily resting rate and nothing else: the ring's average sleep HR is its own
    "Sleep HR" line, and when no daily rate exists the line says so rather than borrow a figure.

    When `today` (the wake-day) is given, both heart-rate lines are gated on the night's age: a night
    more than `HR_MAX_AGE_HOURS` old prints `—` and the reason instead of its figure, so an old reading
    is never read as current."""
    if sleep is None:
        return ["  Sleep: — (no staged night found)"]
    who = sleep["writers"][0] if len(sleep["writers"]) == 1 else sleep["source_label"]
    fs = sleep.get("field_sources", {})

    def by(field: str) -> str:
        name = fs.get(field, who)
        return who if name == fs.get("tst") else name

    note = sleep.get("diary_note")
    lines = [f"  Sleep {format_duration(sleep['duration_min'])} · {who} (night of {sleep['night']})"
             + (f" · diary {format_duration(note['diary_tst'])}" if note else "")]
    if note and note["short_min"] is not None:
        detail = partial_detail(note)
        lines.append(f"  Partial night? The device is {format_duration(note['short_min'])} below the diary, so it may "
                     f"have recorded only part of the night" + (f" ({detail})" if detail else ""))
    if sleep["blended"]:
        lines.append(f"  Sleep stages: withheld — the night spans {' + '.join(sleep['writers'])} "
                     f"and cannot be split per writer")
    elif None not in (sleep["deep_min"], sleep["rem_min"]):
        lines.append(f"  Deep: {sleep['deep_min']:.0f} min  REM: {sleep['rem_min']:.0f} min · {who}")
    else:
        lines.append("  Sleep stages: —")
    if sleep.get("awake_min") is not None:
        lines.append(f"  Awake: {sleep['awake_min']:.0f} min · {by('stages')}")
    if sleep["efficiency_pct"] is not None:
        basis = ", derived from the device's own sleep window" if sleep.get("efficiency_derived") else ""
        lines.append(f"  Sleep efficiency: {sleep['efficiency_pct']:.0f}% · {by('efficiency')}{basis}")
    if sleep["spo2_pct"] is not None:
        lines.append(f"  SpO2: {sleep['spo2_pct']:.1f}% · {by('spo2')}")
    if sleep["resp_rate"] is not None:
        lines.append(f"  Resp rate: {sleep['resp_rate']:.1f} br/min · {by('rr')}")
    old = hr_figures_stale(sleep["night"], today)
    gate = (f"withheld — the last reading is from the night of {sleep['night']}, {old} days before "
            f"{today}, over {HR_MAX_AGE_HOURS} h old") if old is not None else None
    if sleep["sleep_hr_bpm"] is not None:
        lines.append(f"  Sleep HR: — ({gate})" if gate
                     else f"  Sleep HR: {sleep['sleep_hr_bpm']:.0f} bpm · {by('sleep_hr')}")
    rhr = sleep.get("resting_hr_bpm")
    if rhr is not None and gate:
        lines.append(f"  Resting HR: — ({gate})")
    else:
        lines.append(f"  Resting HR: {rhr:.0f} bpm · {by('daily_rhr')}" if rhr is not None
                     else "  Resting HR: — (no daily resting rate)")
    for w in sleep.get("withheld", []):
        lines.append(f"  Withheld: {w['source']} sleep for {w['night']} — {w['reason']}")
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
