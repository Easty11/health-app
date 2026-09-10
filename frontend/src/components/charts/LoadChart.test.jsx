// @vitest-environment jsdom
//
// LoadChart (Visuals increment 1, amended) — SMALL MULTIPLES, bars, per-unit axes. Every
// assertion is on rendered SVG at a fixed mount size (a ResponsiveContainer is 0×0 in jsdom).
// What is proven: one chart per populated window each with its own y-axis and unit label, load
// drawn as bars (not lines), the cold-start (maturity) muting, zero days drawing no bar, the
// empty state, and the shared range selector reissuing the request with the chosen days.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
import LoadChart from './LoadChart'
import loadSeries from '../../fixtures/loadSeries.json'

const FIXED = { width: 720, height: 200 }

// Derived from the fixture so the assertions track the data, not magic numbers.
const nBars = (w) => w.points.filter((p) => p.daily_load > 0).length
const nCold = (w) => w.points.filter((p) => p.daily_load > 0 && p.maturity === 'low').length
const nMature = (w) => w.points.filter((p) => p.daily_load > 0 && p.maturity === 'ok').length
const sum = (f) => loadSeries.windows.reduce((n, w) => n + f(w), 0)

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

async function renderChart(data = loadSeries) {
  api.get.mockResolvedValue({ data })
  let result
  await act(async () => { result = render(<LoadChart {...FIXED} />) })
  await waitFor(() => expect(result.container.querySelector('.recharts-wrapper')).toBeTruthy())
  return result
}

test('renders one chart per populated window, each with its own y-axis and unit label', async () => {
  const { container } = await renderChart()
  expect(container.querySelectorAll('.recharts-wrapper')).toHaveLength(loadSeries.windows.length)
  expect(container.querySelectorAll('.recharts-yAxis')).toHaveLength(loadSeries.windows.length)
  // each window's unit is labelled (figcaption + axis label both carry it — at least once each)
  for (const w of loadSeries.windows) {
    expect(container.textContent).toContain(w.unit)
    expect(container.textContent).toContain(w.load_window)
  }
})

test('load is drawn as bars, not lines', async () => {
  const { container } = await renderChart()
  expect(container.querySelector('.recharts-line-curve')).toBeNull()
  expect(container.querySelectorAll('.load-bar').length).toBe(sum(nBars))
})

test('zero days draw no bar', async () => {
  const { container } = await renderChart()
  // 25 bars per window from 30 days ⇒ 5 rest-day zeros drop out, across 3 windows.
  const totalDays = loadSeries.windows.reduce((n, w) => n + w.points.length, 0)
  expect(container.querySelectorAll('.load-bar').length).toBe(sum(nBars))
  expect(sum(nBars)).toBeLessThan(totalDays)
})

test('pre-maturity bars are muted, mature bars are not — the boundary is drawn not hidden', async () => {
  const { container } = await renderChart()
  expect(container.querySelectorAll('.load-bar--cold').length).toBe(sum(nCold))
  expect(container.querySelectorAll('.load-bar--mature').length).toBe(sum(nMature))
  expect(sum(nCold)).toBeGreaterThan(0)
  expect(sum(nMature)).toBeGreaterThan(0)
})

test('empty series renders the empty state and no chart', async () => {
  api.get.mockResolvedValue({ data: { days: 90, metrics_version: 'banister-v1', windows: [] } })
  let container
  await act(async () => { ({ container } = render(<LoadChart {...FIXED} />)) })
  await waitFor(() => expect(screen.getByText(/no training load yet/i)).toBeTruthy())
  expect(container.querySelector('.recharts-wrapper')).toBeNull()
  expect(container.querySelector('svg')).toBeNull()
})

test('one shared range selector reissues the request with the chosen days', async () => {
  const { container } = await renderChart()
  expect(screen.getAllByRole('group', { name: /range/i })).toHaveLength(1)  // shared, not per-chart
  expect(api.get).toHaveBeenCalledWith('/series/load', { params: { days: 90 } })

  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '180d' })) })
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/series/load', { params: { days: 180 } }))
  await waitFor(() => expect(screen.getByRole('button', { name: '180d' }).getAttribute('aria-pressed')).toBe('true'))
  expect(container.querySelectorAll('.recharts-wrapper')).toHaveLength(loadSeries.windows.length)
})
