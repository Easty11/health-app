// @vitest-environment jsdom
//
// The history shows each day's counted sessions with the rating and source the read door resolved, in place of the
// retired whole-day RPE. A day value that a stale record might still carry is never rendered.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn() } }))

import api from '../api'
import CheckInHistory from './CheckInHistory'

const day = (extra) => ({
  id: 1, date: '2031-06-14', am_timestamp: null, pm_timestamp: '2031-06-14T21:00:00Z', today_rating: 3,
  session_quality: 3, pm_late: false, sessions: [], ...extra,
})

beforeEach(() => { api.get.mockResolvedValue({ data: [] }) })
afterEach(() => { cleanup(); vi.clearAllMocks() })

const renderIt = () => render(<MemoryRouter><CheckInHistory /></MemoryRouter>)

test('each session shows its rating and the source that gave it', async () => {
  api.get.mockResolvedValue({ data: [day({ sessions: [
    { kind: 'hevy', id: 'h1', label: 'Upper body', rpe: 8, source: 'in_app' },
    { kind: 'aerobic', id: '7', label: 'Pilates', rpe: 3, source: 'garmin' },
  ] })] })
  renderIt()
  const list = await screen.findByLabelText('Session RPE')
  const rows = within(list).getAllByRole('listitem').map((li) => li.textContent)
  expect(rows).toEqual(['Upper body8/10in_app', 'Pilates3/10garmin'])
})

test('an unrated session says unrated, and never borrows a number', async () => {
  api.get.mockResolvedValue({ data: [day({ session_rpe: 9, sessions: [
    { kind: 'hevy', id: 'h1', label: 'Upper body', rpe: null, source: null },
  ] })] })
  renderIt()
  const list = await screen.findByLabelText('Session RPE')
  expect(within(list).getByText('unrated')).toBeTruthy()
  expect(screen.queryByText('9')).toBeNull()
})

test('a day with no sessions shows no session block, and a day without a close-out still lists its sessions', async () => {
  api.get.mockResolvedValue({ data: [
    day({ id: 2, date: '2031-06-14', pm_timestamp: null, am_timestamp: '2031-06-14T20:00:00Z', morning_readiness: 3,
      sessions: [{ kind: 'hevy', id: 'h2', label: 'Lower body', rpe: 6, source: 'in_app' }] }),
    day({ id: 1, date: '2031-06-13', sessions: [] }),
  ] })
  renderIt()
  await screen.findByText('Lower body')
  expect(screen.getAllByLabelText('Session RPE')).toHaveLength(1)
})
