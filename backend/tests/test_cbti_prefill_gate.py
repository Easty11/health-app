"""Step 3 — prefill clock defaults and the 4h sanity gate.

Gate 3 is the DEMONSTRATED REJECTION, not the absence of one (#110). A gate that
accepts everything and a gate that correctly rejects a corrupt value both look
like "no rejections in the run" unless the run asserts a rejection AND a pass.
Both are asserted here; the synthetic 12-hour-clock value (10:12 for 22:12) is the
negative control.
"""
from datetime import date, timedelta

import models
from routers.checkin_v2 import (
    DiaryPrefillOut,
    PREFILL_GATE_MAX_DELTA_MIN,
    _diary_prefill,
    get_prefill,
)


# ── the negative control: the gate must reject the 12h-clock corruption ──────────

def test_synthetic_12h_clock_value_is_REJECTED():
    """10:12 is how a 12-hour phone clock stores 22:12 — a 720-min error. It must be
    rejected, not prefilled, and never degraded to the raw value."""
    out = _diary_prefill(bedtime="10:12", wake_time="05:57", prescribed_lights_out="22:12")
    assert out.gate_rejected is True
    assert out.got_into_bed is None and out.lights_out is None
    assert out.final_wake is None and out.out_of_bed is None


def test_a_valid_bedtime_is_NOT_rejected():
    """The control's partner: a real bedtime 8 min from the prescription passes, so
    the rejection above is discrimination, not a gate that rejects everything."""
    out = _diary_prefill(bedtime="22:20", wake_time="05:57", prescribed_lights_out="22:12")
    assert out.gate_rejected is False
    assert out.got_into_bed == "22:20"


# ── the mapping (VERIFIED against 31 real nights: bedtime is bed-entry) ───────────

def test_bedtime_maps_to_got_into_bed_and_defaults_lights_out():
    out = _diary_prefill(bedtime="22:40", wake_time="06:10", prescribed_lights_out="22:30")
    assert out.got_into_bed == "22:40"
    assert out.lights_out == "22:40"          # defaults to got_into_bed (#117)


def test_wake_time_defaults_both_wake_side_fields():
    out = _diary_prefill(bedtime="22:40", wake_time="06:10", prescribed_lights_out="22:30")
    assert out.final_wake == "06:10" and out.out_of_bed == "06:10"


def test_latency_and_waso_are_never_in_the_prefill_shape():
    """The two fields the device biases must have no prefill slot at all — not a
    null one, an absent one — so nothing can seed them later by accident (#117)."""
    for f in ("sleep_latency_min", "waso_min"):
        assert f not in DiaryPrefillOut.model_fields


# ── gate boundary ────────────────────────────────────────────────────────────────

def test_gate_boundary_is_inclusive_at_4h():
    """Exactly 4h (240 min) is a plausible-if-extreme drift and passes; 4h+1 does
    not. The threshold sits between real drift and the 12h corruption."""
    assert PREFILL_GATE_MAX_DELTA_MIN == 240
    # 18:12 is exactly 240 min before 22:12 → passes
    assert _diary_prefill("18:12", "05:00", "22:12").gate_rejected is False
    # 18:11 is 241 min → rejected
    assert _diary_prefill("18:11", "05:00", "22:12").gate_rejected is True


def test_wrap_aware_delta_treats_2350_and_0010_as_close():
    """Midnight must not read as a 23h40m gap — clock_delta wraps. A 00:10 bedtime
    against a 23:50 prescription is 20 min apart and passes."""
    assert _diary_prefill("00:10", "05:00", "23:50").gate_rejected is False


# ── no reference → ungated (recoverable, because these are editable defaults) ─────

def test_no_prescription_passes_ungated():
    out = _diary_prefill(bedtime="19:00", wake_time="05:00", prescribed_lights_out=None)
    assert out.gate_rejected is False and out.got_into_bed == "19:00"


def test_missing_device_value_is_empty_not_rejected():
    out = _diary_prefill(bedtime=None, wake_time=None, prescribed_lights_out="22:30")
    assert out.gate_rejected is False       # absence is not a rejection
    assert out.got_into_bed is None


# ── endpoint wiring: block-gated render + the allowlist ──────────────────────────

def _user(db, email):
    u = models.User(email=email, hashed_password="x")
    db.add(u); db.commit(); db.refresh(u)
    return u


def _open_block_with_rx(db, uid, lo="22:30"):
    b = models.CBTIBlock(user_id=uid, opened_on=date(2026, 7, 1),
                         wake_anchor="05:00", open_reason="test")
    db.add(b); db.commit(); db.refresh(b)
    r = models.CBTIPrescription(block_id=b.id, effective_from=date(2026, 7, 1),
                                prescribed_lights_out=lo, wake_anchor="05:00",
                                window_minutes=390, decision="adopt")
    db.add(r); db.commit()
    return b


def _samsung(db, uid, *, captured_at, bedtime, wake_time, context="passive_overnight"):
    row = models.SamsungHRVReading(user_id=uid, captured_at=captured_at,
                                   bedtime=bedtime, wake_time=wake_time, context=context)
    db.add(row); db.commit()


def test_no_open_block_yields_empty_prefill(db_session):
    u = _user(db_session, "noblk@x.io")
    _samsung(db_session, u.id, captured_at=date.today(), bedtime="22:35", wake_time="05:05")
    out = get_prefill(current_user=u, db=db_session)
    assert out.diary_prefill.got_into_bed is None and out.cbti.block_open is False


def test_open_block_prefills_from_a_passive_overnight_row(db_session):
    u = _user(db_session, "blk@x.io")
    _open_block_with_rx(db_session, u.id, lo="22:30")
    _samsung(db_session, u.id, captured_at=date.today(), bedtime="22:35", wake_time="05:05")
    out = get_prefill(current_user=u, db=db_session)
    assert out.cbti.block_open is True
    assert out.diary_prefill.got_into_bed == "22:35"
    assert out.diary_prefill.lights_out == "22:35"


def test_prefill_ignores_a_calibration_row_the_denylist_would_admit(db_session):
    """The read is on the passive_overnight allowlist. A `calibration` row — which the
    readiness denylist `context != 'session'` would admit — must NOT seed the diary,
    even when it is the most recent reading."""
    u = _user(db_session, "cal@x.io")
    _open_block_with_rx(db_session, u.id, lo="22:30")
    _samsung(db_session, u.id, captured_at=date.today(),
             bedtime="09:99-bad", wake_time="00:00", context="calibration")
    _samsung(db_session, u.id, captured_at=date.today() - timedelta(days=1),
             bedtime="22:40", wake_time="05:10", context="passive_overnight")
    out = get_prefill(current_user=u, db=db_session)
    # the calibration row is the newest, but the allowlist skips it for the overnight one
    assert out.diary_prefill.got_into_bed == "22:40"


def test_endpoint_rejects_a_12h_corrupt_overnight_row(db_session):
    """Full path: a corrupt passive_overnight value reaches the gate and is suppressed."""
    u = _user(db_session, "corrupt@x.io")
    _open_block_with_rx(db_session, u.id, lo="22:12")
    _samsung(db_session, u.id, captured_at=date.today(), bedtime="10:12", wake_time="05:57")
    out = get_prefill(current_user=u, db=db_session)
    assert out.diary_prefill.gate_rejected is True
    assert out.diary_prefill.got_into_bed is None
