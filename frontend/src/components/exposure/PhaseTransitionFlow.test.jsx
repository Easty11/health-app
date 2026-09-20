// @vitest-environment jsdom
//
// PhaseTransitionFlow (#318, PR2 S6, G7) — the 8-step phase-change form. Assertions: it prefills
// from the draft read; Next advances the steps and the draft-discard notice is always shown; the
// acknowledgement tick gates Next when the schedule mismatches the quota at step 5; the single
// confirm POSTs /engine/phase/transition and calls onWritten on success; a 422 shows the server's
// `detail` VERBATIM (the server is the validator, #230 — no client-side re-validation).

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../../api'
import PhaseTransitionFlow from './PhaseTransitionFlow'

const DRAFT = {
  current_phase: { label: 'decompression', intent: 'deload', probe_posture: 'held', entered_on: '2026-09-07' },
  outgoing_review: [
    { window: { label: 'A', start_date: '2026-09-07', end_date: '2026-09-13' },
      slots: [{ kind: 'capacity', key: 'stability', quota: 2, done: 2 }], uncounted: [] },
  ],
  schedule_items: [],
  sport_names_seen: [{ sport_name: 'Pilates', source: 'health_connect' }],
  routine_folders: [{ id: '11', title: 'Decompression' }],
  freshness: { hc_synced_at: null, hc_stale: true, polar_stale: true, polar_pull_ts_exists: false },
}

beforeEach(() => { api.get.mockReset(); api.post.mockReset(); api.get.mockResolvedValue({ data: DRAFT }) })
afterEach(cleanup)

async function renderFlow(onWritten = vi.fn()) {
  await act(async () => { render(<PhaseTransitionFlow onWritten={onWritten} onCancel={vi.fn()} />) })
  await waitFor(() => expect(screen.getByText(/step 1 of 8/i)).toBeTruthy())
  return onWritten
}

const next = async () => { await act(async () => { fireEvent.click(screen.getByRole('button', { name: /^next$/i })) }) }

test('prefills from the draft and advances through steps with a draft-discard notice', async () => {
  await renderFlow()
  expect(screen.getByText(/Review the outgoing phase/i)).toBeTruthy()
  expect(screen.getByText(/Leaving discards this draft/i)).toBeTruthy()
  // outgoing review is rendered
  expect(screen.getByText(/Stability 2\/2/)).toBeTruthy()
  await next()
  expect(screen.getByText(/step 2 of 8/i)).toBeTruthy()
  // Continue → label prefilled from the outgoing phase and locked
  expect(screen.getByDisplayValue('decompression')).toBeTruthy()
})

test('the acknowledgement tick gates Next on a schedule↔quota mismatch (step 5)', async () => {
  await renderFlow()
  await next()  // 2
  await next()  // 3
  await next()  // 4 — quota
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /\+ quota slot/i })) })
  await next()  // 5 — placement; the slot wants 2 sessions, nothing is placed → mismatch
  expect(screen.getByText(/UNPLACED 2/)).toBeTruthy()
  // Next is blocked until the mismatch is acknowledged
  expect(screen.getByRole('button', { name: /^next$/i }).disabled).toBe(true)
  await act(async () => { fireEvent.click(screen.getByRole('checkbox')) })
  expect(screen.getByRole('button', { name: /^next$/i }).disabled).toBe(false)
})

test('the single confirm POSTs the transition and calls onWritten on success', async () => {
  api.post.mockResolvedValue({ data: { training_phase: {}, no_op: false } })
  const onWritten = await renderFlow()
  for (let i = 0; i < 7; i++) await next()   // → step 8 (no slots, so step 5 has no mismatch)
  expect(screen.getByText(/step 8 of 8/i)).toBeTruthy()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /confirm — save phase change/i })) })
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
  const [url, body] = api.post.mock.calls[0]
  expect(url).toBe('/engine/phase/transition')
  expect(body.phase.label).toBe('decompression')   // continued label
  expect(body.phase.source).toBe('api')
  expect(onWritten).toHaveBeenCalled()
})

test('a 422 shows the server detail verbatim (server is the validator)', async () => {
  const detail = 'microcycle.sub_cycles[0].slots[0].device_sports must be a non-empty list of sport names'
  api.post.mockRejectedValue({ response: { status: 422, data: { detail } } })
  const onWritten = await renderFlow()
  for (let i = 0; i < 7; i++) await next()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /confirm — save phase change/i })) })
  await waitFor(() => expect(screen.getByText(detail)).toBeTruthy())
  expect(onWritten).not.toHaveBeenCalled()   // nothing advanced on a refused write
})
