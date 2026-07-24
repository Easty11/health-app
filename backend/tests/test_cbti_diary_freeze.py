"""Step B — AM submit accepts the diary fields and FREEZES diary_se_pct / diary_tst_min.

The freeze is the branch's highest-risk assertion (it ends timeutil's dormancy on the
STORED path). Its test needs a mutation control AND ITS INVERSE: "the frozen value did
not move on read" also passes if the value was never written, so a sanctioned recompute
that DOES move it must accompany it — otherwise the control cannot tell frozen from absent.
"""
from datetime import date

import models
from routers.checkin_v2 import (
    AMCheckInIn,
    DailyRecordOut,
    _freeze_diary,
    submit_am,
)


def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _am_body(**diary):
    base = dict(morning_readiness=3, sleep_quality=3, fatigue=5, motivation=5, life_load=3)
    base.update(diary)
    return AMCheckInIn(**base)


# ── the formula, validated 12/12 against block 2's stored rows ────────────────────

def test_freeze_matches_the_va_formula():
    # block-2 night 2026-03-19: lo=22:35 fw=05:00 oob=05:00 lat=5 waso=30 -> 350 / 90.91
    tst, se, valid = _freeze_diary("22:35", "05:00", "05:00", 5, 30)
    assert valid and tst == 350 and se == 90.91


def test_freeze_wraps_past_midnight():
    # lo after midnight: 00:05 -> 05:20 window, no wrap; tst = 315
    tst, se, valid = _freeze_diary("00:05", "05:20", "08:45", 0, 0)
    assert valid and tst == 315


# ── night-validity filter ─────────────────────────────────────────────────────────

def test_scored_sleep_exceeding_window_is_rejected():
    # final_wake (06:00) after out_of_bed (05:55): sleep_period 420 > tib 415 -> invalid
    tst, se, valid = _freeze_diary("23:00", "06:00", "05:55", 0, 0)
    assert valid is False and tst is None and se is None


def test_negative_tst_is_rejected():
    # latency+waso exceed the sleep period -> tst < 0
    tst, se, valid = _freeze_diary("22:00", "06:00", "06:10", 500, 100)
    assert valid is False and tst is None


def test_missing_inputs_are_invalid_not_zero():
    assert _freeze_diary("22:00", None, "06:00", 5, 10)[2] is False
    assert _freeze_diary("22:00", "06:00", "06:10", None, 10)[2] is False
    assert _freeze_diary(None, "06:00", "06:10", 5, 10)[2] is False


# ── the derived pair is never a client input ──────────────────────────────────────

def test_derived_pair_is_not_accepted_from_the_client():
    for f in ("diary_se_pct", "diary_tst_min"):
        assert f not in AMCheckInIn.model_fields


# ── mutation control AND its inverse ──────────────────────────────────────────────

def test_freeze_is_stored_not_recomputed_on_read(db_session):
    u = _user(db_session, "freeze@x.io")
    body = _am_body(lights_out="22:30", final_wake="05:30", out_of_bed="05:40",
                    sleep_latency_min=10, waso_min=20)
    rec = submit_am(body=body, current_user=u, db=db_session)
    # tib=between(22:30,05:40)=430, sleep_period=between(22:30,05:30)=420, tst=420-10-20=390
    assert rec.diary_tst_min == 390
    tst0, se0 = rec.diary_tst_min, rec.diary_se_pct

    # mutate a derived-from input DIRECTLY (not through submit)
    rec.waso_min = rec.waso_min + 60
    db_session.commit()

    # re-read through the response model — must NOT recompute from the new waso
    rec2 = db_session.query(models.DailyRecord).filter_by(user_id=u.id).first()
    reread = DailyRecordOut.model_validate(rec2)
    assert reread.diary_tst_min == tst0 and reread.diary_se_pct == se0

    # INVERSE: the recompute path IS sensitive to that input, so "did not move" above
    # is a real freeze and not a value that never moves or was never written.
    tst_re, se_re, _ = _freeze_diary("22:30", "05:30", "05:40",
                                     rec2.sleep_latency_min, rec2.waso_min)
    assert tst_re == tst0 - 60 and tst_re != tst0


def test_impossible_night_stores_raw_diary_but_freezes_null(db_session):
    u = _user(db_session, "imposs@x.io")
    body = _am_body(lights_out="23:00", final_wake="06:00", out_of_bed="05:55",
                    sleep_latency_min=0, waso_min=0)
    rec = submit_am(body=body, current_user=u, db=db_session)
    assert rec.lights_out == "23:00"                                  # raw diary kept
    assert rec.diary_tst_min is None and rec.diary_se_pct is None     # freeze suppressed


# ── waking-cause columns: stored, observational, no sum constraint ────────────────

def test_waking_cause_columns_are_stored(db_session):
    u = _user(db_session, "wake@x.io")
    body = _am_body(night_wakings_n=3, wakings_nocturia_n=1, wakings_pain_n=0,
                    wakings_spontaneous_n=2, lights_out="23:45", final_wake="05:30",
                    out_of_bed="05:45", sleep_latency_min=15, waso_min=10)
    rec = submit_am(body=body, current_user=u, db=db_session)
    assert rec.wakings_nocturia_n == 1
    assert rec.wakings_pain_n == 0
    assert rec.wakings_spontaneous_n == 2


def test_no_sum_constraint_between_causes_and_total(db_session):
    """Recall is imperfect; the causes need not sum to night_wakings_n. A submission
    where they disagree must persist, not be rejected."""
    u = _user(db_session, "nosum@x.io")
    body = _am_body(night_wakings_n=5, wakings_nocturia_n=1, wakings_pain_n=1,
                    wakings_spontaneous_n=0)   # 2 != 5, deliberately
    rec = submit_am(body=body, current_user=u, db=db_session)
    assert rec.night_wakings_n == 5
    assert (rec.wakings_nocturia_n, rec.wakings_pain_n, rec.wakings_spontaneous_n) == (1, 1, 0)
