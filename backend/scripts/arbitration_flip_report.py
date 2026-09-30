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

  DB mode (needs DATABASE_URL reachable from where it runs — e.g. `railway run` with the public URL):
      python -m scripts.arbitration_flip_report [--user N]

  CSV mode (needs only the psql route the runbook already uses — `railway connect` to health-app-DB):
      \\copy (SELECT id, user_id, source, source_package, session_date, start_time, stop_time, sport_name,
              duration_minutes, hr_avg, hr_max, z1_seconds, z2_seconds, z3_seconds, z4_seconds, z5_seconds
              FROM aerobic_sessions ORDER BY id) TO 'aerobic_sessions.csv' CSV HEADER
      python -m scripts.arbitration_flip_report --csv aerobic_sessions.csv

The bout list is what the A6 PR records, and what the operator reviews BEFORE merge.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import sys
from datetime import date, datetime
from typing import Any, Iterable, Optional

from sqlalchemy import text

import models
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


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Read-only dry run: which bouts flip canonical row under A6.")
    ap.add_argument("--user", type=int, default=None, help="only this user id (DB mode)")
    ap.add_argument("--csv", default=None, help="a psql \\copy export of aerobic_sessions instead of the DB")
    args = ap.parse_args(argv)

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
