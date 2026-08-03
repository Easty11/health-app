"""CBT-I replay — adjudication against the EFFECTIVE ledger prescription (Q49).

The replay had no tests before this. The flagship here is the exact Q49 regression:
a mid-block operator correction must be adjudicated against, not read as an adherence
failure. The rest pin the structural invariant that makes that true — a cycle never
spans a prescription boundary — plus ledger-anchor use and plateau continuity.

SYNTHETIC data only; no real rows (both repos are public).
"""
from datetime import date, timedelta

from cbti.engine import CYCLE_NIGHTS, Night
from cbti.replay import LedgerRx, replay


def night(d, *, lo, tst=420, se=90.0, wake="05:00", oob="05:00", naps=0, alc=0):
    return Night(date=d, tst_min=tst, se_pct=se, lights_out=lo, out_of_bed=oob,
                 final_wake=wake, naps_min=naps, alcohol_units=alc)


def rx(ef, et, *, lo, anchor="05:00", win=390, dec="adopt"):
    return LedgerRx(effective_from=ef, effective_to=et, lights_out=lo,
                    wake_anchor=anchor, window_minutes=win, decision=dec)


def span(start, n):
    return [start + timedelta(days=i) for i in range(n)]


def _eff_from(rxs, d):
    """The prescription effective on date d = the latest effective_from <= d."""
    return max((r.effective_from for r in rxs if r.effective_from <= d), default=None)


# ── flagship: the Q49 regression ──────────────────────────────────────────────────

def test_mid_cycle_correction_is_adjudicated_not_false_held():
    """Block-3 shape: an operator correction (id=11) supersedes the opening rx (id=10)
    on the 4th night of what a fixed grid would call cycle 1. The nights run under the
    correction (22:30) must adjudicate AGAINST 22:30 — adherent — not against the
    superseded 23:45, which is the false GATE-2 HOLD Q49 names."""
    rx_a = rx(date(2026, 7, 24), date(2026, 7, 26), lo="23:45", anchor="05:45", win=360)
    rx_b = rx(date(2026, 7, 27), None, lo="22:30", anchor="05:00", win=390)

    nights = ([night(d, lo="23:45", tst=349, se=88.0) for d in span(date(2026, 7, 24), 3)]
              + [night(d, lo="22:30", tst=400, se=90.0) for d in span(date(2026, 7, 27), 7)])

    # prescriptions passed unsorted on purpose — replay sorts by effective_from
    series = replay(nights, [rx_b, rx_a], last_night=date(2026, 8, 2))

    # Cycle COUNT is a function of the cadence constant and is deliberately not asserted
    # here — this test pins WHICH PRESCRIPTION each cycle was adjudicated against, which
    # is the Q49 property and is cadence-independent.
    stub = [s for s in series if s["rx_from"] == rx_a.effective_from]
    corr = [s for s in series if s["rx_from"] == rx_b.effective_from]
    assert stub and corr

    # the 3-night stub under id=10: adjudicated against 23:45, never against 22:30
    assert all(s["rx_lights_out"] == "23:45" and s["rx_anchor"] == "05:45" for s in stub)
    assert stub[0]["from"] == date(2026, 7, 24)
    assert max(s["to"] for s in stub) == date(2026, 7, 26)   # never crosses the boundary

    # the correction's cycles: adjudicated against 22:30 → adherent → NOT an adherence
    # hold. Before Q49 these read +75 min against the seeded 23:45 and tripped
    # ADHERENCE_FAIL_N. rx_lights_out == "22:30" IS the proof the ledger, not the
    # regenerated chain, drove adjudication.
    assert all(s["rx_lights_out"] == "22:30" and s["rx_anchor"] == "05:00" for s in corr)
    assert min(s["from"] for s in corr) == date(2026, 7, 27)
    assert max(s["to"] for s in corr) == date(2026, 8, 2)
    assert all("adherence" not in s["reason"] for s in corr)
    assert all(s["decision"] == "extend" for s in corr)
    # nse counts nights logged since THIS prescription took effect and resets at the
    # boundary (#124) — so the correction's last cycle sees all 7 of its nights, however
    # many cycles the cadence split them into.
    assert corr[-1]["nse"] == 7


# ── the invariant that makes the flagship hold ────────────────────────────────────

def test_no_cycle_spans_a_prescription_boundary():
    rx_a = rx(date(2026, 7, 24), date(2026, 7, 30), lo="22:30", win=390)
    rx_b = rx(date(2026, 7, 31), None, lo="22:00", win=420)
    nights = ([night(d, lo="22:30") for d in span(date(2026, 7, 24), 7)]
              + [night(d, lo="22:00") for d in span(date(2026, 7, 31), 7)])

    series = replay(nights, [rx_a, rx_b], last_night=date(2026, 8, 6))
    rxs = [rx_a, rx_b]
    for s in series:
        # the effective prescription is identical at both ends of the cycle window,
        # and equals the one the cycle was adjudicated against
        assert _eff_from(rxs, s["from"]) == _eff_from(rxs, s["to"]) == s["rx_from"]


def test_walks_every_prescription_in_the_ledger():
    rx_a = rx(date(2026, 7, 24), date(2026, 7, 30), lo="22:30")
    rx_b = rx(date(2026, 7, 31), date(2026, 8, 6), lo="22:15")
    rx_c = rx(date(2026, 8, 7), None, lo="22:00")
    nights = ([night(d, lo="22:30") for d in span(date(2026, 7, 24), 7)]
              + [night(d, lo="22:15") for d in span(date(2026, 7, 31), 7)]
              + [night(d, lo="22:00") for d in span(date(2026, 8, 7), 7)])

    series = replay(nights, [rx_a, rx_b, rx_c], last_night=date(2026, 8, 13))
    assert {s["rx_from"] for s in series} == {rx_a.effective_from, rx_b.effective_from,
                                              rx_c.effective_from}


def test_each_cycle_uses_its_own_ledger_anchor():
    rx_a = rx(date(2026, 7, 24), date(2026, 7, 30), lo="23:45", anchor="05:45", win=360)
    rx_b = rx(date(2026, 7, 31), None, lo="22:30", anchor="05:00", win=390)
    nights = ([night(d, lo="23:45", wake="05:45", oob="05:45") for d in span(date(2026, 7, 24), 7)]
              + [night(d, lo="22:30") for d in span(date(2026, 7, 31), 7)])

    series = replay(nights, [rx_a, rx_b], last_night=date(2026, 8, 6))
    anchors = {s["rx_from"]: s["rx_anchor"] for s in series}
    assert anchors[date(2026, 7, 24)] == "05:45"
    assert anchors[date(2026, 7, 31)] == "05:00"


# ── plateau continuity + close is advisory, not terminal ──────────────────────────

def test_prior_tst_carries_across_cycles_and_convergence_does_not_terminate():
    """One prescription in force for 28 nights. Flat TST at a held SE floor plateaus —
    proving `prior_basis_tst` accumulates across cycles — and the walk CONTINUES past
    it. The engine no longer emits `close` at all: a plateau is a CONVERGED HOLD and the
    block stays open, so the titration keeps hunting rather than exiting."""
    only = rx(date(2026, 7, 24), None, lo="22:30", win=390)
    nights = [night(d, lo="22:30", tst=445, se=90.0) for d in span(date(2026, 7, 24), 28)]

    series = replay(nights, [only], last_night=date(2026, 8, 20))
    assert len(series) == 28 // CYCLE_NIGHTS      # whole span walked, nothing terminated
    assert not [s for s in series if s["decision"] == "close"]   # `close` is never emitted
    converged = [s for s in series if s["converged"]]
    assert converged                              # plateau reached → prior_tst carried
    assert series[-1]["cycle"] > converged[0]["cycle"]  # cycles continue past convergence
    assert all(s["decision"] == "hold" for s in converged)


def test_prescription_with_no_nights_is_skipped_not_errored():
    rx_a = rx(date(2026, 7, 24), date(2026, 7, 30), lo="22:30")
    rx_b = rx(date(2026, 7, 31), None, lo="22:00")
    # only rx_b has nights; rx_a's span is empty
    nights = [night(d, lo="22:00") for d in span(date(2026, 7, 31), 7)]
    series = replay(nights, [rx_a, rx_b], last_night=date(2026, 8, 6))
    assert {s["rx_from"] for s in series} == {rx_b.effective_from}
