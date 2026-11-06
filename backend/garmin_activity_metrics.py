"""Garmin per-activity summary metrics and the activity HR stream (Personal API).

Two writes, both soft-fail, both reading Garmin only through the caller's `source.get(path, params)`
(the lane's `PersonalClient`, which only ever sends GETs):

1. SUMMARY METRICS -> `garmin_activity_metrics`. `upsert_metrics` takes the activity DETAIL payload the
   self-evaluation lane (`garmin_selfeval`) already fetched, so the summary costs no extra request. The
   keys are the operator's 6 Nov 2026 `--keys` probe (activity 24970929418): `trainingEffect` is the
   AEROBIC Training Effect (there is no `aerobicTrainingEffect` key). Every metric is stored as received;
   a missing or non-numeric key is NULL, never an error. The `summaryDTO` is kept in `summary_raw` minus its
   location keys (`scrub_location`).
   DISPLAY ONLY: nothing here feeds Pocket load or readiness (a guard test pins it).

2. THE ACTIVITY HR STREAM -> `hr_samples` as `garmin` / `activity_details` (ruling R2): a writer of its
   own, distinct from the `garmin` / `personal_api` all-day wellness lane, which zoning never reads for a
   session. One details call (`/activity-service/activity/{id}/details`) per activity whose stream has not
   been captured (`hr_stream_fetched_at` NULL). Column positions are resolved from `metricDescriptors` by
   key, never hard-coded: `directTimestamp` (epoch ms, UTC) -> `sample_time`, `directHeartRate` -> `bpm`
   (rounded to an integer, otherwise as received; plausibility stays at zone time). A null bpm is skipped.
   Insert-or-ignore on `uq_hr_sample`, so a re-fetch inserts nothing.

RESOLUTION. Garmin's details endpoint thins the stream to `maxChartSize` rows (the `garminconnect`
library's default is 2000). The probe called it with no parameter, so whether it thinned was not
observable there. This module asks for `STREAM_MAX_CHART` rows and no polyline, and reports thinning on
every fetch rather than assuming: `totalMetricsCount` greater than the rows returned counts as `thinned`,
and the effective interval (the median gap between samples) is logged and reported. If the Personal API
host refuses the parameters (HTTP 400), the call is retried once without them (`param_fallback`) and the
thinning report says what that cost.
"""
from __future__ import annotations

import logging
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

import models
from connectors import garmin_personal as gp

logger = logging.getLogger(__name__)

SOURCE = "garmin"
STREAM_PACKAGE = "activity_details"
GARMIN_ACTIVITY_WRITER = (SOURCE, STREAM_PACKAGE)        # the `(source, source_package)` of the stream
WELLNESS_WRITER = (SOURCE, "personal_api")               # the all-day lane: never read for a session

DETAILS_SUFFIX = "/details"
STREAM_MAX_CHART = 100_000                               # rows asked for; 27 h at one sample a second
STREAM_PARAMS = {"maxChartSize": str(STREAM_MAX_CHART), "maxPolylineSize": "0"}
STREAMS_PER_RUN = 10                                     # nightly bound; the backfill walks history
TS_KEY = "directTimestamp"
HR_KEY = "directHeartRate"
SAMPLE_CHUNK = 500

# summaryDTO key -> column. Numbers are stored as received (as float); a non-number is NULL.
NUMERIC_FIELDS: dict[str, str] = {
    "calories": "calories",
    "bmrCalories": "bmr_calories",
    "trainingEffect": "te_aerobic",
    "anaerobicTrainingEffect": "te_anaerobic",
    "activityTrainingLoad": "training_load",
    "avgRespirationRate": "resp_avg",
    "maxRespirationRate": "resp_max",
    "minRespirationRate": "resp_min",
    "recoveryHeartRate": "recovery_hr",
    "moderateIntensityMinutes": "intensity_min_moderate",
    "vigorousIntensityMinutes": "intensity_min_vigorous",
    "waterEstimated": "water_estimated_ml",
    "differenceBodyBattery": "body_battery_delta",
    "duration": "duration_s",
}
TEXT_FIELDS: dict[str, str] = {"trainingEffectLabel": "te_label"}
_TEXT_MAX = 64

# Location keys are never stored (6 Nov 2026: `summary_raw` carried `startLatitude` / `startLongitude` /
# `endLatitude` / `endLongitude`, which for a session at home are the home's coordinates, and nothing reads
# them). Any key ending in Latitude or Longitude, at any depth, is dropped before the payload is kept.
LOCATION_KEY = re.compile(r"(latitude|longitude)$", re.IGNORECASE)


def scrub_location(obj: Any) -> Any:
    """`obj` with every key matching `LOCATION_KEY` removed, at any depth (a new structure; `obj` untouched)."""
    if isinstance(obj, dict):
        return {k: scrub_location(v) for k, v in obj.items() if not LOCATION_KEY.search(str(k))}
    if isinstance(obj, list):
        return [scrub_location(v) for v in obj]
    return obj


def location_keys(obj: Any) -> int:
    """How many location keys `obj` holds, at any depth (the scrub script's count)."""
    if isinstance(obj, dict):
        return sum(1 + location_keys(v) if LOCATION_KEY.search(str(k)) else location_keys(v) for k, v in obj.items())
    if isinstance(obj, list):
        return sum(location_keys(v) for v in obj)
    return 0


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:      # bool, non-number, NaN
        return None
    return float(v)


def _parse_gmt(s: Any) -> Optional[datetime]:
    """`startTimeGMT` ('2026-11-05 21:30:00' or '2026-11-05T21:30:00.0'; no offset: it IS GMT) as aware UTC."""
    if not isinstance(s, str) or not s:
        return None
    try:
        return _utc(datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T")))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 1. Summary metrics
# ---------------------------------------------------------------------------

def parse_metrics(summary: Any, *, start: Optional[datetime] = None,
                  duration_s: Optional[float] = None) -> Optional[dict[str, Any]]:
    """The column values from one `summaryDTO`, or None when it is not an object. `start` and `duration_s`
    (from the activity list) fill the window only when the summary lacks them."""
    if not isinstance(summary, dict):
        return None
    out: dict[str, Any] = {col: _num(summary.get(key)) for key, col in NUMERIC_FIELDS.items()}
    for key, col in TEXT_FIELDS.items():
        v = summary.get(key)
        out[col] = str(v)[:_TEXT_MAX] if isinstance(v, (str, int, float)) and not isinstance(v, bool) else None
    out["start_time_gmt"] = _parse_gmt(summary.get("startTimeGMT")) or _utc(start)
    if out["duration_s"] is None and duration_s is not None:
        out["duration_s"] = _num(duration_s)
    out["summary_raw"] = scrub_location(summary)
    return out


def upsert_metrics(db: Session, user_id: int, activity_id: int, detail: Any, *, now: datetime,
                   start: Optional[datetime] = None, duration_s: Optional[float] = None) -> bool:
    """Insert or update the activity's metrics row from a DETAIL payload. Does not commit. Returns False
    (and writes nothing) when the payload has no `summaryDTO` object. The stream columns are untouched."""
    values = parse_metrics(detail.get("summaryDTO") if isinstance(detail, dict) else None,
                           start=start, duration_s=duration_s)
    if values is None:
        return False
    row = (db.query(models.GarminActivityMetric)
           .filter_by(user_id=user_id, garmin_activity_id=int(activity_id)).first())
    if row is None:
        row = models.GarminActivityMetric(user_id=user_id, garmin_activity_id=int(activity_id))
        db.add(row)
    for col, v in values.items():
        setattr(row, col, v)
    row.fetched_at = now
    return True


# ---------------------------------------------------------------------------
# 2. The activity HR stream
# ---------------------------------------------------------------------------

@dataclass
class StreamParse:
    samples: list[tuple[datetime, int]] = field(default_factory=list)
    rows: int = 0                               # rows returned (`activityDetailMetrics`)
    total_rows: Optional[int] = None            # rows Garmin holds (`totalMetricsCount`), when sent
    null_bpm: int = 0
    interval_s: Optional[float] = None          # median gap between consecutive timestamps
    has_hr: bool = False                        # the descriptors name both the timestamp and HR
    absent: bool = False                        # Garmin has no details at all (404 or an empty body)
    details_available: Optional[bool] = None    # the payload's own `detailsAvailable`, when sent

    @property
    def thinned(self) -> bool:
        return self.total_rows is not None and self.total_rows > self.rows

    @property
    def conclusive(self) -> bool:
        """Whether this result may close the activity's stream for good. True when samples were found,
        when Garmin has no details (`absent`, `detailsAvailable` false, or no rows and a total of 0), or
        when rows came back but carry no HR column (an activity recorded without HR). Anything else (an
        HR column with no usable sample, or no rows while Garmin reports rows exist) is unexplained, so it
        is left for the next run rather than recorded as "no HR" (6 Nov 2026: the first dry run read 0
        samples from 5 activities with no explanation in its counts)."""
        if self.samples or self.absent or self.details_available is False:
            return True
        if self.rows == 0:
            return self.total_rows == 0
        return not self.has_hr

    @property
    def empty_reason(self) -> Optional[str]:
        """Why no samples came back: None when some did, else a short code the counts carry."""
        if self.samples:
            return None
        if self.absent:
            return "absent"
        if self.details_available is False:
            return "details_unavailable"
        if self.rows == 0:
            return "no_rows_total_0" if self.total_rows == 0 else "no_rows"
        return "no_hr_column" if not self.has_hr else "hr_column_no_samples"


def _index_of(descriptors: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in descriptors if isinstance(descriptors, list) else []:
        if not isinstance(d, dict):
            continue
        key, idx = d.get("key"), d.get("metricsIndex")
        if isinstance(key, str) and isinstance(idx, int) and not isinstance(idx, bool) and idx >= 0:
            out[key] = idx
    return out


def _cell(metrics: Any, idx: int) -> Any:
    return metrics[idx] if isinstance(metrics, list) and idx < len(metrics) else None


def parse_hr_stream(details: Any) -> StreamParse:
    """`(sample_time UTC, bpm)` pairs from one details payload. Indices come from `metricDescriptors` by
    key; a payload with no timestamp or no HR descriptor yields no samples (an activity without HR), and
    a row whose timestamp or bpm is null or unusable is skipped. Raises ValueError for a payload that is
    not an object (a shape change: never recorded as "no HR")."""
    if not isinstance(details, dict):
        raise ValueError("details payload is not an object")
    rows = details.get("activityDetailMetrics")
    rows = rows if isinstance(rows, list) else []
    total = details.get("totalMetricsCount")
    out = StreamParse(rows=len(rows), total_rows=total if isinstance(total, int) and not isinstance(total, bool) else None)
    avail = details.get("detailsAvailable")
    out.details_available = avail if isinstance(avail, bool) else None
    idx = _index_of(details.get("metricDescriptors"))
    if TS_KEY not in idx or HR_KEY not in idx:
        return out
    out.has_hr = True
    stamps: list[datetime] = []
    for r in rows:
        metrics = r.get("metrics") if isinstance(r, dict) else None
        ts = _num(_cell(metrics, idx[TS_KEY]))
        if ts is None:
            continue
        try:
            t = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            continue
        stamps.append(t)
        bpm = _num(_cell(metrics, idx[HR_KEY]))
        if bpm is None:
            out.null_bpm += 1
            continue
        out.samples.append((t, int(round(bpm))))
    stamps.sort()
    gaps = [(b - a).total_seconds() for a, b in zip(stamps, stamps[1:]) if b > a]
    out.interval_s = statistics.median(gaps) if gaps else None
    return out


def _dialect_insert(db: Session):
    from sqlalchemy.dialects import postgresql, sqlite
    return postgresql.insert if db.get_bind().dialect.name == "postgresql" else sqlite.insert


def store_stream_samples(db: Session, user_id: int, samples: list[tuple[datetime, int]]) -> int:
    """Insert-or-ignore the stream into `hr_samples` under `garmin` / `activity_details` (R2 only); returns
    rows inserted. Does not commit."""
    if not samples:
        return 0
    insert = _dialect_insert(db)
    table = models.HrSample.__table__
    values = [{"user_id": user_id, "sample_time": t, "bpm": b, "source": SOURCE, "source_package": STREAM_PACKAGE}
              for t, b in samples]
    stored = 0
    for i in range(0, len(values), SAMPLE_CHUNK):
        stmt = (insert(table).values(values[i:i + SAMPLE_CHUNK])
                .on_conflict_do_nothing(index_elements=["user_id", "sample_time", "source", "source_package"]))
        stored += max(db.execute(stmt).rowcount, 0)
    return stored


def read_stream(source: Any, activity_id: int) -> tuple[Optional[StreamParse], bool]:
    """ONE details GET (two only when the host refuses the resolution parameters). Returns `(parse,
    param_fallback)`; parse is an empty `StreamParse` when Garmin has no details (404 or an empty body)."""
    path = f"{gp.ACTIVITY_PATH}/{int(activity_id)}{DETAILS_SUFFIX}"
    fallback = False
    try:
        details = source.get(path, dict(STREAM_PARAMS))
    except gp.PersonalNotFound:
        return StreamParse(absent=True), False
    except gp.PersonalTransientError as exc:
        if str(exc) != "HTTP 400":
            raise
        fallback = True
        try:
            details = source.get(path)
        except gp.PersonalNotFound:
            return StreamParse(absent=True), True
    if details is None:
        return StreamParse(absent=True), fallback
    return parse_hr_stream(details), fallback


def details_shape(details: Any) -> dict[str, Any]:
    """The SHAPE of one details payload, no reading in it: counts, booleans, the descriptor indices of the
    timestamp and HR columns, and the TYPE NAMES of the first row's cells at those indices. For the
    backfill's `--diagnose`, which settles why a stream parsed to nothing."""
    if not isinstance(details, dict):
        return {"payload": type(details).__name__}
    rows = details.get("activityDetailMetrics")
    rows = rows if isinstance(rows, list) else None
    desc = details.get("metricDescriptors")
    raw_idx = {d.get("key"): d.get("metricsIndex") for d in desc if isinstance(d, dict)} if isinstance(desc, list) else {}
    first = next((r.get("metrics") for r in rows or [] if isinstance(r, dict) and r.get("metrics")), None)

    def cell_type(key):
        i = raw_idx.get(key)
        if not isinstance(i, int) or isinstance(i, bool) or not isinstance(first, list) or i >= len(first):
            return None
        return type(first[i]).__name__

    parsed = parse_hr_stream(details)
    return {
        "rows": None if rows is None else len(rows),
        "rows_type": type(details.get("activityDetailMetrics")).__name__,
        "metricsCount": details.get("metricsCount") if isinstance(details.get("metricsCount"), int) else None,
        "totalMetricsCount": parsed.total_rows,
        "measurementCount": details.get("measurementCount") if isinstance(details.get("measurementCount"), int) else None,
        "detailsAvailable": parsed.details_available,
        "descriptors": len(desc) if isinstance(desc, list) else None,
        "ts_index": raw_idx.get(TS_KEY) if isinstance(raw_idx.get(TS_KEY), int) else type(raw_idx.get(TS_KEY)).__name__,
        "hr_index": raw_idx.get(HR_KEY) if isinstance(raw_idx.get(HR_KEY), int) else type(raw_idx.get(HR_KEY)).__name__,
        "first_row_len": len(first) if isinstance(first, list) else None,
        "ts_cell": cell_type(TS_KEY), "hr_cell": cell_type(HR_KEY),
        "samples": len(parsed.samples), "null_bpm": parsed.null_bpm, "empty_reason": parsed.empty_reason,
    }


def capture_stream(db: Session, user_id: int, source: Any, row: models.GarminActivityMetric, *,
                   now: datetime) -> dict[str, Any]:
    """Fetch, store and mark one activity's stream. Does not commit. Raises on a fetch failure (the row
    stays unmarked, so the next run retries it)."""
    parsed, fallback = read_stream(source, row.garmin_activity_id)
    stored = store_stream_samples(db, user_id, parsed.samples)
    if parsed.conclusive:                       # an unexplained empty stays unmarked, so the next run retries it
        row.hr_stream_fetched_at = now
        row.hr_stream_samples = len(parsed.samples)
    if parsed.thinned:
        logger.warning("garmin stream: activity %s thinned: %s of %s rows, effective interval %s s",
                       row.garmin_activity_id, parsed.rows, parsed.total_rows, parsed.interval_s)
    return {"found": len(parsed.samples), "stored": stored, "thinned": parsed.thinned,
            "param_fallback": fallback, "interval_s": parsed.interval_s, "has_hr": parsed.has_hr,
            "marked": parsed.conclusive, "empty_reason": parsed.empty_reason, "null_bpm": parsed.null_bpm}


def new_stream_counts() -> dict[str, int]:
    return {"stream_fetched": 0, "stream_samples": 0, "stream_thinned": 0, "stream_param_fallback": 0,
            "stream_unmarked": 0, "stream_errors": 0}


def sync_streams(db: Session, user_id: int, source: Any, *, now: Optional[datetime] = None,
                 limit: int = STREAMS_PER_RUN) -> dict[str, int]:
    """Capture up to `limit` uncaptured streams, newest activity first; commit per activity; STOP at the
    first failure (soft-fail: counted, logged by class, never raised)."""
    now = _utc(now) or datetime.now(timezone.utc)
    out = new_stream_counts()
    rows = (db.query(models.GarminActivityMetric)
            .filter(models.GarminActivityMetric.user_id == user_id,
                    models.GarminActivityMetric.hr_stream_fetched_at.is_(None))
            .order_by(models.GarminActivityMetric.start_time_gmt.desc().nulls_last(),
                      models.GarminActivityMetric.id.desc())
            .limit(limit).all())
    for row in rows:
        try:
            res = capture_stream(db, user_id, source, row, now=now)
            db.commit()
        except Exception as exc:  # noqa: BLE001 -- the error CLASS is the whole report; never costs the sweep
            db.rollback()
            out["stream_errors"] += 1
            logger.warning("garmin stream: user %s activity %s stopped: %s", user_id, row.garmin_activity_id,
                           type(exc).__name__)
            break
        out["stream_fetched"] += 1
        out["stream_samples"] += res["stored"]
        out["stream_thinned"] += int(res["thinned"])
        out["stream_param_fallback"] += int(res["param_fallback"])
        out["stream_unmarked"] += int(not res["marked"])
    return out
