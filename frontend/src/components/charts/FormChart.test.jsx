// @vitest-environment jsdom
//
// FormChart (Visuals increment 2 / 1b) — the Banister curves. Every assertion is on RENDERED
// SVG (mounted fixed-size so Recharts draws real geometry in jsdom, per #277). What is proven:
// three lines (fitness / fatigue / form) for one window, the negative-capable y-domain (form
// dips below zero and the axis shows it, not a floor clamped at 0), the window selector, the
// cold-start (maturity) dot boundary, and the empty state.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
import FormChart from './FormChart'
import formSeries from '../../fixtures/formSeries.json'

const FIXED = { width: 800, height: 320 }

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

async function renderChart(data = formSeries) {
  api.get.mockResolvedValue({ data })
  let result
  await act(async () => { result = render(<FormChart {...FIXED} />) })
  await waitFor(() => expect(result.container.querySelector('.recharts-line')).toBeTruthy())
  return result
}

test('draws three lines — fitness, fatigue, form', async () => {
  const { container } = await renderChart()
  expect(container.querySelectorAll('.recharts-line')).toHaveLength(3)
})

test('legend names the three curves', async () => {
  await renderChart()
  for (const name of ['Fitness', 'Fatigue', 'Form']) {
    expect(screen.getByText(name)).toBeTruthy()
  }
})

test('the y-axis admits negative values — form below zero is shown, not clamped at 0', async () => {
  const { container } = await renderChart()
  // The default window (mechanical) has form values down to -8, so the fitted axis must extend
  // below zero. Proven by a negative y-axis tick label — a floor clamped at 0 could not produce
  // one.
  // The numeric axis tick labels are the y-axis's; the x-axis labels are dates (NaN under
  // Number()), so filtering to finite numbers isolates the y ticks.
  const ticks = [...container.querySelectorAll('.recharts-cartesian-axis-tick-value')]
    .map((t) => Number(t.textContent))
    .filter((n) => Number.isFinite(n))
  expect(ticks.length).toBeGreaterThan(0)
  expect(Math.min(...ticks)).toBeLessThan(0)
})

test('the window selector switches the window and reissues nothing (one fetch, in-memory switch)', async () => {
  const { container } = await renderChart()
  // First populated window is the default selection.
  expect(screen.getByRole('button', { name: 'mechanical' }).getAttribute('aria-pressed')).toBe('true')
  const callsBefore = api.get.mock.calls.length

  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'neuromuscular' })) })
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'neuromuscular' }).getAttribute('aria-pressed')).toBe('true'))

  // Switching window is a client-side reselection over data already in hand — no refetch.
  expect(api.get.mock.calls.length).toBe(callsBefore)
  expect(container.querySelectorAll('.recharts-line')).toHaveLength(3)
})

test('cold-start days are styled cold, mature days are not — the boundary is drawn not hidden', async () => {
  const { container } = await renderChart()
  const mech = formSeries.windows[0].points
  const coldDays = mech.filter((p) => p.maturity === 'low').length
  const matureDays = mech.filter((p) => p.maturity === 'ok').length
  // One dot per day per line (3 lines), so the per-day maturity count is ×3.
  expect(container.querySelectorAll('.form-dot--cold')).toHaveLength(coldDays * 3)
  expect(container.querySelectorAll('.form-dot--mature')).toHaveLength(matureDays * 3)
  expect(coldDays).toBeGreaterThan(0)
  expect(matureDays).toBeGreaterThan(0)
})

test('changing the days prop refetches the series', async () => {
  api.get.mockResolvedValue({ data: formSeries })
  let rerender
  await act(async () => { ({ rerender } = render(<FormChart {...FIXED} days={90} />)) })
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/series/load', { params: { days: 90 } }))

  await act(async () => { rerender(<FormChart {...FIXED} days={180} />) })
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/series/load', { params: { days: 180 } }))
})

test('empty series renders the empty state and no chart', async () => {
  api.get.mockResolvedValue({ data: { days: 90, metrics_version: 'banister-v1', windows: [] } })
  let container
  await act(async () => { ({ container } = render(<FormChart {...FIXED} />)) })
  await waitFor(() => expect(screen.getByText(/no banister curves yet/i)).toBeTruthy())
  expect(container.querySelector('.recharts-line')).toBeNull()
  expect(container.querySelector('svg')).toBeNull()
})
