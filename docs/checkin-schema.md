# Morning Check-in — field schema

Implementation spec for the Morning Check-in screen. Settled design: DECISIONS_LOG **#29**.
This is the target spec — not yet implemented.

## Subjective wellness items

All items: **0–4 button-group**, hard floor **0**, **dual-anchor** labels, number and
descriptor agree (0 = literal absence). Polarity is **not** normalised in the UI — the
scoring layer owns inversion; the dual anchors make each item's direction explicit.

| Item | 0 | 4 | Notes |
|------|---|---|-------|
| Sleep quality | Poor | Great | |
| Fatigue | Fresh | Exhausted | Replaces the prior "feel right now" item (F2 collapse) |
| Stress | None | Very high | |
| Motivation | None | High | |
| Soreness (one item per active injury) | None | Very sore | **Built.** Derived from the active `type='injury'` ledger — not a fixed pair. See Notes. |

## Alcohol block (conditional, retained)

1. Toggle — **"Drank last night?"**
2. If yes → **units**: stepper `0–15`, default `0` (a discrete count — stepper, not a slider)
3. → **last-drink time**: time-select

## Notes

- **Soreness items are driven from the active injury ledger — built, live since 13 Jul 2026**
  (FEEDBACK 2.6; DECISIONS_LOG #72/#73). `checkin_v2.derive_soreness_items` emits one item per
  active `UserKnowledgeEntry type='injury'` row, keyed by `injury_soreness_key` (sided injuries
  carry the side, so left/right hamstring do not collide); `/checkin-v2/prefill` serves it and
  `CheckInAM.jsx` renders one slider per key, with a "No active injuries to track" empty state.
  Stored as the `daily_records.soreness` JSON dict — not columns.
  *This line previously read "hardcoded for now — **Future:** drive from the active injury list".
  It stayed "future" in the doc for two days after the code shipped, and a later brief was written
  against that stale note and specced work that already existed. The doc is not the tree.*
- **Injury-TYPE-specific probe questions are NOT complete and are not claimed to be**
  (`backend/injury_probes.py`, DECISIONS_LOG #90). The scaffold is versioned and provenance-stamped
  (`PROBE_QUESTIONS_VERSION`, `PROBE_QUESTIONS_PROVENANCE`) and seeded with exactly ONE injury type
  (gastroc strain). Every other injury type falls back to the generic soreness item above — by
  design, never a fabricated question set. Adding a type is a deliberate authoring step; the
  check-in machinery then consumes it. Probe questions are elicitation-only and escalation is
  referral-only, both enforced by tests, not by this doc (#89).
- Direction/polarity inversion is the scoring layer's responsibility, not the UI's
  (Decision 10 logic applied to UX — annotate direction, let scoring invert).
