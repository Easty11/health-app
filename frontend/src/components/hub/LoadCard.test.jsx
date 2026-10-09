// @vitest-environment jsdom
//
// The home load card. Gates (operator brief 2026-10-09):
//   * the card renders AMBER when the Health Connect delivery is 14 h old, and not at 3 h;
//   * a load number never shows without its age (if freshness cannot be read, the card says so);
//   * no acute:chronic ratio, no sweet-spot verdict, no form band label appears anywhere.
// Synthetic numbers only.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
import LoadCard from './LoadCard'
import { fatigueDirection } from '../../lib/fatigueDirection'

const day = (n) => {
  const d = new Date(Date.UTC(2026, 9, 10))
  d.setUTCDate(d.getUTCDate() - n)
  return d.toISOString().slice(0, 10)
}

// 43 ascending days. Fatigue rises by 1 per day, so the 7-day look-back always differs.
function series({ fatigueStep = 1, maturity = 'ok' } = {}) {
  const points = Array.from({ length: 43 }, (_, i) => ({
    day: day(42 - i), daily_load: 10, fitness: 50 + i * 0.5, fatigue: 40 + i * fatigueStep,
    form: 10 - i * 0.25, acute_load: 12.34, chronic_load: 8.06, load_ratio: 1.53, maturity,
  }))
  return { days: 42, metrics_version: 'banister-v2',
           windows: [{ load_window: 'metabolic', unit: 'au', formula_version: 'metab-v1', points }] }
}

const freshness = ({ hcHours = 3, hcStatus } = {}) => ({
  pipes: {
    health_connect: { status: hcStatus ?? (hcHours > 13 ? 'amber' : 'fresh'), age_hours: hcHours, newest_at: 'x' },
    polar: { status: 'info', age_hours: 52, newest_at: 'x' },
    garmin_hrv: { status: 'fresh', age_hours: 5, newest_at: 'x' },
  },
  data_as_of: { age_hours: hcHours, newest_at: 'x' },
  load_inputs_stale: hcHours > 13,
  load_stale_pipes: hcHours > 13 ? ['health_connect'] : [],
})

function mockApi({ s = series(), f = freshness(), sFail = false, fFail = false } = {}) {
  api.get.mockImplementation((url) => {
    if (url === '/series/load') return sFail ? Promise.reject(new Error('x')) : Promise.resolve({ data: s })
    if (url === '/freshness') return fFail ? Promise.reject(new Error('x')) : Promise.resolve({ data: f })
    return Promise.resolve({ data: {} })
  })
}

async function renderCard() {
  await act(async () => { render(<MemoryRouter><LoadCard /></MemoryRouter>) })
  await waitFor(() => expect(screen.getByTestId('freshness-line')).toBeTruthy())
}

beforeEach(() => api.get.mockReset())
afterEach(cleanup)

describe('what the card shows', () => {
  test('form as a number with the direction fatigue is moving, the 42-day sparkline and both means', async () => {
    mockApi()
    await renderCard()
    expect(screen.getByTestId('form-value').textContent).toBe('-0.5')       // 10 - 42 * 0.25
    expect(screen.getByTestId('fatigue-direction').textContent).toContain('fatigue rising')
    expect(screen.getByRole('img', { name: /fitness and fatigue over the last 42 days/i })).toBeTruthy()
    expect(document.querySelector('polyline[data-series="fitness"]')).toBeTruthy()
    expect(document.querySelector('polyline[data-series="fatigue"]')).toBeTruthy()
    expect(screen.getByText('7-day mean')).toBeTruthy()
    expect(screen.getByText('28-day mean')).toBeTruthy()
    expect(screen.getByText(/12\.3 au/)).toBeTruthy()
    expect(screen.getByText(/8\.1 au/)).toBeTruthy()
  })

  test('reads the metabolic lane over 42 days', async () => {
    mockApi()
    await renderCard()
    expect(api.get).toHaveBeenCalledWith('/series/load', { params: { days: 42, windows: 'metabolic' } })
    expect(api.get).toHaveBeenCalledWith('/freshness')
  })

  test('links to the Metrics page', async () => {
    mockApi()
    await renderCard()
    expect(screen.getByRole('link', { name: /metrics/i }).getAttribute('href')).toBe('/metrics')
  })

  test('an early-estimate day is annotated, not hidden', async () => {
    mockApi({ s: series({ maturity: 'low' }) })
    await renderCard()
    expect(screen.getByText(/early estimate/i)).toBeTruthy()
    expect(screen.getByTestId('form-value')).toBeTruthy()
  })

  test('no load computed yet still shows the age of the data', async () => {
    mockApi({ s: { days: 42, metrics_version: 'banister-v2', windows: [] } })
    await renderCard()
    expect(screen.getByText(/no training load computed yet/i)).toBeTruthy()
    expect(screen.getByTestId('freshness-line').textContent).toContain('Health Connect')
  })
})

describe('the freshness line (the point of the card)', () => {
  test('fresh data: the line names each pipe and is not amber', async () => {
    mockApi({ f: freshness({ hcHours: 3 }) })
    await renderCard()
    const line = screen.getByTestId('freshness-line')
    expect(line.textContent).toBe('Data as of 3 h ago · Health Connect 3 h ago · Polar 2 d ago')
    expect(line.className).not.toContain('amber')
    expect(screen.getByLabelText('Load summary').getAttribute('data-stale')).toBe('false')
    expect(screen.getByTestId('load-content').className).not.toContain('opacity')
  })

  test('GATE: the card renders amber and dims when the Health Connect delivery is 14 h old', async () => {
    mockApi({ f: freshness({ hcHours: 14 }) })
    await renderCard()
    const line = screen.getByTestId('freshness-line')
    expect(line.textContent).toContain('Health Connect 14 h ago')
    expect(line.className).toContain('text-amber')
    expect(screen.getByLabelText('Load summary').getAttribute('data-stale')).toBe('true')
    expect(screen.getByTestId('load-content').className).toContain('opacity-50')
    // The warning itself is not dimmed with the numbers.
    expect(line.closest('[data-testid="load-content"]')).toBeNull()
  })

  test('a pipe that never delivered reads "never"', async () => {
    const f = freshness({ hcHours: 3 })
    f.pipes.polar = { status: 'never', age_hours: null, newest_at: null }
    mockApi({ f })
    await renderCard()
    expect(screen.getByTestId('freshness-line').textContent).toContain('Polar never')
  })

  test('if freshness cannot be read the card says so, amber and dimmed, never a bare number', async () => {
    mockApi({ fFail: true })
    await renderCard()
    const line = screen.getByTestId('freshness-line')
    expect(line.textContent).toMatch(/age unavailable/i)
    expect(line.className).toContain('text-amber')
    expect(screen.getByLabelText('Load summary').getAttribute('data-stale')).toBe('true')
  })

  test('if the load series cannot be read the age line still shows', async () => {
    mockApi({ sFail: true })
    await renderCard()
    expect(screen.getByText(/no training load computed yet/i)).toBeTruthy()
    expect(screen.getByTestId('freshness-line').textContent).toContain('Health Connect 3 h ago')
  })
})

describe('what must never appear (F1, #18/#255)', () => {
  test('no ratio, no sweet-spot verdict, no form band label, even when the payload carries a ratio', async () => {
    mockApi()
    await renderCard()
    const text = document.body.textContent.toLowerCase()
    expect(text).not.toMatch(/ratio|acwr|sweet|optimal|danger|overreach|detrain|peak|fresh form|:\s*\d/)
    expect(text).not.toContain('1.5')                       // the payload's load_ratio (1.53) is not rendered
  })
})

describe('fatigueDirection', () => {
  const pts = (fatigues) => fatigues.map((f, i) => ({ day: day(fatigues.length - 1 - i), fatigue: f }))
  test('rising, easing and steady against the stored day a week back', () => {
    expect(fatigueDirection(pts([1, 1, 1, 1, 1, 1, 1, 9])).key).toBe('rising')
    expect(fatigueDirection(pts([9, 1, 1, 1, 1, 1, 1, 1])).key).toBe('easing')
    expect(fatigueDirection(pts([5, 1, 1, 1, 1, 1, 1, 5])).key).toBe('steady')
  })
  test('under a week of history gives no arrow rather than a guess', () => {
    expect(fatigueDirection(pts([1, 2, 3]))).toBeNull()
    expect(fatigueDirection([])).toBeNull()
    expect(fatigueDirection(null)).toBeNull()
  })
})
