// @vitest-environment jsdom
//
// The history marks a PM that was submitted after its own day. `pm_late` is derived server-side
// (never stored); the surface only reads it, and only on the PM half.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn() } }))

import api from '../api'
import CheckInHistory from './CheckInHistory'

const rec = (id, date, extra) => ({
  id, date, am_timestamp: null, pm_timestamp: '2031-06-14T21:00:00Z', today_rating: 3,
  pm_late: false, ...extra,
})

beforeEach(() => { api.get.mockResolvedValue({ data: [] }) })
afterEach(() => { cleanup(); vi.clearAllMocks() })

const renderIt = () => render(<MemoryRouter><CheckInHistory /></MemoryRouter>)

test('a late PM shows the marker on the Evening half', async () => {
  api.get.mockResolvedValue({ data: [rec(1, '2031-06-14', { pm_late: true })] })
  renderIt()
  const marker = await screen.findByText('late')
  expect(marker.parentElement.textContent).toMatch(/Evening/)
})

test('an on-time PM shows no marker', async () => {
  api.get.mockResolvedValue({ data: [rec(1, '2031-06-14', { pm_late: false })] })
  renderIt()
  await screen.findByText('Evening', { exact: false })
  expect(screen.queryByText('late')).toBeNull()
})

test('a record with no PM shows no marker even if pm_late were set', async () => {
  api.get.mockResolvedValue({ data: [rec(1, '2031-06-14', { pm_timestamp: null, pm_late: true,
    am_timestamp: '2031-06-14T20:00:00Z', morning_readiness: 3 })] })
  renderIt()
  await screen.findByText('Morning')
  expect(screen.queryByText('late')).toBeNull()
})

test('only the late day is marked in a mixed list', async () => {
  api.get.mockResolvedValue({ data: [
    rec(2, '2031-06-14', { pm_late: true }),
    rec(1, '2031-06-13', { pm_late: false }),
  ] })
  renderIt()
  await screen.findAllByText('Evening', { exact: false })
  expect(screen.getAllByText('late')).toHaveLength(1)
})
