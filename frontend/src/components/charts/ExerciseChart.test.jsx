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
import exerciseList from '../../fixtures/exerciseList.json'
import exerciseSeries from '../../fixtures/exerciseSeries.json'

const FIXED = { width: 720, height: 180 }
const MARKERS = [{ date: '2026-09-07', label: 'decompression' }]

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

test('phase markers reach the charts (a reference line is drawn)', async () => {
  mockApi()
  const { container } = await renderChart()
  expect(container.querySelectorAll('.recharts-reference-line').length).toBeGreaterThan(0)
  expect(container.textContent).toContain('decompression')
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
