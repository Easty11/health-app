// Late-reported appointments (#346) — Brisbane wall time, at the boundaries.
import { describe, expect, test } from 'vitest'
import { awaitingDays, awaitingLabel } from './awaitingReport'

// 03:00Z == 13:00 Brisbane (UTC+10, no DST).
const NOW = new Date('2026-10-01T03:00:00Z')

describe('awaitingDays', () => {
  test('an appointment at this very minute is not yet past', () => {
    expect(awaitingDays('2026-10-01T13:00', NOW)).toBeNull()
  })
  test('a minute ago, the same day, is past: today', () => {
    expect(awaitingDays('2026-10-01T12:59', NOW)).toBe(0)
  })
  test('days are counted in Brisbane dates, with or without the +10:00 offset', () => {
    expect(awaitingDays('2026-09-28T09:00', NOW)).toBe(3)
    expect(awaitingDays('2026-09-28T09:00+10:00', NOW)).toBe(3)
  })
  test('the Brisbane date, not the UTC date, decides "today"', () => {
    // 15:30Z on 30 Sep is 01:30 on 1 Oct in Brisbane — an appointment at 00:30 Brisbane is today.
    expect(awaitingDays('2026-10-01T00:30', new Date('2026-09-30T15:30:00Z'))).toBe(0)
  })
  test('future and malformed values are not awaiting', () => {
    expect(awaitingDays('2026-10-02T09:00', NOW)).toBeNull()
    expect(awaitingDays('', NOW)).toBeNull()
    expect(awaitingDays(undefined, NOW)).toBeNull()
  })
})

test('labels', () => {
  expect(awaitingLabel(0)).toBe('Awaiting report · today')
  expect(awaitingLabel(1)).toBe('Awaiting report · 1 day')
  expect(awaitingLabel(4)).toBe('Awaiting report · 4 days')
})
