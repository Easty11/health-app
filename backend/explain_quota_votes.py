"""Explain Rule 1 per workout: the per-capacity PRIMARY-tag votes behind each quota credit (#338).

READ-ONLY. Never writes. For each counted (non-excluded, adjudicated-dedup) Hevy workout on the
given LOCAL (Brisbane) days, prints every exercise's primary capacities, the vote totals, the
dominant capacity and what the resolver does with it (counted / off_plan / untagged), using the
resolver's OWN Rule 1 functions so this explanation cannot drift from the count.

    python explain_quota_votes.py <user_id> <YYYY-MM-DD> [<YYYY-MM-DD> ...]
"""
from __future__ import annotations

import sys
from datetime import date

from sqlalchemy.orm import Session

from engine import resolver
from engine.taxonomy import Capacity


def explain(db: Session, user_id: int, days: list[date]) -> list[dict]:
    out: list[dict] = []
    for day in days:
        window = resolver.resolve_window(db, user_id, day)
        slot_order = [s.capacity for s in (window.slots if window else []) if s.kind == "capacity"]
        one_day = resolver.QuotaWindow(start_date=day, end_date=day, label="explain", source="explain")
        workouts, _ = resolver._counted_workouts(
            db, user_id, resolver._in_window_workouts(db, user_id, one_day))
        for w in workouts:
            exercises = (w.raw or {}).get("exercises") or []
            tids = {ex.get("exercise_template_id") for ex in exercises if isinstance(ex, dict)}
            caps = resolver._primary_caps_by_template(db, {t for t in tids if t})
            votes: dict[str, int] = {}
            rows = []
            for ex in exercises:
                tid = ex.get("exercise_template_id") if isinstance(ex, dict) else None
                c = sorted(x.value for x in caps.get(tid, set()))
                for v in c:
                    votes[v] = votes.get(v, 0) + 1
                rows.append({"title": ex.get("title"), "template_id": tid, "capacities": c})
            dominant, untagged = resolver._dominant_capacity(exercises, caps, slot_order)
            outcome = ("untagged" if dominant is None
                       else "counted" if dominant in slot_order else "off_plan")
            out.append({"day": day.isoformat(), "workout": w.hevy_id, "title": w.title,
                        "votes": votes, "untagged": untagged,
                        "dominant": dominant.value if isinstance(dominant, Capacity) else None,
                        "outcome": outcome, "slots": [c.value for c in slot_order],
                        "exercises": rows})
    return out


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python explain_quota_votes.py <user_id> <YYYY-MM-DD> [...]")
        raise SystemExit(2)
    from database import SessionLocal

    _db = SessionLocal()
    try:
        for r in explain(_db, int(sys.argv[1]), [date.fromisoformat(a) for a in sys.argv[2:]]):
            print(f"{r['day']}  {r['title']}  [{r['workout']}]")
            print(f"  votes={r['votes']}  untagged={r['untagged']}  dominant={r['dominant']}  "
                  f"-> {r['outcome']}  (slots: {r['slots']})")
            for e in r["exercises"]:
                print(f"    {str(e['title'])[:40]:<40} {','.join(e['capacities']) or '-'}")
    finally:
        _db.close()
