// @vitest-environment jsdom
//
// ReadinessChart (Visuals increment 2) — the observed readiness trend as SMALL MULTIPLES.
// Every assertion is on rendered SVG (fixed-size mount, per #277). What is proven: two panels
// (self-report + HRV) each on its own axis, the fixed 1–5 domain on the ordinal panel, a NULL
// day rendered as a GAP (no dot, no zero) rather than plotted, and the empty state.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
import ReadinessChart from './ReadinessChart'
import readinessSeries from '../../fixtures/readinessSeries.json'

const FIXED = { width: 700, height: 180 }

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

async function renderChart(data = readinessSeries) {
  api.get.mockResolvedValue({ data })
  let result
  await act(async () => { result = render(<ReadinessChart {...FIXED} />) })
  await waitFor(() => expect(result.container.querySelector('.recharts-line')).toBeTruthy())
  return result
}

const yTicks = (root) =>
  [...root.querySelectorAll('.recharts-cartesian-axis-tick-value')]
    .map((t) => Number(t.textContent))
    .filter((n) => Number.isFinite(n))

test('renders two panels — self-report and HRV — as small multiples, each its own axis', async () => {
  const { container } = await renderChart()
  // One line per panel, two panels.
  expect(container.querySelectorAll('.recharts-line')).toHaveLength(2)
  expect(container.querySelectorAll('.recharts-wrapper')).toHaveLength(2) // two chart panels

  expect(screen.getByLabelText('Morning self-report')).toBeTruthy()
  expect(screen.getByLabelText('Resting HRV')).toBeTruthy()
})

test('the self-report panel is pinned to a 1–5 domain', async () => {
  await renderChart()
  const panel = screen.getByLabelText('Morning self-report')
  const ticks = yTicks(panel)
  expect(ticks.length).toBeGreaterThan(0)
  expect(Math.min(...ticks)).toBe(1)
  expect(Math.max(...ticks)).toBe(5)
})

test('a null day is a gap — no dot plotted there, and no zero', async () => {
  await renderChart()
  const panel = screen.getByLabelText('Morning self-report')
  const nonNull = readinessSeries.points.filter((p) => p.morning_readiness != null).length
  // One dot per OBSERVED day; the null day (2026-08-03) contributes none.
  expect(panel.querySelectorAll('.readiness-dot')).toHaveLength(nonNull)
  expect(nonNull).toBeLessThan(readinessSeries.points.length) // a gap genuinely exists
  // The gap is not a zero: the 1–5 domain never reaches 0.
  expect(yTicks(panel).includes(0)).toBe(false)
})

test('the HRV panel plots its own series in ms', async () => {
  await renderChart()
  const panel = screen.getByLabelText('Resting HRV')
  const nonNull = readinessSeries.points.filter((p) => p.passive_hrv_ms != null).length
  expect(panel.querySelectorAll('.hrv-dot')).toHaveLength(nonNull)
  // HRV values (~44–60 ms) put the axis well above the 1–5 readiness scale — a distinct axis.
  expect(Math.max(...yTicks(panel))).toBeGreaterThan(5)
})

test('changing the days prop refetches the series', async () => {
  api.get.mockResolvedValue({ data: readinessSeries })
  let rerender
  await act(async () => { ({ rerender } = render(<ReadinessChart {...FIXED} days={90} />)) })
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/series/readiness', { params: { days: 90 } }))

  await act(async () => { rerender(<ReadinessChart {...FIXED} days={180} />) })
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/series/readiness', { params: { days: 180 } }))
})

test('empty series renders the empty state and no chart', async () => {
  api.get.mockResolvedValue({ data: { days: 90, points: [] } })
  let container
  await act(async () => { ({ container } = render(<ReadinessChart {...FIXED} />)) })
  await waitFor(() => expect(screen.getByText(/no readiness yet/i)).toBeTruthy())
  expect(container.querySelector('.recharts-line')).toBeNull()
  expect(container.querySelector('svg')).toBeNull()
})
