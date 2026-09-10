// @vitest-environment jsdom
//
// QuotaWindow (resolver brief STEP 7, consumes #276). Assertions: a window renders the card title +
// per-slot {Label} · {done}/{quota}, marks the due slot once, and surfaces `uncounted` distinguishing
// untagged from off_plan; baseline (null window) renders nothing; error renders a fault line; a
// refetchKey change re-reads /engine/resolver.

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
    await waitFor(() => expect(screen.getByText('Quota · Week of 2026-09-07')).toBeTruthy())
  })

  test('renders each slot as {Label} · {done}/{quota}', async () => {
    await renderQuota(resolver)
    await waitFor(() => expect(screen.getByText('Strength')).toBeTruthy())
    expect(screen.getByText('1/2')).toBeTruthy()        // strength done/quota
    expect(screen.getByText('Endurance')).toBeTruthy()
    expect(screen.getByText('1/1')).toBeTruthy()        // endurance met
  })

  test('marks exactly the due slot', async () => {
    await renderQuota(resolver)
    await waitFor(() => expect(screen.getByText('Strength')).toBeTruthy())
    const due = screen.getAllByText('due')
    expect(due).toHaveLength(1)                          // only strength (first unmet, Rule 4)
  })

  test('uncounted distinguishes untagged from off_plan', async () => {
    await renderQuota(resolver)
    await waitFor(() => expect(screen.getByText('Not counted')).toBeTruthy())
    expect(screen.getByText(/untagged · 2 exercises/)).toBeTruthy()
    expect(screen.getByText(/off-plan · Power/)).toBeTruthy()
  })
})

describe('degraded states', () => {
  test('baseline (null window) renders nothing', async () => {
    const { container } = { container: document.body }
    await renderQuota({ window: null, slots: [], due_capacity: null, uncounted: [] })
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
