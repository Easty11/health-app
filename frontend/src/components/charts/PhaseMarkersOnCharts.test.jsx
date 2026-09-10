// @vitest-environment jsdom
//
// The increment-3 gate that the phase-marker overlay reaches EVERY /metrics chart: LoadChart,
// FormChart, ReadinessChart and ExerciseChart each render a ReferenceLine at an in-range phase
// boundary, labelled with the phase name. One small render per chart; each marker sits inside
// that chart's own fixture range so the snap lands.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
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

async function assertMarker(ui) {
  let container
  await act(async () => { ({ container } = render(ui)) })
  await waitFor(() => expect(container.querySelector('.recharts-wrapper')).toBeTruthy())
  await waitFor(() => expect(container.querySelector('.recharts-reference-line')).toBeTruthy())
  expect(container.textContent).toContain('phase-x')
}

test('LoadChart draws the phase marker', async () => {
  api.get.mockResolvedValue({ data: loadSeries })  // days 2026-07-01..30
  await assertMarker(<LoadChart {...FIXED} markers={[{ date: '2026-07-15', label: 'phase-x' }]} />)
})

test('FormChart draws the phase marker', async () => {
  api.get.mockResolvedValue({ data: formSeries })  // days 2026-08-01..05
  await assertMarker(<FormChart {...FIXED} markers={[{ date: '2026-08-03', label: 'phase-x' }]} />)
})

test('ReadinessChart draws the phase marker', async () => {
  api.get.mockResolvedValue({ data: readinessSeries })  // days 2026-08-01..05
  await assertMarker(<ReadinessChart {...FIXED} markers={[{ date: '2026-08-03', label: 'phase-x' }]} />)
})

test('ExerciseChart draws the phase marker', async () => {
  api.get.mockImplementation((url) => {
    if (url === '/series/exercises') return Promise.resolve({ data: exerciseList })
    if (url.startsWith('/series/exercise/')) return Promise.resolve({ data: exerciseSeries })
    return Promise.resolve({ data: {} })
  })
  await assertMarker(<ExerciseChart {...FIXED} markers={[{ date: '2026-09-07', label: 'phase-x' }]} />)
})
