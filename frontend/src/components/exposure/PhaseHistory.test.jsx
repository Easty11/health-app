// @vitest-environment jsdom
//
// PhaseHistory (increment 2, W3) — the read-only ledger. W5: collapsed by default (no fetch);
// expanding fetches exactly once (a re-expand does not refetch); rows render newest first as served;
// nothing is editable.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
import PhaseHistory from './PhaseHistory'
import history from '../../fixtures/phaseHistory.json'

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

test('collapsed by default — no fetch, no rows', () => {
  api.get.mockResolvedValue({ data: { history } })
  render(<PhaseHistory />)
  expect(api.get).not.toHaveBeenCalled()
  expect(screen.queryByText('base build')).toBeNull()
  expect(screen.getByRole('button', { name: /phase history/i })).toBeTruthy()
})

test('expand fetches once; a re-expand does not refetch', async () => {
  api.get.mockResolvedValue({ data: { history } })
  render(<PhaseHistory />)
  const toggle = screen.getByRole('button', { name: /phase history/i })

  await act(async () => { fireEvent.click(toggle) })
  await waitFor(() => expect(screen.getByText('base build')).toBeTruthy())
  expect(api.get).toHaveBeenCalledTimes(1)
  expect(api.get).toHaveBeenCalledWith('/engine/phase/history')

  // collapse, then expand again — the rows are kept, no second request
  await act(async () => { fireEvent.click(toggle) })
  await act(async () => { fireEvent.click(toggle) })
  expect(api.get).toHaveBeenCalledTimes(1)
})

test('rows render newest first, as served', async () => {
  api.get.mockResolvedValue({ data: { history } })
  const { container } = render(<PhaseHistory />)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /phase history/i })) })
  await waitFor(() => expect(screen.getByText('decompression')).toBeTruthy())
  const items = [...container.querySelectorAll('li')]
  expect(items).toHaveLength(2)
  expect(items[0].textContent).toContain('decompression')
  expect(items[1].textContent).toContain('base build')
  // the open row shows "open"; the closed prior shows its close reason and "all" capacities
  expect(items[0].textContent).toContain('open')
  expect(items[1].textContent).toContain('progressed to decompression')
  expect(items[1].textContent).toContain('all')
})

test('no edit affordance — the ledger is read-only', async () => {
  api.get.mockResolvedValue({ data: { history } })
  render(<PhaseHistory />)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /phase history/i })) })
  await waitFor(() => expect(screen.getByText('base build')).toBeTruthy())
  expect(screen.queryByRole('textbox')).toBeNull()
  // the only control is the collapse toggle; no per-row edit/delete/save buttons
  expect(screen.queryByRole('button', { name: /edit|delete|save|remove/i })).toBeNull()
})


// ---- the wire shape: the server returns {history: [...]}, not a bare array (4 Oct 2026) ----------------
// The component read `Array.isArray(res.data)`, so against the real server it always rendered "No phases
// recorded yet" while its tests (a bare-array fixture) passed. The tests above now mock the real envelope.

const serverHistory = {
  history: [
    { id: 9, label: 'decompression', probe_posture: 'held', capacities: null, entered_on: '2026-10-04',
      review_on: '2026-11-16', closed_on: null, close_reason: null },
    { id: 8, label: 'decompression', probe_posture: 'held', capacities: null, entered_on: '2026-09-21',
      review_on: null, closed_on: '2026-10-04', close_reason: 'block did its job: partly' },
    { id: 1, label: 'decompression', probe_posture: 'suppressed', capacities: ['mobility', 'stability'],
      entered_on: '2026-09-07', review_on: '2026-10-05', closed_on: '2026-09-21', close_reason: 'opened decompression' },
  ],
}

test('renders every ledger row the server envelope carries, newest first, only the newest open', async () => {
  api.get.mockResolvedValue({ data: serverHistory })
  render(<PhaseHistory />)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /phase history/i })) })
  await waitFor(() => expect(screen.getAllByText('decompression').length).toBe(3))
  expect(screen.queryByText(/No phases recorded yet/i)).toBeNull()
  const spans = screen.getAllByText(/→/).map((n) => n.textContent.trim())
  expect(spans).toEqual(['2026-10-04 → open', '2026-09-21 → 2026-10-04', '2026-09-07 → 2026-09-21'])
  expect(screen.getByText(/Closed: block did its job: partly/)).toBeTruthy()
})

test('an empty ledger says so; a bare array (the old, wrong shape) is not read as rows', async () => {
  api.get.mockResolvedValue({ data: { history: [] } })
  const { unmount } = render(<PhaseHistory />)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /phase history/i })) })
  await waitFor(() => expect(screen.getByText(/No phases recorded yet/i)).toBeTruthy())
  unmount()
  api.get.mockResolvedValue({ data: serverHistory.history })      // not what the server sends
  render(<PhaseHistory />)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /phase history/i })) })
  await waitFor(() => expect(screen.getByText(/No phases recorded yet/i)).toBeTruthy())
})


// #379 R4 — a zero-length row is LABELLED, never collapsed or hidden: a muted row with a
// "same-day correction" chip, and its close reason is still shown.
test('R4: a zero_length row is labelled "same-day correction", muted, with its close reason; others are not', async () => {
  const rows = [
    { id: 3, label: 'corrected', probe_posture: 'held', capacities: null, entered_on: '2026-10-05',
      closed_on: null, close_reason: null, zero_length: false },
    { id: 2, label: 'first save', probe_posture: 'held', capacities: null, entered_on: '2026-10-05',
      closed_on: '2026-10-05', close_reason: 'opened corrected', zero_length: true },
    { id: 1, label: 'base build', probe_posture: 'held', capacities: null, entered_on: '2026-08-01',
      closed_on: '2026-10-05', close_reason: 'opened first save', zero_length: false },
  ]
  api.get.mockResolvedValue({ data: { history: rows } })
  const { container } = render(<PhaseHistory />)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /phase history/i })) })
  await waitFor(() => expect(screen.getByText('first save')).toBeTruthy())
  const items = [...container.querySelectorAll('li')]
  expect(items).toHaveLength(3)                                         // nothing hidden or collapsed
  const flagged = items.find((li) => li.textContent.includes('first save'))
  expect(flagged.textContent).toContain('same-day correction')
  expect(flagged.textContent).toContain('Closed: opened corrected')     // the reason is still shown
  expect(flagged.getAttribute('data-zero-length')).toBe('true')
  expect(flagged.className).toMatch(/opacity-60/)                       // muted
  expect(container.querySelectorAll('li[data-zero-length]')).toHaveLength(1)
  expect(screen.getAllByText('same-day correction')).toHaveLength(1)    // only the flagged row carries the chip
})
