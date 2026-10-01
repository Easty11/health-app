"""Source-neutral HR zoning — raw samples to zone seconds (Q159 stage 2).

PURE: no DB, no ORM, no knowledge of where a sample came from. The caller selects the
samples (same writer, the user's HRmax in force) and passes them in; this module turns them
into per-band seconds, `hr_avg`, `hr_max` and a coverage figure, or withholds the row with a
named reason. `hc_zone_enrich` (scripts/hc_zone_enrich.py) is the caller for health_connect rows.

Model (operator rulings, G0 1 Oct 2026 — DECISIONS_LOG):

* Bands are %HRmax, lower-inclusive, z5 open-topped: z1 [50,60), z2 [60,70), z3 [70,80),
  z4 [80,90), z5 [90, inf). Percents are INTEGERS compared as `bpm * 100 >= pct * hrmax`, so a
  boundary never depends on float rounding.
* Below band 1 is COVERED time but credited to no band (matches Polar, which reports no zone
  below 50%). A session spent wholly below it writes z1-z5 = 0 with hr_avg/hr_max: "measured,
  none" (INV-7 then emits no TRIMP).
* Interval credit: each sample is credited the gap to the next sample, the last sample the gap
  to `stop`, each capped at `MAX_SAMPLE_GAP_S`; the excess is DROPPED, never credited — unobserved
  time is not invented. Time before the first sample is uncredited.
* Coverage = credited seconds / session seconds. Under `MIN_ZONE_COVERAGE` the row is withheld
  (reason `sparse`) rather than zoned from a fragment.
* hr_avg is time-weighted over credited seconds; hr_max is the highest plausible raw sample in
  the window.
* Plausibility (`PLAUSIBLE_BPM`) is applied here, at zone time, never at storage; drops are
  counted. A sample above the HRmax in force credits z5 and flags `over_ceiling` — HRmax is
  never raised by data.

Reasons are a closed set (`REASONS`): `sparse`, `no_same_writer_hr`, `no_hrmax`, and `none`
(= zoned; nothing withheld it). `no_hrmax` is checked first: it is a user-level precondition,
independent of the samples, so the count of rows it blocks is complete.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional, Sequence

# Lower edge of z1..z5 as an INTEGER percent of HRmax (z5 has no upper edge).
BAND_PCT = (50, 60, 70, 80, 90)
# Longest gap one sample may be credited for (seconds). The invention guard: time with no
# observation is never credited. In-activity HC rows show max gaps of 1-44 s; passive 2-minute
# sampling shows exactly 120 s, which this cap deliberately credits as 60 (coverage ~0.5).
MAX_SAMPLE_GAP_S = 60
# Below this credited/duration fraction the row stays zoneless (reason `sparse`).
MIN_ZONE_COVERAGE = 0.6
# Inclusive bpm bounds a sample must fall in to count; outside is dropped and counted.
PLAUSIBLE_BPM = (30, 240)
# The closed set of per-row outcomes the chain counts.
REASONS = ("sparse", "no_same_writer_hr", "no_hrmax", "none")


@dataclass(frozen=True)
class ZoneResult:
    """Outcome for one session. `zones` is None unless the row is zoned (`reason == 'none'`)."""
    zones: Optional[tuple[int, int, int, int, int]]
    hr_avg: Optional[int]
    hr_max: Optional[int]
    coverage: Optional[float]       # credited / duration; None when it was not computed
    reason: str                     # one of REASONS
    over_ceiling: bool = False      # a plausible sample above the HRmax in force
    dropped_implausible: int = 0
    credited_s: float = 0.0
    n_samples: int = 0              # plausible samples inside [start, stop]


def band_for(bpm: int, hrmax: int, bands: Sequence[int] = BAND_PCT) -> int:
    """0 = below band 1 (covered, uncredited); 1..5 = the band, lower-inclusive, top open."""
    band = 0
    for i, pct in enumerate(bands, start=1):
        if bpm * 100 >= pct * hrmax:
            band = i
    return band


def hrmax_in_force(entries: Iterable[tuple[date, int]], day: date) -> Optional[int]:
    """The HRmax in force on `day`: the entry with the greatest `effective_from` <= `day`, else
    None (no value was in force yet — the row is withheld as `no_hrmax`, never given a default).
    `entries` are `(effective_from, hrmax_bpm)` pairs in any order."""
    best: Optional[tuple[date, int]] = None
    for eff, bpm in entries:
        if eff <= day and (best is None or eff > best[0]):
            best = (eff, bpm)
    return None if best is None else best[1]


def zone_session(
    samples: Iterable[tuple[datetime, int]],
    start: datetime,
    stop: datetime,
    hrmax: Optional[int],
    *,
    bands: Sequence[int] = BAND_PCT,
    max_gap_s: float = MAX_SAMPLE_GAP_S,
    min_coverage: float = MIN_ZONE_COVERAGE,
    plausible: tuple[int, int] = PLAUSIBLE_BPM,
) -> ZoneResult:
    """Zone one session from `(time, bpm)` samples. Times must be timezone-aware (UTC).

    Samples outside [start, stop] are ignored; the caller has already restricted them to one
    writer. `stop <= start` has no duration to cover and raises ValueError — the caller skips
    such rows rather than classify them."""
    duration = (stop - start).total_seconds()
    if duration <= 0:
        raise ValueError("session has no positive duration")

    if hrmax is None:
        return ZoneResult(None, None, None, None, "no_hrmax")

    lo, hi = plausible
    in_window = sorted((t, b) for t, b in samples if start <= t <= stop)
    kept = [(t, b) for t, b in in_window if lo <= b <= hi]
    dropped = len(in_window) - len(kept)
    if not kept:
        return ZoneResult(None, None, None, None, "no_same_writer_hr",
                          dropped_implausible=dropped)

    seconds = [0.0] * 6                         # index 0: below band 1, 1..5: bands
    credited = 0.0
    weighted_bpm = 0.0
    for i, (t, b) in enumerate(kept):
        nxt = kept[i + 1][0] if i + 1 < len(kept) else stop
        credit = min(max((nxt - t).total_seconds(), 0.0), max_gap_s)
        seconds[band_for(b, hrmax, bands)] += credit
        credited += credit
        weighted_bpm += b * credit

    coverage = credited / duration
    top = max(b for _, b in kept)
    over = top > hrmax
    if coverage < min_coverage or credited <= 0:
        return ZoneResult(None, None, None, coverage, "sparse", over_ceiling=over,
                          dropped_implausible=dropped, credited_s=credited, n_samples=len(kept))

    return ZoneResult(
        zones=tuple(int(round(s)) for s in seconds[1:]),    # type: ignore[arg-type]
        hr_avg=int(round(weighted_bpm / credited)),
        hr_max=top,
        coverage=coverage,
        reason="none",
        over_ceiling=over,
        dropped_implausible=dropped,
        credited_s=credited,
        n_samples=len(kept),
    )
