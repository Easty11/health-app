# Morning Check-in — field schema

Implementation spec for the Morning Check-in screen. Settled design: DECISIONS_LOG **#29**.

**IMPLEMENTED.** `backend/routers/checkin_v2.py` serves `/prefill`, `/am`, `/pm`, `/today` and
`/history`, wired at `main.py`; `frontend/src/pages/CheckInAM.jsx` (route `/checkin-am`) and
`NightlyCloseOut.jsx` (route `/nightly`) are the capture surfaces, both behind `RequireAuth`.
This file previously read "target spec — not yet implemented", which was stale by roughly a year
and mis-scoped the CBT-I surfaces work as construction rather than extension until it was checked.

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

- Soreness items are **driven from the active injury list**, not hardcoded.
  `derive_soreness_items` (`checkin_v2.py`) reads active `type='injury'` knowledge entries and keys
  each item via `injury_soreness_key`; `/prefill` returns them and `CheckInAM.jsx` renders them.
  This note previously read "hardcoded for now — **Future:** drive from the active injury list
  (FEEDBACK 2.6)"; that future arrived and the note was not updated.
- **Injury-TYPE-specific probe questions are NOT complete and are not claimed to be**
  (`backend/injury_probes.py`, DECISIONS_LOG #134). The scaffold is versioned and provenance-stamped
  (`PROBE_QUESTIONS_VERSION`, `PROBE_QUESTIONS_PROVENANCE`) and seeded with exactly ONE injury type
  (gastroc strain). Every other injury type falls back to the generic soreness item above — by
  design, never a fabricated question set. Adding a type is a deliberate authoring step; the
  check-in machinery then consumes it. Probe questions are elicitation-only and escalation is
  referral-only, both enforced by tests, not by this doc (#133).
- Direction/polarity inversion is the scoring layer's responsibility, not the UI's
  (Decision 10 logic applied to UX — annotate direction, let scoring invert).
