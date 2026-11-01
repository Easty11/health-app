// @vitest-environment jsdom
//
// Effort is asked PER SESSION. The starting state is the operator's real one (FEEDBACK section 48): the 31 Oct 2026
// case, a 55-min Hevy-only workout and a 52-min Garmin Pilates, both unrated, as the real routes returned it
// (src/fixtures/srpe31Oct.json, regenerated and compared by backend/tests/test_srpe_card_fixture.py). The server is
// simulated only to apply a write and answer the next read; every starting response is the fixture's.
//
// Pinned: two asks for that day; no whole-day question or slider; ratings post on their own route BEFORE the close-out
// and the close-out never carries session_rpe; an untouched card records nothing; a device-rated session is read-only
// with an Override; a failed rating write keeps the card open; a failed read never blocks the close-out; the
// backfill is collapsed, bounded by the server, and saves without a close-out.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import fixture from '../fixtures/srpe31Oct.json'
import NightlyCloseOut from './NightlyCloseOut'

const clone = (o) => JSON.parse(JSON.stringify(o))
const ok = (data) => Promise.resolve({ data })

let server
function startServer(over = {}) {
  server = {
    today: clone(fixture.closeout.today),
    sessions: clone(fixture.closeout.sessions.sessions),
    earlier: clone(fixture.closeout.earlier.sessions),
    ratingsStatus: 200,
    getFails: false,
    ...over,
  }
  api.get.mockImplementation((url) => {
    if (url === '/checkin-v2/today') return ok(server.today)
    if (url === '/checkin-v2/srpe/sessions') return server.getFails ? Promise.reject(new Error('down')) : ok({ sessions: server.sessions })
    if (url === '/checkin-v2/srpe/earlier') return server.getFails ? Promise.reject(new Error('down')) : ok({ sessions: server.earlier })
    return ok({})
  })
  api.post.mockImplementation((url, body) => {
    if (url === '/checkin-v2/srpe/ratings') {
      if (server.ratingsStatus !== 200) {
        return Promise.reject({ response: { status: server.ratingsStatus, data: { detail: 'not a counted session' } } })
      }
      body.ratings.forEach((r) => {
        for (const s of [...server.sessions, ...server.earlier]) {
          if (s.kind === r.kind && s.id === r.id) { s.rpe = r.rpe; s.source = 'in_app' }
        }
      })
      server.earlier = server.earlier.filter((s) => s.rpe == null)
      return ok({ written: body.ratings.length, sessions: [] })
    }
    return ok({})
  })
}
beforeEach(() => startServer())
afterEach(() => { cleanup(); vi.clearAllMocks() })

const posts = (url) => api.post.mock.calls.filter(([u]) => u === url)
const ratingPosts = () => posts('/checkin-v2/srpe/ratings')
const pmPosts = () => posts('/checkin-v2/pm')
const save = () => fireEvent.click(screen.getByRole('button', { name: /Save & Close the Day/ }))
const rate = (session, n) => {
  const group = screen.getByRole('group', { name: `Rate ${session}` })
  fireEvent.click(within(group).getByRole('button', { name: String(n) }))
}

async function open() {
  const view = render(<MemoryRouter><NightlyCloseOut /></MemoryRouter>)
  await screen.findByRole('group', { name: 'Rate Upper body' }).catch(() => null)
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/checkin-v2/srpe/sessions', expect.anything()))
  return view
}

test('the 31 Oct state asks for two ratings, one per session, with each session named', async () => {
  const { container } = await open()
  const upper = await screen.findByRole('group', { name: 'Rate Upper body' })
  const pilates = screen.getByRole('group', { name: 'Rate Pilates' })
  expect(upper).toBeTruthy()
  expect(pilates).toBeTruthy()
  expect(screen.getByText('55 min · 12:00')).toBeTruthy()
  expect(screen.getByText('52 min · 18:00')).toBeTruthy()
  expect(within(upper).getAllByRole('button')).toHaveLength(11)          // 0..10
  // the whole-day question is gone: no slider, no day copy
  expect(container.querySelector('input[type=range]')).toBeNull()
  expect(screen.queryByText(/Session RPE/)).toBeNull()
  expect(screen.queryByText(/Rate the sessions your apps didn't/)).toBeNull()
})

test('rating both and saving posts the ratings first, one per session, and the close-out carries no session_rpe', async () => {
  await open()
  await screen.findByRole('group', { name: 'Rate Upper body' })
  rate('Upper body', 8)
  rate('Pilates', 3)
  save()
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(ratingPosts()).toHaveLength(1)
  expect(ratingPosts()[0][1]).toEqual({ ratings: [
    { kind: 'hevy', id: 'hevy-0031', rpe: 8 },
    { kind: 'aerobic', id: '1', rpe: 3 },
  ] })
  expect(pmPosts()[0][1]).not.toHaveProperty('session_rpe')
  const [rateOrder] = api.post.mock.invocationCallOrder.filter((_, i) => api.post.mock.calls[i][0] === '/checkin-v2/srpe/ratings')
  const [pmOrder] = api.post.mock.invocationCallOrder.filter((_, i) => api.post.mock.calls[i][0] === '/checkin-v2/pm')
  expect(rateOrder).toBeLessThan(pmOrder)
  await screen.findByText('Close-out saved')
  expect(screen.getByText('Sessions rated').nextSibling.textContent).toBe('2/2')
})

test('an untouched card records no rating at all and still closes the day', async () => {
  await open()
  await screen.findByRole('group', { name: 'Rate Upper body' })
  save()
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(ratingPosts()).toHaveLength(0)                                   // no default is ever sent
})

test('only the sessions that were tapped are sent', async () => {
  await open()
  await screen.findByRole('group', { name: 'Rate Upper body' })
  rate('Pilates', 6)
  save()
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(ratingPosts()[0][1]).toEqual({ ratings: [{ kind: 'aerobic', id: '1', rpe: 6 }] })
})

test('a device-rated session shows its rating read-only with an Override, and an override posts one new rating', async () => {
  startServer({ sessions: clone(fixture.closeout.sessions.sessions).map((s) => (s.label === 'Pilates' ? { ...s, rpe: 4, source: 'garmin' } : s)) })
  await open()
  await screen.findByRole('group', { name: 'Rate Upper body' })
  expect(screen.queryByRole('group', { name: 'Rate Pilates' })).toBeNull()      // read-only: no ask
  expect(screen.getByText('garmin', { exact: false })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Override' }))
  rate('Pilates', 6)
  save()
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(ratingPosts()[0][1]).toEqual({ ratings: [{ kind: 'aerobic', id: '1', rpe: 6 }] })
})

test('after an override is saved and re-read, the row shows the new in_app rating read-only again', async () => {
  startServer({ sessions: clone(fixture.closeout.sessions.sessions).map((s) => (s.label === 'Pilates' ? { ...s, rpe: 4, source: 'garmin' } : s)) })
  await open()
  await screen.findByRole('group', { name: 'Rate Upper body' })
  fireEvent.click(screen.getByRole('button', { name: 'Override' }))
  rate('Pilates', 6)
  save()
  await screen.findByText('Close-out saved')
  expect(server.sessions.find((s) => s.label === 'Pilates')).toMatchObject({ rpe: 6, source: 'in_app' })
})

test('a rating write that fails keeps the card open, shows why, keeps the picks, and does not close the day', async () => {
  startServer({ ratingsStatus: 422 })
  await open()
  await screen.findByRole('group', { name: 'Rate Upper body' })
  rate('Upper body', 8)
  save()
  await screen.findByText('not a counted session')
  expect(pmPosts()).toHaveLength(0)
  expect(screen.queryByText('Close-out saved')).toBeNull()
  const group = screen.getByRole('group', { name: 'Rate Upper body' })
  expect(within(group).getByRole('button', { name: '8' }).getAttribute('aria-pressed')).toBe('true')
})

test('a failed read of the sessions never blocks the close-out', async () => {
  startServer({ getFails: true })
  render(<MemoryRouter><NightlyCloseOut /></MemoryRouter>)
  await screen.findByText(/Couldn't load your sessions/)
  save()
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(ratingPosts()).toHaveLength(0)
})

test('a day with no counted session says there is nothing to rate', async () => {
  startServer({ sessions: [] })
  render(<MemoryRouter><NightlyCloseOut /></MemoryRouter>)
  await screen.findByText(/nothing to rate/)
  expect(screen.queryByRole('group')).toBeNull()
})

test('trained-today still gates session quality only; the sessions to rate are shown either way', async () => {
  await open()
  await screen.findByRole('group', { name: 'Rate Upper body' })
  expect(screen.queryByText('Session quality (planned vs actual)')).toBeNull()        // toggle off
  fireEvent.click(screen.getByText('Trained today?').parentElement.querySelector('button'))
  expect(screen.getByText('Session quality (planned vs actual)')).toBeTruthy()
  expect(screen.getByRole('group', { name: 'Rate Upper body' })).toBeTruthy()
})

// -- the backfill (R4) -------------------------------------------------------------------------------------

test('earlier unrated sessions are offered in a collapsed section with their count, bounded by the server', async () => {
  await open()
  await screen.findByRole('group', { name: 'Rate Upper body' })
  const toggle = await screen.findByRole('button', { name: /Earlier sessions unrated \(3\)/ })
  expect(toggle.getAttribute('aria-expanded')).toBe('false')
  expect(screen.queryByRole('group', { name: /Rate Pull/ })).toBeNull()               // collapsed: nothing asked
  expect(api.get).toHaveBeenCalledWith('/checkin-v2/srpe/earlier', { params: {} })     // the server picks the day and the bound
  fireEvent.click(toggle)
  expect(toggle.getAttribute('aria-expanded')).toBe('true')
  expect(screen.getByRole('group', { name: 'Rate Pull 2026-10-25' })).toBeTruthy()
  expect(screen.getByRole('group', { name: 'Rate Lower body 2026-10-30' })).toBeTruthy()
})

test('the backfill saves on its own button, posts only what was tapped, and never closes the day', async () => {
  await open()
  fireEvent.click(await screen.findByRole('button', { name: /Earlier sessions unrated/ }))
  expect(screen.getByRole('button', { name: 'Save earlier ratings (0)' }).disabled).toBe(true)
  rate('Pull 2026-10-25', 7)
  rate('Pilates 2026-10-27', 3)
  fireEvent.click(screen.getByRole('button', { name: 'Save earlier ratings (2)' }))
  await waitFor(() => expect(ratingPosts()).toHaveLength(1))
  expect(ratingPosts()[0][1]).toEqual({ ratings: [
    { kind: 'hevy', id: 'hevy-0025', rpe: 7 },
    { kind: 'aerobic', id: '3', rpe: 3 },
  ] })
  expect(pmPosts()).toHaveLength(0)                                                  // no close-out was forced
  // re-read: the two rated sessions have left the offer, the third remains
  await screen.findByRole('button', { name: /Earlier sessions unrated \(1\)/ })
})

test('the backfill and today are separate: tapping today never sends the earlier picks, and vice versa', async () => {
  await open()
  await screen.findByRole('group', { name: 'Rate Upper body' })
  fireEvent.click(await screen.findByRole('button', { name: /Earlier sessions unrated/ }))
  rate('Pull 2026-10-25', 7)
  rate('Upper body', 8)
  save()
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(ratingPosts()[0][1]).toEqual({ ratings: [{ kind: 'hevy', id: 'hevy-0031', rpe: 8 }] })      // not the Pull
})

test('with nothing earlier to rate the backfill section is absent', async () => {
  startServer({ earlier: [] })
  await open()
  await screen.findByRole('group', { name: 'Rate Upper body' })
  expect(screen.queryByRole('button', { name: /Earlier sessions unrated/ })).toBeNull()
})
