"""counted_workouts — the single "which hevy workouts count" door (#309).

`dedup_flag` is set on BOTH members of a suspected pair; `excluded_at` adjudicates which is
the artifact. So the RETAINED performed log must count, and `dedup_flag IS NOT TRUE` alone
(the old #276 filter) would wrongly drop it. The prod fixture below is the §18 guard: revert
the door to `dedup_flag IS NOT TRUE` and the two retained logs drop out.
"""
from datetime import datetime, timezone

import models
from reads.hevy_reads import counted_workouts


def _u(db, uid=1):
    db.add(models.User(id=uid, email=f"h{uid}@x", hashed_password="x"))
    db.commit()
    return uid


def _w(db, uid, hid, *, flagged=False, excluded=False, partners=None):
    db.add(models.HevyWorkout(
        hevy_id=hid, user_id=uid, start_time=datetime(2026, 6, 17, 6, tzinfo=timezone.utc),
        title="W", raw={"id": hid, "exercises": []},
        dedup_flag=flagged, dedup_partner_ids=partners,
        excluded_at=datetime(2026, 6, 18, tzinfo=timezone.utc) if excluded else None,
    ))
    db.commit()


def _all(db):
    return db.query(models.HevyWorkout).all()


def _ids(ws):
    return sorted(w.hevy_id for w in ws)


def test_prod_five_rows_only_retained_logs_count(db_session):
    """User 1's five flagged/excluded rows: two adjudicated pairs + a deleted-upstream row.
    Only the two RETAINED performed logs count; the two artifacts and the deleted row do not;
    nothing is unadjudicated."""
    uid = _u(db_session)
    _w(db_session, uid, "89b8f0c8", flagged=True, excluded=True, partners=["a0f298a4"])  # artifact
    _w(db_session, uid, "a0f298a4", flagged=True, partners=["89b8f0c8"])                 # performed → counts
    _w(db_session, uid, "0cd0cd00", flagged=True, excluded=True, partners=["f5d877a7"])  # artifact
    _w(db_session, uid, "f5d877a7", flagged=True, partners=["0cd0cd00"])                 # performed → counts
    _w(db_session, uid, "b3ebc404", excluded=True)                                       # deleted upstream
    counted, unadj = counted_workouts(db_session, uid, _all(db_session))
    assert _ids(counted) == ["a0f298a4", "f5d877a7"]
    assert unadj == []


def test_clean_workout_counts(db_session):
    uid = _u(db_session)
    _w(db_session, uid, "clean")
    counted, unadj = counted_workouts(db_session, uid, _all(db_session))
    assert _ids(counted) == ["clean"] and unadj == []


def test_unadjudicated_pair_neither_counts_both_surfaced(db_session):
    """A flagged pair with no excluded member — the operator has not yet adjudicated — counts
    for nothing and both are surfaced (never counted twice, never silently dropped)."""
    uid = _u(db_session)
    _w(db_session, uid, "a", flagged=True, partners=["b"])
    _w(db_session, uid, "b", flagged=True, partners=["a"])
    counted, unadj = counted_workouts(db_session, uid, _all(db_session))
    assert counted == []
    assert _ids(unadj) == ["a", "b"]


def test_partner_outside_the_candidate_set_is_still_seen(db_session):
    """The retained log counts even when its excluded partner is NOT in the candidate list
    (a re-log hours later, outside a resolver window) — partner exclusion is resolved against
    all the user's excluded workouts, not just the passed set."""
    uid = _u(db_session)
    _w(db_session, uid, "artifact", flagged=True, excluded=True, partners=["perf"])
    _w(db_session, uid, "perf", flagged=True, partners=["artifact"])
    # Pass ONLY the performed log as candidate; its partner is excluded but not in the list.
    perf = db_session.query(models.HevyWorkout).filter_by(hevy_id="perf").all()
    counted, unadj = counted_workouts(db_session, uid, perf)
    assert _ids(counted) == ["perf"] and unadj == []
