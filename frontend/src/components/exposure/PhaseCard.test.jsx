// @vitest-environment jsdom
//
// PhaseCard (#318, PR2 S5) — the phase surface. Assertions: it renders the phase + week N + the
// review badge, the #316 week line (scheduled·quota·done + freshness) from /engine/week-plan, and
// ONE "Review / change phase" action that calls onReviewChange; baseline (no phase) shows "Open a
// phase". QuotaWindow (/engine/resolver) and PhaseHistory (/engine/phase/history) are composed and
// served null-ish so the card renders standalone.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../../api'
import PhaseCard from './PhaseCard'

const WEEK = {
  window: { label: 'A', start_date: '2026-09-07', end_date: '2026-09-13', source: 'phase' },
  keys: [{ kind: 'capacity', key: 'stability', quota: 2, done: 1, scheduled: 3, excess: 1, unplaced: 0 }],
  days: [], unlinked_soft: [], one_off_notes: [], needs_planning: false,
  freshness: { hc_synced_at: null, hc_stale: true, polar_stale: true, polar_pull_ts_exists: false },
}
const PHASE = { label: 'decompression', probe_posture: 'held', entered_on: '2026-09-07',
                review_on: '2026-10-05', review_due: true, capacities: ['stability'] }

beforeEach(() => {
  api.get.mockReset(); api.post.mockReset()
  api.post.mockResolvedValue({ data: {} })
  api.get.mockImplementation((url) => {
    if (url === '/engine/week-plan') return Promise.resolve({ data: WEEK })
    if (url === '/engine/resolver') return Promise.resolve({ data: { window: null, slots: [], due_slot: null, uncounted: [] } })
    if (url === '/engine/phase/history') return Promise.resolve({ data: { history: [] } })
    return Promise.resolve({ data: {} })
  })
})
afterEach(cleanup)

test('renders the phase, week N, review badge, the week line, and the one action', async () => {
  const onReviewChange = vi.fn()
  await act(async () => { render(<PhaseCard phase={PHASE} onReviewChange={onReviewChange} />) })
  expect(screen.getByText(/Phase · decompression · week \d+/)).toBeTruthy()
  expect(screen.getByText('review due')).toBeTruthy()
  // The leg strip (Know (d)) replaced the "Schedule vs quota" lines: the quota tray names the key,
  // done/quota, and the over-schedule; the old line is gone.
  await waitFor(() => expect(screen.getByText('Stability · 1/2')).toBeTruthy())
  expect(screen.getByText('1 over quota')).toBeTruthy()
  expect(screen.queryByText('Schedule vs quota')).toBeNull()
  expect(screen.getByText(/Device-evidenced counts may be incomplete/)).toBeTruthy()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /review \/ change phase/i })) })
  expect(onReviewChange).toHaveBeenCalled()
})

test('baseline (no phase) shows "Open a phase"', async () => {
  const onReviewChange = vi.fn()
  await act(async () => { render(<PhaseCard phase={null} onReviewChange={onReviewChange} />) })
  expect(screen.getByRole('button', { name: /^open a phase$/i })).toBeTruthy()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /^open a phase$/i })) })
  expect(onReviewChange).toHaveBeenCalled()
})

// #319 — plan of record on the card: headline + STALE badge from GET /engine/plan-of-record (the
// SAME stale flag the chat computes, never re-derived here), full macro on expand.
test('renders the plan-of-record headline, STALE badge, and full macro on expand', async () => {
  api.get.mockImplementation((url) => {
    if (url === '/engine/plan-of-record') return Promise.resolve({ data: {
      macro: '## Offseason\nPhase 1 base; buffer rule first.', revised_on: '2026-08-15',
      revised_by: 'coach', stale: true } })
    if (url === '/engine/week-plan') return Promise.resolve({ data: WEEK })
    if (url === '/engine/resolver') return Promise.resolve({ data: { window: null, slots: [], due_slot: null, uncounted: [] } })
    if (url === '/engine/phase/history') return Promise.resolve({ data: { history: [] } })
    return Promise.resolve({ data: {} })
  })
  await act(async () => { render(<PhaseCard phase={PHASE} onReviewChange={vi.fn()} onWritten={vi.fn()} />) })
  await waitFor(() => expect(screen.getByText('Offseason')).toBeTruthy())   // headline, '#' stripped
  expect(screen.getByText('plan may be stale')).toBeTruthy()
  expect(screen.queryByText(/buffer rule first/)).toBeNull()               // full macro hidden
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /show full plan/i })) })
  expect(screen.getByText(/buffer rule first/)).toBeTruthy()               // shown on expand
})

// #378 R1 — the direct-open form and the "Advanced" disclosure are gone; closing to baseline stays,
// as its own small control rather than under a disclosure.
test('R1: no Advanced disclosure and no direct open path, with a phase open or at baseline', async () => {
  const { unmount } = render(<PhaseCard phase={PHASE} onReviewChange={vi.fn()} onWritten={vi.fn()} />)
  await act(async () => {})
  expect(screen.queryByRole('button', { name: /advanced/i })).toBeNull()
  expect(screen.queryByRole('button', { name: /open a new phase/i })).toBeNull()
  unmount()
  await act(async () => { render(<PhaseCard phase={null} onReviewChange={vi.fn()} onWritten={vi.fn()} />) })
  expect(screen.queryByRole('button', { name: /advanced/i })).toBeNull()
  expect(screen.queryByRole('button', { name: /open a new phase/i })).toBeNull()
})

test('R1: "End phase → baseline" is its own control, closes through the close route, and refetches', async () => {
  const onWritten = vi.fn()
  await act(async () => { render(<PhaseCard phase={PHASE} onReviewChange={vi.fn()} onWritten={onWritten} />) })
  // visible without opening any disclosure
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'End phase → baseline' })) })
  const confirm = screen.getByRole('button', { name: /confirm — close to baseline/i })
  expect(confirm.disabled).toBe(true)                                   // a reason is required
  await act(async () => { fireEvent.change(screen.getByRole('textbox'), { target: { value: 'phase complete' } }) })
  await act(async () => { fireEvent.click(confirm) })
  expect(api.post).toHaveBeenCalledWith('/engine/phase/close', { close_reason: 'phase complete' })
  expect(onWritten).toHaveBeenCalled()
})

test('R1: there is nothing to end at baseline, so no "End phase" control', async () => {
  await act(async () => { render(<PhaseCard phase={null} onReviewChange={vi.fn()} />) })
  expect(screen.queryByRole('button', { name: 'End phase → baseline' })).toBeNull()
})
