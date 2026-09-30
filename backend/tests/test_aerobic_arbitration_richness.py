"""Brief A / A6 — richness-first arbitration: a row without HR never suppresses a same-bout row with HR.

`_win_key` gains a data tier as its FIRST term, in both regimes (cross-source and HC-HC writer-class):
tier 2 = usable zones, tier 1 = avg HR present with no usable zones, tier 0 = neither. Within a tier the
key that stood before (source rank / writer class -> duration -> start -> id) is unchanged.

Gates (G4):
  * zoned v4 vs zoneless flow_export            -> v4 wins            (the tier overrides the source rank)
  * HC-with-HR vs zoneless v4 (no HR)           -> HC wins
  * both zoned                                  -> source rank decides (unchanged)
  * two HC rows, one with HR                    -> HR wins regardless of duration and writer class
  * all-tier-0 pairs                            -> identical result to master (property test vs a frozen
                                                   copy of master's ordering)
  * mutation check                              -> with the tier removed the discriminating tests fail
                                                   (proved in-suite by patching `_data_tier` to a constant)
Fixtures are synthetic placeholders.
"""
import random
from datetime import datetime, timedelta, timezone

import pytest

import models
from reads import aerobic_reads
from reads.aerobic_reads import arbitrate

T0 = datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc)
NATIVE = "com.sec.android.app.shealth"        # wearable_native
MIRROR = "com.withings.wiscale2"              # aggregator_mirror


def _row(sid, source, *, start_min=0, minutes=45, hr=None, zones=None, package=None):
    start = T0 + timedelta(minutes=start_min)
    z = zones or (None,) * 5
    return models.AerobicSession(
        id=sid, user_id=1, source=source, session_date=start.date(), start_time=start,
        stop_time=start + timedelta(minutes=minutes), duration_minutes=minutes,
        hr_avg=hr, z1_seconds=z[0], z2_seconds=z[1], z3_seconds=z[2], z4_seconds=z[3], z5_seconds=z[4],
        source_package=package,
    )


ZONED = (0, 600, 1800, 300, 0)


def _winner(*rows):
    arbitrate(list(rows))
    won = [r for r in rows if r.canonical]
    assert len(won) == 1, [(r.id, r.source, r.canonical) for r in rows]
    return won[0]


# ── the tiers ────────────────────────────────────────────────────────────────

def test_data_tier_values():
    assert aerobic_reads._data_tier(_row(1, "polar_v4", zones=ZONED, hr=140)) == 2
    assert aerobic_reads._data_tier(_row(2, "polar_v4", zones=ZONED)) == 2                 # zones alone is tier 2
    assert aerobic_reads._data_tier(_row(3, "health_connect", hr=120)) == 1
    assert aerobic_reads._data_tier(_row(4, "polar_v4", hr=120, zones=(0, 0, 0, 0, 0))) == 1   # zero-sum zones: unusable
    assert aerobic_reads._data_tier(_row(5, "polar_flow_export")) == 0
    assert aerobic_reads._data_tier(_row(6, "health_connect", zones=(None,) * 5)) == 0


# ── G4 — cross-source regime ─────────────────────────────────────────────────

def test_zoned_v4_beats_zoneless_flow_export():
    """The source rank alone put flow_export (3) above v4 (2); a zoneless export row then suppressed a zoned
    v4 row and the transform dropped the bout (INV-7)."""
    v4 = _row(1, "polar_v4", zones=ZONED, hr=141)
    export = _row(2, "polar_flow_export")                              # zoneless, no HR — tier 0
    assert _winner(v4, export) is v4


def test_hc_with_hr_beats_zoneless_v4_without_hr():
    hc = _row(1, "health_connect", hr=118, package=NATIVE)
    v4 = _row(2, "polar_v4")                                           # zoneless, no HR
    assert _winner(hc, v4) is hc


def test_both_zoned_source_rank_still_decides():
    v4 = _row(1, "polar_v4", zones=ZONED, hr=141)
    export = _row(2, "polar_flow_export", zones=ZONED, hr=141)
    assert _winner(v4, export) is export                               # same tier: flow_export > v4, unchanged


def test_same_tier_hr_only_source_rank_still_decides():
    hc = _row(1, "health_connect", hr=118, package=NATIVE)
    v4 = _row(2, "polar_v4", hr=119)                                   # both tier 1 → v4 (rank 2) > hc (rank 1)
    assert _winner(hc, v4) is v4


def test_tier_leads_duration_too_in_the_cross_source_regime():
    short_rich = _row(1, "health_connect", hr=118, minutes=30, package=NATIVE)
    long_poor = _row(2, "polar_v4", minutes=60)                        # longer, higher rank — but tier 0
    assert _winner(short_rich, long_poor) is short_rich


# ── G4 — HC–HC writer-class regime ───────────────────────────────────────────

def test_two_hc_rows_one_with_hr_hr_wins_regardless_of_duration():
    with_hr = _row(1, "health_connect", hr=121, minutes=30, package=NATIVE)
    no_hr_longer = _row(2, "health_connect", minutes=50, start_min=1, package=NATIVE)   # same class, longer
    assert _winner(with_hr, no_hr_longer) is with_hr


def test_two_hc_rows_hr_wins_regardless_of_writer_class():
    """Ruling 1 ranked wearable-native above an aggregator mirror; the tier now leads it."""
    mirror_with_hr = _row(1, "health_connect", hr=121, package=MIRROR)
    native_no_hr = _row(2, "health_connect", package=NATIVE)
    assert _winner(mirror_with_hr, native_no_hr) is mirror_with_hr


def test_two_hc_rows_same_tier_writer_class_then_duration_unchanged():
    native = _row(1, "health_connect", hr=120, package=NATIVE, minutes=30)
    mirror = _row(2, "health_connect", hr=120, package=MIRROR, minutes=50)
    assert _winner(native, mirror) is native                            # same tier: writer class decides


# ── G4 — all-tier-0 pairs are exactly master's result ────────────────────────

def _master_win_key(session, dur, start_ts, *, by_writer):
    """Frozen copy of `_win_key` as it stood on master before A6 (no data tier)."""
    rank = (aerobic_reads.writer_class_rank(session.source_package) if by_writer
            else aerobic_reads._rank(session.source))
    return (rank, dur, -start_ts, -(session.id if session.id is not None else 0))


def _master_canonical(sessions):
    """Master's `arbitrate` verbatim, over the frozen key. Returns the set of canonical ids."""
    ts = aerobic_reads._ts
    iv = {}
    for s in sessions:
        a, b = ts(s.start_time), ts(s.stop_time)
        if a is not None and b is not None and b > a:
            iv[id(s)] = (a, b, b - a)
    canon = set()
    for x in sessions:
        xi = iv.get(id(x))
        ok = True
        if xi is not None:
            for y in sessions:
                if y is x:
                    continue
                same = y.source == x.source
                if same and x.source != aerobic_reads.HEALTH_CONNECT:
                    continue
                yi = iv.get(id(y))
                if yi is None:
                    continue
                if min(xi[1], yi[1]) - max(xi[0], yi[0]) < aerobic_reads.OVERLAP_THRESHOLD * min(xi[2], yi[2]):
                    continue
                if _master_win_key(y, yi[2], yi[0], by_writer=same) > _master_win_key(x, xi[2], xi[0], by_writer=same):
                    ok = False
                    break
        if ok:
            canon.add(x.id)
    return canon


def test_all_tier_0_sets_arbitrate_exactly_as_master():
    """Property test: random sets of zoneless, HR-less rows (all tier 0) — every source mix, writer class,
    overlap and duration — get the same canonical set as master's frozen ordering."""
    rng = random.Random(20260930)
    sources = ["polar_flow_export", "polar_v4", "health_connect", "mystery"]
    packages = [NATIVE, MIRROR, "com.unknown.app", None]
    for _ in range(300):
        rows = []
        for i in range(rng.randint(2, 6)):
            rows.append(_row(i + 1, rng.choice(sources), start_min=rng.choice([0, 0, 2, 5, 20, 60]),
                             minutes=rng.choice([20, 30, 45, 60]), package=rng.choice(packages)))
        arbitrate(rows)
        assert {r.id for r in rows if r.canonical} == _master_canonical(rows)


# ── mutation check — the tests above can fail ────────────────────────────────

def test_removing_the_tier_restores_the_suppression(monkeypatch):
    """With `_data_tier` neutralised (the tier removed) the discriminating cases come out as master had
    them — the richer row is suppressed. This is what makes the tests above real: they pass only because
    the tier is there."""
    monkeypatch.setattr(aerobic_reads, "_data_tier", lambda s: 0)

    v4 = _row(1, "polar_v4", zones=ZONED, hr=141)
    export = _row(2, "polar_flow_export")
    assert _winner(v4, export) is export                               # master: the zoneless export row won

    hc = _row(3, "health_connect", hr=118, package=NATIVE)
    v4b = _row(4, "polar_v4")
    assert _winner(hc, v4b) is v4b                                     # master: the row without HR won

    with_hr = _row(5, "health_connect", hr=121, minutes=30, package=NATIVE)
    longer = _row(6, "health_connect", minutes=50, start_min=1, package=NATIVE)
    assert _winner(with_hr, longer) is longer                          # master: duration beat HR


# ── the transform consequence (why the tier matters) ─────────────────────────

def test_the_canonical_row_of_a_zoned_zoneless_pair_is_scoreable(db_session):
    """End to end through the metabolic transform: the zoned v4 row is canonical, so the bout is scored
    (on master the zoneless export twin was canonical and the bout was skipped, INV-7)."""
    import load_events_metabolic as m

    u = models.User(email="t@example.com", hashed_password="x")
    db_session.add(u)
    db_session.commit()
    for r in (_row(None, "polar_v4", zones=ZONED, hr=141), _row(None, "polar_flow_export")):
        r.user_id = u.id
        r.source_session_id = f"s-{r.source}"
        db_session.add(r)
    db_session.commit()

    out = m.compute_metabolic_load_events(db_session, u.id)
    assert out["events_written"] == 1
    assert out["sessions_skipped_no_zones"] == 0
    ev = db_session.query(models.LoadEvent).filter_by(user_id=u.id, formula_version=m.FORMULA_VERSION_METABOLIC).one()
    assert ev.provenance["zone_source"] == "polar_v4"
