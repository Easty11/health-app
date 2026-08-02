"""
Adaptive Exposure Engine — Decision Support module.

Capability-first variety: variety's job is to TEST for deficiency in order to
fortify it (spec §1). The engine runs an explore/exploit split over a capability
taxonomy:

  - FORTIFY (exploit) — known target, known gap → distribute load to close it.
  - PROBE   (explore) — system-initiated sampling of UNTESTED regions, into the
                        user's non-preferred space, to convert unknown →
                        known-deficiency-or-capability (spec §2).

Two-part taxonomy (v2.1 split, spec §3):
  - axis list   (`taxonomy.py`)  — which regions exist; external-authority,
                                    versioned; caps what Probe can discover.
  - map contents (`capability_state` table) — this user's score per region;
                                    self-builds one probe per session (§2.1).

Nothing here gates on the suppressed readiness composite (DECISIONS_LOG #8), and
capability state remains self-reported through the adaptation loop's education
idiom (spec §12) — the VERDICT is never a wearable metric. Quantitative dosing
references the Banister fitness-fatigue model (DECISIONS_LOG #18), never ACWR.

The wearable-metric invariant scopes to the verdict, not to measurement
(DECISIONS_LOG #NEXT). `capability_state.status` is self-reported and stays so.
`capability_observations` (`observations.py`) records measured quantities and MAY
carry device-derived values — GPS max velocity, deceleration counts — because
those are the best available objective measures for exactly the §E regions that
self-report covers worst. This is stated rather than assumed: the failure mode is
widening the invariant silently, so the two halves are named separately here and
on `models.CapabilityState`.
"""
