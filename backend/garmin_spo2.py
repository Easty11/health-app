"""Garmin overnight SpO2 capture, raw, into `spo2_nights` / `spo2_samples` (Q150).

Garmin's SLEEP payload carries the overnight SpO2 series that Health Connect does not: one epoch per
minute (`wellnessEpochSPO2DataDTOList`, each `{epochTimestamp, spo2Reading, readingConfidence,
epochDuration, ...}`), plus `breathingDisruptionData` intervals. The daily SpO2 endpoint is hourly
averages only and is not used. This module reads the sleep payload for a wake-date, stores it, and does
nothing else:

  * RAW. No filtering, no confidence threshold, no range check, no derived metric (no minimum, average
    or dip count) is stored or computed. A null reading, an implausible value and a low confidence are
    all stored as sent; judging them is a later decision (Q150, detector design deferred).
  * The nightly row carries provenance and coverage only: the sleep window, `reading_count`, and
    `gap_count` (places where two consecutive epochs are further apart than the epoch length).
  * A re-pull replaces a night's children, the `hrv_samples` discipline, but only when the payload
    differs from what is stored, and never when the pull returns no SpO2 (an empty or failed read cannot
    wipe a stored night).
  * Reads go through the #361 no-refresh seam (`ProbeSource` = `garmin_identity.LibrarySource` plus a
    generic GET). It runs inside `scripts.garmin_sync.sweep_garmin_hrv` right after that sweep's own
    refresh-and-writeback, so the token it sees is fresh without this module adding a refresh. A token
    that still needs one is reported as `skipped_needs_refresh`, never refreshed. It never writes to
    Garmin.
  * The payload also carries the Garmin profile id and device id. Neither is read, stored or logged:
    only the fields named above are picked out, and only counts and exception class names are logged.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import quote

from sqlalchemy import delete, insert

import models
from encryption import decrypt
from scripts.garmin_identity import RefreshWouldBeNeeded
from scripts.garmin_selfeval_probe import ProbeSource

logger = logging.getLogger(__name__)

SOURCE = "garmin"
SLEEP_PATH = "/wellness-service/wellness/dailySleepData"      # + "/{displayName}" ; garminconnect 0.3.11 get_sleep_data
NON_SLEEP_BUFFER_MINUTES = "60"                                # the value the library sends
SPO2_KEY = "wellnessEpochSPO2DataDTOList"
BREATHING_KEY = "breathingDisruptionData"
DEFAULT_EPOCH_S = 60                                           # used only to size a gap when an epoch names no duration

SourceFactory = Callable[[str], Any]


# -- parsing: pick the named fields out of the payload, nothing else ---------------------------------

def _to_utc(v: Any) -> datetime | None:
    """An aware-UTC instant from epoch milliseconds (or seconds) or an ISO / 'YYYY-MM-DD HH:MM:SS' GMT string."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        if not math.isfinite(v) or v < 1e8:
            return None
        return datetime.fromtimestamp(v / 1000.0 if v > 1e11 else float(v), tz=timezone.utc)
    if isinstance(v, str) and len(v) >= 10 and v[:4].isdigit():
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00").replace(" ", "T"))
        except ValueError:
            return None
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    return None


def _num(v: Any) -> float | None:
    """A finite float from a number or a numeric string (Garmin sends some numbers as strings), else None."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def parse_sleep_night(payload: Any, wake_date: date) -> dict | None:
    """The storable shape of one sleep payload, or None when it carries no SpO2 epoch list.

    `{captured_at, sleep_start, sleep_end, samples, intervals, reading_count, gap_count, skipped,
    duplicates}`. `samples` are sorted by time and de-duplicated on the epoch time (the unique key; the
    first of a repeated time is kept and the rest counted in `duplicates`). An element with no
    parseable time cannot be keyed and is counted in `skipped`; an element with a time is always kept,
    whatever its values.
    """
    if not isinstance(payload, dict):
        return None
    epochs = payload.get(SPO2_KEY)
    if not isinstance(epochs, list) or not epochs:
        return None

    by_time: dict[datetime, dict] = {}
    skipped = duplicates = 0
    for e in epochs:
        t = _to_utc(e.get("epochTimestamp")) if isinstance(e, dict) else None
        if t is None:
            skipped += 1
            continue
        if t in by_time:
            duplicates += 1
            continue
        dur = _num(e.get("epochDuration"))
        by_time[t] = {"reading_time": t, "spo2_pct": _num(e.get("spo2Reading")),
                      "reading_confidence": _num(e.get("readingConfidence")),
                      "epoch_duration_s": None if dur is None else int(dur)}
    samples = [by_time[t] for t in sorted(by_time)]
    if not samples:
        return None

    gap_count = 0
    for a, b in zip(samples, samples[1:]):
        epoch_s = a["epoch_duration_s"] or DEFAULT_EPOCH_S
        if (b["reading_time"] - a["reading_time"]).total_seconds() > epoch_s:
            gap_count += 1

    intervals = []
    raw_intervals = payload.get(BREATHING_KEY)
    for seq, iv in enumerate(raw_intervals if isinstance(raw_intervals, list) else []):
        start = _to_utc(iv.get("startGMT")) if isinstance(iv, dict) else None
        if start is None:
            skipped += 1
            continue
        intervals.append({"seq": seq, "start_time": start, "end_time": _to_utc(iv.get("endGMT")),
                          "value": _num(iv.get("value"))})

    dto = payload.get("dailySleepDTO")
    dto = dto if isinstance(dto, dict) else {}
    return {"captured_at": wake_date,
            "sleep_start": _to_utc(dto.get("sleepStartTimestampGMT")),
            "sleep_end": _to_utc(dto.get("sleepEndTimestampGMT")),
            "samples": samples, "intervals": intervals,
            "reading_count": len(samples), "gap_count": gap_count,
            "skipped": skipped, "duplicates": duplicates}


# -- storage -----------------------------------------------------------------------------------------

def _stored_fingerprint(db, night: models.Spo2Night) -> tuple:
    samples = db.query(models.Spo2Sample).filter_by(spo2_night_id=night.id).all()
    ivs = db.query(models.BreathingDisruptionInterval).filter_by(spo2_night_id=night.id).all()
    return (_utc(night.sleep_start), _utc(night.sleep_end), night.reading_count, night.gap_count,
            frozenset((_utc(s.reading_time), s.spo2_pct, s.reading_confidence, s.epoch_duration_s) for s in samples),
            frozenset((i.seq, _utc(i.start_time), _utc(i.end_time), i.value) for i in ivs))


def _parsed_fingerprint(n: dict) -> tuple:
    return (n["sleep_start"], n["sleep_end"], n["reading_count"], n["gap_count"],
            frozenset((s["reading_time"], s["spo2_pct"], s["reading_confidence"], s["epoch_duration_s"])
                      for s in n["samples"]),
            frozenset((i["seq"], i["start_time"], i["end_time"], i["value"]) for i in n["intervals"]))


def store_night(db, user_id: int, night: dict) -> str:
    """Write one parsed night: 'inserted', 'replaced' (the payload differed) or 'unchanged' (no write).

    Commits. A failure rolls the whole night back; the caller decides what to do with the exception."""
    existing = db.query(models.Spo2Night).filter_by(
        user_id=user_id, captured_at=night["captured_at"], source=SOURCE).first()
    if existing is not None and _stored_fingerprint(db, existing) == _parsed_fingerprint(night):
        return "unchanged"

    if existing is None:
        row = models.Spo2Night(user_id=user_id, captured_at=night["captured_at"], source=SOURCE,
                               sleep_start=night["sleep_start"], sleep_end=night["sleep_end"],
                               reading_count=night["reading_count"], gap_count=night["gap_count"])
        db.add(row)
        db.flush()                                    # assign row.id for the children
        status = "inserted"
    else:
        row = existing
        row.sleep_start, row.sleep_end = night["sleep_start"], night["sleep_end"]
        row.reading_count, row.gap_count = night["reading_count"], night["gap_count"]
        db.execute(delete(models.Spo2Sample).where(models.Spo2Sample.spo2_night_id == row.id))
        db.execute(delete(models.BreathingDisruptionInterval)
                   .where(models.BreathingDisruptionInterval.spo2_night_id == row.id))
        status = "replaced"

    db.execute(insert(models.Spo2Sample), [{**s, "spo2_night_id": row.id} for s in night["samples"]])
    if night["intervals"]:
        db.execute(insert(models.BreathingDisruptionInterval),
                   [{**i, "spo2_night_id": row.id} for i in night["intervals"]])
    db.commit()
    return status


# -- reading -----------------------------------------------------------------------------------------

def display_name_path(source) -> str:
    """The sleep endpoint path for the account behind this source (one socialProfile GET).

    The display name rides in the URL path, URL-encoded as the library does; it is never logged."""
    prof = source.social_profile()
    name = prof.get("displayName") if isinstance(prof, dict) else None
    if not isinstance(name, str) or not name:
        raise LookupError("no displayName in the social profile")
    return f"{SLEEP_PATH}/{quote(name, safe='')}"


def fetch_night(source, path: str, wake_date: date) -> dict | None:
    """One GET of the sleep payload for `wake_date`, parsed. None when it carries no SpO2."""
    payload = source.get(path, {"date": wake_date.isoformat(), "nonSleepBufferMinutes": NON_SLEEP_BUFFER_MINUTES})
    return parse_sleep_night(payload, wake_date)


def sync_user(db, user_id: int, *, start: date, end: date, factory: SourceFactory = ProbeSource) -> dict[str, Any]:
    """One user's SpO2 capture over the wake-dates [start, end]. Never refreshes a token, never writes to
    Garmin, never reads HR.

    Oldest night first; the read STOPS at the first failure, so one bad night cannot turn into a burst of
    failing calls. Returns counts: `nights_fetched`, `nights_inserted`, `nights_replaced`,
    `nights_unchanged`, `nights_empty` (the payload had no SpO2), `readings` (epochs now stored for the
    nights written), `skipped_epochs` (elements with no usable time), `duplicate_epochs`,
    `skipped_needs_refresh` (0/1) and `errors`."""
    out = {"nights_fetched": 0, "nights_inserted": 0, "nights_replaced": 0, "nights_unchanged": 0,
           "nights_empty": 0, "readings": 0, "skipped_epochs": 0, "duplicate_epochs": 0,
           "skipped_needs_refresh": 0, "errors": 0}
    row = db.query(models.UserIntegration).filter_by(user_id=user_id, provider="garmin").first()
    if row is None:
        return out
    try:
        source = factory(decrypt(row.api_key_encrypted))
        path = display_name_path(source)
        d = start
        while d <= end:
            night = fetch_night(source, path, d)
            out["nights_fetched"] += 1
            if night is None:
                out["nights_empty"] += 1
            else:
                status = store_night(db, user_id, night)
                out[f"nights_{status}"] += 1
                out["skipped_epochs"] += night["skipped"]
                out["duplicate_epochs"] += night["duplicates"]
                if status != "unchanged":
                    out["readings"] += night["reading_count"]
            d += timedelta(days=1)
    except RefreshWouldBeNeeded:
        db.rollback()
        out["skipped_needs_refresh"] = 1
    except Exception as exc:  # noqa: BLE001 -- the error CLASS is the whole report; a Garmin hiccup never costs the sweep
        db.rollback()
        out["errors"] += 1
        logger.warning("garmin spo2: user %s read stopped: %s", user_id, type(exc).__name__)
    return out
