// @vitest-environment jsdom
//
// The AM check-in fires the Garmin HRV on-read refresh (#299's pattern on a second surface), so
// opening the check-in lands this morning's night without the Recovery card being opened first.
// Pinned: G1 mount POSTs without force; G2 a real run re-fetches the prefill exactly once and
// updates the tile; G3 a skip re-fetches nothing; G4 a rejected refresh leaves the form working
// and submittable; G5 a user-edited field survives the re-fetch (only the passive tiles update).

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import CheckInAM from './CheckInAM'

const STALE = { hrv_ms: null, hrv_state: 'stale_withheld', sleep_min: 420, existing: null,
                cbti: { block_open: false }, diary_prefill: {} }
const FRESH = { ...STALE, hrv_ms: 62, hrv_state: 'value', hrv_source: 'garmin',
                hrv_vs_baseline: 3.5, morning_readiness: 1 }

let resolveRefresh
const prefillCalls = () => api.get.mock.calls.filter(([u]) => u === '/checkin-v2/prefill').length
const refreshCalls = () => api.post.mock.calls.filter(([u]) => u === '/integrations/garmin/refresh')

beforeEach(() => {
  api.get.mockImplementation(() =>
    Promise.resolve({ data: prefillCalls() <= 1 ? STALE : FRESH }))
  api.post.mockImplementation((url) => {
    if (url === '/integrations/garmin/refresh') {
      return new Promise((res, rej) => { resolveRefresh = { res, rej } })
    }
    return Promise.resolve({ data: { am_timestamp: 'x', naive_baseline: 5 } })
  })
})
afterEach(() => { cleanup(); vi.clearAllMocks() })

const renderIt = () => render(<MemoryRouter><CheckInAM /></MemoryRouter>)

test('G1: mount fires the refresh POST without force', async () => {
  renderIt()
  await screen.findByText('–')
  expect(refreshCalls()).toHaveLength(1)
  expect(refreshCalls()[0][2]).toBeUndefined()           // no { params: { force } }
})

test('G2: a real run re-fetches the prefill exactly once and the tile updates', async () => {
  renderIt()
  await screen.findByText('–')
  resolveRefresh.res({ data: { days_with_data: 1, readings_upserted: 1 } })
  await screen.findByText(/HRV · garmin/)
  expect(screen.getByText(/62/)).toBeTruthy()
  expect(prefillCalls()).toBe(2)
})

test('G3: a skipped result re-fetches nothing', async () => {
  renderIt()
  await screen.findByText('–')
  resolveRefresh.res({ data: { skipped: true, reason: 'fresh' } })
  await new Promise((r) => setTimeout(r, 20))
  expect(prefillCalls()).toBe(1)
  expect(screen.getByText('–')).toBeTruthy()
})

test('G4: a rejected refresh leaves the form rendering and submitting', async () => {
  renderIt()
  await screen.findByText('–')
  resolveRefresh.rej(new Error('network'))
  await new Promise((r) => setTimeout(r, 20))
  expect(prefillCalls()).toBe(1)
  fireEvent.click(screen.getByRole('button', { name: /save|submit/i }))
  await waitFor(() =>
    expect(api.post.mock.calls.some(([u]) => u === '/checkin-v2/am')).toBe(true))
})

test('G5: a user-edited field survives the re-fetch', async () => {
  const { container } = renderIt()
  await screen.findByText('–')
  fireEvent.click(screen.getByTitle('Great'))                 // readiness → 5 (prefill says 3, FRESH says 1)
  const notes = container.querySelector('textarea')
  fireEvent.change(notes, { target: { value: 'slept badly' } })

  resolveRefresh.res({ data: { days_with_data: 1 } })
  await screen.findByText(/HRV · garmin/)

  expect(container.querySelector('textarea').value).toBe('slept badly')
  fireEvent.click(screen.getByRole('button', { name: /save|submit/i }))
  await waitFor(() => {
    const am = api.post.mock.calls.find(([u]) => u === '/checkin-v2/am')
    expect(am).toBeTruthy()
    expect(am[1].morning_readiness).toBe(5)
    expect(am[1].am_notes).toBe('slept badly')
  })
})

test('race: a refresh that lands before the first prefill is not overwritten by it', async () => {
  let resolveFirst
  let n = 0
  api.get.mockImplementation(() => {
    n += 1
    if (n === 1) return new Promise((res) => { resolveFirst = res })   // slow first load
    return Promise.resolve({ data: FRESH })
  })
  renderIt()
  await waitFor(() => expect(refreshCalls()).toHaveLength(1))
  resolveRefresh.res({ data: { days_with_data: 1 } })
  await waitFor(() => expect(n).toBe(2))
  resolveFirst({ data: STALE })                                        // older snapshot arrives last
  await screen.findByText(/HRV · garmin/)
  expect(screen.queryByText('–')).toBeNull()
})
