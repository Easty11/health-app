"""Per-field resolution of a night's recovery metrics, for the MCP `get_recovery_metrics` and,
through `snapshot_reads.latest_sleep_night`, the readiness snapshot and the card.

Read-side only: nothing here ingests, aggregates or writes.

THE SHAPE. A night (keyed on its WAKE-DATE) is a set of CANDIDATES, one per (source, transport)
that has something for it: {source_key: {field: value}}. `resolve_night` walks each field's rank
list (`FIELD_RANK`) and takes the first candidate whose value is not None, so a source that
carries only some fields never suppresses the others. Every resolved value keeps the source that
supplied it; the formatter prints it.

GARMIN RANKS ON (SOURCE, TRANSPORT). `source` stays 'garmin' in every store (#449 R4); the
transport is the second coordinate and gets its own candidate key and its own label:
    garmin_api  -- the Personal API (sleep_nights, daily_physiology, hrv_readings.transport)
    garmin_hc   -- the Garmin package writing into Health Connect
    garmin_di   -- the unofficial DI lane (spo2_nights epochs, the CPAP-seal evidence, #450)
    garmin      -- an `hrv_readings` row with no transport recorded (history before #449)
The rank tables stay per field; there is no cross-domain tier table. Sleep: garmin_api > HC
writers > scraper. SpO2: garmin_di (epoch-derived mean/min) > garmin_api (the nightly summary,
which is the permanent fallback, #450) > scraper > HC UTC-day. Daily RHR: garmin_api only.

TWO FIELD KINDS THAT ARE NOT "FIRST NON-NULL WINS":
  * HRV is never arbitrated (#292): two devices are two instruments and raw ms is never
    blended or ranked, so every source with a value is printed. `HRV_FALLBACK_SOURCES` (the
    Health Connect UTC-day HRV) is shown only when no instrument source has one.
  * The sleep STAGES (deep/rem/light/awake) resolve as ONE group from one source: stages are
    never mixed across writers (the sleep-writer ruling, snapshot_reads). A blended Health
    Connect night (two or more real writers) withholds its stage split, as the snapshot does.

WITHHELD NIGHTS. A wearable's sleep night that cannot be one night (`hc_sleep.night_implausibility`)
is not offered as a candidate: its TST, stages and nadir (the nadir window is the same bad period)
are dropped and the reason is kept in the night's `withheld` map, which the formatter prints. The
guard runs on every wearable lane, so it holds on the Health Connect path whatever ranks above it.

DATE KEYS. Sleep, stages, nadir, `hrv_readings`, `spo2_nights` and the Samsung scraper are all
keyed on the wake-date. `daily_physiology` is keyed on the CALENDAR day Garmin was asked for, which
for a night is its wake-day (the day's resting rate is read as the rate of the day that began with
this wake-up; today's is provisional until the day closes). `health_connect_syncs.oxygen_saturation
/ respiratory_rate / hrv_rmssd` are UTC-date keyed (a pending re-bucketing, see the model), so they
carry their own source key `hc_utc_day` and are the lowest rank of their field.

THE ALL-DAY MEDIAN IS NOT SHOWN. `health_connect_syncs.resting_heart_rate` (the median of every HR
sample in the AEST day) is stored and unread here: it weights samples by count, so a one-second
Polar bout outweighs a day of two-minute Garmin samples (21 Oct 2026: 2,076 Polar samples in 35 min
against 901 Garmin samples in 24 h gave 144 bpm). A daily RHR now exists to show instead.

THE PARTIAL-NIGHT NOTE (Q247). A watch that is woken mid-night keeps only the
longest stint, so its TST can read far below the night the diary records (11 Oct 2026: device 203 min,
diary 439). The stored number is never changed. Where the night has a diary TST, the line shows it
beside the device figure, and when the device is `PARTIAL_NIGHT_MIN` minutes or more below it the line
says the device may have recorded only part of the night, with the device window (the Personal API
sleep row only; the Health Connect `sleep_start` is not ruled) beside the diary lights-out. A night
with no diary TST gets no note and no flag. This reads the recall diary FROM a sensor reader; the I1
firewall binds the other direction (CBT-I never reads a sensor) and is untouched.

SPO2 IS DERIVED HERE. `spo2_nights` stores raw epochs only (Q150: no mean, no min). The nightly
mean and min are computed over the night's non-null `spo2_pct` epochs, UNFILTERED -- no
confidence threshold, no range check -- because none is ruled. See DECISIONS_LOG.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytz
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from reads.hc_sleep import (
    SLEEP_SOURCE_BY_PACKAGE, SLEEP_WRITER_PRIORITY, hc_sleep_writers, night_implausibility,
)

SCRAPER = "samsung_scraper"
GARMIN_API = "garmin_api"
GARMIN_DI = "garmin_di"
GARMIN_NO_TRANSPORT = "garmin"
_HC_WRITERS = tuple(f"{k}_hc" for k in SLEEP_WRITER_PRIORITY)        # garmin_hc, samsung_hc, withings_hc
HC_BLENDED = "hc_multiple"                                            # two or more real writers
HC_UNNAMED = "hc"                                                     # one writer with no friendly name, or none recorded
WITHHELD = "_withheld"                                                # per-night {source_key: reason}, not a source

SOURCE_LABELS = {
    GARMIN_API: "garmin/api",
    "garmin_hc": "garmin/HC",
    GARMIN_DI: "garmin/di",
    GARMIN_NO_TRANSPORT: "garmin",
    "samsung_hc": "samsung/HC",
    "withings_hc": "withings/HC",
    HC_BLENDED: "HC (multiple writers)",
    HC_UNNAMED: "HC",
    SCRAPER: "samsung scraper",
    "hc_utc_day": "HC UTC-day",
}

_TRANSPORT_KEY = {"personal_api": GARMIN_API, "di": GARMIN_DI}

# Sleep order: the Personal API first, then SLEEP_WRITER_PRIORITY as HC writers, an unnamed HC
# writer after them, the scraper last (below every HC writer by the sleep-writer ruling).
SLEEP_RANK = (GARMIN_API,) + _HC_WRITERS + (HC_UNNAMED, SCRAPER)
STAGE_RANK = SLEEP_RANK                      # HC_BLENDED is deliberately absent: no stage split from a blend
TST_RANK = (GARMIN_API,) + _HC_WRITERS + (HC_BLENDED, HC_UNNAMED, SCRAPER)
NADIR_RANK = _HC_WRITERS + (HC_UNNAMED,)     # only Health Connect derives a nadir (hr_nadir.py)

FIELD_RANK: dict[str, tuple[str, ...]] = {
    "tst": TST_RANK,
    "stages": STAGE_RANK,                                   # deep / rem / light / awake, one source
    "efficiency": (GARMIN_API, SCRAPER),                    # the HC aggregate does not carry it
    "score": (GARMIN_API,),                                 # Garmin's own composite; display only
    "spo2": (GARMIN_DI, GARMIN_API, SCRAPER, "hc_utc_day"),  # nightly mean (+ min where the source has one)
    "rr": (GARMIN_API, SCRAPER, "hc_utc_day"),
    "sleep_hr": (SCRAPER,),                                 # the ring's average HR over the night
    "sleep_nadir_hr": NADIR_RANK,
    # The real daily resting rate: dailyHeartRate.restingHeartRate. Never the HR-zones endpoint's
    # 7-day auto figure and never averageSpO2HRSleep (a sleep HR).
    "daily_rhr": (GARMIN_API,),
}
STAGE_FIELDS = ("deep", "rem", "light", "awake")
HRV_SOURCES = (GARMIN_API, GARMIN_DI, GARMIN_NO_TRANSPORT, SCRAPER)
HRV_FALLBACK_SOURCES = ("hc_utc_day",)

# (field, source) pairs whose value is computed here or in the mapper, not read off the device.
DERIVED = {("efficiency", GARMIN_API)}

# field -> the candidate keys that supply it (a "group" field names several)
_FIELD_KEYS = {
    "tst": ("tst",),
    "stages": STAGE_FIELDS,
    "efficiency": ("efficiency",),
    "score": ("score",),
    "spo2": ("spo2", "spo2_min"),
    "rr": ("rr", "rr_low", "rr_high"),
    "sleep_hr": ("sleep_hr",),
    "sleep_nadir_hr": ("sleep_nadir_hr",),
    "daily_rhr": ("daily_rhr",),
}

# A source takes the stage group only if it carries an asleep stage: awake minutes alone are not a
# split, and would otherwise win the group and leave deep/REM/light blank.
_CARRY_KEYS = {"stages": ("deep", "rem", "light")}

Candidates = dict[str, dict[str, Any]]            # source_key -> {field: value}


def _carries(cand: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(cand.get(k) is not None for k in keys)


def resolve_night(night: date, cands: Candidates) -> dict[str, Any]:
    """One night's resolved view: for each ranked field `{"value": {...}, "source": key}`
    (or None when no source carries it), plus `hrv`, a list of `(source, ms)`, and `withheld`,
    the `{source_key: reason}` of any sleep night refused as implausible."""
    out: dict[str, Any] = {"night": night}
    for field, rank in FIELD_RANK.items():
        keys = _FIELD_KEYS[field]
        carry = _CARRY_KEYS.get(field, keys)
        hit = next((s for s in rank if s in cands and _carries(cands[s], carry)), None)
        out[field] = None if hit is None else {
            "source": hit, "value": {k: cands[hit].get(k) for k in keys},
        }
    hrv = [(s, cands[s]["hrv"]) for s in HRV_SOURCES if cands.get(s, {}).get("hrv") is not None]
    if not hrv:
        hrv = [(s, cands[s]["hrv"]) for s in HRV_FALLBACK_SOURCES if cands.get(s, {}).get("hrv") is not None]
    out["hrv"] = hrv
    out["withheld"] = dict(cands.get(WITHHELD, {}))
    return out


_NOT_ALONE = ("daily_rhr",)


def resolve(candidates: dict[date, Candidates]) -> list[dict[str, Any]]:
    """Resolved nights, newest first. A night with no value in any field is dropped."""
    nights = [resolve_night(n, c) for n, c in sorted(candidates.items(), reverse=True)]
    # The daily resting rate is keyed on a calendar day, so today's row exists before today's
    # night does; it rides along on a night but does not keep an otherwise empty one.
    return [n for n in nights
            if n["hrv"] or n["withheld"] or any(n[f] for f in FIELD_RANK if f not in _NOT_ALONE)]


# -- loading: one candidate per source store, all keyed on the wake-date --------------------------

def _add(cands: dict[date, Candidates], night: date, source: str, **fields: Any) -> None:
    present = {k: v for k, v in fields.items() if v is not None}
    if present:
        cands.setdefault(night, {}).setdefault(source, {}).update(present)


def _withhold(cands: dict[date, Candidates], night: date, source: str, reason: str) -> None:
    cands.setdefault(night, {}).setdefault(WITHHELD, {})[source] = reason


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


def _transport_key(transport: str | None) -> str:
    return _TRANSPORT_KEY.get(transport or "", GARMIN_NO_TRANSPORT)


def _minutes(seconds: int | None) -> int | None:
    return None if seconds is None else int(round(seconds / 60))


def load_candidates(db: Session, user_id: int, since: date) -> dict[date, Candidates]:
    cands: dict[date, Candidates] = {}

    for r in db.query(models.SamsungHRVReading).filter(
        models.SamsungHRVReading.user_id == user_id,
        models.SamsungHRVReading.captured_at >= since,
        models.SamsungHRVReading.context == "passive_overnight",
    ):
        # The card has always taken the total when the scraper stored one; the table took the actual.
        # Neither is dropped: the actual wins where both exist, the total stands in where it is alone.
        _add(cands, r.captured_at, SCRAPER, hrv=r.hrv_ms,
             tst=r.actual_sleep_time_minutes if r.actual_sleep_time_minutes is not None
             else r.total_sleep_time_minutes,
             efficiency=r.sleep_efficiency_pct, deep=r.deep_minutes, rem=r.rem_minutes,
             light=r.light_minutes, awake=r.awake_minutes, spo2=r.spo2_average_pct,
             rr=r.respiratory_rate, sleep_hr=r.sleep_hr_bpm)

    for r in db.query(models.HrvReading).filter(
        models.HrvReading.user_id == user_id,
        models.HrvReading.captured_at >= since,
        models.HrvReading.source == "garmin",
    ):
        _add(cands, r.captured_at, _transport_key(r.transport), hrv=r.rmssd_ms)

    for r in db.query(models.SleepNight).filter(
        models.SleepNight.user_id == user_id,
        models.SleepNight.captured_at >= since,
        models.SleepNight.source == "garmin",
    ):
        key = _transport_key(r.transport)
        tst, deep, rem, light = (_minutes(r.sleep_time_s), _minutes(r.deep_s), _minutes(r.rem_s),
                                 _minutes(r.light_s))
        stage_sum = None if None in (deep, rem, light) else deep + rem + light
        why = night_implausibility(tst, stage_sum, r.sleep_start, r.sleep_end)
        if why:
            _withhold(cands, r.captured_at, key, why)
        else:
            _add(cands, r.captured_at, key, tst=tst, deep=deep, rem=rem, light=light,
                 awake=_minutes(r.awake_s), efficiency=r.efficiency_pct, score=r.sleep_score)
        # Not sleep-duration facts, so the guard on the duration does not reach them.
        _add(cands, r.captured_at, key, rr=r.respiration_avg, rr_low=r.respiration_low,
             rr_high=r.respiration_high, spo2=r.spo2_avg_pct, spo2_min=r.spo2_lowest_pct)

    for r in db.query(models.DailyPhysiology).filter(
        models.DailyPhysiology.user_id == user_id,
        models.DailyPhysiology.date >= since,
        models.DailyPhysiology.source == "garmin",
    ):
        _add(cands, r.date, _transport_key(r.transport), daily_rhr=r.resting_hr_bpm)

    for r in db.query(models.HealthConnectSync).filter(
        models.HealthConnectSync.user_id == user_id,
        models.HealthConnectSync.date >= since,
    ):
        nadir = r.hr_nadir_bpm
        if r.sleep_duration_minutes is not None:
            key = _hc_source_key(hc_sleep_writers(db, user_id, r.date))
            stages = (r.deep_sleep_minutes, r.rem_sleep_minutes, r.light_sleep_minutes)
            stage_sum = None if None in stages else sum(stages)
            why = night_implausibility(r.sleep_duration_minutes, stage_sum, r.sleep_start, r.sleep_end)
            if why:
                _withhold(cands, r.date, key, why)
                nadir = None                       # read over the same bad period: it goes with the night
            else:
                _add(cands, r.date, key, tst=r.sleep_duration_minutes, deep=r.deep_sleep_minutes,
                     rem=r.rem_sleep_minutes, light=r.light_sleep_minutes)
        if nadir is not None:
            _add(cands, r.date, _hc_package_key(r.hr_nadir_source_package), sleep_nadir_hr=nadir)
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
        _add(cands, night, GARMIN_DI, spo2=float(mean), spo2_min=float(low))

    return cands


# -- the partial-night note (Q247, Q248) -----------------------------------------------------------

PARTIAL_NIGHT_MIN = 60          # flag when the device TST is at least this many minutes below the diary TST
WINDOW_TOLERANCE_MIN = 60       # Q248: the device window is late or early only by at least this much
_AEST = pytz.timezone("Australia/Brisbane")   # no DST; the diary's clocks are operator-local


def load_diary(db: Session, user_id: int, since: date) -> dict[date, dict[str, Any]]:
    """`{wake-date: {"tst": minutes, "lights_out": "HH:MM" | None, "final_wake": "HH:MM" | None}}` for nights
    with a diary TST. A night the diary has not been logged for is absent, which is what keeps it unflagged."""
    rows = db.query(models.DailyRecord.date, models.DailyRecord.diary_tst_min, models.DailyRecord.lights_out,
                    models.DailyRecord.final_wake).filter(
        models.DailyRecord.user_id == user_id,
        models.DailyRecord.date >= since,
        models.DailyRecord.diary_tst_min.isnot(None),
    )
    return {d: {"tst": tst, "lights_out": lo, "final_wake": fw} for d, tst, lo, fw in rows}


def load_device_nights(db: Session, user_id: int, since: date) -> dict[date, dict[str, Any]]:
    """`{wake-date: {"start", "end", "awake_min"}}` from the Personal API's sleep row. Health Connect's
    `sleep_start` is not read: its meaning per source is not ruled (models.HealthConnectSync)."""
    rows = db.query(models.SleepNight.captured_at, models.SleepNight.sleep_start, models.SleepNight.sleep_end,
                    models.SleepNight.awake_s).filter(
        models.SleepNight.user_id == user_id,
        models.SleepNight.source == "garmin",
        models.SleepNight.captured_at >= since,
        models.SleepNight.sleep_start.isnot(None),
        models.SleepNight.sleep_end.isnot(None),
    )
    return {d: {"start": a, "end": b, "awake_min": _minutes(w)} for d, a, b, w in rows}


def _aest(dt: datetime) -> datetime:
    if dt.tzinfo is None:                       # SQLite round-trips TIMESTAMPTZ naive; the stored value is UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_AEST)


def _clock(dt: datetime) -> str:
    return _aest(dt).strftime("%H:%M")


def _diary_clock(night: date, hhmm: str | None, *, bedtime: bool) -> datetime | None:
    """A diary clock ("HH:MM", Brisbane) as a datetime on the right side of the wake-date. A bedtime at or after
    noon belongs to the evening before the wake-date; one before noon (a shift night) is after midnight, on it.
    A final wake is on the wake-date. None when the clock is absent or unreadable."""
    if not hhmm:
        return None
    try:
        h, m = (int(x) for x in hhmm.split(":"))
        day = night - timedelta(days=1) if (bedtime and h >= 12) else night
        return _AEST.localize(datetime(day.year, day.month, day.day, h, m))
    except (ValueError, TypeError):
        return None


def _window_kinds(night: date, diary: dict[str, Any], dev: dict[str, Any]) -> tuple[list[str], int | None, int | None]:
    """How the device window falls short of the diary night: `started_late` (it opens at least
    WINDOW_TOLERANCE_MIN after the diary lights-out), `finished_early` (it closes at least that long before the
    diary final wake), or `broken_up` (it covers the night at both ends, so the gap is awake time inside it).
    `broken_up` is asserted only when both diary clocks are present; with one missing and no other kind, the
    mechanism is not determinable and the list is empty."""
    start, end = _aest(dev["start"]), _aest(dev["end"])
    lo = _diary_clock(night, diary.get("lights_out"), bedtime=True)
    fw = _diary_clock(night, diary.get("final_wake"), bedtime=False)
    late = None if lo is None else round((start - lo).total_seconds() / 60)
    early = None if fw is None else round((fw - end).total_seconds() / 60)
    kinds: list[str] = []
    if late is not None and late >= WINDOW_TOLERANCE_MIN:
        kinds.append("started_late")
    if early is not None and early >= WINDOW_TOLERANCE_MIN:
        kinds.append("finished_early")
    if not kinds and late is not None and early is not None:
        kinds.append("broken_up")
    return kinds, late, early


def partial_note(night: date, device_tst: int | None, tst_source: str | None, diary: dict[str, Any] | None,
                 dev: dict[str, Any] | None) -> dict[str, Any] | None:
    """The diary beside the device figure, flagged when the device is short, and for a flagged night which way
    the window falls short. None when either TST is missing. The window rides only when the Personal API
    supplied the TST it describes."""
    if diary is None or device_tst is None:
        return None
    short = diary["tst"] - device_tst
    flagged = short >= PARTIAL_NIGHT_MIN
    dev = dev if tst_source == GARMIN_API else None
    kinds, late, early = _window_kinds(night, diary, dev) if (flagged and dev) else ([], None, None)
    return {
        "diary_tst": diary["tst"],
        "lights_out": diary.get("lights_out"),
        "final_wake": diary.get("final_wake"),
        "short_min": short if flagged else None,
        "window": f"{_clock(dev['start'])}\u2013{_clock(dev['end'])}" if dev else None,
        "kinds": kinds,
        "late_min": late,
        "early_min": early,
        "awake_min": dev["awake_min"] if dev else None,
    }


def format_minutes(minutes: float) -> str:
    """4 h 14 m, or 37 m: whole minutes, never a bare decimal."""
    total = int(round(minutes))
    return f"{total // 60} h {total % 60:02d} m" if total >= 60 else f"{total} m"


def partial_clause(note: dict[str, Any]) -> str:
    """What happened to the window, from the facts in hand. A flagged night whose mechanism cannot be told (a
    Health Connect night, or a diary clock missing) keeps the generic sentence and whatever evidence exists."""
    kinds, win = note["kinds"], note["window"]
    if not kinds:
        bits = ([f"device window {win}"] if win else []) + (
            [f"diary lights-out {note['lights_out']}"] if note["lights_out"] else [])
        return "the device may have recorded only part of the night" + (f" ({', '.join(bits)})" if bits else "")
    labels = {"started_late": "started late", "finished_early": "finished early", "broken_up": "broken up"}
    facts = []
    if "started_late" in kinds:
        facts.append(f"starts {format_minutes(note['late_min'])} after diary lights-out {note['lights_out']}")
    if "finished_early" in kinds:
        facts.append(f"ends {format_minutes(note['early_min'])} before diary final wake {note['final_wake']}")
    if "broken_up" in kinds:
        awake = note["awake_min"]
        facts.append("covers the night but scores "
                     + (f"{awake} min awake inside it" if awake is not None else "awake time inside it"))
    return (f"window {' and '.join(labels[k] for k in kinds)}: the device window {win} "
            + " and ".join(facts))


def annotate_partial(resolved: list[dict[str, Any]], diary: dict[date, dict[str, Any]],
                     devices: dict[date, dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach `diary_note` to each resolved night that has both a device TST and a diary TST. In place."""
    for r in resolved:
        tst = r["tst"]
        if tst is None:
            continue
        note = partial_note(r["night"], tst["value"]["tst"], tst["source"], diary.get(r["night"]),
                            devices.get(r["night"]))
        if note is not None:
            r["diary_note"] = note
    return resolved


# -- rendering ------------------------------------------------------------------------------------

def _label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def _tag(source: str, derived: bool = False) -> str:
    return f" [{_label(source)}{', derived' if derived else ''}]"


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
        if hit is None or v is None:
            return f"{name}=—"
        return f"{name}={_n(v, unit, fmt)}" + _tag(hit["source"], (field, hit["source"]) in DERIVED)

    tst = one("TST", "tst", " min")
    note = r.get("diary_note")
    if note:
        if note["short_min"] is None:
            tst += f" (diary {note['diary_tst']} min)"
        else:
            tst += f" (diary {note['diary_tst']} min; {note['short_min']} min below the diary; {partial_clause(note)})"
    parts.append(tst)
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
    rr = one("RR", "rr", " br/min", ".1f")
    if r["rr"] and r["rr"]["value"]["rr_low"] is not None and r["rr"]["value"]["rr_high"] is not None:
        v = r["rr"]["value"]
        rr = rr.replace(" br/min", f" br/min (low {v['rr_low']:.0f}, high {v['rr_high']:.0f})", 1)
    parts.append(rr)
    # The daily resting rate is its own figure: never filled from a sleep-window figure. Those
    # carry their own labels below.
    parts.append(one("RHR", "daily_rhr", " bpm"))
    parts.append(one("Sleep-nadir HR", "sleep_nadir_hr", " bpm"))
    parts.append(one("Sleep HR", "sleep_hr", " bpm"))
    if r["score"]:
        parts.append(one("Sleep score", "score", ""))
    if r["withheld"]:
        parts.append("Withheld: " + "; ".join(f"{_label(s)} sleep — {why}" for s, why in r["withheld"].items()))
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
        f"source that supplied it; sources: {', '.join(_label(s) for s in used)})",
        f"Data window: {resolved[-1]['night']} → {resolved[0]['night']}\n",
    ]
    lines += [format_night(r) for r in resolved]
    return "\n".join(lines)


def recovery_text(db: Session, user_id: int, since: date, days: int) -> str:
    resolved = annotate_partial(resolve(load_candidates(db, user_id, since)),
                                load_diary(db, user_id, since), load_device_nights(db, user_id, since))
    return format_recovery(resolved, days)
