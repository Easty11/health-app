// @vitest-environment jsdom
//
// The gate that the phase bands (R11) reach EVERY /metrics chart: LoadChart, FormChart,
// ReadinessChart and ExerciseChart each shade a band for an in-window phase and carry ONE legend
// naming it. A phase that starts after the chart's last data day has no band but is in the legend,
// marked "no data yet". The name is never drawn inside a chart. One small render per chart; each
// phase sits inside that chart's own fixture range, and the later one after it.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
import { phaseSegments } from './PhaseMarkers'
import LoadChart from './LoadChart'
import FormChart from './FormChart'
import ReadinessChart from './ReadinessChart'
import ExerciseChart from './ExerciseChart'
import loadSeries from '../../fixtures/loadSeries.json'
import formSeries from '../../fixtures/formSeries.json'
import readinessSeries from '../../fixtures/readinessSeries.json'
import exerciseList from '../../fixtures/exerciseList.json'
import exerciseSeries from '../../fixtures/exerciseSeries.json'

const FIXED = { width: 720, height: 180 }

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

// A ledger as the chart sees it: `phase-x` from `from` onward, then `phase-later` from a date after
// every fixture's last day.
const ledger = (from) => phaseSegments([
  { id: 0, label: 'phase-x', entered_on: from, closed_on: '2026-12-01' },
  { id: 1, label: 'phase-later', entered_on: '2026-12-01', closed_on: null },
])

async function assertBands(ui, bandCount) {
  let container
  await act(async () => { ({ container } = render(ui)) })
  await waitFor(() => expect(container.querySelector('.recharts-wrapper')).toBeTruthy())
  await waitFor(() => expect(container.querySelector('.recharts-reference-area')).toBeTruthy())
  // The in-window phase is a band per chart; the later one is not drawn.
  expect(container.querySelectorAll('.recharts-reference-area').length).toBe(bandCount)
  // One legend per card, naming both phases; the later one is marked.
  const legends = container.querySelectorAll('.phase-legend')
  expect(legends).toHaveLength(1)
  expect(legends[0].textContent).toContain('phase-x')
  const later = [...legends[0].querySelectorAll('li')].find((li) => li.textContent.includes('phase-later'))
  expect(later.textContent).toContain('no data yet')
  // No in-chart text label.
  for (const svg of container.querySelectorAll('svg')) expect(svg.textContent).not.toContain('phase-')
}

test('LoadChart shades the phase band and carries one legend', async () => {
  api.get.mockResolvedValue({ data: loadSeries })  // days 2026-07-01..30
  await assertBands(<LoadChart {...FIXED} markers={ledger('2026-07-15')} />, 3)  // three windows, one legend
})

test('FormChart shades the phase band and carries one legend', async () => {
  api.get.mockResolvedValue({ data: formSeries })  // days 2026-08-01..05
  await assertBands(<FormChart {...FIXED} markers={ledger('2026-08-03')} />, 1)
})

test('ReadinessChart shades the phase band and carries one legend', async () => {
  api.get.mockResolvedValue({ data: readinessSeries })  // days 2026-08-01..05
  await assertBands(<ReadinessChart {...FIXED} markers={ledger('2026-08-03')} />, 2)  // two panels, one legend
})

test('ExerciseChart shades the phase band and carries one legend', async () => {
  api.get.mockImplementation((url) => {
    if (url === '/series/exercises') return Promise.resolve({ data: exerciseList })
    if (url.startsWith('/series/exercise/')) return Promise.resolve({ data: exerciseSeries })
    return Promise.resolve({ data: {} })
  })
  await assertBands(<ExerciseChart {...FIXED} markers={ledger('2026-09-07')} />, 2)  // two panels, one legend
})
