// phaseTransitionLib — the pure helpers behind the 2026-09-21 phase-form fixes. These assert the
// pieces the gates rest on: a placement never resolves to 'unknown' (B1/F10), the confirm diff
// puts removals first (B2/F16), and the all-capacity-removed guard (B2).

import { expect, test } from 'vitest'
import {
  buildMicrocycle, deriveTimeOfDay, diffSlots, microcycleSlots, normaliseActivityName,
  normaliseTimeRange, removesAllCapacity,
} from './phaseTransitionLib'

test('deriveTimeOfDay never yields unknown — a bucket, or a bucket derived from a range (B1/F10)', () => {
  expect(deriveTimeOfDay('evening', '')).toBe('evening')
  expect(deriveTimeOfDay('', '')).toBe('evening')        // default, never 'unknown'
  expect(deriveTimeOfDay('morning', '17:30-18:30')).toBe('evening')  // range wins, derives evening
  expect(deriveTimeOfDay('evening', '06:00-07:00')).toBe('morning')  // 06:00 → morning
  expect(deriveTimeOfDay('evening', '13:00-14:00')).toBe('afternoon')
  expect(['morning', 'afternoon', 'evening']).toContain(deriveTimeOfDay('bogus', 'nonsense'))
})

test('normaliseTimeRange accepts HH:MM-HH:MM, rejects malformed/backwards', () => {
  expect(normaliseTimeRange('17:30-18:30')).toBe('17:30-18:30')
  expect(normaliseTimeRange('7:00 - 8:00')).toBe('7:00-8:00')
  expect(normaliseTimeRange('18:30-17:30')).toBe(null)   // backwards
  expect(normaliseTimeRange('evening')).toBe(null)
  expect(normaliseTimeRange('25:00-26:00')).toBe(null)
})

test('normaliseActivityName lowercases and underscores (F7)', () => {
  expect(normaliseActivityName('  Pilates Flow ')).toBe('pilates_flow')
})

test('microcycleSlots reads a stored microcycle back into slot shape (F6 prefill)', () => {
  const mc = { sub_cycle_days: 7, sub_cycles: [{ label: 'A', slots: [
    { capacity: 'stability', sessions_per_cycle: 2, minutes: 30 },
    { activity: 'pilates', device_sports: ['Pilates'], sessions_per_cycle: 2, minutes: 50 },
  ] }] }
  const slots = microcycleSlots(mc)
  expect(slots).toHaveLength(2)
  expect(slots[0]).toMatchObject({ kind: 'capacity', key: 'stability', sessions: 2 })
  expect(slots[1]).toMatchObject({ kind: 'activity', key: 'pilates', sessions: 2, device_sports: ['Pilates'] })
})

test('diffSlots reports removals, changes and adds (F16, B2)', () => {
  const outgoing = [
    { kind: 'capacity', key: 'stability', sessions: 2 },
    { kind: 'capacity', key: 'strength', sessions: 1 },
  ]
  const next = [
    { kind: 'capacity', key: 'stability', sessions: 3 },  // change 2→3
    { kind: 'activity', key: 'pilates', sessions: 2 },     // add
    // strength dropped → remove
  ]
  const d = diffSlots(outgoing, next)
  expect(d.removes.map((s) => s.key)).toEqual(['strength'])
  expect(d.changes).toEqual([expect.objectContaining({ key: 'stability', from: 2, to: 3 })])
  expect(d.adds.map((s) => s.key)).toEqual(['pilates'])
})

test('removesAllCapacity fires only when capacity existed and none survives (B2)', () => {
  const out = [{ kind: 'capacity', key: 'stability', sessions: 2 }]
  expect(removesAllCapacity(out, [{ kind: 'activity', key: 'pilates', sessions: 2 }])).toBe(true)
  expect(removesAllCapacity(out, [{ kind: 'capacity', key: 'stability', sessions: 0 }])).toBe(true) // zero = removed
  expect(removesAllCapacity(out, [{ kind: 'capacity', key: 'stability', sessions: 3 }])).toBe(false)
  expect(removesAllCapacity([], [{ kind: 'activity', key: 'pilates', sessions: 2 }])).toBe(false) // none to remove
})

test('buildMicrocycle keeps one sub-cycle and the slot kinds', () => {
  const mc = buildMicrocycle([
    { kind: 'capacity', key: 'stability', sessions: 3, minutes: 30 },
    { kind: 'activity', key: 'pilates', sessions: 2, minutes: 50, device_sports: ['Pilates'] },
  ])
  expect(mc.sub_cycles).toHaveLength(1)
  expect(mc.sub_cycles[0].slots[0]).toMatchObject({ capacity: 'stability', sessions_per_cycle: 3 })
  expect(mc.sub_cycles[0].slots[1]).toMatchObject({ activity: 'pilates', device_sports: ['Pilates'] })
})
