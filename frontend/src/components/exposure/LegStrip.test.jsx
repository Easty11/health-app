// @vitest-environment jsdom
//
// LegStrip (Know (d), R6 / R7). One column per day of the window, derived from `week.days`; hard items
// are solid blocks with a time; actuals are marks on their own day; soft pools appear ONLY in the tray
// ("Gym · 1/2 · Mon Wed Fri", "to place N"), never repeated per day; an unavailable day is greyed and a
// caution is a small note; the load_window kind reads "Conditioning" and never "metabolic".
//
// Mutation controls (run by hand, recorded in the PR): rendering `flexible` inside DayColumn fails the
// R6 test; `keyLabel` returning the title-cased token fails the R7 test.

import { afterEach, expect, test } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'

import LegStrip from './LegStrip'

afterEach(cleanup)

function day(date, weekday, over = {}) {
  return { date, weekday, hard: [], flexible: [], actual: [], available: true, caution: null, ...over }
}

const GYM = { activity: 'Gym', satisfies: { capacity: 'stability' }, pool: 2, time_of_day: 'evening' }

// Sun 4 Oct -> Sat 10 Oct 2026: the block-2 leg runs Sunday-Saturday because the phase was entered Sunday.
const SUN_SAT = {
  window: { label: 'A', start_date: '2026-10-04', end_date: '2026-10-10', source: 'phase' },
  days: [
    day('2026-10-04', 'sunday'),
    day('2026-10-05', 'monday', {
      flexible: [GYM],
      hard: [{ activity: 'Work', expected_load: 'none', same_day_training: true, time_range: '08:00-16:00' }],
      actual: [{ kind: 'capacity', key: 'stability', ref: 'w1', title: 'Pull day' }],
    }),
    day('2026-10-06', 'tuesday', {
      hard: [{ activity: 'Rugby', expected_load: 'heavy', same_day_training: false, time_of_day: 'evening',
               satisfies: { activity: 'rugby' } }],
      available: false,
    }),
    day('2026-10-07', 'wednesday', { flexible: [GYM], caution: 'day after heavy' }),
    day('2026-10-08', 'thursday', {
      hard: [{ activity: 'Dentist', expected_load: 'none', same_day_training: true, time_of_day: 'unknown' }],
    }),
    day('2026-10-09', 'friday', { flexible: [GYM] }),
    day('2026-10-10', 'saturday'),
  ],
  keys: [
    { kind: 'capacity', key: 'stability', quota: 2, done: 1, scheduled: 2, excess: 0, unplaced: 0 },
    { kind: 'load_window', key: 'metabolic', quota: 2, done: 0, scheduled: 0, excess: 0, unplaced: 2 },
    { kind: 'activity', key: 'rugby', quota: 1, done: 0, scheduled: 1, excess: 0, unplaced: 0 },
  ],
}

test('one column per day of the window, in window order, derived rather than hardcoded', () => {
  render(<LegStrip week={SUN_SAT} />)
  const cols = screen.getAllByTestId('leg-day')
  expect(cols.map((c) => c.getAttribute('data-date'))).toEqual(SUN_SAT.days.map((d) => d.date))
  expect(within(cols[0]).getByText('Sun')).toBeTruthy()          // a Sun-Sat leg starts on Sunday
  expect(within(cols[6]).getByText('Sat')).toBeTruthy()
})

test('a Mon-Sun window starts on Monday (the order is the data\'s, not a constant)', () => {
  const week = {
    window: { label: 'Week', start_date: '2026-09-07', end_date: '2026-09-13', source: 'weekly' },
    days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
      .map((w, i) => day(`2026-09-${String(7 + i).padStart(2, '0')}`, w)),
    keys: [],
  }
  render(<LegStrip week={week} />)
  const cols = screen.getAllByTestId('leg-day')
  expect(cols).toHaveLength(7)
  expect(within(cols[0]).getByText('Mon')).toBeTruthy()
  expect(within(cols[6]).getByText('Sun')).toBeTruthy()
})

test('hard items are solid blocks with their time: a range, else the band, never "unknown"', () => {
  render(<LegStrip week={SUN_SAT} />)
  const cols = screen.getAllByTestId('leg-day')
  expect(within(within(cols[1]).getByTestId('leg-hard')).getByText('08:00-16:00')).toBeTruthy()   // range
  expect(within(within(cols[2]).getByTestId('leg-hard')).getByText('evening')).toBeTruthy()       // band
  const dentist = within(cols[4]).getByTestId('leg-hard')
  expect(dentist.textContent).toBe('Dentist')                                                     // unknown -> none
})

test('an actual session is a mark on the day it happened, and only there', () => {
  render(<LegStrip week={SUN_SAT} />)
  const cols = screen.getAllByTestId('leg-day')
  expect(within(cols[1]).getByTestId('leg-actual').textContent).toContain('Pull day')
  expect(screen.getAllByTestId('leg-actual')).toHaveLength(1)
})

test('R6: a soft pool appears once, in the tray, and never per day', () => {
  const { container } = render(<LegStrip week={SUN_SAT} />)
  expect(screen.getByText('Gym · 1/2 · Mon Wed Fri')).toBeTruthy()          // the tray row, once
  // Gym is a flexible item on THREE days; it must not be drawn in any day column.
  for (const col of screen.getAllByTestId('leg-day')) expect(col.textContent).not.toContain('Gym')
  expect((container.textContent.match(/Gym/g) ?? []).length).toBe(1)
})

test('the tray says "to place N" when the quota exceeds what is scheduled', () => {
  render(<LegStrip week={SUN_SAT} />)
  expect(screen.getByText('to place 2')).toBeTruthy()                       // conditioning: quota 2, scheduled 0
  expect(screen.queryByText(/to place 0/)).toBeNull()
  cleanup()
  const short = { ...SUN_SAT, keys: [{ kind: 'capacity', key: 'stability', quota: 3, done: 1, scheduled: 2, excess: 0, unplaced: 1 }] }
  render(<LegStrip week={short} />)
  expect(screen.getByText('to place 1')).toBeTruthy()
})

test('an unavailable day is greyed and a caution is a small note', () => {
  render(<LegStrip week={SUN_SAT} />)
  const cols = screen.getAllByTestId('leg-day')
  expect(cols[2].getAttribute('data-available')).toBe('false')              // the heavy hard day
  expect(cols[2].className).toMatch(/opacity-70/)
  expect(cols[1].getAttribute('data-available')).toBe('true')
  expect(within(cols[3]).getByText('day after heavy')).toBeTruthy()
})

test('R7: the load_window kind reads "Conditioning", never "metabolic"', () => {
  const { container } = render(<LegStrip week={SUN_SAT} />)
  expect(screen.getByText('Conditioning · 0/2')).toBeTruthy()
  expect(container.textContent).not.toMatch(/metabolic/i)
})

test('a quota over-scheduled shows "N over quota"; an unlinked soft item is named, with no quota', () => {
  const week = {
    ...SUN_SAT,
    days: [day('2026-10-04', 'sunday', { flexible: [{ activity: 'Walk', satisfies: null, pool: 3 }] })],
    keys: [{ kind: 'capacity', key: 'stability', quota: 2, done: 1, scheduled: 3, excess: 1, unplaced: 0 }],
  }
  render(<LegStrip week={week} />)
  expect(screen.getByText('1 over quota')).toBeTruthy()
  expect(screen.getByText('Walk · no quota · Sun')).toBeTruthy()
})

// ── R9 (amends R6): a soft item whose candidate days equal its pool is drawn on its days, outlined ──

const FIXED_GYM = { activity: 'Gym', satisfies: { capacity: 'stability' }, pool: 3, time_range: '06:00-07:00' }

function weekWith(flexByDay, keys) {
  const names = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
  return {
    window: { label: 'A', start_date: '2026-10-04', end_date: '2026-10-10', source: 'phase' },
    days: names.map((w, i) => day(`2026-10-${String(4 + i).padStart(2, '0')}`, w, { flexible: flexByDay[w] ?? [] })),
    keys: keys ?? [{ kind: 'capacity', key: 'stability', quota: 3, done: 0, scheduled: 3, excess: 0, unplaced: 0 }],
  }
}

test('R9: pool equal to candidate days -> an outlined block on each of those days, and only those', () => {
  const week = weekWith({ monday: [FIXED_GYM], wednesday: [FIXED_GYM], friday: [FIXED_GYM] })
  render(<LegStrip week={week} />)
  const cols = screen.getAllByTestId('leg-day')
  const withBlock = cols.filter((c) => within(c).queryByTestId('leg-soft-fixed'))
  expect(withBlock.map((c) => c.getAttribute('data-date'))).toEqual(['2026-10-05', '2026-10-07', '2026-10-09'])
  const block = within(cols[1]).getByTestId('leg-soft-fixed')
  expect(block.textContent).toContain('Gym')
  expect(block.textContent).toContain('06:00-07:00')
  // outlined, not the solid hard block
  expect(block.className).toMatch(/border/)
  expect(block.className).not.toMatch(/bg-gray-800/)
  expect(block.getAttribute('title')).toContain('every listed day')
})

test('R9: a pool with MORE days than sessions stays tray-only (R6 holds there)', () => {
  const week = weekWith({
    monday: [{ ...FIXED_GYM, pool: 2 }], wednesday: [{ ...FIXED_GYM, pool: 2 }], friday: [{ ...FIXED_GYM, pool: 2 }],
  })
  render(<LegStrip week={week} />)
  expect(screen.queryAllByTestId('leg-soft-fixed')).toHaveLength(0)
  expect(screen.getByText('Gym · 0/3 · Mon Wed Fri')).toBeTruthy()
})

test('R9: a missing pool (an older server) never reads as fixed', () => {
  const noPool = { activity: 'Gym', satisfies: { capacity: 'stability' } }
  render(<LegStrip week={weekWith({ monday: [noPool], wednesday: [noPool], friday: [noPool] })} />)
  expect(screen.queryAllByTestId('leg-soft-fixed')).toHaveLength(0)
})

test('R9: an item drawn on its days is not also listed by day in the tray; done still renders only where it happened', () => {
  const week = weekWith({ monday: [FIXED_GYM], wednesday: [FIXED_GYM], friday: [FIXED_GYM] })
  week.days[3].actual = [{ kind: 'capacity', key: 'stability', ref: 'w9', title: 'Legs' }]    // done on Wednesday
  render(<LegStrip week={week} />)
  expect(screen.getByText('Gym · 0/3')).toBeTruthy()                       // no "Mon Wed Fri" repeated here
  expect(screen.queryByText(/Gym · 0\/3 · /)).toBeNull()
  const actual = screen.getAllByTestId('leg-actual')
  expect(actual).toHaveLength(1)
  expect(actual[0].closest('[data-testid="leg-day"]').getAttribute('data-date')).toBe('2026-10-07')
})

// ── tray candidate days: de-duplicated, Monday first ─────────────────────────────────────────────

test('tray candidate days are de-duplicated and ordered Mon -> Sun, whatever day the leg starts', () => {
  const a = { activity: 'Gym A', satisfies: { capacity: 'stability' }, pool: 1 }
  const b = { activity: 'Gym B', satisfies: { capacity: 'stability' }, pool: 1 }
  // Sun-Sat window; Wed carries BOTH items (the live "Mon Tue Wed Wed Thu" case), Sun is first in the window.
  const week = weekWith({ sunday: [a], monday: [b], wednesday: [a, b] },
    [{ kind: 'capacity', key: 'stability', quota: 2, done: 0, scheduled: 2, excess: 0, unplaced: 0 }])
  render(<LegStrip week={week} />)
  expect(screen.getByText('Gym A / Gym B · 0/2 · Mon Wed Sun')).toBeTruthy()
  expect(screen.getByText('Gym A / Gym B · 0/2 · Mon Wed Sun').getAttribute('title')).toBe('candidate days: Mon Wed Sun')
})

// ── mobile layout: a row per day below 640px, never a character-by-character wrap ────────────────

test('layout: one row per day below 640px, seven columns from 640px; blocks truncate with a title', () => {
  render(<LegStrip week={SUN_SAT} />)
  const strip = screen.getByRole('group', { name: 'Leg days' })
  expect(strip.className).toMatch(/\bgrid-cols-1\b/)
  expect(strip.className).toContain('sm:[grid-template-columns:repeat(var(--leg-cols),minmax(0,1fr))]')
  expect(strip.style.getPropertyValue('--leg-cols')).toBe('7')
  const col = screen.getAllByTestId('leg-day')[0]
  expect(col.className).toMatch(/\bflex-row\b/)
  expect(col.className).toMatch(/\bsm:flex-col\b/)
  // A hard block truncates (never `break-words`) and carries its full text.
  const rugby = screen.getAllByTestId('leg-hard').find((n) => n.textContent.startsWith('Rugby'))
  expect(rugby.getAttribute('title')).toBe('Rugby · evening')
  expect(rugby.querySelector('.truncate')).toBeTruthy()
  expect(rugby.className).not.toMatch(/break-words/)
  const longName = 'Instrument calibration and validation'
  cleanup()
  const long = { ...SUN_SAT, days: [day('2026-10-04', 'sunday', { hard: [{ activity: longName, expected_load: 'none', same_day_training: true, time_range: '08:00-16:00' }] })], keys: [] }
  render(<LegStrip week={long} />)
  const block = screen.getByTestId('leg-hard')
  expect(block.getAttribute('title')).toBe(`${longName} · 08:00-16:00`)
  expect(block.querySelector('.truncate').textContent).toBe(longName)      // whole text in the DOM, clipped by CSS
})
