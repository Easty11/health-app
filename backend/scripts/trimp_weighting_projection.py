"""Read-only projection for Q230: what would the metabolic lane look like under a Banister-derived zone table?

THE QUESTION. The metabolic window weights minutes in HR zone z by z (Edwards, `metab-v1`, unit
`trimp_edw_au`). Q230 asks whether it should instead use weights derived from Banister's exponential
TRIMP. This script answers "what would change over the last 90 days" WITHOUT changing anything: it reads
exported rows, applies a candidate zone-weight table to the SAME stored zone seconds, and prints daily
fitness / fatigue / form under both, using the production rollup (`load_metrics.compute_window_series`
and its `TAU_FATIGUE_DAYS["metabolic"]`, `TAU_FITNESS_DAYS`), not a copy of it.

IT WRITES NOTHING. CSV mode only: it opens no database connection, imports nothing from `database`, and
changes no transform, version, row or schema. Recompute and migration are not in play.

THE CANDIDATE (operator scope ruling, 10 Oct 2026). NOT per-sample Banister: Polar rows carry zone seconds
only, and mixing formulas inside one window is forbidden (INV-2, `load_events_metabolic`). The candidate is
ONE fixed table applied to stored zone seconds for every source:

    x_z    = (mid_z% * HRmax - HRrest) / (HRmax - HRrest)          mid-point of band z, in %HRmax
    w_z    = x_z * a * exp(b * x_z)                                 Banister's per-minute TRIMP at x_z
    weight = w_z / w_1                                              normalised so Z1 = 1, as Edwards has it

Band mid-points come from `hr_zones.BAND_PCT` (50/60/70/80/90, z5 open-topped, closed here at 100% of HRmax):
55, 65, 75, 85, 95. The weight includes the HR-reserve factor `x` (Banister's TRIMP is duration * x * a *
exp(b * x)); the exponential alone would not be comparable with Edwards' 1 to 5.
  * HRmax  = `hr_zones.hrmax_in_force` on the as-of day, from the exported `user_hrmax` rows.
  * HRrest = the MEAN of `hr_nadir_bpm` over the window (the sleep nadir, `nadir-v1`), with sensitivity at
             -5 and +5 bpm. `health_connect_syncs.resting_heart_rate` is the all-day median and is NEVER used.
  * Sex    = a per-user constant (`USER_SEX`, default male). The tree holds no sex field; that is a later
             open-question note for multi-user, not a blocker.

PROVENANCE OF THE COEFFICIENTS (#32 discipline) - STATUS: cited from secondary sources, PRIMARY NOT READ.
Male a = 0.64, b = 1.92, x = (HRex - HRrest) / (HRmax - HRrest). Found stated identically, with the women's pair
(0.86, 1.67), in several secondary papers surfaced by search on 10 Oct 2026 (Frontiers in Physiology 2020,
10.3389/fphys.2020.00480; Frontiers in Neuroscience 2017, 10.3389/fnins.2017.00612; PMC6709800; PMC12528351),
which attribute it to Banister (1991), "Modeling elite athletic performance", in Physiological Testing of
Elite Athletes (Human Kinetics; bibliographic details as cited by those sources, not opened here), and one to
Banister and Calvert (1980). PubMed confirms Morton, Fitz-Clarke and Banister 1990, J Appl Physiol 69(3):1171-7
(10.1152/jappl.1990.69.3.1171), but its abstract does not state the coefficients. The full texts could not be
fetched from the build environment (publisher and PMC hosts are blocked), so NO primary source has been read.
Verify against the primary text before any decision rests on the absolute numbers.

HOW TO FEED IT (three exports, one statement per run: Railway's query editor silently no-ops a multi-statement
paste, FEEDBACK 29). `--print-sql` prints them, ready to paste:

    python -m scripts.trimp_weighting_projection --print-sql [--user N] [--days 90]
    python -m scripts.trimp_weighting_projection --sessions sessions.csv --hrmax hrmax.csv --nadir nadir.csv

Run it from `backend/` with the project venv (it imports the load modules, which need SQLAlchemy installed,
but it never connects to a database). Output is ASCII so a Windows console renders it.

WHY THE SESSIONS EXPORT IS A JOIN, NOT `SELECT ... FROM aerobic_sessions`. The production metabolic series is
the set of `load_events` rows the transform wrote: canonical sessions only (a same-bout twin is arbitrated
away) with usable zones (INV-7). A plain `aerobic_sessions` export would include the twins and the
unscoreable rows, and re-implementing arbitration here would be a second copy. Joining `load_events` to
`aerobic_sessions` on `source_ref` gives exactly the sessions production counted, with their zone seconds, and
the deposited `load` is kept so the script can check its own Edwards recomputation against it.

LIMITS, stated so they are not read as findings. The stocks are seeded at the first exported day (the
`banister-v4` first-week-mean seed, over the exported window), so absolute fitness / fatigue / form differ from
the production trace, which starts at the user's calendar start; the DIFFERENCE between the two formulas over
one window is the quantity of interest. Export a longer window (for example 180 days) to give the stocks a
warm-up: the report covers the last `--days` either way. The candidate's units are not Edwards units: Z1 is 1 in
both, higher zones weigh more. The weights are evaluated at zone mid-points, an approximation.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Sequence

from hr_zones import BAND_PCT, HrmaxEntry, hrmax_in_force
from load_events_metabolic import (
    EDWARDS_WEIGHTS,
    FORMULA_VERSION_METABOLIC,
    WINDOW_METABOLIC,
)
from load_metrics import TAU_FATIGUE_DAYS, _local_day, compute_window_series

# ---------------------------------------------------------------------------
# Constants (provenance above)
# ---------------------------------------------------------------------------

# Banister's HR-weighting coefficients, (a, b) in a * exp(b * x). Cited from secondary sources; PRIMARY NOT READ.
SEX_COEFFICIENTS: dict[str, tuple[float, float]] = {"male": (0.64, 1.92)}
DEFAULT_SEX = "male"
# Per-user sex constant (operator ruling, 10 Oct 2026). Empty means every user takes DEFAULT_SEX. No sex field
# exists in the tree (`models.User` has none), so a multi-user build needs one first.
USER_SEX: dict[int, str] = {}

RHR_OFFSET_BPM = 5.0        # sensitivity: nadir mean -5 and +5 (operator ruling)
REPORT_DAYS = 90
TOP_SESSIONS = 5
LOAD_MATCH_TOL = 1e-6       # relative tolerance for "recomputed Edwards equals the deposited load"
ZONES = (1, 2, 3, 4, 5)


class InputError(ValueError):
    """A problem with the supplied exports, reported plainly and exiting 2."""


# ---------------------------------------------------------------------------
# The export statements (one per run). Built from the module constants so the filters cannot drift.
# ---------------------------------------------------------------------------

def export_statements(user_id: int = 1, days: int = REPORT_DAYS) -> dict[str, str]:
    """The three Postgres statements, each ONE line (a paste cannot lose a line break). Column names are
    checked against the models by `tests/test_trimp_weighting_projection.py`."""
    sessions = (
        "SELECT a.user_id, a.id AS session_id, a.session_date, a.start_time, le.occurred_at, a.sport_name, "
        "a.source, le.load, a.z1_seconds, a.z2_seconds, a.z3_seconds, a.z4_seconds, a.z5_seconds, "
        "u.rpe_complete_from "
        "FROM load_events le "
        "JOIN aerobic_sessions a ON CAST(a.id AS TEXT) = le.source_ref AND a.user_id = le.user_id "
        "JOIN users u ON u.id = le.user_id "
        f"WHERE le.user_id = {int(user_id)} AND le.source = 'aerobic_sessions' "
        f"AND le.load_window = '{WINDOW_METABOLIC}' AND le.formula_version = '{FORMULA_VERSION_METABOLIC}' "
        f"AND le.occurred_at >= now() - interval '{int(days)} days' "
        "ORDER BY le.occurred_at, a.id"
    )
    hrmax = (
        "SELECT id, user_id, effective_from, hrmax_bpm, restates_id "
        f"FROM user_hrmax WHERE user_id = {int(user_id)} ORDER BY effective_from, id"
    )
    nadir = (
        "SELECT user_id, date, hr_nadir_bpm, hr_nadir_reason "
        f"FROM health_connect_syncs WHERE user_id = {int(user_id)} AND date >= current_date - {int(days)} "
        "ORDER BY date"
    )
    return {"sessions.csv": sessions, "hrmax.csv": hrmax, "nadir.csv": nadir}


# ---------------------------------------------------------------------------
# Parsing (CSV in, plain values out)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionRow:
    user_id: int
    session_id: int
    session_date: Optional[date]
    occurred_at: Optional[datetime]
    sport: str
    source: str
    deposited_load: float
    zones: tuple[Optional[float], ...]      # seconds in z1..z5; None where the cell was blank
    rpe_complete_from: Optional[date]


def _blank(v: Optional[str]) -> bool:
    return v is None or v.strip() == "" or v.strip().lower() in ("null", "none", "\\n")


def _parse_date(v: Optional[str], col: str) -> Optional[date]:
    if _blank(v):
        return None
    try:
        return date.fromisoformat(v.strip()[:10])
    except ValueError as exc:
        raise InputError(f"column {col}: {v!r} is not a date") from exc


def _parse_ts(v: Optional[str], col: str) -> Optional[datetime]:
    """An ISO timestamp as aware UTC. Accepts the editor's `2026-10-01 09:30:00+00`, `...+00:00`, `...Z` and a
    naive value (read as UTC, the stored-instant convention)."""
    if _blank(v):
        return None
    s = v.strip().replace(" ", "T", 1)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    tail = s[-3:]
    if len(s) > 10 and tail[0] in "+-" and tail[1:].isdigit():       # `+00` -> `+00:00`
        s += ":00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise InputError(f"column {col}: {v!r} is not a timestamp") from exc
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _parse_num(v: Optional[str], col: str) -> Optional[float]:
    if _blank(v):
        return None
    try:
        return float(v.strip())
    except ValueError as exc:
        raise InputError(f"column {col}: {v!r} is not a number") from exc


def _read(path: str, required: Sequence[str]) -> list[dict[str, str]]:
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            header = [h.strip() for h in (reader.fieldnames or [])]
            missing = [c for c in required if c not in header]
            if missing:
                raise InputError(f"{path}: missing column(s) {missing}; header is {header}")
            return [{(k or "").strip(): v for k, v in row.items()} for row in reader]
    except FileNotFoundError as exc:
        raise InputError(f"{path}: file not found") from exc


_SESSION_COLUMNS = ("user_id", "session_id", "occurred_at", "sport_name", "source", "load",
                    "z1_seconds", "z2_seconds", "z3_seconds", "z4_seconds", "z5_seconds")


def sessions_from_csv(path: str) -> list[SessionRow]:
    out = []
    for r in _read(path, _SESSION_COLUMNS):
        load = _parse_num(r["load"], "load")
        if load is None:
            raise InputError(f"{path}: session {r['session_id']} has no load")
        out.append(SessionRow(
            user_id=int(float(r["user_id"])), session_id=int(float(r["session_id"])),
            session_date=_parse_date(r.get("session_date"), "session_date"),
            occurred_at=_parse_ts(r["occurred_at"], "occurred_at"),
            sport=(r["sport_name"] or "").strip() or "unknown", source=(r["source"] or "").strip(),
            deposited_load=load,
            zones=tuple(_parse_num(r[f"z{z}_seconds"], f"z{z}_seconds") for z in ZONES),
            rpe_complete_from=_parse_date(r.get("rpe_complete_from"), "rpe_complete_from"),
        ))
    return out


def hrmax_from_csv(path: str) -> list[tuple[int, HrmaxEntry]]:
    """(user_id, HrmaxEntry) pairs from a `user_hrmax` export."""
    out = []
    for r in _read(path, ("id", "user_id", "effective_from", "hrmax_bpm", "restates_id")):
        eff = _parse_date(r["effective_from"], "effective_from")
        bpm = _parse_num(r["hrmax_bpm"], "hrmax_bpm")
        if eff is None or bpm is None:
            raise InputError(f"{path}: a user_hrmax row has no effective_from or hrmax_bpm")
        restates = _parse_num(r["restates_id"], "restates_id")
        out.append((int(float(r["user_id"])),
                    HrmaxEntry(eff, int(bpm), int(float(r["id"])), int(restates) if restates is not None else None)))
    return out


def nadir_from_csv(path: str) -> list[tuple[int, date, float]]:
    """(user_id, date, hr_nadir_bpm) for the rows that HAVE a nadir; a NULL nadir is a decided absence."""
    out = []
    for r in _read(path, ("user_id", "date", "hr_nadir_bpm")):
        bpm = _parse_num(r["hr_nadir_bpm"], "hr_nadir_bpm")
        d = _parse_date(r["date"], "date")
        if bpm is None or d is None:
            continue
        out.append((int(float(r["user_id"])), d, bpm))
    return out


# ---------------------------------------------------------------------------
# The two weight tables, per-session TRIMP, the daily series (pure)
# ---------------------------------------------------------------------------

def band_midpoints_pct() -> dict[int, float]:
    """Mid-point of each zone's band in % of HRmax. z5 is open-topped in the platform definition; it is
    closed here at 100% (HRmax is the ceiling by definition)."""
    edges = list(BAND_PCT) + [100]
    return {z: (edges[z - 1] + edges[z]) / 2.0 for z in ZONES}


def banister_zone_weights(hrmax: float, hrrest: float, coeffs: tuple[float, float]) -> dict[int, float]:
    """Per-zone weights from Banister's per-minute TRIMP at each band mid-point, normalised so Z1 = 1."""
    if not (0 < hrrest < hrmax):
        raise InputError(f"resting HR {hrrest:g} must lie between 0 and HRmax {hrmax:g}")
    a, b = coeffs
    raw: dict[int, float] = {}
    for z, pct in band_midpoints_pct().items():
        x = (pct / 100.0 * hrmax - hrrest) / (hrmax - hrrest)
        if x <= 0:
            raise InputError(f"resting HR {hrrest:g} leaves the Z{z} mid-point ({pct:g}% of HRmax {hrmax:g}) "
                             "at or below rest, so the zone has no heart-rate reserve to weigh")
        raw[z] = x * a * math.exp(b * x)
    return {z: raw[z] / raw[1] for z in ZONES}


def session_trimp(zone_seconds: Sequence[Optional[float]], weights: dict[int, float]) -> float:
    """sum over zones of (seconds / 60) * weight; a blank zone is 0 (the fail-closed rows never reach here)."""
    return sum(((s or 0.0) / 60.0) * weights[z] for z, s in zip(ZONES, zone_seconds))


def daily_loads(sessions: Iterable[SessionRow], weights: dict[int, float], as_of: date) -> dict[date, float]:
    """Σ load per user-local day, bucketed and truncated exactly as `load_metrics.compute_load_metrics`
    does: `_local_day(occurred_at)`; a day after `as_of` is dropped; a day before the user's
    `rpe_complete_from` is dropped. Every session's day appears (a zero load still places the day)."""
    daily: dict[date, float] = {}
    for s in sessions:
        if s.occurred_at is None:
            continue
        day = _local_day(s.occurred_at)
        if day > as_of or (s.rpe_complete_from is not None and day < s.rpe_complete_from):
            continue
        daily[day] = daily.get(day, 0.0) + session_trimp(s.zones, weights)
    return daily


def _series(sessions: list[SessionRow], weights: dict[int, float], as_of: date):
    return compute_window_series(daily_loads(sessions, weights, as_of), as_of,
                                 tau_fatigue_days=TAU_FATIGUE_DAYS[WINDOW_METABOLIC])


def _in_scope(sessions: Iterable[SessionRow], as_of: date) -> list[SessionRow]:
    """Sessions that survive the same day cut the series applies (dated, not after as_of, not pre-epoch)."""
    out = []
    for s in sessions:
        if s.occurred_at is None:
            continue
        day = _local_day(s.occurred_at)
        if day > as_of or (s.rpe_complete_from is not None and day < s.rpe_complete_from):
            continue
        out.append(s)
    return out


# ---------------------------------------------------------------------------
# The projection (pure over parsed inputs)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Projection:
    user_id: int
    sex: str
    coeffs: tuple[float, float]
    as_of: date
    window_start: date
    hrmax: int
    hrmax_changes: list[HrmaxEntry]         # entries whose effective_from falls inside the window
    rhr: float
    rhr_n: int
    rhr_min: float
    rhr_max: float
    tables: list[tuple[float, dict[int, float]]]        # (offset, candidate weights) for -5, 0, +5
    rows: list[dict[str, Any]]              # daily rows at the central RHR
    summaries: list[dict[str, Any]]         # one per RHR value
    top: list[dict[str, Any]]
    n_sessions: int
    n_dropped: int
    check_max_abs_diff: float
    check_mismatches: int


def _summary(edw, cand, report_from: date) -> dict[str, Any]:
    deltas = [(c.day, c.form - e.form, c.daily_load, e.daily_load) for e, c in zip(edw, cand) if c.day >= report_from]
    if not deltas:
        return {"max_abs": 0.0, "max_day": None, "mean": 0.0, "mean_abs": 0.0, "n": 0, "load_ratio": None}
    worst = max(deltas, key=lambda t: (abs(t[1]), t[0]))
    tot_c, tot_e = sum(t[2] for t in deltas), sum(t[3] for t in deltas)
    return {"max_abs": worst[1], "max_day": worst[0], "mean": sum(t[1] for t in deltas) / len(deltas),
            "mean_abs": sum(abs(t[1]) for t in deltas) / len(deltas), "n": len(deltas),
            "load_ratio": (tot_c / tot_e) if tot_e > 0 else None}


def project(sessions: list[SessionRow], hrmax_entries: list[HrmaxEntry], nadir: list[tuple[date, float]],
            *, user_id: int, as_of: date, days: int = REPORT_DAYS, top_n: int = TOP_SESSIONS,
            rhr_offset: float = RHR_OFFSET_BPM) -> Projection:
    if not sessions:
        raise InputError("no sessions: the export is empty for this user and window")
    sex = USER_SEX.get(user_id, DEFAULT_SEX)
    coeffs = SEX_COEFFICIENTS[sex]
    window_start = as_of - timedelta(days=days - 1)

    hrmax = hrmax_in_force(hrmax_entries, as_of)
    if hrmax is None:
        raise InputError(f"no HRmax in force on {as_of}: the user_hrmax export has no row on or before it")
    changes = sorted((e for e in hrmax_entries if window_start <= e.effective_from <= as_of),
                     key=lambda e: (e.effective_from, e.id or 0))

    in_window = [bpm for d, bpm in nadir if window_start <= d <= as_of]
    if not in_window:
        raise InputError(f"no hr_nadir_bpm values between {window_start} and {as_of}: the resting HR has no "
                         "default, and health_connect_syncs.resting_heart_rate (the all-day median) is not "
                         "a resting rate and is never used")
    rhr = sum(in_window) / len(in_window)

    offsets = (-rhr_offset, 0.0, rhr_offset)
    tables = [(o, banister_zone_weights(hrmax, rhr + o, coeffs)) for o in offsets]

    scope = _in_scope(sessions, as_of)
    edw_series = _series(sessions, EDWARDS_WEIGHTS, as_of)
    series_by_offset = [(o, edw_series, _series(sessions, w, as_of)) for o, w in tables]
    # SHAPE-ONLY companion. Normalising to Z1 = 1 raises total load (higher zones weigh more than Edwards'),
    # so the raw form delta mixes a level shift with the change of shape. Rescaling the candidate to the
    # Edwards total over the window removes the level, leaving what the reweighting does to the pattern.
    in_win = [s for s in _in_scope(sessions, as_of) if _local_day(s.occurred_at) >= window_start]
    tot_e = sum(session_trimp(s.zones, EDWARDS_WEIGHTS) for s in in_win)
    summaries = []
    for o, w in tables:
        tot_c = sum(session_trimp(s.zones, w) for s in in_win)
        k = (tot_e / tot_c) if tot_c > 0 else 1.0
        scaled = _summary(edw_series, _series(sessions, {z: v * k for z, v in w.items()}, as_of), window_start)
        cand = next(c for oo, _e, c in series_by_offset if oo == o)
        summaries.append({"offset": o, "rhr": rhr + o, **_summary(edw_series, cand, window_start),
                          "scaled_max_abs": scaled["max_abs"], "scaled_mean_abs": scaled["mean_abs"]})

    central = next(t for t in series_by_offset if t[0] == 0.0)
    rows = [{
        "date": e.day.isoformat(), "edwards_load": e.daily_load, "candidate_load": c.daily_load,
        "edwards_fitness": e.fitness, "edwards_fatigue": e.fatigue, "edwards_form": e.form,
        "candidate_fitness": c.fitness, "candidate_fatigue": c.fatigue, "candidate_form": c.form,
        "form_delta": c.form - e.form,
    } for e, c in zip(central[1], central[2]) if e.day >= window_start]

    central_w = next(w for o, w in tables if o == 0.0)
    moves = []
    for s in scope:
        day = _local_day(s.occurred_at)
        if day < window_start:
            continue
        e_t, c_t = session_trimp(s.zones, EDWARDS_WEIGHTS), session_trimp(s.zones, central_w)
        moves.append({"date": day.isoformat(), "occurred_at": s.occurred_at, "session_id": s.session_id,
                      "sport": s.sport, "source": s.source, "minutes": [(z or 0.0) / 60.0 for z in s.zones],
                      "edwards": e_t, "candidate": c_t, "delta": c_t - e_t,
                      "pct": ((c_t - e_t) / e_t * 100.0) if e_t > 0 else None})
    moves.sort(key=lambda m: (-abs(m["delta"]), m["occurred_at"], m["session_id"]))

    # Control: the script's Edwards must equal what production deposited, or the export is not the
    # production set (or the transform has moved since). Reported, never silently ignored.
    diffs = [abs(session_trimp(s.zones, EDWARDS_WEIGHTS) - s.deposited_load) for s in scope]
    mism = sum(1 for s, d in zip(scope, diffs) if d > LOAD_MATCH_TOL * max(1.0, abs(s.deposited_load)))

    return Projection(
        user_id=user_id, sex=sex, coeffs=coeffs, as_of=as_of, window_start=window_start, hrmax=hrmax,
        hrmax_changes=changes, rhr=rhr, rhr_n=len(in_window), rhr_min=min(in_window), rhr_max=max(in_window),
        tables=tables, rows=rows, summaries=summaries, top=moves[:top_n],
        n_sessions=len(scope), n_dropped=len(sessions) - len(scope),
        check_max_abs_diff=max(diffs) if diffs else 0.0, check_mismatches=mism)


# ---------------------------------------------------------------------------
# Rendering (ASCII)
# ---------------------------------------------------------------------------

def _f(v: float, nd: int = 2) -> str:
    return f"{v:.{nd}f}"


def render(p: Projection) -> str:
    L: list[str] = []
    L.append("TRIMP weighting projection (Q230) - READ ONLY. Nothing was changed or recomputed.")
    L.append("Results come from the exported rows of an operator run; Code did not run this against production.")
    L.append("")
    L.append(f"User {p.user_id}   window {p.window_start} -> {p.as_of} ({(p.as_of - p.window_start).days + 1} days)"
             f"   sessions in scope {p.n_sessions} (dropped by the day cut: {p.n_dropped})")
    L.append(f"Candidate: fixed Banister-derived zone table applied to stored zone seconds, every source; "
             f"{p.sex} coefficients a={p.coeffs[0]:g}, b={p.coeffs[1]:g}.")
    L.append("Coefficient status: cited from secondary sources; the PRIMARY (Banister 1991) was NOT read. "
             "Verify before relying on absolute numbers.")
    L.append(f"HRmax in force on {p.as_of}: {p.hrmax} bpm.")
    for e in p.hrmax_changes:
        L.append(f"  WARNING: an HRmax row dated {e.effective_from} ({e.bpm} bpm) falls inside the window; "
                 f"the table uses the value in force on {p.as_of} for every day.")
    L.append(f"Resting HR: mean hr_nadir_bpm over the window = {_f(p.rhr, 1)} bpm "
             f"(n={p.rhr_n} nights, range {_f(p.rhr_min, 1)} to {_f(p.rhr_max, 1)}); sensitivity at -5 and +5.")
    L.append("")
    L.append("Zone weights (minutes in zone x weight; Z1 = 1 in both; the candidate's unit is not Edwards' unit)")
    def _off(o: float) -> str:
        return f"{o:+g}" if o else "+0"

    L.append(f"  {'':<30}" + "".join(f"{'Z' + str(z):>8}" for z in ZONES))
    L.append(f"  {'Edwards (metab-v1)':<30}" + "".join(f"{EDWARDS_WEIGHTS[z]:>8.2f}" for z in ZONES))
    for off, w in p.tables:
        L.append(f"  {'Banister-derived, RHR ' + _off(off):<30}" + "".join(f"{w[z]:>8.2f}" for z in ZONES))
    for off, w in p.tables:
        L.append(f"  {'  ratio to Edwards, RHR ' + _off(off):<30}"
                 + "".join(f"{w[z] / EDWARDS_WEIGHTS[z]:>8.2f}" for z in ZONES))
    L.append("")
    L.append("Form delta (candidate form minus Edwards form), same rollup and tau-set as load_metrics")
    L.append(f"  {'RHR (bpm)':<12}{'max |delta|':>12}{'on':>13}{'mean delta':>13}{'mean |delta|':>14}{'load ratio':>12}"
             f"{'max |d| *':>11}{'mean |d| *':>12}")
    for s in p.summaries:
        ratio = _f(s["load_ratio"], 2) if s["load_ratio"] is not None else "n/a"
        L.append(f"  {_f(s['rhr'], 1):<12}{_f(s['max_abs']):>12}{str(s['max_day'] or '-'):>13}"
                 f"{_f(s['mean']):>13}{_f(s['mean_abs']):>14}{ratio:>12}"
                 f"{_f(s['scaled_max_abs']):>11}{_f(s['scaled_mean_abs']):>12}")
    L.append("  (load ratio = total candidate load / total Edwards load over the window)")
    L.append("  (* shape only: the candidate rescaled to the Edwards total, so the level shift from the Z1 = 1")
    L.append("     normalisation is removed and what is left is the reweighting's effect on the pattern)")
    L.append("")
    L.append(f"The {len(p.top)} sessions whose TRIMP moves most (central RHR)")
    L.append(f"  {'date':<11}{'sport':<20}{'source':<18}{'min z1..z5':<26}{'Edwards':>9}{'cand.':>9}{'delta':>9}{'pct':>8}")
    for m in p.top:
        mins = " ".join(f"{x:.0f}" for x in m["minutes"])
        pct = f"{m['pct']:+.0f}%" if m["pct"] is not None else "n/a"
        L.append(f"  {m['date']:<11}{m['sport'][:19]:<20}{m['source'][:17]:<18}{mins:<26}"
                 f"{_f(m['edwards']):>9}{_f(m['candidate']):>9}{m['delta']:>+9.2f}{pct:>8}")
    L.append("")
    L.append("Integrity control: the script's Edwards recomputed from the exported zone seconds vs the deposited load")
    if p.check_mismatches == 0:
        L.append(f"  OK: all {p.n_sessions} sessions match (max abs difference {p.check_max_abs_diff:.2e}).")
    else:
        L.append(f"  WARNING: {p.check_mismatches} of {p.n_sessions} sessions differ (max abs difference "
                 f"{_f(p.check_max_abs_diff, 4)}). The export is not the set production counted, or the "
                 "transform has changed since; do not read the comparison until this is explained.")
    L.append("")
    L.append("Daily fitness / fatigue / form at the central RHR (stocks are seeded at the first exported day,")
    L.append("so absolute values differ from production; read the delta column)")
    L.append(f"  {'date':<11}{'E.load':>8}{'C.load':>8}{'E.fit':>8}{'E.fat':>8}{'E.form':>8}"
             f"{'C.fit':>8}{'C.fat':>8}{'C.form':>8}{'d.form':>9}")
    for r in p.rows:
        L.append(f"  {r['date']:<11}{r['edwards_load']:>8.1f}{r['candidate_load']:>8.1f}"
                 f"{r['edwards_fitness']:>8.2f}{r['edwards_fatigue']:>8.2f}{r['edwards_form']:>8.2f}"
                 f"{r['candidate_fitness']:>8.2f}{r['candidate_fatigue']:>8.2f}{r['candidate_form']:>8.2f}"
                 f"{r['form_delta']:>+9.2f}")
    return "\n".join(L) + "\n"


def write_daily_csv(rows: list[dict[str, Any]], path: str) -> None:
    cols = ["date", "edwards_load", "candidate_load", "edwards_fitness", "edwards_fatigue", "edwards_form",
            "candidate_fitness", "candidate_fatigue", "candidate_form", "form_delta"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: (r[k] if k == "date" else f"{r[k]:.6f}") for k in cols})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _aest_today() -> date:
    return _local_day(datetime.now(timezone.utc))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Read-only projection of the metabolic lane under a Banister-derived zone table (Q230).")
    ap.add_argument("--print-sql", action="store_true", help="print the three export statements and exit")
    ap.add_argument("--sessions", help="sessions export (load_events joined to aerobic_sessions)")
    ap.add_argument("--hrmax", help="user_hrmax export")
    ap.add_argument("--nadir", help="health_connect_syncs nadir export")
    ap.add_argument("--user", type=int, default=None, help="user id (default: the only user in the sessions file)")
    ap.add_argument("--as-of", dest="as_of", default=None, help="last day of the window, YYYY-MM-DD (default: today, AEST)")
    ap.add_argument("--days", type=int, default=REPORT_DAYS, help=f"days to report (default {REPORT_DAYS})")
    ap.add_argument("--top", type=int, default=TOP_SESSIONS)
    ap.add_argument("--rhr-offset", type=float, default=RHR_OFFSET_BPM, dest="rhr_offset")
    ap.add_argument("--csv-out", dest="csv_out", default=None, help="also write the daily table to this CSV")
    args = ap.parse_args(argv)

    try:
        if args.print_sql:
            uid = args.user if args.user is not None else 1
            for name, sql in export_statements(uid, args.days).items():
                print(f"-- {name}  (run on its own; export the result as CSV)")
                print(sql + ";\n")
            return 0
        if not (args.sessions and args.hrmax and args.nadir):
            raise InputError("--sessions, --hrmax and --nadir are all required (or use --print-sql)")
        if args.days < 8:
            raise InputError("--days must be at least 8 (the stock seed is the first week's mean)")
        sessions = sessions_from_csv(args.sessions)
        users = sorted({s.user_id for s in sessions})
        uid = args.user if args.user is not None else (users[0] if len(users) == 1 else None)
        if uid is None:
            raise InputError(f"the sessions file holds users {users}; pass --user N")
        as_of = date.fromisoformat(args.as_of) if args.as_of else _aest_today()
        p = project(
            [s for s in sessions if s.user_id == uid],
            [e for u, e in hrmax_from_csv(args.hrmax) if u == uid],
            [(d, b) for u, d, b in nadir_from_csv(args.nadir) if u == uid],
            user_id=uid, as_of=as_of, days=args.days, top_n=args.top, rhr_offset=args.rhr_offset)
    except (InputError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    sys.stdout.write(render(p))
    if args.csv_out:
        write_daily_csv(p.rows, args.csv_out)
        print(f"daily table written to {args.csv_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
