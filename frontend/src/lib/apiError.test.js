// Regression cover for the banner that could not name its own failure.
//
// The defect: `/labs/confirm` rejected a genuine report with a Pydantic 422 whose
// `detail` is a LIST of `{loc, msg, type}`, and the catch block's
// `typeof detail === 'string' ? detail : detail?.error` matched neither arm — so the
// structured rejection collapsed to the constant "Failed to save report". G1 below is
// the case that was broken; G2/G3/G4 pin the behaviour that must NOT regress while
// fixing it, since the two previously-handled shapes still occur.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import { formatApiError } from './apiError'

// Shaped like axios: the detail lives at err.response.data.detail, and a transport
// failure has no `response` at all.
const rejection = (detail) => ({ response: { data: { detail } } })

describe('formatApiError — FastAPI request-validation 422 (the defect)', () => {
  it('G1: renders field path and message from a list-form detail, not the fallback', () => {
    const err = rejection([
      {
        loc: ['body', 'results', 2, 'field_confidence', 'ref'],
        msg: 'Input should be a valid number',
        type: 'float_type',
      },
    ])
    const out = formatApiError(err, 'Failed to save report')

    expect(out).toBe('results.2.field_confidence.ref: Input should be a valid number')
    expect(out).not.toBe('Failed to save report')
  })

  it('G1b: joins several rejected fields rather than reporting only the first', () => {
    const out = formatApiError(
      rejection([
        { loc: ['body', 'report', 'source_completeness'], msg: 'Field required', type: 'missing' },
        { loc: ['body', 'report', 'panel_name_raw'], msg: 'Field required', type: 'missing' },
      ]),
      'Failed to save report',
    )

    expect(out).toBe(
      'report.source_completeness: Field required; report.panel_name_raw: Field required',
    )
  })

  it('G1c: truncates a long list but states the true total, never silently', () => {
    const many = Array.from({ length: 9 }, (_, i) => ({
      loc: ['body', 'results', i, 'field_confidence', 'ref'],
      msg: 'Field required',
      type: 'missing',
    }))
    const out = formatApiError(rejection(many), 'Failed to save report')

    expect(out).toContain('results.0.field_confidence.ref: Field required')
    expect(out).toContain('(+4 more)')
    // The count is the part that must be honest — 5 shown of 9.
    expect(out.match(/Field required/g)).toHaveLength(5)
  })

  it('keeps a non-body loc prefix, which is load-bearing', () => {
    const out = formatApiError(
      rejection([{ loc: ['query', 'on_duplicate'], msg: 'Input should be a valid string', type: 'string_type' }]),
      'fallback',
    )

    expect(out).toBe('query.on_duplicate: Input should be a valid string')
  })

  it('falls back when a list carries no readable entries, rather than printing junk', () => {
    expect(formatApiError(rejection([null, 'nonsense']), 'fallback')).toBe('fallback')
  })
})

describe('formatApiError — shapes that already worked and must not regress', () => {
  it('G2: a string detail passes through unchanged (handler-raised HTTPException)', () => {
    const out = formatApiError(
      rejection('report.dates.collected is required — it is the timeline anchor and cannot be stored null'),
      'Failed to save report',
    )

    expect(out).toBe(
      'report.dates.collected is required — it is the timeline anchor and cannot be stored null',
    )
  })

  it('G3: an object detail with .error still resolves to that message', () => {
    expect(formatApiError(rejection({ error: 'extraction failed' }), 'fallback')).toBe('extraction failed')
  })

  it('G4: an absent detail falls back — the transport case, the only one it should describe', () => {
    expect(formatApiError(rejection(undefined), 'Failed to save report')).toBe('Failed to save report')
    expect(formatApiError({}, 'Failed to save report')).toBe('Failed to save report')
    expect(formatApiError(undefined, 'Failed to save report')).toBe('Failed to save report')
    // An empty string is not a message; it would render as a blank banner.
    expect(formatApiError(rejection(''), 'Failed to save report')).toBe('Failed to save report')
  })
})

// The helper being correct proves nothing if a call site still collapses the detail
// itself. This asserts the WIRING, which is the part the unit tests above cannot see —
// and it is the whole defect: the logic was never wrong, it was never reached.
describe('Metrics.jsx call sites are actually wired to the helper', () => {
  const source = readFileSync(
    fileURLToPath(new URL('../pages/Metrics.jsx', import.meta.url)),
    'utf-8',
  )

  it('both the /extract and /confirm catch blocks route through formatApiError', () => {
    expect(source).toContain("formatApiError(err, 'Failed to read report')")
    expect(source).toContain("formatApiError(err, 'Failed to save report')")
  })

  it('neither call site retains the string-or-.error collapse that discarded the list', () => {
    expect(source).not.toMatch(/typeof detail === 'string' \? detail : detail\?\.error/)
  })
})
