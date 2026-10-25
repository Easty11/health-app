"""Per-field resolution of a night's recovery metrics, for the MCP `get_recovery_metrics`.

Read-side only: nothing here ingests, aggregates or writes.

THE SHAPE. A night (keyed on its WAKE-DATE) is a set of CANDIDATES, one per source store that
has something for it: {source_key: {field: value}}. `resolve_night` walks each field's rank
list (`FIELD_RANK`) and takes the first candidate whose value is not None, so a source that
carries only some fields never suppresses the others (the old reader fell back to the HC store
only when the Samsung+HRV union returned ZERO rows, so one Garmin HRV row blanked everything
else). Every resolved value keeps the source that supplied it; the formatter prints it.

ADDING A SOURCE (the Garmin Personal API migration): write its loader so it adds a candidate
under a new source key, add the key to `SOURCE_LABELS`, and insert it into the rank tuples of
the fields it carries. Nothing else changes -- `daily_rhr` already ranks `garmin_api` first
with no loader behind it, so that slot reads "awaiting" until a loader exists.

TWO FIELD KINDS THAT ARE NOT "FIRST NON-NULL WINS":
  * HRV is never arbitrated (#292): two devices are two instruments and raw ms is never
    blended or ranked, so every source with a value is printed. `HRV_FALLBACK_SOURCES` (the
    Health Connect UTC-day HRV) is shown only when no instrument source has one.
  * The sleep STAGES (deep/rem/light/awake) resolve as ONE group from one source: stages are
    never mixed across writers (the sleep-writer ruling, snapshot_reads). A blended Health
    Connect night (two or more real writers) withholds its stage split, as the snapshot does.

SLEEP SOURCE ORDER is `SLEEP_WRITER_PRIORITY` (snapshot_reads), not a new rank: Garmin >
Samsung Health relay > Withings, all as Health Connect writers, then the Samsung scraper below
every HC writer. The HC aggregate is one row per night built over every writer's sessions
(`health_connect_syncs`), so the writer is read from `health_connect_record_sources`.

DATE KEYS. Sleep, stages, nadir, `hrv_readings`, `spo2_nights` and the Samsung scraper are all
keyed on the wake-date. `health_connect_syncs.oxygen_saturation / respiratory_rate / hrv_rmssd`
are UTC-date keyed (a pending re-bucketing, see the model), so they carry their own source key
`hc_utc_day` and are the lowest rank of their field. `resting_heart_rate` there is the AEST-day
median of every HR sample -- not a resting rate -- and carries `hc_aest_day`.

SPO2 IS DERIVED HERE. `spo2_nights` stores raw epochs only (Q150: no mean, no min). The nightly
mean and min below are computed over the night's non-null `spo2_pct` epochs, UNFILTERED -- no
confidence threshold, no range check -- because none is ruled. See DECISIONS_LOG.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from reads.snapshot_reads import SLEEP_SOURCE_BY_PACKAGE, SLEEP_WRITER_PRIORITY, hc_sleep_writers

SCRAPER = "samsung_scraper"
_HC_WRITERS = tuple(f"{k}_hc" for k in SLEEP_WRITER_PRIORITY)        # garmin_hc, samsung_hc, withings_hc
HC_BLENDED = "hc_multiple"                                            # two or more real writers
HC_UNNAMED = "hc"                                                     # one writer with no friendly name, or none recorded

SOURCE_LABELS = {
    "garmin": "garmin",
    "garmin_hc": "garmin/HC",
    "samsung_hc": "samsung/HC",
    "withings_hc": "withings/HC",
    HC_BLENDED: "HC (multiple writers)",
    HC_UNNAMED: "HC",
    SCRAPER: "samsung scraper",
    "hc_aest_day": "HC all-day",
    "hc_utc_day": "HC UTC-day",
    "garmin_api": "garmin personal API",
}

# Sleep order: SLEEP_WRITER_PRIORITY as HC writers, an unnamed HC writer after them, the
# scraper last (below every HC writer by the sleep-writer ruling).
SLEEP_RANK = _HC_WRITERS + (HC_UNNAMED, SCRAPER)
STAGE_RANK = SLEEP_RANK                      # HC_BLENDED is deliberately absent: no stage split from a blend
TST_RANK = _HC_WRITERS + (HC_BLENDED, HC_UNNAMED, SCRAPER)

FIELD_RANK: dict[str, tuple[str, ...]] = {
    "tst": TST_RANK,
    "stages": STAGE_RANK,                                   # deep / rem / light / awake, one source
    "efficiency": (SCRAPER,),                               # the HC aggregate does not carry it
    "spo2": ("garmin", SCRAPER, "hc_utc_day"),              # nightly mean (+ min where the source has one)
    "rr": (SCRAPER, "hc_utc_day"),
    "sleep_hr": (SCRAPER,),                                 # the ring's average HR over the night
    "sleep_nadir_hr": SLEEP_RANK,
    "all_day_median_hr": ("hc_aest_day",),
    # The real daily resting rate. No loader yet: the Personal API migration adds `garmin_api`.
    "daily_rhr": ("garmin_api",),
}
STAGE_FIELDS = ("deep", "rem", "light", "awake")
HRV_SOURCES = ("garmin", SCRAPER)
HRV_FALLBACK_SOURCES = ("hc_utc_day",)

# field -> the candidate keys that supply it (a "group" field names several)
_FIELD_KEYS = {
    "tst": ("tst",),
    "stages": STAGE_FIELDS,
    "efficiency": ("efficiency",),
    "spo2": ("spo2", "spo2_min"),
    "rr": ("rr",),
    "sleep_hr": ("sleep_hr",),
    "sleep_nadir_hr": ("sleep_nadir_hr",),
    "all_day_median_hr": ("all_day_median_hr",),
    "daily_rhr": ("daily_rhr",),
}

Candidates = dict[str, dict[str, Any]]            # source_key -> {field: value}


def _carries(cand: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(cand.get(k) is not None for k in keys)


def resolve_night(night: date, cands: Candidates) -> dict[str, Any]:
    """One night's resolved view: for each ranked field `{"value": {...}, "source": key}`
    (or None when no source carries it), plus `hrv`, a list of `(source, ms)`."""
    out: dict[str, Any] = {"night": night}
    for field, rank in FIELD_RANK.items():
        keys = _FIELD_KEYS[field]
        hit = next((s for s in rank if s in cands and _carries(cands[s], keys)), None)
        out[field] = None if hit is None else {
            "source": hit, "value": {k: cands[hit].get(k) for k in keys},
        }
    hrv = [(s, cands[s]["hrv"]) for s in HRV_SOURCES if cands.get(s, {}).get("hrv") is not None]
    if not hrv:
        hrv = [(s, cands[s]["hrv"]) for s in HRV_FALLBACK_SOURCES if cands.get(s, {}).get("hrv") is not None]
    out["hrv"] = hrv
    return out


_NOT_ALONE = ("all_day_median_hr", "daily_rhr")


def resolve(candidates: dict[date, Candidates]) -> list[dict[str, Any]]:
    """Resolved nights, newest first. A night with no value in any field is dropped."""
    nights = [resolve_night(n, c) for n, c in sorted(candidates.items(), reverse=True)]
    # all-day median HR rides along on a night but is not a recovery metric on its own, and
    # the empty daily_rhr slot is not data: neither keeps an otherwise empty night.
    return [n for n in nights if n["hrv"] or any(n[f] for f in FIELD_RANK if f not in _NOT_ALONE)]


# -- loading: one candidate per source store, all keyed on the wake-date --------------------------

def _add(cands: dict[date, Candidates], night: date, source: str, **fields: Any) -> None:
    present = {k: v for k, v in fields.items() if v is not None}
    if present:
        cands.setdefault(night, {}).setdefault(source, {}).update(present)


def _hc_source_key(packages: set[str]) -> str:
    if len(packages) >= 2:
        return HC_BLENDED
    if len(packages) == 1:
        key = SLEEP_SOURCE_BY_PACKAGE.get(next(iter(packages)))
        if key:
            return f"{key}_hc"
    return HC_UNNAMED


def _hc_package_key(package: str | None) -> str:
    key = SLEEP_SOURCE_BY_PACKAGE.get(package or "")
    return f"{key}_hc" if key else HC_UNNAMED


def load_candidates(db: Session, user_id: int, since: date) -> dict[date, Candidates]:
    cands: dict[date, Candidates] = {}

    for r in db.query(models.SamsungHRVReading).filter(
        models.SamsungHRVReading.user_id == user_id,
        models.SamsungHRVReading.captured_at >= since,
        models.SamsungHRVReading.context == "passive_overnight",
    ):
        _add(cands, r.captured_at, SCRAPER, hrv=r.hrv_ms, tst=r.actual_sleep_time_minutes,
             efficiency=r.sleep_efficiency_pct, deep=r.deep_minutes, rem=r.rem_minutes,
             light=r.light_minutes, awake=r.awake_minutes, spo2=r.spo2_average_pct,
             rr=r.respiratory_rate, sleep_hr=r.sleep_hr_bpm)

    for r in db.query(models.HrvReading).filter(
        models.HrvReading.user_id == user_id,
        models.HrvReading.captured_at >= since,
        models.HrvReading.source == "garmin",
    ):
        _add(cands, r.captured_at, "garmin", hrv=r.rmssd_ms)

    for r in db.query(models.HealthConnectSync).filter(
        models.HealthConnectSync.user_id == user_id,
        models.HealthConnectSync.date >= since,
    ):
        if r.sleep_duration_minutes is not None:
            key = _hc_source_key(hc_sleep_writers(db, user_id, r.date))
            _add(cands, r.date, key, tst=r.sleep_duration_minutes, deep=r.deep_sleep_minutes,
                 rem=r.rem_sleep_minutes, light=r.light_sleep_minutes)
        if r.hr_nadir_bpm is not None:
            _add(cands, r.date, _hc_package_key(r.hr_nadir_source_package),
                 sleep_nadir_hr=r.hr_nadir_bpm)
        _add(cands, r.date, "hc_aest_day", all_day_median_hr=r.resting_heart_rate)
        _add(cands, r.date, "hc_utc_day", hrv=r.hrv_rmssd, spo2=r.oxygen_saturation,
             rr=r.respiratory_rate)

    for night, mean, low in (
        db.query(models.Spo2Night.captured_at, func.avg(models.Spo2Sample.spo2_pct),
                 func.min(models.Spo2Sample.spo2_pct))
        .join(models.Spo2Sample, models.Spo2Sample.spo2_night_id == models.Spo2Night.id)
        .filter(models.Spo2Night.user_id == user_id, models.Spo2Night.captured_at >= since,
                models.Spo2Night.source == "garmin", models.Spo2Sample.spo2_pct.isnot(None))
        .group_by(models.Spo2Night.id, models.Spo2Night.captured_at)
    ):
        _add(cands, night, "garmin", spo2=float(mean), spo2_min=float(low))

    return cands


# -- rendering ------------------------------------------------------------------------------------

def _tag(source: str) -> str:
    return f" [{SOURCE_LABELS.get(source, source)}]"


def _n(v: float | None, unit: str = "", fmt: str = ".0f") -> str:
    return "—" if v is None else f"{v:{fmt}}{unit}"


def format_night(r: dict[str, Any]) -> str:
    """One night, one line, every field with the source that supplied it. A field no source
    carries prints '—' (absent, never zero)."""
    hrv = ", ".join(f"{ms:.0f} ms{_tag(s)}" for s, ms in r["hrv"]) or "—"
    parts = [f"HRV={hrv}"]

    def one(name: str, field: str, unit: str, fmt: str = ".0f", key: str | None = None) -> str:
        hit = r[field]
        v = hit["value"][key or field] if hit else None
        return f"{name}={_n(v, unit, fmt)}" + (_tag(hit["source"]) if hit and v is not None else "")

    parts.append(one("TST", "tst", " min"))
    stages = r["stages"]
    if stages:
        v = stages["value"]
        parts.append(
            f"Deep={_n(v['deep'], 'm')} REM={_n(v['rem'], 'm')} Light={_n(v['light'], 'm')} "
            f"Awake={_n(v['awake'], 'm')}{_tag(stages['source'])}"
        )
    else:
        parts.append("Deep=— REM=— Light=— Awake=—")
    parts.append(one("Eff", "efficiency", "%"))
    spo2 = r["spo2"]
    if spo2:
        low = spo2["value"]["spo2_min"]
        parts.append(f"SpO2={spo2['value']['spo2']:.1f}%" + (f" (min {low:.0f}%)" if low is not None else "")
                     + _tag(spo2["source"]))
    else:
        parts.append("SpO2=—")
    parts.append(one("RR", "rr", " br/min", ".1f"))
    # The daily resting rate has a named slot and no source yet: it is never filled from a
    # sleep-window or all-day figure. Those carry their own labels below.
    parts.append(one("RHR", "daily_rhr", " bpm") if r["daily_rhr"] else "RHR=— (no daily-RHR source yet)")
    parts.append(one("Sleep-nadir HR", "sleep_nadir_hr", " bpm"))
    parts.append(one("Sleep HR", "sleep_hr", " bpm"))
    parts.append(one("All-day median HR", "all_day_median_hr", " bpm"))
    return f"{r['night']}: " + " | ".join(parts)


def format_recovery(resolved: list[dict[str, Any]], days: int) -> str:
    if not resolved:
        return f"No recovery data found in the last {days} days."
    used = sorted({
        s for r in resolved
        for s in [x for x, _ in r["hrv"]] + [r[f]["source"] for f in FIELD_RANK if r[f]]
    })
    lines = [
        f"Recovery metrics — last {days} days (one line per wake-day; each value is tagged with the "
        f"source that supplied it; sources: {', '.join(SOURCE_LABELS.get(s, s) for s in used)})",
        f"Data window: {resolved[-1]['night']} → {resolved[0]['night']}\n",
    ]
    lines += [format_night(r) for r in resolved]
    return "\n".join(lines)


def recovery_text(db: Session, user_id: int, since: date, days: int) -> str:
    return format_recovery(resolve(load_candidates(db, user_id, since)), days)
