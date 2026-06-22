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

Nothing here gates on the suppressed readiness composite (DECISIONS_LOG #8) and
nothing introduces a wearable metric — capability state is self-reported through
the adaptation loop's education idiom (spec §12). Quantitative dosing references
the Banister fitness-fatigue model (DECISIONS_LOG #18), never ACWR.
"""
