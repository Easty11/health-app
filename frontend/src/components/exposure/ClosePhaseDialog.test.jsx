// @vitest-environment jsdom
//
// ClosePhaseDialog (increment 2, W2). W5: Confirm is disabled until close_reason is non-empty (the
// #222 "reads as an accident" guard); a 404 gives its own message; a 422 shows the server detail.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { post: vi.fn() } }))

import api from '../../api'
import ClosePhaseDialog from './ClosePhaseDialog'

beforeEach(() => { api.post.mockReset() })
afterEach(cleanup)

function confirmBtn() {
  return screen.getByRole('button', { name: /confirm — close to baseline/i })
}

test('Confirm is disabled until close_reason is non-empty', () => {
  render(<ClosePhaseDialog onWritten={vi.fn()} />)
  expect(confirmBtn().disabled).toBe(true)
  fireEvent.change(screen.getByPlaceholderText(/phase complete/), { target: { value: 'done' } })
  expect(confirmBtn().disabled).toBe(false)
})

test('a 404 renders "No open phase to close."', async () => {
  api.post.mockRejectedValue({ response: { status: 404 } })
  render(<ClosePhaseDialog onWritten={vi.fn()} />)
  fireEvent.change(screen.getByPlaceholderText(/phase complete/), { target: { value: 'done' } })
  await act(async () => { fireEvent.click(confirmBtn()) })
  expect(screen.getByText('No open phase to close.')).toBeTruthy()
})

test('a 422 renders the server detail', async () => {
  api.post.mockRejectedValue({
    response: { status: 422, data: { detail: 'close_reason is required' } },
  })
  render(<ClosePhaseDialog onWritten={vi.fn()} />)
  fireEvent.change(screen.getByPlaceholderText(/phase complete/), { target: { value: ' ' } })
  // a non-empty (whitespace) reason enables the control; the server rejects it and we surface detail
  fireEvent.change(screen.getByPlaceholderText(/phase complete/), { target: { value: 'x' } })
  await act(async () => { fireEvent.click(confirmBtn()) })
  expect(screen.getByText('close_reason is required')).toBeTruthy()
})

test('a 200 fires onWritten', async () => {
  const onWritten = vi.fn()
  api.post.mockResolvedValue({ data: { training_phase: null } })
  render(<ClosePhaseDialog onWritten={onWritten} />)
  fireEvent.change(screen.getByPlaceholderText(/phase complete/), { target: { value: 'done' } })
  await act(async () => { fireEvent.click(confirmBtn()) })
  expect(api.post).toHaveBeenCalledWith('/engine/phase/close', { close_reason: 'done' })
  expect(onWritten).toHaveBeenCalledTimes(1)
})
