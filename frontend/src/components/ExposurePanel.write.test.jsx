// @vitest-environment jsdom
//
// ExposurePanel integration — the write surface composed into the read panel (increment 2, W4/W5).
// Kept in its own file so the #272 read-path tests (ExposurePanel.test.jsx) stay untouched.
//
// W5 integration assertions: the review-due chip opens the form; a 201 triggers exactly one refetch
// of /engine/next and the panel re-renders from the new payload; no write touches the chat channel
// (#59); and baseline (no phase) shows only "Open next phase".

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import ExposurePanel from './ExposurePanel'
import decompression from '../fixtures/engineNextDecompression.json'
import held from '../fixtures/engineNextHeld.json'

beforeEach(() => { api.get.mockReset(); api.post.mockReset() })
afterEach(cleanup)

async function renderReady(payload, onDiscuss = vi.fn()) {
  api.get.mockResolvedValue({ data: payload })
  await act(async () => { render(<ExposurePanel onDiscuss={onDiscuss} />) })
  await waitFor(() => expect(screen.queryByText('Reading the engine…')).toBeNull())
  return onDiscuss
}

function fillForm({ posture = 'held' } = {}) {
  fireEvent.change(screen.getByPlaceholderText(/Aerobic Base/), { target: { value: 'Aerobic Base' } })
  fireEvent.click(screen.getByRole('button', { name: posture }))
}

test('the review-due chip opens the form (#228 — a prompt, not a transition)', async () => {
  const reviewDue = { ...decompression, training_phase: { ...decompression.training_phase, review_due: true } }
  await renderReady(reviewDue)
  // no form before the operator acts
  expect(screen.queryByText('New phase')).toBeNull()
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /review due — open the next phase/i }))
  })
  expect(screen.getByText('New phase')).toBeTruthy()
  // opening a form writes nothing
  expect(api.post).not.toHaveBeenCalled()
})

test('a 201 triggers exactly one refetch and the panel re-renders from the new payload', async () => {
  // The panel now reads two endpoints (/engine/next + /engine/resolver via QuotaWindow), so dispatch
  // by URL rather than by call order: /engine/next serves decompression then held (FIFO), and
  // /engine/resolver serves a baseline null window (QuotaWindow renders nothing — out of the way).
  const nextQueue = [decompression, held]
  api.get.mockImplementation((url) => {
    if (url === '/engine/resolver') {
      return Promise.resolve({ data: { window: null, slots: [], due_capacity: null, uncounted: [] } })
    }
    return Promise.resolve({ data: nextQueue.shift() ?? held })
  })
  api.post.mockResolvedValue({ data: { training_phase: {} } })
  const onDiscuss = vi.fn()
  await act(async () => { render(<ExposurePanel onDiscuss={onDiscuss} />) })
  await waitFor(() => expect(screen.getByText('Phase · decompression')).toBeTruthy())
  // pre-write: decompression suppresses the probe, so no probe card
  expect(screen.queryByText('Probe · Carry')).toBeNull()

  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /^open next phase$/i })) })
  fillForm()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /open phase/i })) })

  // the refetched payload (held) surfaces the probe card — the visible proof the write took
  await waitFor(() => expect(screen.getByText('Probe · Carry')).toBeTruthy())
  // exactly one refetch of /engine/next (mount + post-write); resolver calls are counted separately
  const nextCalls = api.get.mock.calls.filter((c) => c[0] === '/engine/next')
  expect(nextCalls).toHaveLength(2)
  // no chat push on write (#59)
  expect(onDiscuss).not.toHaveBeenCalled()
})

test('closing to baseline does not push to chat (#59)', async () => {
  api.get.mockResolvedValue({ data: held }) // phase open → Close control present
  api.post.mockResolvedValue({ data: { training_phase: null } })
  const onDiscuss = vi.fn()
  await act(async () => { render(<ExposurePanel onDiscuss={onDiscuss} />) })
  await waitFor(() => expect(screen.getByText('Phase · rebuild')).toBeTruthy())

  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /close to baseline/i })) })
  fireEvent.change(screen.getByPlaceholderText(/phase complete/), { target: { value: 'done' } })
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /confirm — close to baseline/i }))
  })
  expect(api.post).toHaveBeenCalledWith('/engine/phase/close', { close_reason: 'done' })
  expect(onDiscuss).not.toHaveBeenCalled()
})

test('baseline (no phase) shows only "Open next phase"', async () => {
  const baseline = { ...decompression, training_phase: null, probe: null }
  await renderReady(baseline)
  expect(screen.getByRole('button', { name: /^open next phase$/i })).toBeTruthy()
  expect(screen.queryByRole('button', { name: /close to baseline/i })).toBeNull()
})
