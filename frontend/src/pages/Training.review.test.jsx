// @vitest-environment jsdom
//
// Brief A A3, end to end through the real shell: a trigger on the Training page's WorkoutPanel -> HubLayout's
// `sendToChat` -> the docked ChatPanel -> POST /chat carries `focus_session`. Each hop was written by a different
// change, so each could be right and the chain still drop the reference (the "function exists, nothing reaches
// it" class) — this drives the chain, not the parts.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import Training from './Training'

const HEVY = {
  id: 'hv1', title: 'Lower', start_time: '2026-09-28T21:00:00+00:00', end_time: '2026-09-28T22:10:00+00:00',
  exercises: [{ title: 'Hip Thrust', exercise_template_id: 'T1', sets: [{ type: 'normal', weight_kg: 100, reps: 8 }] }],
}
const AEROBIC = [{ id: 12, source: 'polar_v4', session_date: '2026-09-28', start_time: '2026-09-27T22:01:00Z',
  sport_name: 'Elliptical', duration_minutes: 45, hr_avg: 128, hr_max: 151, calories: 380, z1_seconds: 60,
  z2_seconds: 1500, z3_seconds: 900, z4_seconds: 240, z5_seconds: 0, canonical: true }]

beforeEach(() => {
  localStorage.clear()
  api.get.mockReset()
  api.post.mockReset()
  api.get.mockImplementation((url) => {
    if (url === '/integrations/hevy/workout-count') return Promise.resolve({ data: { workout_count: 1 } })
    if (url.startsWith('/integrations/hevy/workouts?')) return Promise.resolve({ data: { workouts: [HEVY] } })
    if (url.startsWith('/integrations/polar/aerobic-sessions')) return Promise.resolve({ data: AEROBIC })
    return Promise.resolve({ data: {} })
  })
  api.post.mockImplementation((url) => Promise.resolve({
    data: url === '/chat' ? { response: 'ok', actions_taken: [], write_results: [] } : {},
  }))
})
afterEach(cleanup)

const chatCalls = () => api.post.mock.calls.filter(([url]) => url === '/chat')

async function openTraining() {
  await act(async () => { render(<MemoryRouter><Training /></MemoryRouter>) })
  await waitFor(() => expect(screen.getByText('Lower')).toBeTruthy())
}

describe('Training page -> chat carries the session reference', () => {
  test('Review in context (Strength card) posts focus_session scope=context', async () => {
    await openTraining()
    await act(async () => { fireEvent.click(screen.getAllByText('Review in context')[0]) })
    await waitFor(() => expect(chatCalls()).toHaveLength(1))
    expect(chatCalls()[0][1]).toEqual({
      message: 'Context review: Lower, 2026-09-29',
      conversation_history: [],
      focus_session: { kind: 'hevy', id: 'hv1', scope: 'context' },
    })
  })

  test('Review in context (Aerobic card) posts the aerobic reference', async () => {
    await openTraining()
    await act(async () => { fireEvent.click(screen.getAllByText('Review in context')[1]) })
    await waitFor(() => expect(chatCalls()).toHaveLength(1))
    expect(chatCalls()[0][1].focus_session).toEqual({ kind: 'aerobic', id: '12', scope: 'context' })
  })

  test('Session feedback (Hevy detail) posts focus_session scope=session, and no set lines', async () => {
    await openTraining()
    await act(async () => { fireEvent.click(screen.getByText('Lower')) })
    await act(async () => { fireEvent.click(screen.getByText('Session feedback')) })
    await waitFor(() => expect(chatCalls()).toHaveLength(1))
    const body = chatCalls()[0][1]
    expect(body.message).toBe('Session review: Lower, 2026-09-29')
    expect(body.focus_session).toEqual({ kind: 'hevy', id: 'hv1', scope: 'session' })
    expect(JSON.stringify(body)).not.toMatch(/kg|×|Hip Thrust/)
  })
})
