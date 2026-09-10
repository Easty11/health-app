// @vitest-environment jsdom
//
// LoadChart (Visuals increment 1) — the first chart in the app. Every assertion is on RENDERED
// SVG, never on "it mounted": the chart is mounted at a fixed width/height so Recharts draws
// real geometry in jsdom (a ResponsiveContainer would be 0×0 here and render no series — the
// whole reason TimeSeriesChart defaults to fixed size). What is proven: one line per window,
// one dot per data point, the maturity (cold-start) styling boundary, the empty state, and
// that the range selector reissues the request with the chosen `days`.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
import LoadChart from './LoadChart'
import loadSeries from '../../fixtures/loadSeries.json'

const FIXED = { width: 800, height: 320 }

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

async function renderChart(data = loadSeries) {
  api.get.mockResolvedValue({ data })
  let result
  await act(async () => { result = render(<LoadChart {...FIXED} />) })
  await waitFor(() => expect(result.container.querySelector('.recharts-line')).toBeTruthy())
  return result
}

test('draws one line per window', async () => {
  const { container } = await renderChart()
  expect(container.querySelectorAll('.recharts-line')).toHaveLength(loadSeries.windows.length)
})

test('legend carries one entry per window', async () => {
  const { container } = await renderChart()
  expect(container.querySelectorAll('.recharts-legend-item')).toHaveLength(loadSeries.windows.length)
})

test('draws one dot per data point, in one dot-group per window', async () => {
  const { container } = await renderChart()
  const groups = container.querySelectorAll('.recharts-line-dots')
  expect(groups).toHaveLength(loadSeries.windows.length)

  const pointsPerWindow = loadSeries.windows[0].points.length
  for (const g of groups) {
    expect(g.querySelectorAll('.load-dot')).toHaveLength(pointsPerWindow)
  }
  const total = loadSeries.windows.reduce((n, w) => n + w.points.length, 0)
  expect(container.querySelectorAll('.load-dot')).toHaveLength(total)
})

test('pre-maturity points are styled cold, mature points are not — the boundary is drawn not hidden', async () => {
  const { container } = await renderChart()
  const expectCold = loadSeries.windows.reduce(
    (n, w) => n + w.points.filter((p) => p.maturity === 'low').length, 0,
  )
  const expectMature = loadSeries.windows.reduce(
    (n, w) => n + w.points.filter((p) => p.maturity === 'ok').length, 0,
  )
  expect(container.querySelectorAll('.load-dot--cold')).toHaveLength(expectCold)
  expect(container.querySelectorAll('.load-dot--mature')).toHaveLength(expectMature)
  // Both states are present — the boundary exists, neither side is suppressed.
  expect(expectCold).toBeGreaterThan(0)
  expect(expectMature).toBeGreaterThan(0)
})

test('empty series renders the empty state and no chart', async () => {
  api.get.mockResolvedValue({ data: { days: 90, metrics_version: 'banister-v1', windows: [] } })
  let container
  await act(async () => { ({ container } = render(<LoadChart {...FIXED} />)) })
  await waitFor(() => expect(screen.getByText(/no training load yet/i)).toBeTruthy())
  expect(container.querySelector('.recharts-line')).toBeNull()
  expect(container.querySelector('svg')).toBeNull()
})

test('range selector reissues the request with the chosen days', async () => {
  const { container } = await renderChart()
  // initial load is the default 90-day window
  expect(api.get).toHaveBeenCalledWith('/series/load', { params: { days: 90 } })

  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '180d' })) })
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/series/load', { params: { days: 180 } }))

  // and the 180d control reads as selected
  await waitFor(() => expect(screen.getByRole('button', { name: '180d' }).getAttribute('aria-pressed')).toBe('true'))
  expect(container.querySelectorAll('.recharts-line')).toHaveLength(loadSeries.windows.length)
})
