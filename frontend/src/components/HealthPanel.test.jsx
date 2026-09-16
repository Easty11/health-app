// @vitest-environment jsdom
//
// HealthPanel on-read Garmin refresh (#299). The card renders the cached /health/summary on
// first paint; on open it fires POST /integrations/garmin/refresh (server-gated) and the Refresh
// affordance forces. What is proven: first paint is not blocked on the refresh, the mount refresh
// is issued, a real run re-fetches /health/summary (a skip does not), and Refresh sends
// ?force=true.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import HealthPanel from './HealthPanel'

const SUMMARY = {
  latest_hrv: { hrv_ms: 78, source: 'garmin', captured_at: '2026-09-14', status: 'BALANCED' },
  latest: null,
  vs_baseline: null,
  baseline_hrv: null,
  trend: [],
}

beforeEach(() => {
  vi.clearAllMocks()
  api.get.mockResolvedValue({ data: SUMMARY })                 // /health/summary
  api.post.mockResolvedValue({ data: { skipped: true, reason: 'fresh' } })
})
afterEach(cleanup)

test('renders the cached summary on first paint, then fires POST /integrations/garmin/refresh', async () => {
  await act(async () => { render(<HealthPanel />) })
  // first paint: the cached HRV headline is shown (not blocked on the refresh)
  await waitFor(() => expect(screen.getByText('78')).toBeTruthy())
  await waitFor(() =>
    expect(api.post).toHaveBeenCalledWith('/integrations/garmin/refresh', null, undefined))
})

test('sleep block renders the freshest staged night, source-chipped, with — for fields the source lacks', async () => {
  // Garmin/HC night wins: staging present, sub-metrics the HC aggregate does not carry are null.
  api.get.mockResolvedValue({ data: {
    ...SUMMARY,
    latest_sleep: {
      night: '2026-09-16', source: 'garmin', source_label: 'Garmin',
      duration_min: 381, deep_min: 39, rem_min: 40, light_min: 302, score: 6,
      efficiency_pct: null, awake_min: null, resp_rate: null,
      sleep_hr_bpm: null, spo2_pct: null, bedtime: null, wake_time: null,
    },
  } })
  await act(async () => { render(<HealthPanel />) })
  // Source provenance line: chip + the night this sleep is from.
  await waitFor(() => expect(screen.getByText(/Sleep · Garmin · 16 Sep/)).toBeTruthy())
  // Staging present.
  expect(screen.getByText('6h 21m')).toBeTruthy()      // 381 min duration
  expect(screen.getByText('39m')).toBeTruthy()          // deep
  // Efficiency is not staged by HC → '—', never a stale Samsung value.
  expect(screen.getAllByText('—').length).toBeGreaterThan(0)
})

test('a real run re-fetches /health/summary; a skip does not', async () => {
  await act(async () => { render(<HealthPanel />) })
  await waitFor(() => expect(api.post).toHaveBeenCalled())
  const summaryCalls = () => api.get.mock.calls.filter((c) => c[0] === '/health/summary').length
  await waitFor(() => expect(summaryCalls()).toBe(1)) // mount fetch only (server said skip)
  const afterMount = summaryCalls()

  // Refresh forces; a real run (not skipped) re-fetches /health/summary once.
  api.post.mockResolvedValue({ data: { readings_upserted: 1, days_with_data: 1 } })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Refresh' })) })
  await waitFor(() =>
    expect(api.post).toHaveBeenLastCalledWith(
      '/integrations/garmin/refresh', null, { params: { force: true } }))
  await waitFor(() => expect(summaryCalls()).toBe(afterMount + 1))
})
