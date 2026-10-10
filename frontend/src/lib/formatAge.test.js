import { describe, expect, test } from 'vitest'
import { formatAge, formatPipeAge } from './formatAge'

describe('formatAge', () => {
  test('minutes under an hour, hours under two days, days after', () => {
    expect(formatAge(0.5)).toBe('30 min ago')
    expect(formatAge(0)).toBe('0 min ago')
    expect(formatAge(3)).toBe('3 h ago')
    expect(formatAge(14)).toBe('14 h ago')
    expect(formatAge(47.4)).toBe('47 h ago')
    expect(formatAge(72)).toBe('3 d ago')
  })
  test('a missing age is unknown, never a number', () => {
    expect(formatAge(null)).toBe('unknown')
    expect(formatAge(undefined)).toBe('unknown')
    expect(formatAge(NaN)).toBe('unknown')
  })
  test('a pipe that never delivered reads never; an absent pipe reads unknown', () => {
    expect(formatPipeAge({ status: 'never', age_hours: null })).toBe('never')
    expect(formatPipeAge(undefined)).toBe('unknown')
    expect(formatPipeAge({ status: 'amber', age_hours: 14 })).toBe('14 h ago')
  })
})
