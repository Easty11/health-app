// @vitest-environment jsdom
//
// Needs your call on the AM saved screen (DECISIONS_LOG "Proposals and reviews due render on the AM
// check-in saved screen"): reviews due then proposals, from /knowledge/review-due and /knowledge/proposals,
// with the SAME actions and routes as the Injuries page (shared components); both empty renders nothing;
// a failed read renders nothing and never blocks the saved screen; the reads fire once after save, never
// before and never on every render. Fixtures are SYNTHETIC.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import CheckInAM from './CheckInAM'

const BASE = { hrv_ms: null, hrv_state: 'absent', sleep_min: null, existing: null,
               cbti: { block_open: false }, diary_prefill: {}, missed_pm: null }
const SAVED = { ...BASE, existing: { am_timestamp: 'x', naive_baseline: 6 } }

const PROPOSALS = [
  { id: 10, type: 'constraint', key: 'c_prop', active: true, source: 'chat', added_at: '2025-12-01',
    value: { scope: { tier: 'advisory', text: 'cap on movement A' }, kind: 'cap', parent_key: 'injury_part_a_left',
      exit: { on_condition: 'condition A' }, review_by: '2026-01-15', status: 'proposed', asserted_by: null } },
]
const DUE = { as_of: '2026-11-04', withheld_labs: 0, items: [
  { id: 5, type: 'constraint', key: 'c_due', what: 'BLOCK (advisory) — no movement B', tags: ['review due'],
    parent_key: 'injury_part_b_right', authority: 'user', status: 'confirmed', review_by: '2026-10-20',
    exit_on_date: null, days_overdue: 15 },
] }

let prefill, proposals, due, failReads
function routeGets() {
  api.get.mockImplementation((url) => {
    if (url === '/checkin-v2/prefill') return Promise.resolve({ data: prefill })
    if (failReads) return Promise.reject(new Error('down'))
    if (url === '/knowledge/proposals') return Promise.resolve({ data: proposals })
    if (url === '/knowledge/review-due') return Promise.resolve({ data: due })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}
const gets = (url) => api.get.mock.calls.filter(([u]) => u === url).length

beforeEach(() => {
  prefill = SAVED; proposals = PROPOSALS; due = DUE; failReads = false
  api.get.mockReset(); api.post.mockReset()
  routeGets()
  api.post.mockImplementation((url) => {
    if (url === '/integrations/garmin/refresh') return Promise.resolve({ data: { skipped: true } })
    return Promise.resolve({ data: {} })
  })
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

const renderIt = () => render(<MemoryRouter><CheckInAM /></MemoryRouter>)

test('both lists populated: reviews due then proposals, between the saved summary and the buttons', async () => {
  renderIt()
  await screen.findByText('Morning check-in saved')
  const block = await screen.findByRole('region', { name: 'Needs your call' })
  const reviewDue = within(block).getByRole('region', { name: 'Review due' })
  expect(within(reviewDue).getByText(/no movement B/)).toBeTruthy()
  expect(within(block).getByText(/cap on movement A/)).toBeTruthy()
  expect(reviewDue.compareDocumentPosition(within(block).getByText(/cap on movement A/)) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  const heading = screen.getByText('Morning check-in saved')
  const button = screen.getByRole('button', { name: 'Go to Dashboard' })
  expect(heading.compareDocumentPosition(block) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(block.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

test('Confirm, Decline, Keep and Resolve POST the same routes and bodies as the Injuries page, then re-read', async () => {
  renderIt()
  const block = await screen.findByRole('region', { name: 'Needs your call' })
  const proposal = within(block).getByText(/cap on movement A/).closest('li')
  await act(async () => { within(proposal).getByRole('button', { name: 'Clinician' }).click() })
  await act(async () => { within(proposal).getByRole('button', { name: 'Confirm proposal' }).click() })
  expect(api.post).toHaveBeenCalledWith('/knowledge/constraints/10/confirm', { asserted_by: 'clinician' })
  await waitFor(() => expect(gets('/knowledge/proposals')).toBe(2))      // the re-read after the act

  const dueItem = within(block).getByText(/no movement B/).closest('li')
  await act(async () => { within(dueItem).getByRole('button', { name: /Keep — review again on/ }).click() })
  fireEvent.change(within(dueItem).getByLabelText('Review again on'), { target: { value: '2099-01-01' } })
  await act(async () => { within(dueItem).getByRole('button', { name: 'Keep' }).click() })
  expect(api.post).toHaveBeenCalledWith('/knowledge/constraints/5/review', { review_by: '2099-01-01' })
})

test('Resolve and Decline POST the resolve routes with a basis and an authority, as on the Injuries page', async () => {
  renderIt()
  const block = await screen.findByRole('region', { name: 'Needs your call' })
  const proposal = within(block).getByText(/cap on movement A/).closest('li')
  const dueItem = within(block).getByText(/no movement B/).closest('li')
  await act(async () => { within(dueItem).getByRole('button', { name: 'Resolve…' }).click() })
  fireEvent.change(within(dueItem).getByLabelText(/why is this no longer needed/), { target: { value: 'cleared by the physio, full range' } })
  await act(async () => { within(dueItem).getByRole('button', { name: 'User' }).click() })
  await act(async () => { within(dueItem).getByRole('button', { name: 'Confirm resolution' }).click() })
  expect(api.post).toHaveBeenCalledWith('/knowledge/constraints/5/resolve', { basis: 'cleared by the physio, full range', resolved_by: 'user' })

  await act(async () => { within(proposal).getByRole('button', { name: 'Decline…' }).click() })
  fireEvent.change(within(proposal).getByLabelText(/why decline this proposal/), { target: { value: 'not an active restriction now' } })
  // Two authority rows are on the item now (Confirm's and the decline form's); the form's is last.
  await act(async () => { within(proposal).getAllByRole('button', { name: 'User' }).at(-1).click() })
  await act(async () => { within(proposal).getByRole('button', { name: 'Decline proposal' }).click() })
  expect(api.post).toHaveBeenCalledWith('/knowledge/constraints/10/resolve', { basis: 'not an active restriction now', resolved_by: 'user' })
})

test('both lists empty: no block, no empty-state text', async () => {
  proposals = []; due = { ...DUE, items: [] }
  renderIt()
  await screen.findByText('Morning check-in saved')
  await waitFor(() => expect(gets('/knowledge/proposals')).toBe(1))
  expect(screen.queryByRole('region', { name: 'Needs your call' })).toBeNull()
  expect(screen.queryByText(/Review due/)).toBeNull()
  expect(screen.queryByText(/Awaiting your confirmation/)).toBeNull()
})

test('a failed read renders nothing and leaves the saved screen intact', async () => {
  failReads = true
  renderIt()
  await screen.findByText('Morning check-in saved')
  await waitFor(() => expect(gets('/knowledge/proposals')).toBe(1))
  expect(screen.queryByRole('region', { name: 'Needs your call' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Go to Dashboard' })).toBeTruthy()
  expect(console.warn).toHaveBeenCalled()
})

test('the reads fire once after save, never on the form and never per render', async () => {
  prefill = BASE
  renderIt()
  await screen.findByText('Morning Check-in')
  expect(gets('/knowledge/proposals')).toBe(0)
  expect(gets('/knowledge/review-due')).toBe(0)
  fireEvent.click(screen.getByRole('button', { name: 'Save Check-in' }))
  await screen.findByText('Morning check-in saved')
  await screen.findByRole('region', { name: 'Needs your call' })
  expect(gets('/knowledge/proposals')).toBe(1)
  expect(gets('/knowledge/review-due')).toBe(1)
  // Interaction that re-renders without an act on a row: still one read each.
  const proposal = screen.getByText(/cap on movement A/).closest('li')
  await act(async () => { within(proposal).getByRole('button', { name: 'User' }).click() })
  expect(gets('/knowledge/proposals')).toBe(1)
})
