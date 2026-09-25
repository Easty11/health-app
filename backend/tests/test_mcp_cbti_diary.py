"""The `get_cbti_diary` MCP tool — read-only CBT-I diary + prescription ledger + ISI.

The tool exists so a reader can pull what a CBT-I clinician works from: the nightly
recall diary (`daily_records` diary columns), the prescription history (`cbti_blocks` /
`cbti_prescriptions`) and the outcome measure (`cbti_isi`). `get_checkin_history` only
serves the ratings columns.

These run the tool's real SQL (`_load_cbti_diary`) against the in-memory SQLite schema —
so a renamed column fails here, not in prod — and exercise the pure formatter. The
`@mcp.tool()` wrapper adds only `_current_user_id()` (bearer token) + `engine.connect()`.
Mirrors `test_mcp_training_load` / `test_recovery_source_label`.

I1 sensor firewall: CBT-I reads the recall diary only. Pinned twice — the SELECT names no
sensor table/column, and the formatter renders nothing outside `_CBTI_DIARY_COLS` even
when a row carries a sensor value.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import models
from mcp_server import (
    _CBTI_BLOCKS_SQL, _CBTI_DIARY_COLS, _CBTI_DIARY_SQL, _CBTI_ISI_SQL, _CBTI_RX_SQL,
    _format_cbti_diary, _load_cbti_diary, _rx_in_force,
)


def _seed(db, uid=7, other_uid=8):
    for u in (uid, other_uid):
        db.add(models.User(id=u, email=f"u{u}@x.com", hashed_password="x"))
    db.commit()
    blk = models.CBTIBlock(id=2, user_id=uid, opened_on=date(2026, 9, 1), wake_anchor="05:30",
                           open_reason="block 3 open")
    other_blk = models.CBTIBlock(id=9, user_id=other_uid, opened_on=date(2026, 9, 1),
                                 wake_anchor="06:00")
    db.add_all([blk, other_blk])
    db.commit()
    db.add_all([
        models.CBTIPrescription(id=1, block_id=2, effective_from=date(2026, 9, 1),
                                effective_to=date(2026, 9, 10), prescribed_lights_out="22:30",
                                wake_anchor="05:30", window_minutes=420, decision="adopt",
                                basis_n_diary=7, basis_n_samsung=0, rationale="adopt\nin-flight"),
        models.CBTIPrescription(id=2, block_id=2, effective_from=date(2026, 9, 11),
                                prescribed_lights_out="21:45", wake_anchor="05:30",
                                window_minutes=465, decision="extend", basis_tst_min=400,
                                basis_se_pct=88.25, basis_nights_n=7),
        models.CBTIPrescription(id=3, block_id=9, effective_from=date(2026, 9, 1),
                                prescribed_lights_out="23:00", wake_anchor="06:00",
                                window_minutes=420, decision="adopt"),
        models.CBTIISI(block_id=2, timepoint="baseline",
                       administered_at=datetime(2026, 9, 1, 9, 10, tzinfo=timezone.utc),
                       item_1=0, item_2=3, item_3=2, item_4=3, item_5=2, item_6=2, item_7=3,
                       total_reported=16, administered_via="QxMD"),
        models.CBTIISI(block_id=9, timepoint="baseline",
                       administered_at=datetime(2026, 9, 1, 9, 10, tzinfo=timezone.utc),
                       item_1=4, item_2=4, item_3=4, item_4=4, item_5=4, item_6=4, item_7=4),
        models.CBTIISI(block_id=None, timepoint="baseline",   # screening — unattributable
                       administered_at=datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc),
                       item_1=1, item_2=1, item_3=1, item_4=1, item_5=1, item_6=1, item_7=1),
    ])
    db.add_all([
        # PM nap on 09-09 belongs to night 09-10.
        models.DailyRecord(user_id=uid, date=date(2026, 9, 9), naps_min=20),
        models.DailyRecord(user_id=uid, date=date(2026, 9, 10), got_into_bed="22:20",
                           lights_out="22:35", sleep_latency_min=15, waso_min=40,
                           night_wakings_n=3, wakings_nocturia_n=2, wakings_pain_n=0,
                           wakings_spontaneous_n=1, final_wake="05:25", out_of_bed="05:35",
                           alcohol_units=0, diary_tst_min=355, diary_se_pct=84.52,
                           passive_sleep_min=999, passive_hrv_ms=77.0),
        models.DailyRecord(user_id=uid, date=date(2026, 9, 12), lights_out="21:50",
                           final_wake="05:30", diary_tst_min=410),
        models.DailyRecord(user_id=uid, date=date(2026, 9, 13), sleep_quality=3),  # ratings only
        models.DailyRecord(user_id=other_uid, date=date(2026, 9, 12), lights_out="01:00"),
    ])
    db.commit()


import pytest


@pytest.fixture()
def db(db_session):
    _seed(db_session)
    return db_session


def _out(db, since=date(2026, 9, 10), uid=7):
    return _format_cbti_diary(_load_cbti_diary(db.connection(), uid, since), since, 42)


def test_real_sql_serves_diary_with_prescription_in_force_and_shifted_nap(db):
    out = _out(db)
    rows = [l for l in out.splitlines() if l.startswith("2026-09-1")]
    header = next(l for l in out.splitlines() if l.startswith("date | "))
    assert header.split(" | ") == ["date", "rx_id", "rx_lights_out", "rx_wake_anchor",
                                   *_CBTI_DIARY_COLS]
    n10 = dict(zip(header.split(" | "), rows[0].split(" | ")))
    assert n10["date"] == "2026-09-10" and n10["rx_id"] == "1"
    assert n10["rx_lights_out"] == "22:30" and n10["rx_wake_anchor"] == "05:30"
    assert n10["wakings_nocturia_n"] == "2" and n10["wakings_spontaneous_n"] == "1"
    assert n10["naps_min"] == "20"                  # logged PM 09-09, belongs to night 09-10
    assert n10["diary_se_pct"] == "84.5"
    n12 = dict(zip(header.split(" | "), rows[1].split(" | ")))
    assert n12["rx_id"] == "2" and n12["rx_lights_out"] == "21:45"
    assert n12["naps_min"] == "—"


def test_nap_day_before_window_is_not_served_as_a_night(db):
    out = _out(db)
    assert "2026-09-09 |" not in out                # fetched only for the nap shift


def test_ratings_only_day_is_not_a_diary_night(db):
    assert "2026-09-13 |" not in _out(db)


def test_scoped_to_the_caller(db):
    out = _out(db)
    assert "01:00" not in out                       # other user's diary
    assert "rx 3" not in out and "block 9" not in out
    assert "total=28" not in out                    # other user's ISI


def test_ledger_and_isi(db):
    out = _out(db)
    assert "block 2: 2026-09-01 → open wake_anchor=05:30" in out
    assert "rx 1 [block 2] 2026-09-01 → 2026-09-10: lights_out=22:30" in out
    assert "rx 2 [block 2] 2026-09-11 → live: lights_out=21:45" in out
    assert "basis_se_pct=88.2" in out or "basis_se_pct=88.3" in out
    assert "rationale: adopt in-flight" in out      # newlines flattened
    assert "total=15 (reported 16) items=[0, 3, 2, 3, 2, 2, 3] via=QxMD" in out
    assert "2026-09-01 19:10 [block 2, baseline]" in out   # 09:10 UTC shown in Brisbane
    assert "total=7" not in out                     # NULL-block screening not served


def test_rx_gap_between_prescriptions_has_none_in_force():
    rxs = [{"id": 1, "effective_from": date(2026, 9, 1), "effective_to": date(2026, 9, 5)},
           {"id": 2, "effective_from": date(2026, 9, 10), "effective_to": None}]
    assert _rx_in_force(date(2026, 8, 31), rxs) is None
    assert _rx_in_force(date(2026, 9, 5), rxs)["id"] == 1
    assert _rx_in_force(date(2026, 9, 7), rxs) is None
    assert _rx_in_force(date(2026, 9, 30), rxs)["id"] == 2


def test_i1_sql_names_no_sensor_source():
    sql = " ".join([_CBTI_DIARY_SQL, _CBTI_BLOCKS_SQL, _CBTI_RX_SQL, _CBTI_ISI_SQL]).lower()
    for banned in ("passive_", "health_connect", "samsung_hrv", "hrv_readings",
                   "sleep_start", "sleep_end", "sleep_onset", "hrv_ms"):
        assert banned not in sql, banned


def test_i1_formatter_renders_no_sensor_value_even_if_present(db):
    """The seeded 09-10 row carries passive_sleep_min=999 / passive_hrv_ms=77; a row
    handed straight to the formatter with those keys must not render them."""
    out = _format_cbti_diary(
        {"nights": [{"date": date(2026, 9, 10), "lights_out": "22:35",
                     "passive_sleep_min": 999, "passive_hrv_ms": 77.0}]},
        date(2026, 9, 1), 42)
    assert "999" not in out and "77" not in out
    assert "22:35" in _out(db) and "999" not in _out(db)


def test_empty_is_a_clean_readout():
    out = _format_cbti_diary({}, date(2026, 9, 1), 42)
    assert "(no diary nights since 2026-09-01)" in out
    assert "(no CBT-I blocks)" in out and "(no prescriptions)" in out
    assert "(no block-linked ISI administrations)" in out
