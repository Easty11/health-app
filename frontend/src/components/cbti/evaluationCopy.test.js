// The CBT-I evaluation copy, pinned. These functions describe a titration decision the
// engine made (#118); the risk they carry is wording that misstates what the engine did —
// a delta phrase on a window that did not move, or a "close" verb the hunting engine
// never emits. The cases below are the ones that would read wrong to the operator.
import { describe, expect, it } from 'vitest'

import {
  decisionHeadline, exclusionNote, formatMinutes, nextEvaluationNote,
} from './evaluationCopy'

const basis = (over = {}) => ({
  window_minutes_current: 390,
  window_minutes_proposed: 405,
  ...over,
})

describe('formatMinutes', () => {
  it('renders hours and padded minutes', () => {
    expect(formatMinutes(405)).toBe('6h 45m')
    expect(formatMinutes(390)).toBe('6h 30m')
  })
  it('drops the hour part under 60 minutes', () => {
    expect(formatMinutes(45)).toBe('45m')
  })
  it('null is an em-dash, not 0', () => {
    expect(formatMinutes(null)).toBe('—')
    expect(formatMinutes(undefined)).toBe('—')
  })
})

describe('decisionHeadline', () => {
  it('appends the signed delta ONLY on window-moving decisions', () => {
    expect(decisionHeadline('extend', basis())).toBe('Extend the window by +15 min')
    expect(decisionHeadline('compress', basis({ window_minutes_proposed: 375 })))
      .toBe('Compress the window by -15 min')
  })
  it('a HOLD names the decision without a nonsense magnitude', () => {
    // hold carries the window unchanged; a "+15 min" here would misdescribe it.
    expect(decisionHeadline('hold', basis({ window_minutes_proposed: 390 }))).toBe('Hold the window')
    expect(decisionHeadline('adopt', basis())).toBe('Adopt the window')
  })
  it('an unknown decision falls back rather than inventing a verb', () => {
    // The hunting engine emits no block-ending decision, so `close` has no verb; if one
    // ever reached the surface it must render literally, not as a fabricated sentence.
    expect(decisionHeadline('close', basis())).toBe('Decision: close')
  })
  it('a moving decision with equal from/to drops the magnitude', () => {
    expect(decisionHeadline('extend', basis({ window_minutes_proposed: 390 }))).toBe('Extend the window')
  })
})

describe('exclusionNote', () => {
  it('null when nothing was excluded', () => {
    expect(exclusionNote({})).toBe(null)
    expect(exclusionNote(null)).toBe(null)
    expect(exclusionNote(undefined)).toBe(null)
  })
  it('pluralises the count', () => {
    expect(exclusionNote({ '2026-08-10': 'nap' })).toBe('1 night excluded from the basis')
    expect(exclusionNote({ '2026-08-10': 'nap', '2026-08-11': 'alcohol' }))
      .toBe('2 nights excluded from the basis')
  })
})

describe('nextEvaluationNote', () => {
  it('counts down to the 4-night cadence by default', () => {
    // CYCLE_NIGHTS = 4: day 3 of the cycle leaves one night.
    expect(nextEvaluationNote(3)).toBe('Next evaluation in 1 night')
    expect(nextEvaluationNote(1)).toBe('Next evaluation in 3 nights')
  })
  it('nothing to say once the cycle has elapsed', () => {
    expect(nextEvaluationNote(4)).toBe(null)
    expect(nextEvaluationNote(5)).toBe(null)
  })
  it('null days yields no note', () => {
    expect(nextEvaluationNote(null)).toBe(null)
    expect(nextEvaluationNote(undefined)).toBe(null)
  })
})
