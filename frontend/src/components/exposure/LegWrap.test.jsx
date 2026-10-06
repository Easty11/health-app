// @vitest-environment jsdom
//
// LegWrap (Know (d), R2 / R3 / R4 / R7 / R8). One row per completed leg from GET /engine/legs, with a
// phase caption, done/quota per key, the leg-over-leg delta, a partial marker, an empty state, and the
// server's note on what is excluded. R8: NO delta ("—") when the leg or its predecessor is partial.
//
// Mutation controls (run by hand, recorded in the PR): `deltaText` ignoring `partial` /
// `previous_partial` fails the R8 tests; `keyLabel` returning the title-cased token fails R7.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../../api'
import LegWrap from './LegWrap'

const EXCLUDED = 'weekly-template periods are not included: the template is not versioned'

function leg(over) {
  return {
    start_date: '2026-10-04', end_date: '2026-10-10', label: 'A', phase: { id: 2, label: 'block-2' },
    partial: false, previous_partial: false,
    keys: [{ kind: 'capacity', key: 'strength', quota: 3, done: 2, delta_done: 1 }],
    ...over,
  }
}

function serve(legs) {
  api.get.mockResolvedValue({ data: { legs, excluded: EXCLUDED } })
}

async function mount(legs) {
  serve(legs)
  await act(async () => { render(<LegWrap />) })
  await waitFor(() => expect(screen.getByRole('region', { name: 'Leg wrap' })).toBeTruthy())
}

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

const deltas = () => screen.getAllByTestId('leg-delta').map((n) => n.textContent)

test('one row per leg: dates, phase caption, done/quota, and the delta; reads /engine/legs', async () => {
  await mount([
    leg({}),
    leg({ start_date: '2026-09-27', end_date: '2026-10-03', phase: { id: 2, label: 'block-2' },
          keys: [{ kind: 'capacity', key: 'strength', quota: 3, done: 1, delta_done: -2 }], previous_partial: false }),
  ])
  expect(api.get).toHaveBeenCalledWith('/engine/legs?n=8')
  expect(screen.getByText('Done vs quota, by leg')).toBeTruthy()
  const rows = screen.getAllByTestId('leg-row')
  expect(rows).toHaveLength(2)
  expect(within(rows[0]).getByText('4 Oct – 10 Oct')).toBeTruthy()
  expect(within(rows[0]).getByText('block-2 · leg A')).toBeTruthy()
  expect(within(rows[0]).getByText('2/3')).toBeTruthy()
  expect(deltas()).toEqual(['+1', '−2'])
})

test('R4: a partial leg carries a partial marker with its actual dates', async () => {
  await mount([leg({ start_date: '2026-08-31', end_date: '2026-09-03', partial: true })])
  const row = screen.getByTestId('leg-row')
  expect(within(row).getByText('partial')).toBeTruthy()
  expect(within(row).getByText('31 Aug – 3 Sep')).toBeTruthy()
})

test('R8: no delta when the leg is partial, even if the server sent one', async () => {
  await mount([leg({ partial: true, keys: [{ kind: 'capacity', key: 'strength', quota: 3, done: 0, delta_done: -2 }] })])
  expect(deltas()).toEqual(['—'])
})

test('R8: no delta when the predecessor in the list is partial', async () => {
  await mount([
    leg({ previous_partial: true, keys: [{ kind: 'capacity', key: 'strength', quota: 3, done: 3, delta_done: 3 }] }),
    leg({ start_date: '2026-08-31', end_date: '2026-09-03', partial: true, previous_partial: false,
          keys: [{ kind: 'capacity', key: 'strength', quota: 3, done: 0, delta_done: 0 }] }),
  ])
  expect(deltas()).toEqual(['—', '—'])
})

test('R8: the oldest returned row withholds its delta on `previous_partial` alone (its predecessor is not in the list)', async () => {
  await mount([leg({ previous_partial: true, keys: [{ kind: 'capacity', key: 'strength', quota: 3, done: 2, delta_done: 2 }] })])
  expect(deltas()).toEqual(['—'])
})

test('R8 control: full leg, full predecessor, shared key -> the delta shows (and zero reads ±0)', async () => {
  await mount([
    leg({ keys: [{ kind: 'capacity', key: 'strength', quota: 3, done: 2, delta_done: 0 }] }),
  ])
  expect(deltas()).toEqual(['±0'])
})

test('a key with no counterpart, an unknown predecessor, or a missing flag shows "—"', async () => {
  await mount([
    leg({ keys: [{ kind: 'capacity', key: 'strength', quota: 3, done: 2, delta_done: null }] }),
    leg({ start_date: '2026-09-20', end_date: '2026-09-26', previous_partial: null }),     // ledger start
    leg({ start_date: '2026-09-13', end_date: '2026-09-19', previous_partial: undefined }), // older server
  ])
  expect(deltas()).toEqual(['—', '—', '—'])
})

test('R7: the load_window kind reads "Conditioning", never "metabolic"', async () => {
  await mount([leg({ keys: [{ kind: 'load_window', key: 'metabolic', quota: 2, done: 1, delta_done: 1 }] })])
  const row = screen.getByTestId('leg-row')
  expect(within(row).getByText('Conditioning')).toBeTruthy()
  expect(row.textContent).not.toMatch(/metabolic/i)
})

test('empty state, and the exclusion note says weekly-template periods are left out', async () => {
  await mount([])
  expect(screen.getByText('No completed legs yet.')).toBeTruthy()
  expect(screen.getByText(/Weekly-template periods are not included: the template is not versioned/)).toBeTruthy()
  expect(screen.queryByTestId('leg-row')).toBeNull()
})

test('a failed read says so rather than rendering an empty history', async () => {
  api.get.mockRejectedValue(new Error('boom'))
  await act(async () => { render(<LegWrap />) })
  await waitFor(() => expect(screen.getByText('Could not load the leg wrap.')).toBeTruthy())
})
