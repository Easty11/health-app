// @vitest-environment jsdom
//
// PhaseForm (increment 2, W1) — the open-a-phase write surface. Assertions track W5: the submit body
// carries the fixed api-client fields and omits the microcycle key when empty; "All capacities"
// sends null; a 422 renders its detail and retains the form; submit is disabled in flight; and the
// advanced microcycle field rejects non-JSON before any request leaves.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { post: vi.fn() } }))

import api from '../../api'
import PhaseForm from './PhaseForm'
import { todayLocal } from './phaseTime'

beforeEach(() => { api.post.mockReset() })
afterEach(cleanup)

function fillRequired({ posture = 'held' } = {}) {
  fireEvent.change(screen.getByPlaceholderText(/Aerobic Base/), { target: { value: 'Aerobic Base' } })
  fireEvent.click(screen.getByRole('button', { name: posture }))
}

describe('submit body shape — API client, no minted source (#230)', () => {
  test('carries asserted_by/source/asserted_on, omits microcycle when empty, null for All', async () => {
    api.post.mockResolvedValue({ data: { training_phase: {} } })
    render(<PhaseForm hasOpenPhase={false} onWritten={vi.fn()} />)
    fillRequired()
    fireEvent.click(screen.getByRole('button', { name: /all capacities/i }))

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /open phase/i }))
    })

    expect(api.post).toHaveBeenCalledTimes(1)
    const [url, body] = api.post.mock.calls[0]
    expect(url).toBe('/engine/phase')
    expect(body.asserted_by).toBe('user')
    expect(body.source).toBe('api')
    expect(body.asserted_on).toBe(todayLocal())
    expect(body.probe_posture).toBe('held')
    expect('microcycle' in body).toBe(false)
    expect(body.capacities).toBe(null)
  })

  test('onWritten fires on a 201', async () => {
    const onWritten = vi.fn()
    api.post.mockResolvedValue({ data: { training_phase: {} } })
    render(<PhaseForm hasOpenPhase={false} onWritten={onWritten} />)
    fillRequired()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /open phase/i }))
    })
    expect(onWritten).toHaveBeenCalledTimes(1)
  })
})

describe('422 — detail rendered, form retained', () => {
  test('shows the server detail and keeps the populated label', async () => {
    api.post.mockRejectedValue({
      response: { status: 422, data: { detail: 'entered_on must be on or before today' } },
    })
    render(<PhaseForm hasOpenPhase={false} onWritten={vi.fn()} />)
    fillRequired()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /open phase/i }))
    })
    expect(screen.getByText('entered_on must be on or before today')).toBeTruthy()
    // form retained — the label the operator typed is still there
    expect(screen.getByPlaceholderText(/Aerobic Base/).value).toBe('Aerobic Base')
  })
})

describe('submit disabled while in flight — double-submit impossible', () => {
  test('the button disables on the first click and does not re-post', async () => {
    let release
    api.post.mockImplementation(() => new Promise((res) => { release = res }))
    render(<PhaseForm hasOpenPhase={false} onWritten={vi.fn()} />)
    fillRequired()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /open phase/i }))
    })
    const btn = screen.getByRole('button', { name: /opening/i })
    expect(btn.disabled).toBe(true)
    await act(async () => { release({ data: {} }) })
    expect(api.post).toHaveBeenCalledTimes(1)
  })
})

describe('advanced microcycle — client check is JSON.parse + object, nothing more', () => {
  test('non-JSON is rejected before any request leaves', async () => {
    api.post.mockResolvedValue({ data: {} })
    render(<PhaseForm hasOpenPhase={false} onWritten={vi.fn()} />)
    fillRequired()
    fireEvent.click(screen.getByRole('button', { name: /advanced/i }))
    fireEvent.change(screen.getByPlaceholderText(/weekly/), { target: { value: 'not json {' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /open phase/i }))
    })
    expect(api.post).not.toHaveBeenCalled()
    expect(screen.getByText(/Microcycle must be valid JSON/)).toBeTruthy()
  })

  test('valid JSON object is sent under the microcycle key', async () => {
    api.post.mockResolvedValue({ data: {} })
    render(<PhaseForm hasOpenPhase={false} onWritten={vi.fn()} />)
    fillRequired()
    fireEvent.click(screen.getByRole('button', { name: /advanced/i }))
    fireEvent.change(screen.getByPlaceholderText(/weekly/), { target: { value: '{"weekly":[1,2]}' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /open phase/i }))
    })
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
    expect(api.post.mock.calls[0][1].microcycle).toEqual({ weekly: [1, 2] })
  })
})

describe('close_prior_reason visibility tracks an open phase', () => {
  test('hidden at baseline, shown when a phase is open', () => {
    const { rerender } = render(<PhaseForm hasOpenPhase={false} onWritten={vi.fn()} />)
    expect(screen.queryByText(/Close prior reason/)).toBeNull()
    rerender(<PhaseForm hasOpenPhase onWritten={vi.fn()} />)
    expect(screen.getByText(/Close prior reason/)).toBeTruthy()
  })
})
