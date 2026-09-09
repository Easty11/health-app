// The pure copy helper — assertions track F1's composition rules, not cosmetics.
//
// Composition: `<Mode> · <object> [· <Phase capitalised>, review …]`, joined with ` · `. The phase
// clause reads `review due` when review_due, else `review <d Mon>` from review_on. The date is
// parsed at noon (never midnight) so a date-only string does not slip to the previous local day.

import { describe, expect, test } from 'vitest'
import { exposureTileCopy, formatReviewDate } from './exposureTileCopy'
import decompression from '../../fixtures/engineNextDecompression.json'

describe('exposureTileCopy — composition (F1)', () => {
  test('fortify + phase: mode, target_label, capitalised phase, review date', () => {
    // The live decompression payload: review_due false, review_on 2026-10-05.
    expect(exposureTileCopy(decompression)).toBe(
      'Fortify · Anti-lateral-flexion · Decompression, review 5 Oct',
    )
  })

  test('probe + no phase: two parts only, object is probe.label', () => {
    const payload = {
      mode_recommended: 'probe',
      fortify: { target_label: 'Anti-lateral-flexion' },
      probe: { label: 'Carry' },
    }
    expect(exposureTileCopy(payload)).toBe('Probe · Carry')
  })

  test('review_due true collapses the date to the phrase "review due"', () => {
    const payload = {
      mode_recommended: 'fortify',
      fortify: { target_label: 'T' },
      training_phase: { label: 'rebuild', review_due: true, review_on: '2026-10-06' },
    }
    const copy = exposureTileCopy(payload)
    expect(copy).toBe('Fortify · T · Rebuild, review due')
    expect(copy).not.toMatch(/Oct/)
  })
})

describe('formatReviewDate', () => {
  test('a date-only string formats as "review <d Mon>"', () => {
    expect(formatReviewDate('2026-10-05')).toBe('review 5 Oct')
  })

  test('a missing date does not throw and does not fabricate one', () => {
    expect(formatReviewDate(null)).toBe('review date unknown')
  })
})
