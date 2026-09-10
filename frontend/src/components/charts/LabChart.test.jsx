// @vitest-environment jsdom
//
// LabChart (Lab visuals) — one marker's trend against its per-draw reference range. Every
// assertion is on rendered SVG at a fixed mount size (a ResponsiveContainer is 0×0 in jsdom).
// Proven: the stepped band has draws−1 segments, the censored value is a hollow marker and a
// GAP (not a line vertex), derived and low-confidence points are marked, and the excluded
// results are summarised beneath.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
import LabChart from './LabChart'
import labSeries from '../../fixtures/labSeries.json'

const FIXED = { width: 720, height: 220 }

function mockApi(series = labSeries) {
  api.get.mockImplementation((url) => {
    if (url.startsWith('/series/lab/')) return Promise.resolve({ data: series })
    return Promise.resolve({ data: {} })
  })
}

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

async function renderChart(props = {}) {
  let result
  await act(async () => { result = render(<LabChart canonical="testosterone_total" {...FIXED} {...props} />) })
  await waitFor(() => expect(result.container.querySelector('.recharts-wrapper')).toBeTruthy())
  return result
}

test('the reference band has one segment per gap between draws (draws − 1)', async () => {
  mockApi()
  const { container } = await renderChart()
  const draws = labSeries.points.length
  expect(container.querySelectorAll('.recharts-reference-area')).toHaveLength(draws - 1)
})

test('a censored value is a hollow marker at the bound and a gap in the line', async () => {
  mockApi()
  const { container } = await renderChart()
  const censored = labSeries.points.filter((p) => p.operator)
  expect(censored).toHaveLength(1)  // fixture sanity
  // Hollow marker: one reference dot at the censored bound.
  expect(container.querySelectorAll('.recharts-reference-dot')).toHaveLength(1)
  // Gap: a measured dot for every NON-censored point, and none for the censored one.
  expect(container.querySelectorAll('.lab-dot')).toHaveLength(labSeries.points.length - censored.length)
})

test('derived and low-confidence points are marked distinctly', async () => {
  mockApi()
  const { container } = await renderChart()
  expect(container.querySelectorAll('.lab-dot--derived')).toHaveLength(
    labSeries.points.filter((p) => p.is_derived).length,
  )
  expect(container.querySelectorAll('.lab-dot--muted')).toHaveLength(
    labSeries.points.filter((p) => !p.operator && !p.is_derived && p.confidence < 0.85).length,
  )
})

test('excluded results are summarised beneath, by reason, with the bind hint for unmapped', async () => {
  mockApi()
  const { container } = await renderChart()
  expect(screen.getByText(/3 results not plotted/i)).toBeTruthy()
  expect(container.textContent).toMatch(/non-numeric/i)     // qualitative
  expect(container.textContent).toMatch(/unit mismatch/i)   // unit_mismatch
  expect(container.textContent).toMatch(/not yet mapped/i)  // unmapped
  expect(container.textContent).toMatch(/bind them/i)       // unmapped → bind control below
})

test('no excluded section when nothing is excluded', async () => {
  mockApi({ ...labSeries, excluded: [] })
  const { container } = await renderChart()
  expect(container.textContent).not.toMatch(/not plotted/i)
})

test('empty series renders an empty state and no chart', async () => {
  mockApi({ canonical: 'x', unit: null, points: [], excluded: [] })
  let container
  await act(async () => { ({ container } = render(<LabChart canonical="x" {...FIXED} />)) })
  await waitFor(() => expect(screen.getByText(/no plottable results/i)).toBeTruthy())
  expect(container.querySelector('.recharts-wrapper')).toBeNull()
})
