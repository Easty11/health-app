"""Source-neutral HR zoning — raw samples to zone seconds (Q159 stage 2; per-class model, design 0010).

PURE: no DB, no ORM, no knowledge of where a sample came from. The caller selects the
samples (same writer, the anchors in force) and passes them in; this module turns them
into per-band seconds, `hr_avg`, `hr_max` and a coverage figure, or withholds the row with a
named reason. `hc_zone_enrich` is the caller for `aerobic_sessions` rows.

Model (operator rulings, G0 1 Oct 2026 and the zone-model ruling of 5 Nov 2026 — DECISIONS_LOG,
design doc `docs/design/0010-threshold-anchored-hr-zones.md`):

* Two bases, chosen per sport class (`sport_classes.zone_basis_for`):
    - `lthr` (the cycling class): % of the lactate-threshold HR, Friel. z1 < 81 | z2 81-89 |
      z3 90-93 | z4 94-99 | z5 100+. z1 has no floor.
    - `hrr`  (every other sport): % of heart-rate reserve (HRmax - RHR), Karvonen. z1 50-59 |
      z2 60-69 | z3 70-79 | z4 80-89 | z5 90+. Below 50 % HRR is COVERED time credited to no
      band (as the retired %HRmax model did below 50 % HRmax; Polar reports no zone there).
  Percents are INTEGERS compared in integer arithmetic (`bpm * 100 >= pct * lthr`;
  `(bpm - rhr) * 100 >= pct * (hrmax - rhr)`), so a boundary never depends on float rounding.
  The resolver precomputes each band's lower edge in bpm (`ZoneSpec.edges_bpm`), which is the
  same comparison and is what every surface shows.
* Anchors are dated, append-only entries (`user_hrmax` for HRmax; `user_hr_anchors` for LTHR and
  RHR), resolved per session date by `anchor_in_force` (dated change vs restatement, #383). A
  missing anchor withholds the row (`no_anchor`) — never a default.
* Interval credit: each sample is credited the gap to the next sample, the last sample the gap
  to `stop`, each capped at `MAX_SAMPLE_GAP_S`; the excess is DROPPED, never credited — unobserved
  time is not invented. Time before the first sample is uncredited.
* Coverage = credited seconds / session seconds. Under `MIN_ZONE_COVERAGE` the row is withheld
  (reason `sparse`) rather than zoned from a fragment.
* hr_avg is time-weighted over credited seconds; hr_max is the highest plausible raw sample in
  the window.
* Plausibility (`PLAUSIBLE_BPM`) is applied here, at zone time, never at storage; drops are
  counted. A sample above the HRmax in force credits the top band it reaches and flags
  `over_ceiling` — HRmax is never raised by data. The ceiling is HRmax under either basis.

Reasons are a closed set (`REASONS`): `sparse`, `no_same_writer_hr`, `no_anchor`, and `none`
(= zoned; nothing withheld it). `no_anchor` is checked first: it is a user-level precondition,
independent of the samples, so the count of rows it blocks is complete.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Optional, Sequence, Union

# Lower edge of z1..z5 as an INTEGER percent of the basis anchor (z5 has no upper edge).
BASIS_LTHR = "lthr"
BASIS_HRR = "hrr"
BASES = (BASIS_LTHR, BASIS_HRR)
LTHR_BAND_PCT = (0, 81, 90, 94, 100)     # Friel: z1 is everything below 81 % (no floor)
HRR_BAND_PCT = (50, 60, 70, 80, 90)      # Karvonen: below 50 % of reserve is covered, uncredited
BAND_PCT_BY_BASIS = {BASIS_LTHR: LTHR_BAND_PCT, BASIS_HRR: HRR_BAND_PCT}
# The retired single-basis table (% of HRmax, G0 1 Oct 2026). Kept ONLY for the operator reports
# that project the old model (`scripts/trimp_weighting_projection.py`); nothing zones on it.
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
REASONS = ("sparse", "no_same_writer_hr", "no_anchor", "none")
# The anchors, by kind. `hrmax` lives in `user_hrmax`; the other two in `user_hr_anchors`.
ANCHOR_KINDS = ("hrmax", "lthr", "rhr")
ANCHORS_NEEDED = {BASIS_LTHR: ("lthr",), BASIS_HRR: ("hrmax", "rhr")}


def _ceil_div(num: int, den: int) -> int:
    return -(-num // den)


@dataclass(frozen=True)
class ZoneSpec:
    """The zone definition in force for ONE session: the basis, its anchors, and the five band
    lower edges in bpm (lower-inclusive; z5 open-topped). `hrmax` is the ceiling for `over_ceiling`
    (None when no HRmax is in force under the `lthr` basis — then nothing is over)."""
    basis: str
    edges_bpm: tuple[int, int, int, int, int]
    anchors: dict                      # {"lthr": 158} or {"hrmax": 179, "rhr": 51}
    hrmax: Optional[int]

    @property
    def pct(self) -> tuple[int, ...]:
        return BAND_PCT_BY_BASIS[self.basis]


def zone_spec(basis: str, *, lthr: Optional[int] = None, hrmax: Optional[int] = None,
              rhr: Optional[int] = None) -> ZoneSpec:
    """Build the `ZoneSpec` for a basis from its anchors; raises ValueError when one is missing
    or incoherent (RHR not below HRmax). Edges: `lthr` → ceil(pct × LTHR / 100);
    `hrr` → RHR + ceil(pct × (HRmax − RHR) / 100). Both equal the integer comparison in the
    module docstring, so `band_for` can compare bpm against the edge directly."""
    if basis == BASIS_LTHR:
        if lthr is None:
            raise ValueError("lthr basis needs an LTHR anchor")
        edges = tuple(_ceil_div(p * lthr, 100) for p in LTHR_BAND_PCT)
        return ZoneSpec(basis, edges, {"lthr": lthr}, hrmax)   # type: ignore[arg-type]
    if basis == BASIS_HRR:
        if hrmax is None or rhr is None:
            raise ValueError("hrr basis needs HRmax and RHR anchors")
        if rhr >= hrmax:
            raise ValueError(f"RHR {rhr} is not below HRmax {hrmax}: no heart-rate reserve")
        reserve = hrmax - rhr
        edges = tuple(rhr + _ceil_div(p * reserve, 100) for p in HRR_BAND_PCT)
        return ZoneSpec(basis, edges, {"hrmax": hrmax, "rhr": rhr}, hrmax)   # type: ignore[arg-type]
    raise ValueError(f"unknown zone basis {basis!r}")


def band_for(bpm: int, spec_or_hrmax: Union[ZoneSpec, int], bands: Sequence[int] = BAND_PCT) -> int:
    """0 = below band 1 (covered, uncredited); 1..5 = the band, lower-inclusive, top open.

    Takes a `ZoneSpec` (the model) or, for the retired %HRmax projection only, an integer HRmax
    with `bands` as integer percents of it."""
    band = 0
    if isinstance(spec_or_hrmax, ZoneSpec):
        for i, edge in enumerate(spec_or_hrmax.edges_bpm, start=1):
            if bpm >= edge:
                band = i
        return band
    hrmax = spec_or_hrmax
    for i, pct in enumerate(bands, start=1):
        if bpm * 100 >= pct * hrmax:
            band = i
    return band


@dataclass(frozen=True)
class HrmaxEntry:
    """One dated anchor row as the resolver sees it (a `user_hrmax` or `user_hr_anchors` row).
    `id` and `restates` carry the restatement link (#383): `restates` is the `id` of the entry this
    one corrects. A plain `(effective_from, bpm)` pair is an entry with neither: it can restate
    nothing and cannot be restated."""
    effective_from: date
    bpm: int
    id: Optional[int] = None
    restates: Optional[int] = None


AnchorEntry = HrmaxEntry       # the general name; the class predates the second anchor table


def entry_from_row(row) -> HrmaxEntry:
    """A `HrmaxEntry` from a `models.UserHrmax` or `models.UserHrAnchor` (duck-typed: this module
    stays free of the ORM; the bpm column is `hrmax_bpm` on the first and `bpm` on the second)."""
    bpm = getattr(row, "hrmax_bpm", None)
    if bpm is None:
        bpm = row.bpm
    return HrmaxEntry(row.effective_from, bpm, row.id, row.restates_id)


def hrmax_in_force(entries: Iterable[Union[HrmaxEntry, tuple[date, int]]], day: date) -> Optional[int]:
    """The anchor in force on `day`, else None (no value was in force yet: the row is withheld as
    `no_anchor`, never given a default). `entries` are `HrmaxEntry`s or `(effective_from, bpm)`
    pairs, in any order: the answer never depends on input order. Named for its first anchor;
    `anchor_in_force` is the same function for every kind.

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
            raise ValueError(f"anchor entry {e.id} restates {e.restates}, which is not among the entries")
        if target.effective_from != e.effective_from:
            raise ValueError(f"anchor entry {e.id} ({e.effective_from}) restates {e.restates} "
                             f"({target.effective_from}): a restatement shares its target's date")
    superseded = {e.restates for e in es if e.restates is not None}
    eligible = [e for e in es if e.effective_from <= day and (e.id is None or e.id not in superseded)]
    if not eligible:
        return None
    top = max(e.effective_from for e in eligible)
    winners = [e for e in eligible if e.effective_from == top]
    if len(winners) > 1:
        raise ValueError(f"ambiguous anchor on {top}: {len(winners)} entries "
                         f"({', '.join(str(e.bpm) for e in winners)} bpm), none restating another")
    return winners[0].bpm


anchor_in_force = hrmax_in_force


def resolve_zone_spec(basis: str, day: date, *,
                      hrmax_entries: Iterable = (), lthr_entries: Iterable = (),
                      rhr_entries: Iterable = ()) -> Optional[ZoneSpec]:
    """The `ZoneSpec` in force on `day` for `basis`, or None when an anchor the basis needs is not in
    force (the row is then `no_anchor`). HRmax is resolved under either basis so the ceiling flag
    works for the cycling class too; an incoherent HRR pair (RHR >= HRmax) also yields None."""
    hrmax = anchor_in_force(hrmax_entries, day)
    if basis == BASIS_LTHR:
        lthr = anchor_in_force(lthr_entries, day)
        return None if lthr is None else zone_spec(BASIS_LTHR, lthr=lthr, hrmax=hrmax)
    if basis == BASIS_HRR:
        rhr = anchor_in_force(rhr_entries, day)
        if hrmax is None or rhr is None or rhr >= hrmax:
            return None
        return zone_spec(BASIS_HRR, hrmax=hrmax, rhr=rhr)
    raise ValueError(f"unknown zone basis {basis!r}")


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


def zone_session(
    samples: Iterable[tuple[datetime, int]],
    start: datetime,
    stop: datetime,
    spec: Optional[ZoneSpec],
    *,
    max_gap_s: float = MAX_SAMPLE_GAP_S,
    min_coverage: float = MIN_ZONE_COVERAGE,
    plausible: tuple[int, int] = PLAUSIBLE_BPM,
) -> ZoneResult:
    """Zone one session from `(time, bpm)` samples under `spec`. Times must be timezone-aware (UTC).

    Samples outside [start, stop] are ignored; the caller has already restricted them to one
    writer. `stop <= start` has no duration to cover and raises ValueError — the caller skips
    such rows rather than classify them."""
    duration = (stop - start).total_seconds()
    if duration <= 0:
        raise ValueError("session has no positive duration")

    if spec is None:
        return ZoneResult(None, None, None, None, "no_anchor")

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
        seconds[band_for(b, spec)] += credit
        credited += credit
        weighted_bpm += b * credit

    coverage = credited / duration
    top = max(b for _, b in kept)
    over = spec.hrmax is not None and top > spec.hrmax
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
