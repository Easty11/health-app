"""Sleep-nadir resting HR: the derived resting rate DECISIONS_LOG.md:480 calls primary.

`health_connect_syncs.resting_heart_rate` is the median of ALL the day's HR samples, activity
included, so a day dominated by a workout reads ~120 bpm "resting" (7 Oct 2026: 118, from a
BikeErg session). The nadir below is the resting rate that decision names: the lowest sustained
window inside the night's main sleep period, read from `hr_samples` (deduped, cumulative, and the
store zoning already uses) and measured on a time grid so sample density cannot weight it.

The method (every number is a named constant; `FORMULA` names the set in force):

  1. Period: `[sleep_onset ?? sleep_start, sleep_end]` of the row (#328), the main sleep period.
  2. Samples: `hr_samples` inside the period, one writer only (the package whose samples cover the
     most grid minutes; an exact tie goes to the lexically first package, as #328 does for the
     sleep edges). A ring's HR is never blended with a watch's. Samples outside
     `hr_zones.PLAUSIBLE_BPM` are dropped.
  3. Grid: one value per minute (the mean of that minute's samples). A minute with no sample
     carries the last observed value forward for at most `NADIR_CARRY_MAX_MIN` minutes, then is
     missing.
  4. Statistic: the minimum, over every `NADIR_WINDOW_MIN`-minute sliding window with at least
     `NADIR_MIN_PRESENT_FRAC` of its minutes present, of the mean of the window's present minutes.
  5. Floor: the writer's grid must cover at least `NADIR_MIN_COVERAGE_MIN` minutes AND at least
     `NADIR_MIN_COVERAGE_FRAC` of the period, else NULL with a reason.

NULL is a decided value, never a guess: `reason` is one of `REASONS` and is rendered as "not
available (...)". `compute_for_row` writes all six `hr_nadir_*` columns on every run, including
NULLs; the sync upsert (`_aggregate_day`) only ever writes non-null values, which is why the nadir
does not ride it. Recomputing from `hr_samples` is idempotent and reflows late HR.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional

from sqlalchemy.orm.attributes import flag_modified

import models
from hr_zones import PLAUSIBLE_BPM

FORMULA = "nadir-v1"

NADIR_WINDOW_MIN = 30            # window length; matches the device RHR definition (lowest 30-min average)
NADIR_MIN_PRESENT_FRAC = 0.8     # a window needs >= 80% of its minutes present (24 of 30)
NADIR_CARRY_MAX_MIN = 5          # carry the last observed minute forward at most this many minutes
NADIR_MIN_COVERAGE_MIN = 180     # the grid must cover >= 3 h of the period ...
NADIR_MIN_COVERAGE_FRAC = 0.5    # ... AND >= 50% of it
NADIR_SWEEP_DAYS = 14            # the nightly sweep recomputes the trailing 14 days

REASONS = ("no_sleep_period", "no_samples", "insufficient_coverage", "no_valid_window")

# How each reason reads where a NULL nadir is shown (chat prompt). Plain words, no codes.
REASON_TEXT = {
    "no_sleep_period": "no sleep period recorded",
    "no_samples": "no overnight HR samples",
    "insufficient_coverage": "insufficient overnight HR coverage",
    "no_valid_window": "no sufficiently complete 30-minute window",
}


@dataclass(frozen=True)
class NadirResult:
    bpm: Optional[float] = None
    window_start: Optional[datetime] = None
    coverage: Optional[float] = None        # fraction of the period's minutes on the writer's grid
    package: Optional[str] = None
    reason: Optional[str] = None            # None iff a nadir was computed


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Aware-UTC view of a stored instant. SQLite hands timestamps back naive; Postgres hands them
    back aware (FEEDBACK §49), so the grid maths needs one shape."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _minute_means(samples: Iterable[tuple[datetime, int]], t0: datetime, n: int) -> dict[int, float]:
    """Minute index -> mean bpm over the plausible samples that fall in `[t0, t0 + n min)`."""
    lo, hi = PLAUSIBLE_BPM
    t0s = t0.timestamp()
    sums: dict[int, float] = defaultdict(float)
    counts: dict[int, int] = defaultdict(int)
    for t, bpm in samples:
        if not (lo <= bpm <= hi):
            continue
        idx = int((t.timestamp() - t0s) // 60)
        if 0 <= idx < n:
            sums[idx] += bpm
            counts[idx] += 1
    return {i: sums[i] / counts[i] for i in sums}


def _fill(observed: Mapping[int, float], n: int) -> list[Optional[float]]:
    """The grid: an observed minute keeps its mean; an unobserved one carries the last observed
    value for at most NADIR_CARRY_MAX_MIN minutes, then stays missing (None)."""
    out: list[Optional[float]] = [None] * n
    last_i: Optional[int] = None
    last_v = 0.0
    for m in range(n):
        if m in observed:
            out[m] = observed[m]
            last_i, last_v = m, observed[m]
        elif last_i is not None and m - last_i <= NADIR_CARRY_MAX_MIN:
            out[m] = last_v
    return out


def nadir_from_samples(
    samples_by_package: Mapping[str, Iterable[tuple[datetime, int]]],
    start: datetime,
    end: datetime,
) -> NadirResult:
    """Pure core: the sleep nadir for `[start, end)` from each writer's `(time, bpm)` samples.

    Times must be aware (any zone). Returns a NadirResult; `reason` is set (and `bpm` None) when
    the nadir is withheld, and `coverage`/`package` still say what the best writer covered."""
    start, end = _utc(start), _utc(end)
    if start is None or end is None or end <= start:
        return NadirResult(reason="no_sleep_period")
    t0 = start.replace(second=0, microsecond=0)
    n = math.ceil((end - t0).total_seconds() / 60.0)

    best_pkg: Optional[str] = None
    best_grid: list[Optional[float]] = []
    best_cov = 0
    for pkg in sorted(samples_by_package):           # sorted: an exact coverage tie keeps the lexically first
        observed = _minute_means(samples_by_package[pkg], t0, n)
        if not observed:
            continue
        grid = _fill(observed, n)
        cov = sum(v is not None for v in grid)
        if cov > best_cov:
            best_pkg, best_grid, best_cov = pkg, grid, cov
    if best_pkg is None:
        return NadirResult(reason="no_samples")

    coverage = best_cov / n
    if best_cov < NADIR_MIN_COVERAGE_MIN or coverage < NADIR_MIN_COVERAGE_FRAC:
        return NadirResult(coverage=round(coverage, 3), package=best_pkg, reason="insufficient_coverage")

    w = NADIR_WINDOW_MIN
    need = math.ceil(round(w * NADIR_MIN_PRESENT_FRAC, 9))
    pre_cnt = [0]
    pre_sum = [0.0]
    for v in best_grid:
        pre_cnt.append(pre_cnt[-1] + (v is not None))
        pre_sum.append(pre_sum[-1] + (v if v is not None else 0.0))
    best: Optional[tuple[float, int]] = None
    for i in range(0, n - w + 1):
        present = pre_cnt[i + w] - pre_cnt[i]
        if present < need:
            continue
        mean = (pre_sum[i + w] - pre_sum[i]) / present
        if best is None or mean < best[0]:            # strict: the earliest window wins a tie
            best = (mean, i)
    if best is None:
        return NadirResult(coverage=round(coverage, 3), package=best_pkg, reason="no_valid_window")
    return NadirResult(
        bpm=round(best[0], 1),
        window_start=t0 + timedelta(minutes=best[1]),
        coverage=round(coverage, 3),
        package=best_pkg,
    )


def sleep_period(row: Any) -> Optional[tuple[datetime, datetime]]:
    """The row's main sleep period: first real asleep stage (else the earliest edge) to the last
    edge. None when the row carries no usable clocks."""
    start = _utc(getattr(row, "sleep_onset", None) or getattr(row, "sleep_start", None))
    end = _utc(getattr(row, "sleep_end", None))
    if start is None or end is None or end <= start:
        return None
    return start, end


def _samples_by_package(db: Any, user_id: int, start: datetime, end: datetime) -> dict[str, list[tuple[datetime, int]]]:
    q = (db.query(models.HrSample.sample_time, models.HrSample.bpm, models.HrSample.source_package)
         .filter(models.HrSample.user_id == user_id,
                 models.HrSample.source == "health_connect",
                 models.HrSample.sample_time >= start,
                 models.HrSample.sample_time < end))
    out: dict[str, list[tuple[datetime, int]]] = defaultdict(list)
    for t, bpm, pkg in q.all():
        out[pkg].append((_utc(t), bpm))
    return out


def _write(row: Any, r: NadirResult) -> bool:
    """Set all six columns (NULLs included). True when any stored value moved."""
    new = (r.bpm, r.window_start, r.coverage, r.package, r.reason, FORMULA)
    old = (row.hr_nadir_bpm, row.hr_nadir_window_start, row.hr_nadir_coverage,
           row.hr_nadir_source_package, row.hr_nadir_reason, row.hr_nadir_formula)
    if old == new:
        return False
    (row.hr_nadir_bpm, row.hr_nadir_window_start, row.hr_nadir_coverage,
     row.hr_nadir_source_package, row.hr_nadir_reason, row.hr_nadir_formula) = new
    # `synced_at` means "when the phone last synced" (week_plan's freshness read,
    # /health-connect/status) and carries `onupdate=now()`, which any UPDATE of this row would
    # fire. Pin it to its current value so a recompute -- above all the nightly sweep -- never
    # fakes a sync. (Reading it first loads it; flag_modified then puts it in the SET clause.)
    _ = row.synced_at
    flag_modified(row, "synced_at")
    return True


def compute_for_row(db: Any, user_id: int, row: Any) -> tuple[NadirResult, bool]:
    """Recompute and store one row's nadir. Returns (result, changed)."""
    period = sleep_period(row)
    if period is None:
        result = NadirResult(reason="no_sleep_period")
    else:
        result = nadir_from_samples(_samples_by_package(db, user_id, *period), *period)
    return result, _write(row, result)


def _summary() -> dict[str, Any]:
    return {"rows": 0, "computed": 0, "null": 0, "changed": 0, "reasons": {r: 0 for r in REASONS}}


def compute_for_rows(db: Any, user_id: int, rows: Iterable[Any]) -> dict[str, Any]:
    """Recompute `rows`; no commit (the sync commits once). The chain-report dict."""
    out = _summary()
    for row in rows:
        result, changed = compute_for_row(db, user_id, row)
        out["rows"] += 1
        out["changed"] += int(changed)
        if result.reason is None:
            out["computed"] += 1
        else:
            out["null"] += 1
            out["reasons"][result.reason] += 1
    return out


def compute_for_dates(db: Any, user_id: int, dates: Iterable[date]) -> dict[str, Any]:
    """Recompute the user's rows dated in `dates` (the sync's touched dates). No commit."""
    wanted = sorted(set(dates))
    if not wanted:
        return _summary()
    rows = (db.query(models.HealthConnectSync)
            .filter(models.HealthConnectSync.user_id == user_id,
                    models.HealthConnectSync.date.in_(wanted))
            .order_by(models.HealthConnectSync.date)
            .all())
    return compute_for_rows(db, user_id, rows)


def compute_user(db: Any, user_id: int, *, days: int = NADIR_SWEEP_DAYS, today: Optional[date] = None) -> dict[str, Any]:
    """The nightly sweep: recompute the trailing `days` of the user's rows; commit once."""
    from load_metrics import _local_day          # lazy: keeps this module import-light for context_builder
    today = today or _local_day()
    rows = (db.query(models.HealthConnectSync)
            .filter(models.HealthConnectSync.user_id == user_id,
                    models.HealthConnectSync.date >= today - timedelta(days=days))
            .order_by(models.HealthConnectSync.date)
            .all())
    out = compute_for_rows(db, user_id, rows)
    db.commit()
    return out
