"""Read-only dry run for Brief A A6 (richness-first arbitration): which same-bout pairs change canonical row?

`reads.aerobic_reads._win_key` now leads with a data tier (2 usable zones / 1 avg HR / 0 neither), so a
row without HR can no longer suppress a same-bout row with HR. This script arbitrates each user's FULL
`aerobic_sessions` set twice — once with the tier neutralised (master's ordering) and once as shipped —
and lists every bout whose canonical row flips: date, sport, old -> new (id, source, tier), and whether the
flip makes the bout newly scoreable by the metabolic transform.

It WRITES NOTHING. It reads rows, runs the pure `arbitrate` in memory, and prints. The `.canonical`
attribute it sets lives on the in-memory objects only (there is no such column). On Postgres the DB mode also
opens `SET TRANSACTION READ ONLY` as a belt over the braces.

Two ways to feed it:

  DB mode (needs DATABASE_URL reachable from where it runs: inside the container, from /app, via
  `railway ssh --service health-app-backend`; `railway run` injects the private host and cannot reach it):
      /opt/venv/bin/python -m scripts.arbitration_flip_report [--user N]

  CSV mode (needs only the psql route the runbook already uses — `railway connect` to health-app-DB):
      \\copy (SELECT id, user_id, source, source_package, session_date, start_time, stop_time, sport_name,
              duration_minutes, hr_avg, hr_max, z1_seconds, z2_seconds, z3_seconds, z4_seconds, z5_seconds
              FROM aerobic_sessions ORDER BY id) TO 'aerobic_sessions.csv' CSV HEADER
      python -m scripts.arbitration_flip_report --csv aerobic_sessions.csv

The bout list is what the A6 PR records, and what the operator reviews BEFORE merge.

HC ZONE PROJECTION (`--hc-zones`, Q159 stage 2, G2) — the same dry run for the HC zone fill. It applies
`hr_zones.zone_session` (the module the chain step uses) IN MEMORY to every health_connect row and reports:
per HC row the projected coverage, reason, zones, hr_avg/hr_max and a marker for any row within +-0.05 of
`MIN_ZONE_COVERAGE`; the over-ceiling rows; every bout whose canonical row flips once the projected zones
exist; the per-day metabolic TRIMP delta; and, for every HC row that shares a bout with a Polar row, the
minutes per band HC-zoned vs Polar-zoned (the interim invariance check). It WRITES NOTHING.

  Post-deploy (hr_samples exists and holds the re-posted HR):
      python -m scripts.arbitration_flip_report --hc-zones [--user N]
  Pre-merge the table does not exist and no bpm is stored anywhere, so ZONES CANNOT be projected; the
  COVERAGE / REASON projection can, from HR timestamps alone (no bpm). Over psql (`railway connect`):
      \\copy (SELECT user_id, record_start, source_package FROM health_connect_record_sources
              WHERE record_type = 'heart_rate') TO 'hc_hr_times.csv' CSV HEADER
      python -m scripts.arbitration_flip_report --hc-zones --csv aerobic_sessions.csv \\
          --record-sources-csv hc_hr_times.csv --hrmax 1=173@2026-06-01
  `--hrmax USER=BPM@YYYY-MM-DD` (repeatable) supplies HRmax entries in CSV mode, or adds to `user_hrmax`
  in DB mode; zones are shown as `-` in the timestamps-only mode (the row's reason and coverage are exact).
  A `--hrmax` entry is a projected DATED change (forward only). One dated on a date that already has a
  stored row is refused as ambiguous (it used to be silently ignored): date it after, e.g. 2026-03-02.
"""
from __future__ import annotations

import argparse
import bisect
import contextlib
import csv
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import text

import models
from hr_zones import MIN_ZONE_COVERAGE, entry_from_row, hrmax_in_force, zone_session
from load_events_metabolic import compute_metabolic_load
from reads import aerobic_reads

_CSV_COLUMNS = (
    "id", "user_id", "source", "source_package", "session_date", "start_time", "stop_time", "sport_name",
    "duration_minutes", "hr_avg", "hr_max", "z1_seconds", "z2_seconds", "z3_seconds", "z4_seconds", "z5_seconds",
)


@contextlib.contextmanager
def _tier_neutralised():
    """Master's ordering: `_data_tier` constant, so `_win_key` reduces to its pre-A6 form."""
    real = aerobic_reads._data_tier
    aerobic_reads._data_tier = lambda _s: 0
    try:
        yield
    finally:
        aerobic_reads._data_tier = real


def _same_bout(a, b) -> bool:
    """The arbitration's own overlap predicate (interval overlap >= OVERLAP_THRESHOLD of the shorter)."""
    ai = (aerobic_reads._ts(a.start_time), aerobic_reads._ts(a.stop_time))
    bi = (aerobic_reads._ts(b.start_time), aerobic_reads._ts(b.stop_time))
    if None in ai or None in bi or ai[1] <= ai[0] or bi[1] <= bi[0]:
        return False
    overlap = min(ai[1], bi[1]) - max(ai[0], bi[0])
    return overlap >= aerobic_reads.OVERLAP_THRESHOLD * min(ai[1] - ai[0], bi[1] - bi[0])


def _desc(s) -> dict[str, Any]:
    return {"id": s.id, "source": s.source, "tier": aerobic_reads._data_tier(s),
            "scoreable": aerobic_reads._has_usable_zones(s)}


def flip_report_from_rows(rows: list) -> list[dict[str, Any]]:
    """Flips for ONE user's full session set (arbitration never sees a window). Each record is a bout:
    {user_id, date, sport, old: {id, source, tier, scoreable}, new: {...}, newly_scoreable, oldly_scoreable}.
    A bout's `old`/`new` may be None on the (non-transitive-cluster) edge where a flip has no counterpart."""
    with _tier_neutralised():
        aerobic_reads.arbitrate(rows)
        old = {s.id: bool(s.canonical) for s in rows}
    aerobic_reads.arbitrate(rows)
    new = {s.id: bool(s.canonical) for s in rows}

    by_id = {s.id: s for s in rows}
    lost = [by_id[i] for i in by_id if old[i] and not new[i]]      # was canonical, no longer is
    gained = [by_id[i] for i in by_id if not old[i] and new[i]]    # was not canonical, now is

    records: list[dict[str, Any]] = []
    used_gained: set[int] = set()
    for l in sorted(lost, key=lambda s: (s.session_date, s.id)):
        partner = next((g for g in gained if g.id not in used_gained and _same_bout(l, g)), None)
        if partner is not None:
            used_gained.add(partner.id)
        records.append(_record(l, partner))
    for g in sorted(gained, key=lambda s: (s.session_date, s.id)):
        if g.id not in used_gained:
            records.append(_record(None, g))
    records.sort(key=lambda r: (r["date"], r["user_id"]))
    return records


def _record(loser, gainer) -> dict[str, Any]:
    ref = loser if loser is not None else gainer
    old = _desc(loser) if loser is not None else None
    new = _desc(gainer) if gainer is not None else None
    return {
        "user_id": ref.user_id, "date": ref.session_date.isoformat(), "sport": ref.sport_name or "unknown",
        "old": old, "new": new,
        # The metabolic consequence: a bout is scored iff its canonical row has usable zones (INV-7).
        "newly_scoreable": bool(new and new["scoreable"] and not (old and old["scoreable"])),
        "no_longer_scoreable": bool(old and old["scoreable"] and not (new and new["scoreable"])),
    }


def flip_report(db, user_id: Optional[int] = None) -> list[dict[str, Any]]:
    """DB mode: every user with aerobic sessions (or one), full set each. Read-only."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SET TRANSACTION READ ONLY"))
    q = db.query(models.AerobicSession)
    if user_id is not None:
        q = q.filter(models.AerobicSession.user_id == user_id)
    by_user: dict[int, list] = {}
    for s in q.order_by(models.AerobicSession.id).all():
        by_user.setdefault(s.user_id, []).append(s)
    out: list[dict[str, Any]] = []
    for rows in by_user.values():
        out.extend(flip_report_from_rows(rows))
    db.rollback()   # nothing was written; end the read transaction
    out.sort(key=lambda r: (r["date"], r["user_id"]))
    return out


# ── CSV mode ──────────────────────────────────────────────────────────────────

def _opt(v: str, cast):
    return None if v is None or v == "" else cast(v)


def rows_from_csv(path: str) -> dict[int, list]:
    """Transient (never-added-to-a-session) AerobicSession objects from a psql `\\copy ... CSV HEADER`
    export, grouped by user."""
    by_user: dict[int, list] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in _CSV_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"CSV is missing column(s): {', '.join(missing)}")
        for r in reader:
            s = models.AerobicSession(
                id=int(r["id"]), user_id=int(r["user_id"]), source=r["source"],
                source_package=_opt(r["source_package"], str),
                session_date=date.fromisoformat(r["session_date"]),
                start_time=_opt(r["start_time"], datetime.fromisoformat),
                stop_time=_opt(r["stop_time"], datetime.fromisoformat),
                sport_name=_opt(r["sport_name"], str),
                duration_minutes=_opt(r["duration_minutes"], float),
                hr_avg=_opt(r["hr_avg"], int), hr_max=_opt(r["hr_max"], int),
                z1_seconds=_opt(r["z1_seconds"], int), z2_seconds=_opt(r["z2_seconds"], int),
                z3_seconds=_opt(r["z3_seconds"], int), z4_seconds=_opt(r["z4_seconds"], int),
                z5_seconds=_opt(r["z5_seconds"], int),
            )
            by_user.setdefault(s.user_id, []).append(s)
    return by_user


# ── rendering ─────────────────────────────────────────────────────────────────

def _cell(d: Optional[dict[str, Any]]) -> str:
    return "—" if d is None else f"#{d['id']} {d['source']} (tier {d['tier']})"


def render_markdown(records: Iterable[dict[str, Any]], *, sessions_seen: Optional[int] = None) -> str:
    recs = list(records)
    lines = []
    if sessions_seen is not None:
        lines.append(f"Sessions arbitrated: {sessions_seen}. Bouts whose canonical row flips: {len(recs)}.")
    else:
        lines.append(f"Bouts whose canonical row flips: {len(recs)}.")
    if not recs:
        lines.append("No flips: every bout keeps its canonical row.")
        return "\n".join(lines)
    lines += ["", "| user | date | sport | old canonical | new canonical | metabolic effect |",
              "|---|---|---|---|---|---|"]
    for r in recs:
        effect = ("bout NEWLY scored" if r["newly_scoreable"]
                  else "bout NO LONGER scored" if r["no_longer_scoreable"] else "none (scoring unchanged)")
        lines.append(f"| {r['user_id']} | {r['date']} | {r['sport']} | {_cell(r['old'])} | {_cell(r['new'])} | {effect} |")
    return "\n".join(lines)


# ── HC zone projection (Q159 stage 2, G2) ────────────────────────────────────

NEAR_THRESHOLD = 0.05            # a row this close to MIN_ZONE_COVERAGE is reported as sensitive
_ISO_FRAC = re.compile(r"([.][0-9]{6})[0-9]+")


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _parse_hr_time(s: str) -> Optional[datetime]:
    """Parse a stored HR timestamp (psql or ISO, optional nanosecond fraction); None if unparseable."""
    try:
        return _utc(datetime.fromisoformat(_ISO_FRAC.sub(r"\1", s.strip()).replace("Z", "+00:00")))
    except ValueError:
        return None


class SampleIndex:
    """`(user_id, source_package)` -> time-sorted `(t, bpm)`; `window` is a bisect slice, so one run
    over a year of samples stays cheap. Pure data; no DB."""

    def __init__(self, triples: Iterable[tuple[int, str, datetime, int]]):
        by: dict[tuple[int, str], list[tuple[datetime, int]]] = defaultdict(list)
        for uid, pkg, t, bpm in triples:
            by[(uid, pkg)].append((t, bpm))
        self._by = {k: sorted(v) for k, v in by.items()}
        self._times = {k: [t for t, _ in v] for k, v in self._by.items()}

    def window(self, user_id: int, pkg: str, start: datetime, stop: datetime) -> list[tuple[datetime, int]]:
        key = (user_id, pkg)
        if key not in self._by:
            return []
        lo = bisect.bisect_left(self._times[key], start)
        hi = bisect.bisect_right(self._times[key], stop)
        return self._by[key][lo:hi]


def samples_from_csv(path: str) -> SampleIndex:
    """psql `\\copy (SELECT user_id, sample_time, bpm, source_package FROM hr_samples ...) CSV HEADER`."""
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            t = _parse_hr_time(r["sample_time"])
            if t is not None:
                out.append((int(r["user_id"]), r["source_package"] or "unknown", t, int(r["bpm"])))
    return SampleIndex(out)


# bpm used for a timestamps-only projection. It only has to survive the plausibility filter: reasons and
# coverage do not depend on its value, and zones are not reported in this mode.
_PLACEHOLDER_BPM = 100


def samples_from_record_sources_csv(path: str) -> SampleIndex:
    """Timestamps-only HR (`health_connect_record_sources` heart_rate rows): exact coverage and reason,
    no zones. The pre-merge projection — no bpm exists anywhere until S2 is deployed and HCA re-posts."""
    out = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            t = _parse_hr_time(r["record_start"])
            if t is not None:
                out.append((int(r["user_id"]), r["source_package"] or "unknown", t, _PLACEHOLDER_BPM))
    return SampleIndex(out)


def parse_hrmax_args(specs: Iterable[str]) -> dict[int, list[tuple[date, int]]]:
    """`USER=BPM@YYYY-MM-DD` -> {user: [(effective_from, bpm)]}."""
    out: dict[int, list[tuple[date, int]]] = defaultdict(list)
    for spec in specs:
        m = re.fullmatch(r"(\d+)=(\d+)@(\d{4}-\d{2}-\d{2})", spec)
        if not m:
            raise SystemExit(f"--hrmax must be USER=BPM@YYYY-MM-DD, got {spec!r}")
        out[int(m.group(1))].append((date.fromisoformat(m.group(3)), int(m.group(2))))
    return out


def _clone(s) -> "models.AerobicSession":
    """A transient copy (never attached to a session), so projecting zones cannot touch a real row."""
    return models.AerobicSession(
        id=s.id, user_id=s.user_id, source=s.source, source_package=s.source_package,
        session_date=s.session_date, start_time=s.start_time, stop_time=s.stop_time,
        sport_name=s.sport_name, duration_minutes=s.duration_minutes, hr_avg=s.hr_avg, hr_max=s.hr_max,
        cardio_load=getattr(s, "cardio_load", None),
        z1_seconds=s.z1_seconds, z2_seconds=s.z2_seconds, z3_seconds=s.z3_seconds,
        z4_seconds=s.z4_seconds, z5_seconds=s.z5_seconds)


def project_hc_zones(rows: list, samples: SampleIndex, hrmax: dict[int, list[tuple[date, int]]],
                     *, timestamps_only: bool = False) -> tuple[list[dict[str, Any]], list]:
    """Project `hc_zone_enrich` over ONE user-set of rows, in memory. Returns (per-HC-row records,
    the row set AFTER projection: transient clones, HC rows carrying the projected zones or NULL)."""
    after = [_clone(s) for s in rows]
    records: list[dict[str, Any]] = []
    for s in after:
        if s.source != aerobic_reads.HEALTH_CONNECT:
            continue
        start, stop = _utc(s.start_time), _utc(s.stop_time)
        base = {"id": s.id, "user_id": s.user_id, "date": s.session_date.isoformat(),
                "sport": s.sport_name or "unknown", "writer": s.source_package or "unknown",
                "dur_min": round((s.duration_minutes or 0.0), 1)}
        if start is None or stop is None or stop <= start:
            records.append({**base, "reason": "no_interval", "coverage": None, "zones": None,
                            "hr_avg": None, "hr_max": None, "over_ceiling": False, "near": False})
            continue
        in_force = hrmax_in_force(hrmax.get(s.user_id, []), s.session_date)
        window = (samples.window(s.user_id, s.source_package or "unknown", start, stop)
                  if in_force is not None else [])
        res = zone_session(window, start, stop, in_force)
        z = res.zones
        s.z1_seconds, s.z2_seconds, s.z3_seconds, s.z4_seconds, s.z5_seconds = z if z else (None,) * 5
        s.hr_avg, s.hr_max = (res.hr_avg, res.hr_max) if z else (None, None)
        records.append({**base, "reason": res.reason, "coverage": res.coverage,
                        "zones": None if timestamps_only else z, "hrmax": in_force,
                        "hr_avg": None if timestamps_only else res.hr_avg,
                        "hr_max": None if timestamps_only else res.hr_max,
                        "over_ceiling": res.over_ceiling and not timestamps_only,
                        "near": res.coverage is not None and abs(res.coverage - MIN_ZONE_COVERAGE) <= NEAR_THRESHOLD})
    return records, after


def canonical_flips(before: list, after: list) -> list[dict[str, Any]]:
    """Bouts whose canonical row differs between two states of the SAME session set (ids match)."""
    aerobic_reads.arbitrate(before)
    aerobic_reads.arbitrate(after)
    old = {s.id: bool(s.canonical) for s in before}
    new = {s.id: bool(s.canonical) for s in after}
    b_by, a_by = {s.id: s for s in before}, {s.id: s for s in after}
    lost = [b_by[i] for i in b_by if old[i] and not new.get(i, False)]
    gained = [a_by[i] for i in a_by if not old.get(i, False) and new[i]]
    recs: list[dict[str, Any]] = []
    used: set[int] = set()
    for l in sorted(lost, key=lambda s: (s.session_date, s.id)):
        partner = next((g for g in gained if g.id not in used and _same_bout(l, g)), None)
        if partner is not None:
            used.add(partner.id)
        recs.append(_record(l, partner))
    for g in sorted(gained, key=lambda s: (s.session_date, s.id)):
        if g.id not in used:
            recs.append(_record(None, g))
    return recs


def trimp_by_day(rows: list) -> dict[str, float]:
    """Edwards TRIMP per local day over the CANONICAL, qualifying rows — the transform's own rule
    (`load_events_metabolic.compute_metabolic_load_events`), without writing a load_event."""
    aerobic_reads.arbitrate(rows)
    out: dict[str, float] = defaultdict(float)
    for s in rows:
        if not s.canonical:
            continue
        ml = compute_metabolic_load({1: s.z1_seconds, 2: s.z2_seconds, 3: s.z3_seconds,
                                     4: s.z4_seconds, 5: s.z5_seconds})
        if ml.qualifying:
            out[s.session_date.isoformat()] += ml.trimp
    return dict(out)


def trimp_delta(before: list, after: list) -> list[tuple[str, float, float]]:
    b, a = trimp_by_day(before), trimp_by_day(after)
    days = sorted(set(b) | set(a))
    return [(d, b.get(d, 0.0), a.get(d, 0.0)) for d in days if abs(a.get(d, 0.0) - b.get(d, 0.0)) > 1e-9]


def polar_twin_comparison(after: list, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For every zoned HC row sharing a bout with a Polar row: minutes per band, HC-zoned vs the Polar
    row's own stored zones (the interim invariance check — divergence is an operator ruling)."""
    by_id = {s.id: s for s in after}
    out = []
    for rec in records:
        if rec["zones"] is None:
            continue
        hc = by_id[rec["id"]]
        for p in after:
            if p.source.startswith("polar_") and p.user_id == hc.user_id and _same_bout(hc, p):
                pz = [p.z1_seconds, p.z2_seconds, p.z3_seconds, p.z4_seconds, p.z5_seconds]
                if any(v is None for v in pz):
                    continue
                out.append({"hc_id": hc.id, "hc_writer": hc.source_package, "polar_id": p.id,
                            "polar_source": p.source, "date": rec["date"], "sport": rec["sport"],
                            "hc_min": [round(v / 60.0, 2) for v in rec["zones"]],
                            "polar_min": [round(v / 60.0, 2) for v in pz]})
    return out


def render_hc_zone_report(records, flips, deltas, twins, *, timestamps_only: bool = False) -> str:
    L: list[str] = []
    zoned = [r for r in records if r["reason"] == "none"]
    reasons: dict[str, int] = defaultdict(int)
    for r in records:
        reasons[r["reason"]] += 1
    L.append(f"HC rows: {len(records)}. Projected zoned: {len(zoned)}. "
             f"Reasons: " + ", ".join(f"{k}={v}" for k, v in sorted(reasons.items())) + ".")
    L.append(f"MIN_ZONE_COVERAGE = {MIN_ZONE_COVERAGE}; rows within +-{NEAR_THRESHOLD} of it are marked NEAR.")
    if timestamps_only:
        L.append("TIMESTAMPS-ONLY projection: coverage and reason are exact, zones/hr are not available (no bpm yet).")
    L += ["", "| id | date | sport | writer | min | HRmax | coverage | reason | zones s (z1..z5) | hr avg/max | flags |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(records, key=lambda r: (r["date"], r["id"])):
        cov = "-" if r["coverage"] is None else f"{r['coverage']:.3f}"
        zs = "-" if r["zones"] is None else "/".join(str(v) for v in r["zones"])
        hr = "-" if r["hr_avg"] is None else f"{r['hr_avg']}/{r['hr_max']}"
        flags = ", ".join(f for f, on in (("NEAR", r["near"]), ("OVER-CEILING", r["over_ceiling"])) if on) or ""
        L.append(f"| #{r['id']} | {r['date']} | {r['sport']} | {r['writer']} | {r['dur_min']} | "
                 f"{r.get('hrmax') or '-'} | {cov} | {r['reason']} | {zs} | {hr} | {flags} |")
    over = [r for r in records if r["over_ceiling"]]
    L += ["", f"Over-ceiling rows (flag only; HRmax is never auto-raised): {len(over)}."]
    for r in over:
        L.append(f"  - #{r['id']} {r['date']} {r['sport']}: max {r['hr_max']} > HRmax {r.get('hrmax')}")
    L += ["", f"Canonical flips once the projected zones exist: {len(flips)}."]
    if flips:
        L += ["", "| user | date | sport | old canonical | new canonical | metabolic effect |", "|---|---|---|---|---|---|"]
        for f in flips:
            effect = ("bout NEWLY scored" if f["newly_scoreable"]
                      else "bout NO LONGER scored" if f["no_longer_scoreable"] else "none (scoring unchanged)")
            L.append(f"| {f['user_id']} | {f['date']} | {f['sport']} | {_cell(f['old'])} | {_cell(f['new'])} | {effect} |")
    L += ["", f"Per-day metabolic TRIMP delta (canonical, qualifying rows): {len(deltas)} day(s) change."]
    if deltas:
        L += ["", "| day | before | after | delta |", "|---|---|---|---|"]
        for d, b, a in deltas:
            L.append(f"| {d} | {b:.1f} | {a:.1f} | {a - b:+.1f} |")
        L.append(f"| **total** | {sum(b for _, b, _ in deltas):.1f} | {sum(a for _, _, a in deltas):.1f} | "
                 f"{sum(a - b for _, b, a in deltas):+.1f} |")
    L += ["", f"HC-zoned vs Polar-zoned minutes per band (HC rows sharing a bout with a Polar row): {len(twins)}."]
    for t in twins:
        diff = [round(h - p, 2) for h, p in zip(t["hc_min"], t["polar_min"])]
        L += [f"", f"  {t['date']} {t['sport']}: HC #{t['hc_id']} [{t['hc_writer']}] vs {t['polar_source']} #{t['polar_id']}",
              f"    HC    z1..z5 min: {t['hc_min']}", f"    Polar z1..z5 min: {t['polar_min']}",
              f"    HC - Polar:       {diff}"]
    return "\n".join(L)


def hc_zone_report_from_rows(rows: list, samples: SampleIndex, hrmax: dict, *, timestamps_only: bool = False) -> str:
    """The whole G2 report for ONE user's full session set."""
    before = [_clone(s) for s in rows]
    try:
        records, after = project_hc_zones(rows, samples, hrmax, timestamps_only=timestamps_only)
    except ValueError as exc:       # `hrmax_in_force` refuses an ambiguous or incoherent entry set
        raise SystemExit(f"HRmax entries cannot be resolved: {exc}")
    return render_hc_zone_report(records, canonical_flips(before, after), trimp_delta(before, after),
                                 [] if timestamps_only else polar_twin_comparison(after, records),
                                 timestamps_only=timestamps_only)


def _hc_zones_main(args) -> int:
    """`--hc-zones`: the G2 projection. DB mode reads `hr_samples` + `user_hrmax` (post-deploy); CSV
    mode reads exports (`--csv` aerobic_sessions plus `--samples-csv` or `--record-sources-csv`)."""
    extra = parse_hrmax_args(args.hrmax or [])
    timestamps_only = bool(args.record_sources_csv)
    if args.csv:
        by_user = rows_from_csv(args.csv)
        if not (args.samples_csv or args.record_sources_csv):
            raise SystemExit("CSV mode needs --samples-csv (hr_samples export) or --record-sources-csv (timestamps only)")
        samples = (samples_from_record_sources_csv(args.record_sources_csv) if timestamps_only
                   else samples_from_csv(args.samples_csv))
        hrmax = {u: list(v) for u, v in extra.items()}
    else:
        from database import SessionLocal
        db = SessionLocal()
        try:
            if db.get_bind().dialect.name == "postgresql":
                db.execute(text("SET TRANSACTION READ ONLY"))
            by_user = {}
            q = db.query(models.AerobicSession)
            if args.user is not None:
                q = q.filter(models.AerobicSession.user_id == args.user)
            for s in q.order_by(models.AerobicSession.id).all():
                by_user.setdefault(s.user_id, []).append(s)
            try:
                triples = [(h.user_id, h.source_package, _utc(h.sample_time), h.bpm)
                           for h in db.query(models.HrSample).filter(
                               models.HrSample.source == aerobic_reads.HEALTH_CONNECT).all()]
                stored = db.query(models.UserHrmax).all()
            except Exception as exc:  # noqa: BLE001
                raise SystemExit(f"hr_samples / user_hrmax unreadable ({type(exc).__name__}): the migration has not run "
                                 "here. Pre-merge, use CSV mode with --record-sources-csv.")
            samples = SampleIndex(triples)
            hrmax = defaultdict(list)
            for h in stored:
                hrmax[h.user_id].append(entry_from_row(h))
            for u, v in extra.items():
                hrmax[u].extend(v)
            hrmax = dict(hrmax)
            reports = []
            for uid, rows in sorted(by_user.items()):
                if any(s.source == aerobic_reads.HEALTH_CONNECT for s in rows):
                    reports.append(f"## user {uid}\n\n" + hc_zone_report_from_rows(rows, samples, hrmax))
            db.rollback()                       # nothing was written; end the read transaction
            print("\n\n".join(reports) if reports else "No health_connect rows.")
            return 0
        finally:
            db.close()
    if args.user is not None:
        by_user = {u: r for u, r in by_user.items() if u == args.user}
    reports = [f"## user {uid}\n\n" + hc_zone_report_from_rows(rows, samples, hrmax, timestamps_only=timestamps_only)
               for uid, rows in sorted(by_user.items())
               if any(s.source == aerobic_reads.HEALTH_CONNECT for s in rows)]
    print("\n\n".join(reports) if reports else "No health_connect rows.")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Read-only dry run: which bouts flip canonical row under A6, "
                                             "or (--hc-zones) what the HC zone fill would do.")
    ap.add_argument("--user", type=int, default=None, help="only this user id (DB mode)")
    ap.add_argument("--csv", default=None, help="a psql \\copy export of aerobic_sessions instead of the DB")
    ap.add_argument("--hc-zones", dest="hc_zones", action="store_true",
                    help="project the HC zone fill (Q159 stage 2) instead of the A6 flip report")
    ap.add_argument("--samples-csv", dest="samples_csv", default=None, help="hr_samples export (with --hc-zones --csv)")
    ap.add_argument("--record-sources-csv", dest="record_sources_csv", default=None,
                    help="HR timestamps export, pre-merge (coverage/reason only; with --hc-zones --csv)")
    ap.add_argument("--hrmax", action="append", default=None, metavar="USER=BPM@YYYY-MM-DD",
                    help="HRmax entry (repeatable); CSV mode's only source, added to user_hrmax in DB mode")
    args = ap.parse_args(argv)

    if args.hc_zones:
        return _hc_zones_main(args)

    if args.csv:
        by_user = rows_from_csv(args.csv)
        if args.user is not None:
            by_user = {u: r for u, r in by_user.items() if u == args.user}
        records = sorted((rec for rows in by_user.values() for rec in flip_report_from_rows(rows)),
                         key=lambda r: (r["date"], r["user_id"]))
        seen = sum(len(r) for r in by_user.values())
    else:
        from database import SessionLocal
        db = SessionLocal()
        try:
            seen = db.query(models.AerobicSession).count()
            records = flip_report(db, args.user)
        finally:
            db.close()
    print(render_markdown(records, sessions_seen=seen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
