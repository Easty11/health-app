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
| Shoulder soreness | None | Very sore | Hardcoded for now |
| Hamstring soreness | None | Very sore | Hardcoded for now |

## Alcohol block (conditional, retained)

1. Toggle — **"Drank last night?"**
2. If yes → **units**: stepper `0–15`, default `0` (a discrete count — stepper, not a slider)
3. → **last-drink time**: time-select

## Notes

- Soreness items are hardcoded for now. **Future:** drive from the active injury list,
  movement-pattern indexed (FEEDBACK 2.6).
- Direction/polarity inversion is the scoring layer's responsibility, not the UI's
  (Decision 10 logic applied to UX — annotate direction, let scoring invert).
