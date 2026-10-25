"""Garmin Personal API wellness lane (S3): sleep, daily HR, hourly SpO2, body battery, stress, HR-zone config.

Per day and endpoint: fetch -> LAND the raw payload (`garmin_raw.land`, scrubbed + hashed) -> map the landed
payload into the canonical tables -> commit. The mappers are pure functions of the payload, so they are
re-runnable from the raw landing without a re-fetch (`remap_user`): a shape that turns out different from
what a mapper assumed is a code fix plus a remap, not a lost night.

What is VERIFIED against real payloads (chat probe, 24-25 Oct 2026): the sleep field names, the daily
heart-rate `restingHeartRate` + ~2-min samples, the 24 hourly SpO2 averages. What is NOT yet: the exact
shapes of body battery, stress and the HR-zone endpoint, which the mappers read defensively (candidate keys,
NULL when absent, a warning when a non-empty payload yields nothing). The raw landing is the safety net.

Traps encoded here (each has a test): `averageSpO2HRSleep` is a heart rate and is never read as SpO2; times
are the GMT instants Garmin sends, never keyed on the profile timezone; sleep `calendarDate` is the wake
date; daily RHR comes from the daily heart-rate endpoint, while the HR-zones endpoint's resting HR is
Garmin's 7-day auto value and is stored apart (`rhr_7d_auto_bpm`).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

import garmin_raw
import models
from connectors import garmin_personal as gp
from garmin_spo2 import _num, _to_utc

logger = logging.getLogger(__name__)

SOURCE = "garmin"
TRANSPORT = "personal_api"
HR_SOURCE_PACKAGE = "personal_api"
EFFICIENCY_FORMULA = "garmin_window_tst_over_span_v1"

EP_SLEEP, EP_HEART_RATE, EP_SPO2_HOURLY = "sleep", "heart_rate", "spo2_hourly"
EP_BODY_BATTERY, EP_STRESS, EP_HR_ZONES = "body_battery", "stress", "hr_zones"
DAY_ENDPOINTS = (EP_SLEEP, EP_HEART_RATE, EP_SPO2_HOURLY, EP_BODY_BATTERY, EP_STRESS)


def _int(v: Any) -> Optional[int]:
    f = _num(v)
    return None if f is None else int(round(f))


# Keys that label a skeleton rather than carry data (the day asked for, and the identity keys the landing scrubs).
_LABEL_KEYS = frozenset({"calendardate", "date"}) | garmin_raw.IDENTITY_KEYS


def _is_skeleton(o: Any) -> bool:
    """True when `o` holds no value at all: only None, empty containers, label keys, and `[timestamp, None...]`
    placeholder pairs. Observed 25 Oct 2026 (prod, user 1): for a day with no data the host does NOT answer with
    an empty body; it answers 200 with the full field set, every value null (sleep, heart rate, hourly SpO2,
    body battery with `[ts, None]` pairs). Only HRV and stress answer empty. Anything with a real value, or a
    shape this function does not know, is content, so an unrecognised payload is landed, never dropped."""
    if o is None:
        return True
    if isinstance(o, dict):
        return all(_is_skeleton(v) for k, v in o.items() if str(k).lower() not in _LABEL_KEYS)
    if isinstance(o, list):
        if len(o) >= 2 and all(x is None for x in o[1:]):
            return True                                  # [timestamp, None]: a timestamp with no reading
        return all(_is_skeleton(v) for v in o)
    return False


def _is_empty(payload: Any) -> bool:
    return _is_skeleton(payload)


# -- mappers (pure) ---------------------------------------------------------------------------------

def parse_sleep(payload: Any, asked: date) -> Optional[dict]:
    """Storable sleep night, or None when the payload carries no sleep. Accepts the fields either flat or
    under `dailySleepDTO`."""
    if not isinstance(payload, dict):
        return None
    dto = payload.get("dailySleepDTO")
    dto = dto if isinstance(dto, dict) else payload
    start, end = _to_utc(dto.get("sleepStartTimestampGMT")), _to_utc(dto.get("sleepEndTimestampGMT"))
    tst = _int(dto.get("sleepTimeSeconds"))
    if start is None and end is None and tst is None:
        return None

    cal = dto.get("calendarDate")
    try:
        captured = date.fromisoformat(cal[:10]) if isinstance(cal, str) and len(cal) >= 10 else asked
    except ValueError:
        captured = asked

    scores = dto.get("sleepScores")
    overall, subs = None, None
    if isinstance(scores, dict):
        ov = scores.get("overall")
        overall = _int(ov.get("value") if isinstance(ov, dict) else ov)
        subs = {k: v for k, v in scores.items() if k != "overall"} or None
    need = dto.get("sleepNeed")
    need = need if isinstance(need, (dict, list)) else ({"value": need} if _num(need) is not None else None)

    efficiency = None
    if tst is not None and start is not None and end is not None and end > start:
        pct = 100.0 * tst / (end - start).total_seconds()
        if 0 <= pct <= 100:                  # >100 means the window or TST is not what we assumed: no figure
            efficiency = round(pct, 1)
    return {
        "captured_at": captured, "sleep_start": start, "sleep_end": end, "sleep_time_s": tst,
        "deep_s": _int(dto.get("deepSleepSeconds")), "light_s": _int(dto.get("lightSleepSeconds")),
        "rem_s": _int(dto.get("remSleepSeconds")), "awake_s": _int(dto.get("awakeSleepSeconds")),
        "respiration_avg": _num(dto.get("averageRespirationValue")),
        "respiration_low": _num(dto.get("lowestRespirationValue")),
        "respiration_high": _num(dto.get("highestRespirationValue")),
        # averageSpO2Value / lowestSpO2Value ONLY. averageSpO2HRSleep is a heart rate (trap).
        "spo2_avg_pct": _num(dto.get("averageSpO2Value")), "spo2_lowest_pct": _num(dto.get("lowestSpO2Value")),
        "sleep_score": overall, "sleep_scores_subs": subs, "awake_count": _int(dto.get("awakeCount")),
        "avg_sleep_stress": _num(dto.get("avgSleepStress")), "sleep_need": need,
        "efficiency_pct": efficiency, "efficiency_formula": EFFICIENCY_FORMULA if efficiency is not None else None,
    }


def parse_heart_rate(payload: Any) -> Optional[dict]:
    """`{resting, rhr_7d_avg, samples: [(utc, bpm)]}` from the daily heart-rate payload, or None."""
    if not isinstance(payload, dict):
        return None
    samples = []
    for pair in payload.get("heartRateValues") or []:
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            t, bpm = _to_utc(pair[0]), _int(pair[1])
            if t is not None and bpm is not None and bpm > 0:
                samples.append((t, bpm))
    resting = _int(payload.get("restingHeartRate"))
    if resting is None and not samples:
        return None
    return {"resting": resting, "rhr_7d_avg": _int(payload.get("lastSevenDaysAvgRestingHeartRate")),
            "samples": samples}


def parse_spo2_hourly(payload: Any) -> list[tuple[datetime, Optional[float]]]:
    """Hourly SpO2 averages from the daily SpO2 payload: `[(hour_start_utc, pct)]`. Reads
    `spO2HourlyAverages` as `[ts, value]` pairs or `{startGMT|timestamp, value}` objects."""
    if not isinstance(payload, dict):
        return []
    out: dict[datetime, Optional[float]] = {}
    for item in payload.get("spO2HourlyAverages") or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            t, v = _to_utc(item[0]), _num(item[1])
        elif isinstance(item, dict):
            t = _to_utc(item.get("startGMT") or item.get("timestamp") or item.get("startTimestampGMT"))
            v = _num(item.get("value", item.get("spo2Value")))
        else:
            continue
        if t is not None:
            out.setdefault(t, v)
    return sorted(out.items())


def parse_body_battery(payload: Any) -> Optional[dict]:
    """`{high, low, charged, drained}` from the body-battery report for one day, or None."""
    item = payload[0] if isinstance(payload, list) and payload else payload
    if not isinstance(item, dict):
        return None
    levels = []
    for entry in item.get("bodyBatteryValuesArray") or []:
        if isinstance(entry, (list, tuple)):
            for cand in (entry[1:2] + entry[2:3]) if len(entry) >= 2 else []:
                n = _int(cand)
                if n is not None and 0 <= n <= 100:
                    levels.append(n)
                    break
    out = {"high": max(levels) if levels else None, "low": min(levels) if levels else None,
           "charged": _int(item.get("charged")), "drained": _int(item.get("drained"))}
    return out if any(v is not None for v in out.values()) else None


def parse_stress(payload: Any, asked: date) -> Optional[dict]:
    """`{avg, max}` stress for `asked` from the daily stress stats payload, or None."""
    items = payload if isinstance(payload, list) else (payload.get("values") if isinstance(payload, dict) else None)
    if not isinstance(items, list):
        items = [payload] if isinstance(payload, dict) else []
    chosen = None
    for it in items:
        if isinstance(it, dict) and str(it.get("calendarDate", ""))[:10] == asked.isoformat():
            chosen = it
            break
    if chosen is None and len(items) == 1 and isinstance(items[0], dict):
        chosen = items[0]
    if chosen is None:
        return None
    vals = chosen.get("values") if isinstance(chosen.get("values"), dict) else chosen
    out = {"avg": _int(vals.get("overallStressLevel", vals.get("avgStressLevel"))),
           "max": _int(vals.get("maxStressLevel"))}
    return out if any(v is not None for v in out.values()) else None


def parse_hr_zones(payload: Any) -> Optional[dict]:
    """`{max_hr, lthr, rhr_7d_auto, method}` from the HR-zone config, or None when no figure is found.
    A list (per sport) yields its DEFAULT entry, else the first object."""
    item = payload
    if isinstance(payload, list):
        dicts = [p for p in payload if isinstance(p, dict)]
        item = next((p for p in dicts if str(p.get("sport", "")).upper() == "DEFAULT"), dicts[0] if dicts else None)
    if not isinstance(item, dict):
        return None

    def first(*keys):
        for k in keys:
            if item.get(k) is not None:
                return item[k]
        return None

    method = first("trainingMethod", "method")
    out = {"max_hr": _int(first("maxHeartRateUsed", "maxHeartRate")),
           "lthr": _int(first("lactateThresholdHeartRateUsed", "lactateThresholdHeartRate", "lthr")),
           "rhr_7d_auto": _int(first("restingHeartRateUsed", "restingHeartRate")),
           "method": str(method)[:60] if method is not None else None}
    return out if any(out[k] is not None for k in ("max_hr", "lthr", "rhr_7d_auto")) else None


# -- storage ----------------------------------------------------------------------------------------

def store_sleep(db, user_id: int, n: dict) -> str:
    row = db.query(models.SleepNight).filter_by(user_id=user_id, captured_at=n["captured_at"], source=SOURCE).first()
    fields = {k: v for k, v in n.items() if k != "captured_at"}
    if row is None:
        db.add(models.SleepNight(user_id=user_id, captured_at=n["captured_at"], source=SOURCE,
                                 transport=TRANSPORT, **fields))
        db.flush()                                    # autoflush is off: make the row visible to the next lookup
        return "inserted"
    for k, v in fields.items():
        setattr(row, k, v)
    row.transport = TRANSPORT
    return "updated"


def store_daily_physiology(db, user_id: int, day: date, **fields: Any) -> None:
    """Upsert the day's row, setting only the fields given non-None (three endpoints each own some)."""
    row = db.query(models.DailyPhysiology).filter_by(user_id=user_id, date=day, source=SOURCE).first()
    if row is None:
        row = models.DailyPhysiology(user_id=user_id, date=day, source=SOURCE, transport=TRANSPORT)
        db.add(row)
        db.flush()                                    # autoflush is off: the next endpoint's call must find this row
    for k, v in fields.items():
        if v is not None:
            setattr(row, k, v)


def store_hr_samples(db, user_id: int, samples: list[tuple[datetime, int]]) -> int:
    """Insert-or-ignore on (user, time, source, package). Returns rows inserted."""
    if not samples:
        return 0
    lo, hi = min(t for t, _ in samples), max(t for t, _ in samples)
    have = {t if t.tzinfo else t.replace(tzinfo=timezone.utc) for (t,) in db.query(models.HrSample.sample_time).filter(
        models.HrSample.user_id == user_id, models.HrSample.source == SOURCE,
        models.HrSample.source_package == HR_SOURCE_PACKAGE,
        models.HrSample.sample_time >= lo, models.HrSample.sample_time <= hi).all()}
    new = [models.HrSample(user_id=user_id, sample_time=t, bpm=b, source=SOURCE, source_package=HR_SOURCE_PACKAGE)
           for t, b in samples if t not in have]
    db.add_all(new)
    return len(new)


def store_spo2_hourly(db, user_id: int, hours: list[tuple[datetime, Optional[float]]]) -> int:
    n = 0
    for t, v in hours:
        row = db.query(models.Spo2Hourly).filter_by(user_id=user_id, hour_start=t, source=SOURCE).first()
        if row is None:
            db.add(models.Spo2Hourly(user_id=user_id, hour_start=t, avg_pct=v, source=SOURCE, transport=TRANSPORT))
            db.flush()
            n += 1
        elif row.avg_pct != v:
            row.avg_pct = v
    return n


def store_hr_zone_snapshot(db, user_id: int, z: dict, sha: str, *, now: Optional[datetime] = None) -> bool:
    """Append a snapshot only when the tuple differs from the user's latest. True when a row was added."""
    latest = (db.query(models.HrZoneConfigSnapshot).filter_by(user_id=user_id)
              .order_by(models.HrZoneConfigSnapshot.captured_at.desc(), models.HrZoneConfigSnapshot.id.desc()).first())
    cur = (z["max_hr"], z["lthr"], z["rhr_7d_auto"], z["method"])
    if latest is not None and (latest.max_hr_bpm, latest.lthr_bpm, latest.rhr_7d_auto_bpm, latest.method) == cur:
        return False
    db.add(models.HrZoneConfigSnapshot(
        user_id=user_id, source=SOURCE, transport=TRANSPORT, max_hr_bpm=z["max_hr"], lthr_bpm=z["lthr"],
        rhr_7d_auto_bpm=z["rhr_7d_auto"], method=z["method"], payload_sha256=sha,
        captured_at=now or datetime.now(timezone.utc)))
    db.flush()
    return True


# -- apply one landed payload ------------------------------------------------------------------------

def apply_payload(db, user_id: int, endpoint: str, ref: str, payload: Any, sha: str,
                  counts: dict, *, now: Optional[datetime] = None) -> None:
    """Map one landed payload into its canonical table(s). Flushes nothing itself; the caller commits."""
    if endpoint == EP_HR_ZONES:
        z = parse_hr_zones(payload)
        if z is None:
            if not _is_empty(payload):
                logger.warning("garmin wellness: user %s hr_zones payload yielded no figure (shape?)", user_id)
                counts["unmapped"] += 1
            return
        if store_hr_zone_snapshot(db, user_id, z, sha, now=now):
            counts["hr_zone_snapshots"] += 1
        return

    day = date.fromisoformat(ref)
    if endpoint == EP_SLEEP:
        n = parse_sleep(payload, day)
        if n is None:
            counts["unmapped"] += 0 if _is_empty(payload) else 1
            return
        counts[f"sleep_{store_sleep(db, user_id, n)}"] += 1
    elif endpoint == EP_HEART_RATE:
        hr = parse_heart_rate(payload)
        if hr is None:
            counts["unmapped"] += 0 if _is_empty(payload) else 1
            return
        store_daily_physiology(db, user_id, day, resting_hr_bpm=hr["resting"], rhr_7d_avg_bpm=hr["rhr_7d_avg"])
        counts["hr_samples"] += store_hr_samples(db, user_id, hr["samples"])
    elif endpoint == EP_SPO2_HOURLY:
        hours = parse_spo2_hourly(payload)
        if not hours and not _is_empty(payload):
            logger.warning("garmin wellness: user %s %s spo2_hourly payload yielded no hours (shape?)", user_id, ref)
            counts["unmapped"] += 1
        counts["spo2_hours"] += store_spo2_hourly(db, user_id, hours)
    elif endpoint == EP_BODY_BATTERY:
        bb = parse_body_battery(payload)
        if bb is None:
            counts["unmapped"] += 0 if _is_empty(payload) else 1
            return
        store_daily_physiology(db, user_id, day, body_battery_high=bb["high"], body_battery_low=bb["low"],
                               body_battery_charged=bb["charged"], body_battery_drained=bb["drained"])
    elif endpoint == EP_STRESS:
        st = parse_stress(payload, day)
        if st is None:
            counts["unmapped"] += 0 if _is_empty(payload) else 1
            return
        store_daily_physiology(db, user_id, day, stress_avg=st["avg"], stress_max=st["max"])


def _new_counts() -> dict:
    return {"days": 0, "payloads_landed": 0, "payloads_unchanged": 0, "empty": 0, "unmapped": 0,
            "sleep_inserted": 0, "sleep_updated": 0, "hr_samples": 0, "spo2_hours": 0, "hr_zone_snapshots": 0}


_FETCH: dict[str, Callable[[gp.PersonalClient, str], Any]] = {
    EP_SLEEP: lambda c, d: c.sleep_day(d),
    EP_HEART_RATE: lambda c, d: c.heart_rate_day(d),
    EP_SPO2_HOURLY: lambda c, d: c.spo2_hourly_day(d),
    EP_BODY_BATTERY: lambda c, d: c.body_battery_day(d),
    EP_STRESS: lambda c, d: c.stress_day(d),
}


def sync_user(db, user_id: int, client: gp.PersonalClient, *, start: date, end: date,
              with_zones: bool = True, now: Optional[datetime] = None) -> dict:
    """One user's wellness capture over the wake/calendar dates [start, end], oldest first. STOPS at the first
    failure (one bad day cannot become a burst of failing calls): the PersonalApiError propagates after the
    session is rolled back and the counts so far are attached as `exc.counts`. Commits per payload."""
    counts = _new_counts()
    try:
        d = start
        while d <= end:
            ref = d.isoformat()
            counts["days"] += 1
            for ep in DAY_ENDPOINTS:
                payload = _FETCH[ep](client, ref)
                if _is_empty(payload):
                    counts["empty"] += 1
                    continue
                landed = garmin_raw.land(db, user_id, ep, ref, payload, now=now)
                counts["payloads_landed" if landed.inserted else "payloads_unchanged"] += 1
                apply_payload(db, user_id, ep, ref, landed.payload, landed.sha256, counts, now=now)
                db.commit()
            d += timedelta(days=1)
        if with_zones:
            payload = client.hr_zones()
            if not _is_empty(payload):
                landed = garmin_raw.land(db, user_id, EP_HR_ZONES, "current", payload, now=now)
                counts["payloads_landed" if landed.inserted else "payloads_unchanged"] += 1
                apply_payload(db, user_id, EP_HR_ZONES, "current", landed.payload, landed.sha256, counts, now=now)
                db.commit()
    except gp.PersonalApiError as exc:
        db.rollback()
        exc.counts = counts                    # type: ignore[attr-defined]
        raise
    return counts


def remap_user(db, user_id: int, *, start: date, end: date, now: Optional[datetime] = None) -> dict:
    """Re-run the mappers over the CURRENT landed payload of every (endpoint, day) in [start, end]. No network.
    The recovery path after a mapper fix."""
    counts = _new_counts()
    d = start
    while d <= end:
        ref = d.isoformat()
        for ep in DAY_ENDPOINTS:
            row = (db.query(models.GarminRawPayload).filter_by(user_id=user_id, endpoint=ep, ref=ref)
                   .order_by(models.GarminRawPayload.fetched_at.desc(), models.GarminRawPayload.id.desc()).first())
            if row is not None:
                apply_payload(db, user_id, ep, ref, row.payload, row.payload_sha256, counts, now=now)
        counts["days"] += 1
        d += timedelta(days=1)
    db.commit()
    return counts
