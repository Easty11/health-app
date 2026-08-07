// A null `field_confidence` sub-field means NOT EXPRESSED — never zero.
//
// `FieldConfidence`'s sub-fields became Optional so a ref-less row can honestly say it
// had no `ref` to score. That loosening only helps if every consumer treats null as
// ABSENT, and JS makes that easy to get wrong in two different ways:
//
//   `null < 0.85`            -> true   (null coerces to 0)   -> isSuspect
//   `0.97 + null`            -> 0.97   (null coerces to 0)   -> confidencePct sum
//   ...and the null still counts in `values.length`          -> confidencePct mean
//
// Both would report a clean extraction as a problem. These pin the guarded behaviour.
import { describe, expect, it } from 'vitest'

import { confidencePct, isSuspect } from './labRowClassification'

// isSuspect also flags unmapped markers, so every row here is mapped — otherwise the
// assertion would pass for the wrong reason and prove nothing about confidence.
const MAP = { Bilirubin: { marker_canonical: 'bilirubin_total' } }

const row = (conf, over = {}) => ({
  marker_name_raw: 'Bilirubin',
  value_num: 28,
  unit_canonical: 'umol/L',
  flag_agreement: true,
  field_confidence: conf,
  ...over,
})

const GOOD = { name: 0.99, value: 0.98, unit: 0.97, ref: 0.96 }

describe('isSuspect — null is absent, not zero', () => {
  it('a null sub-field does NOT make the row suspect', () => {
    // The ref-less row: no reference interval on the report, so no ref confidence.
    expect(isSuspect(row({ name: 0.99, value: 0.98, unit: 0.97, ref: null }), MAP)).toBe(false)
  })

  it('all four null does NOT make the row suspect', () => {
    expect(isSuspect(row({ name: null, value: null, unit: null, ref: null }), MAP)).toBe(false)
  })

  it('a GENUINELY low confidence still makes the row suspect', () => {
    // The guard must not have flattened the real signal — this is the case the whole
    // suspect mechanism exists for.
    expect(isSuspect(row({ ...GOOD, ref: 0.5 }), MAP)).toBe(true)
  })

  it('a low confidence alongside a null is still suspect', () => {
    expect(isSuspect(row({ name: 0.99, value: 0.5, unit: 0.97, ref: null }), MAP)).toBe(true)
  })

  it('all-good confidences are not suspect', () => {
    expect(isSuspect(row(GOOD), MAP)).toBe(false)
  })

  it('the other suspect rules are untouched', () => {
    expect(isSuspect(row(GOOD, { flag_agreement: false }), MAP)).toBe(true)
    expect(isSuspect(row(GOOD, { marker_name_raw: 'R U-Creatinine' }), MAP)).toBe(true) // unmapped
    expect(isSuspect(row(GOOD, { value_num: null, value_qualitative: null }), MAP)).toBe(true)
  })
})

describe('confidencePct — averages over expressed fields only', () => {
  it('excludes a null from BOTH the sum and the denominator', () => {
    // Unguarded this is (0.99+0.98+0.97+0)/4 = 73%. Guarded it is the mean of three.
    expect(confidencePct(row({ name: 0.99, value: 0.98, unit: 0.97, ref: null }))).toBe(98)
  })

  it('is unchanged when every field is expressed', () => {
    expect(confidencePct(row(GOOD))).toBe(98) // (0.99+0.98+0.97+0.96)/4 = 0.975 -> 98
  })

  it('all-null returns null, the same as an absent object', () => {
    // Not 0%, which would read as a confident statement of no confidence.
    expect(confidencePct(row({ name: null, value: null, unit: null, ref: null }))).toBe(null)
    expect(confidencePct(row(null))).toBe(null)
    expect(confidencePct(row(undefined))).toBe(null)
  })

  it('a single expressed field averages to itself', () => {
    expect(confidencePct(row({ name: 0.8, value: null, unit: null, ref: null }))).toBe(80)
  })
})
