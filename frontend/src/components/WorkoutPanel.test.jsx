// @vitest-environment jsdom
//
// Brief A A3/A5 — session review by REFERENCE, and a session list that is correct.
//
// A3: the two triggers send a short message plus `focus_session`; the client no longer formats a session
//     (the lossy formatHevyMessage/formatPolarMessage are gone), so no set lines can be dropped or invented.
// A5: the aerobic list renders canonical rows only, every displayed date is the local calendar date, the
//     header names every source, and a row with no HR says so instead of showing bare dashes.
//
// Fixtures are synthetic placeholders.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import WorkoutPanel from './WorkoutPanel'

// 07:00 AEST on 29 Sep == 21:00 UTC on 28 Sep — the UTC-sliced date is the 28th.
const HEVY = {
  id: 'hv1', title: 'Lower', start_time: '2026-09-28T21:00:00+00:00', end_time: '2026-09-28T22:10:00+00:00',
  exercises: [{
    title: 'Hip Thrust', exercise_template_id: 'T1', notes: 'left side tight',
    sets: [{ type: 'normal', weight_kg: 100, reps: 8, rpe: 7.5 }, { type: 'normal', distance_meters: 40 }],
  }],
}

// The list endpoint returns EVERY source's row with the derived `canonical` flag.
const AEROBIC = [
  // 28 Sep elliptical: a zoneless Flow-export twin (non-canonical) and the zoned v4 row (canonical)
  { id: 11, source: 'polar_flow_export', session_date: '2026-09-28', start_time: '2026-09-27T22:00:00Z', sport_name: 'Elliptical',
    duration_minutes: 45, hr_avg: null, hr_max: null, calories: null, z1_seconds: null, z2_seconds: null, z3_seconds: null,
    z4_seconds: null, z5_seconds: null, canonical: false },
  { id: 12, source: 'polar_v4', session_date: '2026-09-28', start_time: '2026-09-27T22:01:00Z', sport_name: 'Elliptical',
    duration_minutes: 45, hr_avg: 128, hr_max: 151, calories: 380, z1_seconds: 60, z2_seconds: 1500, z3_seconds: 900, z4_seconds: 240,
    z5_seconds: 0, canonical: true },
  // 26 Sep pilates: 08:30 AEST on the 26th is the 25th in UTC; session_date is the local 26th. Zoneless, no HR.
  { id: 13, source: 'health_connect', session_date: '2026-09-26', start_time: '2026-09-25T22:30:00Z', sport_name: 'Pilates',
    duration_minutes: 50, hr_avg: null, hr_max: null, calories: null, z1_seconds: null, z2_seconds: null, z3_seconds: null,
    z4_seconds: null, z5_seconds: null, canonical: true },
]

function mockApi({ aerobic = AEROBIC } = {}) {
  api.get.mockImplementation((url) => {
    if (url === '/integrations/hevy/workout-count') return Promise.resolve({ data: { workout_count: 3 } })
    if (url.startsWith('/integrations/hevy/workouts?')) return Promise.resolve({ data: { workouts: [HEVY] } })
    if (url === '/integrations/hevy/workouts/all') return Promise.resolve({ data: { workouts: [HEVY] } })
    if (url.startsWith('/integrations/polar/aerobic-sessions')) return Promise.resolve({ data: aerobic })
    if (url.startsWith('/health/session-analysis/')) return Promise.resolve({ data: null })
    if (url === '/health/latest-session-analysis') return Promise.resolve({ data: null })
    return Promise.resolve({ data: {} })
  })
  api.post.mockResolvedValue({ data: {} })
}

async function renderPanel(onFeedback = vi.fn()) {
  await act(async () => { render(<WorkoutPanel onFeedback={onFeedback} />) })
  await waitFor(() => expect(screen.getByText('Lower')).toBeTruthy())
  return onFeedback
}

async function openAerobicHistory() {
  const seeAll = screen.getAllByText('See all →')[1]
  await act(async () => { fireEvent.click(seeAll) })
  await waitFor(() => expect(screen.getByText('Aerobic sessions')).toBeTruthy())
}

beforeEach(() => { api.get.mockReset(); api.post.mockReset(); mockApi() })
afterEach(cleanup)

// ── A5 — the list ───────────────────────────────────────────────────────────

describe('A5 the session list', () => {
  test('a 07:00 AEST Hevy session shows its AEST date, not the UTC date', async () => {
    await renderPanel()
    expect(screen.getByText('2026-09-29')).toBeTruthy()
    expect(screen.queryByText('2026-09-28', { selector: 'span' })).toBeNull()   // the card's date span
  })

  test('the latest aerobic card is the newest CANONICAL row even when the newest row is a twin', async () => {
    mockApi({ aerobic: AEROBIC })   // newest-first by date: id 11 (non-canonical) precedes id 12
    await renderPanel()
    // Card for the canonical v4 row carries HR; the zoneless twin (no HR) would render no HR line.
    expect(screen.getByText(/Avg 128 bpm/)).toBeTruthy()
  })

  test('the history is titled for every source and lists one row per bout, dated locally', async () => {
    await renderPanel()
    await openAerobicHistory()
    expect(screen.queryByText('Polar History')).toBeNull()
    expect(screen.getByText('2 sessions')).toBeTruthy()             // 3 rows, one non-canonical twin dropped
    expect(screen.getAllByText('Elliptical')).toHaveLength(1)       // one 28 Sep elliptical
    const pilates = screen.getByText('Pilates').closest('div[class*="border-l-4"]')
    expect(within(pilates).getByText('2026-09-26')).toBeTruthy()    // session_date, not the UTC 25th
  })

  test('a row with no HR says so in the detail tiles instead of bare dashes', async () => {
    await renderPanel()
    await openAerobicHistory()
    await act(async () => { fireEvent.click(screen.getByText('Pilates')) })
    expect(screen.getByText('No HR from this source')).toBeTruthy()
    expect(screen.getByText('No kcal from this source')).toBeTruthy()
    expect(screen.queryByText('Avg HR')).toBeNull()
  })

  test('a row with HR keeps its numbers', async () => {
    await renderPanel()
    await openAerobicHistory()
    await act(async () => { fireEvent.click(screen.getByText('Elliptical')) })
    expect(screen.getByText('128')).toBeTruthy()
    expect(screen.getByText('151')).toBeTruthy()
    expect(screen.getByText('380')).toBeTruthy()
    expect(screen.queryByText('No HR from this source')).toBeNull()
  })
})

// ── A3 — the triggers send a reference, not a rendering ─────────────────────

describe('A3 session feedback (detail views, scope=session)', () => {
  test('Hevy detail: short message + focus_session, and no set lines anywhere in the message', async () => {
    const onFeedback = await renderPanel()
    await act(async () => { fireEvent.click(screen.getByText('Lower')) })
    await act(async () => { fireEvent.click(screen.getByText('Session feedback')) })
    await waitFor(() => expect(onFeedback).toHaveBeenCalledTimes(1))

    const [message, focus] = onFeedback.mock.calls[0]
    expect(message).toBe('Session review: Lower, 2026-09-29')
    expect(focus).toEqual({ kind: 'hevy', id: 'hv1', scope: 'session' })
    expect(message).not.toMatch(/kg|×|est\. 1RM|Total volume|Hip Thrust/)
    // A4: session_analysis never reaches chat context, so the stored-analysis call is left as it was.
    expect(api.post).toHaveBeenCalledWith('/health/analyse-session', expect.objectContaining({ workout_id: 'hv1' }))
  })

  test('aerobic detail: short message + focus_session', async () => {
    const onFeedback = await renderPanel()
    await openAerobicHistory()
    await act(async () => { fireEvent.click(screen.getByText('Elliptical')) })
    await act(async () => { fireEvent.click(screen.getByText('Session feedback')) })

    const [message, focus] = onFeedback.mock.calls[0]
    expect(message).toBe('Session review: Elliptical, 2026-09-28')
    expect(focus).toEqual({ kind: 'aerobic', id: '12', scope: 'session' })
    expect(message).not.toMatch(/bpm|Z\d|HR Zones|Avg HR/)
  })

  test('the old label and formatters are gone', async () => {
    await renderPanel()
    await act(async () => { fireEvent.click(screen.getByText('Lower')) })
    expect(screen.queryByText('Get AI Feedback')).toBeNull()
    expect(screen.getByText('Session feedback')).toBeTruthy()
    // the volume / e1RM stats stay on the detail card only
    expect(screen.getByText('Working sets')).toBeTruthy()
    expect(screen.getByText('Volume')).toBeTruthy()
  })
})

describe('A3 review in context (the list cards, scope=context)', () => {
  test('the Strength card anchors on its (most recent) workout', async () => {
    const onFeedback = await renderPanel()
    await act(async () => { fireEvent.click(screen.getAllByText('Review in context')[0]) })

    expect(onFeedback).toHaveBeenCalledTimes(1)
    const [message, focus] = onFeedback.mock.calls[0]
    expect(message).toBe('Context review: Lower, 2026-09-29')
    expect(focus).toEqual({ kind: 'hevy', id: 'hv1', scope: 'context' })
    expect(screen.getByText('Training Data')).toBeTruthy()          // still on the list: the card did not open
  })

  test('the Aerobic card anchors on its (canonical, most recent) session', async () => {
    const onFeedback = await renderPanel()
    await act(async () => { fireEvent.click(screen.getAllByText('Review in context')[1]) })

    const [message, focus] = onFeedback.mock.calls[0]
    expect(message).toBe('Context review: Elliptical, 2026-09-28')
    expect(focus).toEqual({ kind: 'aerobic', id: '12', scope: 'context' })
  })
})
