// @vitest-environment jsdom
//
// The AM catch-up asks for effort per session too, for the MISSED day. Starting state: the operator's real one
// (src/fixtures/srpe31Oct.json, the routes' own responses): yesterday (30 Oct) holds an unrated Hevy workout and a ride
// Garmin rated 6; earlier unrated sessions sit behind a collapsed backfill. Ratings are posted before the close-out,
// the close-out carries for_date and no session_rpe, and a device-rated session is read-only with an Override.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import fixture from '../fixtures/srpe31Oct.json'
import MissedPMCard from './MissedPMCard'

const clone = (o) => JSON.parse(JSON.stringify(o))
const ok = (data) => Promise.resolve({ data })
const MISSED = fixture.catchup.missed_pm
let server

beforeEach(() => {
  server = {
    sessions: clone(fixture.catchup.sessions.sessions),
    earlier: clone(fixture.catchup.earlier.sessions),
  }
  api.get.mockImplementation((url) => {
    if (url === '/checkin-v2/srpe/sessions') return ok({ sessions: server.sessions })
    if (url === '/checkin-v2/srpe/earlier') return ok({ sessions: server.earlier })
    return ok({})
  })
  api.post.mockImplementation((url, body) => {
    if (url === '/checkin-v2/srpe/ratings') {
      body.ratings.forEach((r) => {
        for (const s of [...server.sessions, ...server.earlier]) {
          if (s.kind === r.kind && s.id === r.id) { s.rpe = r.rpe; s.source = 'in_app' }
        }
      })
      server.earlier = server.earlier.filter((s) => s.rpe == null)
    }
    return ok({})
  })
})
afterEach(() => { cleanup(); vi.clearAllMocks() })

const posts = (url) => api.post.mock.calls.filter(([u]) => u === url)
const rate = (name, n) => fireEvent.click(within(screen.getByRole('group', { name: `Rate ${name}` })).getByRole('button', { name: String(n) }))

async function open(props = {}) {
  const view = render(<MissedPMCard missedPm={MISSED} {...props} />)
  await screen.findByRole('group', { name: 'Rate Lower body' })
  return view
}

test('it reads the missed day, not today, and asks for the unrated session while showing the device-rated one read-only', async () => {
  const { container } = await open()
  expect(api.get).toHaveBeenCalledWith('/checkin-v2/srpe/sessions', { params: { since: '2026-10-30', until: '2026-10-30' } })
  expect(api.get).toHaveBeenCalledWith('/checkin-v2/srpe/earlier', { params: { before: '2026-10-30' } })
  expect(screen.getByText('Rate yesterday\'s sessions')).toBeTruthy()
  expect(screen.queryByRole('group', { name: 'Rate Biking' })).toBeNull()                 // Garmin rated it: read-only
  expect(screen.getByText('garmin', { exact: false })).toBeTruthy()
  expect(container.querySelector('input[type=range]')).toBeNull()                          // no whole-day slider
  expect(screen.queryByLabelText('Session RPE')).toBeNull()
})

test('Save yesterday posts the rating first, then the close-out with for_date and no session_rpe', async () => {
  await open()
  rate('Lower body', 7)
  fireEvent.click(screen.getByRole('button', { name: 'Save yesterday' }))
  await waitFor(() => expect(posts('/checkin-v2/pm')).toHaveLength(1))
  expect(posts('/checkin-v2/srpe/ratings')[0][1]).toEqual({ ratings: [{ kind: 'hevy', id: 'hevy-0030', rpe: 7 }] })
  const body = posts('/checkin-v2/pm')[0][1]
  expect(body).toMatchObject({ for_date: '2026-10-30', trained_today: false })
  expect(body).not.toHaveProperty('session_rpe')
  const order = (u) => api.post.mock.invocationCallOrder[api.post.mock.calls.findIndex(([x]) => x === u)]
  expect(order('/checkin-v2/srpe/ratings')).toBeLessThan(order('/checkin-v2/pm'))
})

test('an override of the device rating posts one new rating for that session', async () => {
  await open()
  fireEvent.click(screen.getByRole('button', { name: 'Override' }))
  rate('Biking', 4)
  fireEvent.click(screen.getByRole('button', { name: 'Save yesterday' }))
  await waitFor(() => expect(posts('/checkin-v2/pm')).toHaveLength(1))
  expect(posts('/checkin-v2/srpe/ratings')[0][1]).toEqual({ ratings: [{ kind: 'aerobic', id: '2', rpe: 4 }] })
})

test('an untouched card sends no ratings', async () => {
  await open()
  fireEvent.click(screen.getByRole('button', { name: 'Save yesterday' }))
  await waitFor(() => expect(posts('/checkin-v2/pm')).toHaveLength(1))
  expect(posts('/checkin-v2/srpe/ratings')).toHaveLength(0)
})

test('the backfill is collapsed with its count and saves on its own, without a close-out', async () => {
  await open()
  const toggle = screen.getByRole('button', { name: /Earlier sessions unrated \(2\)/ })
  expect(toggle.getAttribute('aria-expanded')).toBe('false')
  fireEvent.click(toggle)
  rate('Pull 2026-10-25', 5)
  fireEvent.click(screen.getByRole('button', { name: 'Save earlier ratings (1)' }))
  await waitFor(() => expect(posts('/checkin-v2/srpe/ratings')).toHaveLength(1))
  expect(posts('/checkin-v2/srpe/ratings')[0][1]).toEqual({ ratings: [{ kind: 'hevy', id: 'hevy-0025', rpe: 5 }] })
  expect(posts('/checkin-v2/pm')).toHaveLength(0)
  await screen.findByRole('button', { name: /Earlier sessions unrated \(1\)/ })
})

test('a card that is not showing loads nothing', () => {
  render(<MissedPMCard missedPm={MISSED} outcome="skipped" />)
  render(<MissedPMCard missedPm={null} />)
  expect(api.get).not.toHaveBeenCalled()
})
