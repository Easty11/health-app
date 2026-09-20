// @vitest-environment jsdom
//
// ExposurePanel integration — the Phase card + structured change flow (#318, PR2), replacing the
// increment-2 Open/Close buttons + inline PhaseForm/ClosePhaseDialog. Assertions: the card shows the
// phase and ONE "Review / change phase" action; that action opens the 8-step flow and writes
// nothing until its confirm; baseline shows "Open a phase"; no write touches the chat channel (#59).

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import ExposurePanel from './ExposurePanel'
import decompression from '../fixtures/engineNextDecompression.json'

const NULL_WINDOW = { window: null, slots: [], due_capacity: null, due_slot: null, uncounted: [] }
const NULL_WEEK = null
const DRAFT = {
  current_phase: { label: 'decompression', intent: 'deload', probe_posture: 'held', entered_on: '2026-09-07' },
  outgoing_review: [], schedule_items: [], sport_names_seen: [{ sport_name: 'Pilates', source: 'health_connect' }],
  routine_folders: [], freshness: { hc_synced_at: null, hc_stale: true, polar_stale: true, polar_pull_ts_exists: false },
}

// Dispatch by URL: /engine/next → payload; /engine/resolver → null window (QuotaWindow renders
// nothing); /engine/week-plan → null (the week line is absent); the transition draft → DRAFT.
function mockGet(payload) {
  api.get.mockImplementation((url) => {
    if (url === '/engine/resolver') return Promise.resolve({ data: NULL_WINDOW })
    if (url === '/engine/week-plan') return Promise.resolve({ data: NULL_WEEK })
    if (url === '/engine/phase/transition/draft') return Promise.resolve({ data: DRAFT })
    return Promise.resolve({ data: payload })
  })
}

beforeEach(() => { api.get.mockReset(); api.post.mockReset() })
afterEach(cleanup)

async function renderReady(payload, onDiscuss = vi.fn()) {
  mockGet(payload)
  await act(async () => { render(<ExposurePanel onDiscuss={onDiscuss} />) })
  await waitFor(() => expect(screen.queryByText('Reading the engine…')).toBeNull())
  return onDiscuss
}

test('the Phase card shows one "Review / change phase" action; it opens the 8-step flow', async () => {
  await renderReady(decompression)
  await waitFor(() => expect(screen.getByText(/Phase · decompression/)).toBeTruthy())
  // no flow before the operator acts
  expect(screen.queryByText(/step 1 of 8/i)).toBeNull()
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /review \/ change phase/i }))
  })
  await waitFor(() => expect(screen.getByText(/step 1 of 8/i)).toBeTruthy())
  // opening the flow writes nothing
  expect(api.post).not.toHaveBeenCalled()
})

test('opening the flow and leaving it never pushes to chat (#59) and writes nothing', async () => {
  const onDiscuss = await renderReady(decompression)
  await waitFor(() => expect(screen.getByText(/Phase · decompression/)).toBeTruthy())
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /review \/ change phase/i }))
  })
  await waitFor(() => expect(screen.getByText(/step 1 of 8/i)).toBeTruthy())
  // close the flow (the ✕) — the draft is discarded, nothing written
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '✕' })) })
  expect(screen.queryByText(/step 1 of 8/i)).toBeNull()
  expect(api.post).not.toHaveBeenCalled()
  expect(onDiscuss).not.toHaveBeenCalled()
})

test('baseline (no phase) shows "Open a phase" and no phase heading', async () => {
  const baseline = { ...decompression, training_phase: null, probe: null }
  await renderReady(baseline)
  expect(screen.getByRole('button', { name: /open a phase/i })).toBeTruthy()
  expect(screen.queryByText(/Phase · /)).toBeNull()
})
