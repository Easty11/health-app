import { describe, expect, test } from 'vitest'
import { localDate } from './sessionDates'

describe('localDate', () => {
  test('a 07:00 AEST session shows its AEST date, not the UTC date', () => {
    // 2026-09-29 07:00 AEST == 2026-09-28 21:00 UTC — iso.slice(0, 10) would say the 28th.
    expect(localDate('2026-09-28T21:00:00+00:00')).toBe('2026-09-29')
    expect(localDate('2026-09-28T21:00:00Z')).toBe('2026-09-29')
  })

  test('the same instant with an explicit +10:00 offset is the same date', () => {
    expect(localDate('2026-09-29T07:00:00+10:00')).toBe('2026-09-29')
  })

  test('late evening AEST stays on its own date', () => {
    // 23:30 AEST on the 26th == 13:30 UTC on the 26th
    expect(localDate('2026-09-26T13:30:00Z')).toBe('2026-09-26')
  })

  test('a bare date passes through (aerobic session_date is already local)', () => {
    expect(localDate('2026-09-26')).toBe('2026-09-26')
  })

  test('missing and garbage inputs read as a dash', () => {
    expect(localDate(null)).toBe('—')
    expect(localDate('')).toBe('—')
    expect(localDate('not-a-date')).toBe('—')
  })
})
