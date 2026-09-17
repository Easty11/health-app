// @vitest-environment jsdom
//
// QuotaWindow (resolver brief STEP 7, consumes #276/#307). Assertions: a window renders the card
// title + per-slot {Label} · {done}/{quota} across BOTH kinds (capacity + the load_window
// "Conditioning" slot), marks the due slot once via `due_slot` (on either kind), and surfaces
// `uncounted` distinguishing all four reasons (untagged / off_plan for Hevy; concurrent_strength /
// untimed for aerobic sessions); baseline (null window) renders nothing; error renders a fault
// line; a refetchKey change re-reads /engine/resolver.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
import QuotaWindow from './QuotaWindow'
import resolver from '../../fixtures/engineResolver.json'

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

async function renderQuota(payload, refetchKey = 0) {
  api.get.mockResolvedValue({ data: payload })
  await act(async () => { render(<QuotaWindow refetchKey={refetchKey} />) })
}

describe('a live quota window', () => {
  test('reads /engine/resolver and titles the card from the window label', async () => {
    await renderQuota(resolver)
    expect(api.get).toHaveBeenCalledWith('/engine/resolver')
    await waitFor(() => expect(screen.getByText('Quota · A')).toBeTruthy())
  })

  test('renders each slot as {Label} · {done}/{quota}, across both kinds', async () => {
    await renderQuota(resolver)
    await waitFor(() => expect(screen.getByText('Strength')).toBeTruthy())
    expect(screen.getByText('1/2')).toBeTruthy()        // strength done/quota
    expect(screen.getByText('Endurance')).toBeTruthy()
    expect(screen.getByText('1/1')).toBeTruthy()        // endurance met
    expect(screen.getByText('Conditioning')).toBeTruthy()  // the load_window slot (#307)
    expect(screen.getByText('1/3')).toBeTruthy()        // conditioning done/quota
  })

  test('marks exactly the due slot, from due_slot (Rule 4, first unmet in order)', async () => {
    await renderQuota(resolver)
    await waitFor(() => expect(screen.getByText('Strength')).toBeTruthy())
    const due = screen.getAllByText('due')
    expect(due).toHaveLength(1)                          // only strength (due_slot = capacity/strength)
  })

  test('the due marker lands on a load_window slot when due_slot names it', async () => {
    // A conditioning-first window with everything else met → the load_window slot is due.
    const payload = {
      window: { start_date: '2026-09-07', end_date: '2026-09-13', label: 'B', source: 'phase' },
      slots: [
        { kind: 'load_window', load_window: 'metabolic', quota: 2, done: 0, remaining: 2, sessions_counted: [] },
        { kind: 'capacity', capacity: 'strength', quota: 1, done: 1, remaining: 0, workouts_counted: ['w1'] },
      ],
      due_capacity: null,
      due_slot: { kind: 'load_window', key: 'metabolic' },
      uncounted: [],
    }
    await renderQuota(payload)
    await waitFor(() => expect(screen.getByText('Conditioning')).toBeTruthy())
    const due = screen.getAllByText('due')
    expect(due).toHaveLength(1)
    // The due chip sits on the Conditioning row, not Strength (met).
    const conditioningRow = screen.getByText('Conditioning').closest('li')
    expect(conditioningRow.textContent).toContain('due')
  })

  test('uncounted names all four reasons', async () => {
    await renderQuota(resolver)
    await waitFor(() => expect(screen.getByText('Not counted')).toBeTruthy())
    expect(screen.getByText(/untagged · 2 exercises/)).toBeTruthy()
    expect(screen.getByText(/off-plan · Power/)).toBeTruthy()
    expect(screen.getByText(/concurrent strength · Row/)).toBeTruthy()   // aerobic overlapping the gym
    expect(screen.getByText(/untimed · Swim/)).toBeTruthy()              // NULL start/stop
  })
})

describe('degraded states', () => {
  test('baseline (null window) renders nothing', async () => {
    const { container } = { container: document.body }
    await renderQuota({ window: null, slots: [], due_capacity: null, due_slot: null, uncounted: [] })
    // nothing from this component — no card title, no "Not counted"
    expect(screen.queryByText(/^Quota ·/)).toBeNull()
    expect(screen.queryByText('Not counted')).toBeNull()
    expect(container).toBeTruthy()
  })

  test('no uncounted line when the list is empty', async () => {
    await renderQuota({ ...resolver, uncounted: [] })
    await waitFor(() => expect(screen.getByText('Strength')).toBeTruthy())
    expect(screen.queryByText('Not counted')).toBeNull()
  })

  test('a fetch error renders a fault line, not silence-as-empty', async () => {
    api.get.mockRejectedValue(new Error('boom'))
    await act(async () => { render(<QuotaWindow />) })
    await waitFor(() => expect(screen.getByText(/Could not load the quota window/)).toBeTruthy())
  })
})

test('a refetchKey change re-reads /engine/resolver', async () => {
  api.get.mockResolvedValue({ data: resolver })
  const { rerender } = render(<QuotaWindow refetchKey={0} />)
  await waitFor(() => expect(screen.getByText('Strength')).toBeTruthy())
  expect(api.get).toHaveBeenCalledTimes(1)
  await act(async () => { rerender(<QuotaWindow refetchKey={1} />) })
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2))
})
