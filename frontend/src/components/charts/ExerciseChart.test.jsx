// @vitest-environment jsdom
//
// ExerciseChart (Visuals increment 3) — per-exercise e1RM + volume, two small multiples on
// distinct units, with the training-phase overlay. Every assertion is on rendered SVG at a fixed
// mount size (a ResponsiveContainer is 0×0 in jsdom). What is proven: two panels on different
// units (kg vs kg·reps), a GAP where e1RM is null, the selector (most-frequent first, default
// selected), and that phase markers reach the chart.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
import ExerciseChart from './ExerciseChart'
import { phaseSegments } from './PhaseMarkers'
import exerciseList from '../../fixtures/exerciseList.json'
import exerciseSeries from '../../fixtures/exerciseSeries.json'

const FIXED = { width: 720, height: 180 }
const MARKERS = phaseSegments([
  { id: 1, label: 'decompression', entered_on: '2026-09-07', closed_on: null },
])

// Route the mock by URL: the selector list, then the chosen template's series.
function mockApi(list = exerciseList, series = exerciseSeries) {
  api.get.mockImplementation((url) => {
    if (url === '/series/exercises') return Promise.resolve({ data: list })
    if (url.startsWith('/series/exercise/')) return Promise.resolve({ data: series })
    return Promise.resolve({ data: {} })
  })
}

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

async function renderChart(props = {}) {
  let result
  await act(async () => { result = render(<ExerciseChart {...FIXED} markers={MARKERS} {...props} />) })
  await waitFor(() => expect(result.container.querySelector('.recharts-wrapper')).toBeTruthy())
  return result
}

test('renders two panels on distinct units — e1RM in kg, volume in kg·reps', async () => {
  mockApi()
  const { container } = await renderChart()
  expect(container.querySelectorAll('.recharts-wrapper')).toHaveLength(2)
  // e1RM is a line, volume is bars — one of each, never an overlay.
  expect(container.querySelector('.recharts-line-curve')).toBeTruthy()
  expect(container.querySelectorAll('.load-bar').length).toBeGreaterThan(0)
  expect(container.textContent).toContain('(kg)')
  expect(container.textContent).toContain('kg·reps')
})

test('the e1RM line has a gap where the session value is null', async () => {
  mockApi()
  const { container } = await renderChart()
  // One dot per non-null e1RM point; the single null point draws none (the gap).
  const nonNull = exerciseSeries.points.filter((p) => p.e1rm_kg != null).length
  expect(exerciseSeries.points.some((p) => p.e1rm_kg == null)).toBe(true)  // fixture has a gap
  expect(container.querySelectorAll('.e1rm-dot').length).toBe(nonNull)
})

test('phase bands reach both panels, and the name is in the one legend, not the charts', async () => {
  mockApi()
  const { container } = await renderChart()
  expect(container.querySelectorAll('.recharts-reference-area')).toHaveLength(2)   // a band per panel
  expect(container.querySelectorAll('.phase-legend')).toHaveLength(1)
  expect(container.querySelector('.phase-legend').textContent).toContain('decompression')
  for (const svg of container.querySelectorAll('svg')) expect(svg.textContent).not.toContain('decompression')
})

test('the x-axis is time-scaled: the gap between sessions is drawn as the gap in days', async () => {
  // Fixture sessions 27 Jul, 1 Aug, 10 Aug: gaps of 5 and 9 days. A category axis would space
  // them evenly; the time axis puts the dots 5:9 apart.
  mockApi()
  const { container } = await renderChart()
  const dates = exerciseSeries.points.map((p) => p.date)
  const i = dates.indexOf('2026-07-27')
  expect(dates.slice(i, i + 3)).toEqual(['2026-07-27', '2026-08-01', '2026-08-10'])
  const cx = [...container.querySelectorAll('.e1rm-dot')].map((d) => parseFloat(d.getAttribute('cx')))
  const withE1rm = exerciseSeries.points.filter((p) => p.e1rm_kg != null).map((p) => p.date)
  const at = (d) => cx[withE1rm.indexOf(d)]
  expect((at('2026-08-01') - at('2026-07-27')) / (at('2026-08-10') - at('2026-08-01'))).toBeCloseTo(5 / 9, 2)
})

test('a phase that starts after the last session is legend-only, marked no data yet', async () => {
  mockApi()
  const { container } = await renderChart({
    markers: phaseSegments([{ id: 2, label: 'aerobic base', entered_on: '2027-01-01', closed_on: null }]),
  })
  expect(container.querySelector('.recharts-reference-area')).toBeNull()
  expect(container.querySelector('.phase-legend').textContent).toMatch(/aerobic base.*no data yet/)
})

test('the selector lists exercises most-frequent first and defaults to the most frequent', async () => {
  mockApi()
  await renderChart()
  const buttons = screen.getAllByRole('button')
  expect(buttons.map((b) => b.textContent)).toEqual(['Back Squat', 'Bench Press', 'Deadlift'])
  expect(buttons[0].getAttribute('aria-pressed')).toBe('true')  // most frequent selected
})

test('picking another exercise re-fetches its series', async () => {
  mockApi()
  await renderChart()
  expect(api.get).toHaveBeenCalledWith('/series/exercise/SQ', { params: { days: 90 } })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Bench Press' })) })
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/series/exercise/BP', { params: { days: 90 } }))
})

test('empty selector renders the empty state and no chart', async () => {
  mockApi([], exerciseSeries)
  let container
  await act(async () => { ({ container } = render(<ExerciseChart {...FIXED} />)) })
  await waitFor(() => expect(screen.getByText(/three logged sessions/i)).toBeTruthy())
  expect(container.querySelector('.recharts-wrapper')).toBeNull()
})
