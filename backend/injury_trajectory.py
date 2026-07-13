"""Injury expected-trajectory evaluation (Step 3).

Injury entries (`user_knowledge_entries` type='injury') may carry a `trajectory`
in their JSON `value` — no schema change; it sits alongside signal_type/
restrictions/detail:

    "trajectory": {
        "shape": "settling" | "stable" | "resolving_by",
        "declared_on": "YYYY-MM-DD",             # baseline for divergence timing
        "resolve_by": "YYYY-MM-DD",              # resolving_by only
        "review_when": {"metric": "soreness", "op": "<=", "threshold": 1,
                        "sustained_days": 3},    # symptom-gated exit condition
    }

Two consumers, both SURFACING ONLY — neither alters restrictions[] nor gates
selection. Restrictions are set at injury onset; the check-in monitors, it does
not renegotiate (see DECISIONS_LOG). Divergence = observed soreness contradicts
the plan's expected trajectory. Review = soreness reaches the symptom-gated exit
condition → prompt to revisit. Rhymes with the lab-side declare-expectation /
flag-divergence / never-suppress pattern (#63) in shape only — no shared code
(lab is marker/delta semantics; this is a soreness series vs a declared shape).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

import models


def injury_soreness_key(value: dict[str, Any]) -> str:
    """Stable soreness key for an injury entry. `body_part` alone collides when the
    same part is injured on both sides (left + right hamstring), so sided injuries
    carry the side. Maps back to the injury via (body_part, side); never free-floats."""
    body_part = str(value.get("body_part", "injury")).strip().lower().replace(" ", "_")
    side = str(value.get("side", "")).strip().lower()
    if side in ("", "bilateral", "both"):
        return body_part
    return f"{body_part}_{side}"


def _parse_date(s: Any) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _soreness_series(
    user_id: int, key: str, db: Session, since: date | None = None
) -> list[tuple[date, int]]:
    """Ascending (date, soreness) for one injury key, read from daily_records."""
    q = db.query(models.DailyRecord).filter(
        models.DailyRecord.user_id == user_id,
        models.DailyRecord.soreness.isnot(None),
    )
    if since is not None:
        q = q.filter(models.DailyRecord.date >= since)
    out: list[tuple[date, int]] = []
    for r in q.order_by(models.DailyRecord.date.asc()).all():
        v = (r.soreness or {}).get(key)
        if v is not None:
            try:
                out.append((r.date, int(v)))
            except (TypeError, ValueError):
                pass
    return out


_MIN_SETTLING_WINDOW_DAYS = 4      # don't call "not settling" before this much elapsed
_STABLE_SURPRISE_DELTA = 2         # a move >= this from baseline is a surprise


def _divergence_message(
    shape: str,
    series: list[tuple[date, int]],
    resolve_by: date | None,
    today: date,
) -> str | None:
    pts = series
    if shape == "settling":
        if len(pts) >= 2:
            (first_d, first_v), (last_d, last_v) = pts[0], pts[-1]
            elapsed = (last_d - first_d).days
            if elapsed >= _MIN_SETTLING_WINDOW_DAYS and last_v >= first_v:
                return (
                    f"expected settling, but soreness flat/rising "
                    f"({first_v}->{last_v} over {elapsed}d) — plan may be wrong, revisit"
                )
    elif shape == "stable":
        if len(pts) >= 2:
            base_v, last_v = pts[0][1], pts[-1][1]
            if abs(last_v - base_v) >= _STABLE_SURPRISE_DELTA:
                direction = "worsening" if last_v > base_v else "improving"
                return (
                    f"expected stable, but soreness {direction} "
                    f"({base_v}->{last_v}) — surprise worth surfacing"
                )
    elif shape == "resolving_by":
        if resolve_by is not None and today > resolve_by:
            last_v = pts[-1][1] if pts else None
            if last_v is None or last_v > 1:
                shown = last_v if last_v is not None else "unknown"
                return (
                    f"expected resolved by {resolve_by}, still symptomatic "
                    f"(soreness {shown}) — revisit"
                )
    return None


_OPS = {
    "<=": lambda v, t: v <= t, ">=": lambda v, t: v >= t,
    "<": lambda v, t: v < t, ">": lambda v, t: v > t, "==": lambda v, t: v == t,
}


def _review_message(
    review_when: dict | None, series: list[tuple[date, int]]
) -> str | None:
    if not review_when:
        return None
    thr = review_when.get("threshold")
    op = review_when.get("op", "<=")
    n = int(review_when.get("sustained_days", 1) or 1)
    fn = _OPS.get(op)
    if thr is None or fn is None or len(series) < n:
        return None
    tail = series[-n:]
    if all(fn(v, thr) for _, v in tail):
        return (
            f"review trigger: soreness {op} {thr} sustained {n}d — "
            f"looks resolved, review the restriction"
        )
    return None


def evaluate(user_id: int, db: Session, today: date | None = None) -> dict[str, list[dict]]:
    """Divergence + symptom-gated review flags for the user's active injuries that
    declare a trajectory. Surfacing only — returns messages, changes nothing."""
    today = today or date.today()
    rows = (
        db.query(models.UserKnowledgeEntry)
        .filter_by(user_id=user_id, type="injury", active=True)
        .all()
    )
    divergences: list[dict] = []
    reviews: list[dict] = []
    for r in rows:
        val = r.value or {}
        traj = val.get("trajectory")
        if not traj:
            continue
        key = injury_soreness_key(val)
        label = key.replace("_", " ")
        declared_on = _parse_date(traj.get("declared_on"))
        resolve_by = _parse_date(traj.get("resolve_by"))
        series = _soreness_series(user_id, key, db, since=declared_on)

        dmsg = _divergence_message(
            str(traj.get("shape", "")).lower(), series, resolve_by, today
        )
        if dmsg:
            divergences.append({"key": key, "label": label, "message": dmsg})

        rmsg = _review_message(traj.get("review_when"), series)
        if rmsg:
            reviews.append({"key": key, "label": label, "message": rmsg})
    return {"divergences": divergences, "reviews": reviews}
