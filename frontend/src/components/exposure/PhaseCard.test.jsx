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

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

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
  api.get.mockReset()
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
  await waitFor(() => expect(screen.getByText(/Stability — scheduled 3 · quota 2 · done 1 — MISMATCH \+1/)).toBeTruthy())
  expect(screen.getByText(/Device-evidenced counts may be incomplete/)).toBeTruthy()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /review \/ change phase/i })) })
  expect(onReviewChange).toHaveBeenCalled()
})

test('baseline (no phase) shows "Open a phase"', async () => {
  const onReviewChange = vi.fn()
  await act(async () => { render(<PhaseCard phase={null} onReviewChange={onReviewChange} />) })
  expect(screen.getByRole('button', { name: /open a phase/i })).toBeTruthy()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /open a phase/i })) })
  expect(onReviewChange).toHaveBeenCalled()
})
