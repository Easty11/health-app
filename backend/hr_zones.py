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
from typing import Iterable, Optional, Sequence, Union

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


@dataclass(frozen=True)
class HrmaxEntry:
    """One `user_hrmax` row as the resolver sees it. `id` and `restates` carry the restatement link
    (#383): `restates` is the `id` of the entry this one corrects. A plain `(effective_from, bpm)`
    pair is an entry with neither: it can restate nothing and cannot be restated."""
    effective_from: date
    bpm: int
    id: Optional[int] = None
    restates: Optional[int] = None


def entry_from_row(row) -> HrmaxEntry:
    """A `HrmaxEntry` from a `models.UserHrmax` (duck-typed: this module stays free of the ORM)."""
    return HrmaxEntry(row.effective_from, row.hrmax_bpm, row.id, row.restates_id)


def hrmax_in_force(entries: Iterable[Union[HrmaxEntry, tuple[date, int]]], day: date) -> Optional[int]:
    """The HRmax in force on `day`, else None (no value was in force yet: the row is withheld as
    `no_hrmax`, never given a default). `entries` are `HrmaxEntry`s or `(effective_from, bpm)`
    pairs, in any order: the answer never depends on input order.

    Two kinds of change, ranked explicitly (#383):

    * A DATED change applies from its `effective_from` forward only. Among the entries live on `day`,
      the greatest `effective_from` <= `day` wins.
    * A RESTATEMENT (`restates` set) is a correction from better evidence. It stands in for the entry
      it restates over that entry's whole span, so the restated entry is never in force once a
      restatement of it exists, even on the same date. Chains resolve to the latest: an entry that
      any other entry restates is superseded, and what remains is the end of each chain.

    Incoherent input raises ValueError rather than guessing: a restatement of an entry that is not
    in `entries` or that sits on a different date (the database refuses both), or two live entries on
    the winning date where neither restates the other (the old silent first-in-input-order tie)."""
    es = [e if isinstance(e, HrmaxEntry) else HrmaxEntry(*e) for e in entries]
    by_id = {e.id: e for e in es if e.id is not None}
    for e in es:
        if e.restates is None:
            continue
        target = by_id.get(e.restates)
        if target is None:
            raise ValueError(f"HRmax entry {e.id} restates {e.restates}, which is not among the entries")
        if target.effective_from != e.effective_from:
            raise ValueError(f"HRmax entry {e.id} ({e.effective_from}) restates {e.restates} "
                             f"({target.effective_from}): a restatement shares its target's date")
    superseded = {e.restates for e in es if e.restates is not None}
    eligible = [e for e in es if e.effective_from <= day and (e.id is None or e.id not in superseded)]
    if not eligible:
        return None
    top = max(e.effective_from for e in eligible)
    winners = [e for e in eligible if e.effective_from == top]
    if len(winners) > 1:
        raise ValueError(f"ambiguous HRmax on {top}: {len(winners)} entries "
                         f"({', '.join(str(e.bpm) for e in winners)} bpm), none restating another")
    return winners[0].bpm


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
