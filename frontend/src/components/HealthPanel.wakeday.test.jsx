// @vitest-environment jsdom
//
// Wake-day slot states on the Recovery page (S1). A figure the CURRENT wake-day lacks reads as a WORD
// (pending / not synced / missing), never a dash; the capture status names what is outstanding and offers a
// retry; a figure of an earlier night keeps its plain dash; a refresh response's `status` replaces the slots
// so they fill when the fetch returns; Resting HR is on the page.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { act } from 'react'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import HealthPanel from './HealthPanel'

const NIGHT = (night, extra = {}) => ({
  night, source: 'garmin', source_label: 'Garmin', duration_min: 413, deep_min: 59, rem_min: 59, light_min: 295,
  awake_min: null, efficiency_pct: null, resp_rate: null, spo2_pct: null, resting_hr_bpm: null,
  sleep_hr_bpm: null, ...extra,
})
const summary = (night, extra) => ({
  latest_hrv: { hrv_ms: 68, source: 'garmin', captured_at: night, status: 'BALANCED' },
  latest: null, vs_baseline: null, baseline_hrv: null, trend: [], latest_sleep: NIGHT(night, extra),
})
const slot = (state, message) => ({ state, ...(message ? { message } : {}) })
const WAKE = (state, message, extra = {}) => ({
  connected: true, wake_day: '2026-11-02', window_open: state !== 'missing', closes_at: '10:00',
  complete: false, last_outcome: state === 'not_synced' ? 'not_synced' : null,
  slots: { sleep: { state: 'filled' }, efficiency: slot(state, message), awake: slot(state, message),
           spo2: slot(state, message), rr: slot(state, message), rhr: slot(state, message) },
  gaps: ['efficiency', 'awake', 'spo2', 'rr', 'rhr'],
  message: message ?? 'Overnight data for 2026-11-02 is still arriving: efficiency, awake, spo2, rr, rhr pending',
  ...extra,
})

let wakeResponse, summaryResponse
beforeEach(() => {
  vi.clearAllMocks()
  api.get.mockImplementation((url) =>
    Promise.resolve({ data: url === '/integrations/garmin/wake-day' ? wakeResponse : summaryResponse }))
  api.post.mockResolvedValue({ data: { skipped: true, reason: 'throttled' } })
})
afterEach(cleanup)

const renderIt = async () => { await act(async () => { render(<HealthPanel />) }) }

test('pending: the missing vitals read "pending", never a dash, on the current wake-day', async () => {
  summaryResponse = summary('2026-11-02')
  wakeResponse = WAKE('pending')
  await renderIt()
  await screen.findByText(/still arriving/)
  for (const label of ['Efficiency', 'Resp Rate', 'SpO2', 'Resting HR']) {
    const tile = screen.getByText(label).parentElement
    expect(within(tile).getByText('pending')).toBeTruthy()
    expect(within(tile).queryByText('—')).toBeNull()
  }
  expect(screen.getByText(/Awake pending/)).toBeTruthy()
})

test('not synced: the named message and a Retry that forces a refresh', async () => {
  summaryResponse = summary('2026-11-02')
  const msg = 'Garmin not synced yet — open Garmin Connect, then Refresh'
  wakeResponse = WAKE('not_synced', msg)
  await renderIt()
  await screen.findByText(msg)
  expect(within(screen.getByText('SpO2').parentElement).getByText('not synced')).toBeTruthy()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Retry' })) })
  await waitFor(() => expect(api.post).toHaveBeenLastCalledWith(
    '/integrations/garmin/refresh', null, { params: { via: 'recovery', force: true } }))
})

test('after 10:00 a missing slot says missing and the reason is on the page', async () => {
  summaryResponse = summary('2026-11-02')
  wakeResponse = WAKE('missing', 'missing — the Garmin key was refused', {
    window_open: false, message: 'Capture for 2026-11-02 closed at 10:00 without: spo2 (the Garmin key was refused)' })
  await renderIt()
  await screen.findByText(/closed at 10:00 without/)
  expect(within(screen.getByText('SpO2').parentElement).getByText('missing')).toBeTruthy()
})

test("an earlier night's card keeps its plain dash: today's slot words are not stamped onto it", async () => {
  summaryResponse = summary('2026-11-01')                  // the page shows yesterday's night (today has none)
  wakeResponse = WAKE('pending')
  await renderIt()
  await screen.findByText(/still arriving/)                // the status still names today
  expect(within(screen.getByText('SpO2').parentElement).getByText('—')).toBeTruthy()
  expect(screen.queryByText('pending')).toBeNull()
})

test('slots fill when the refresh returns: its status replaces the pending words', async () => {
  summaryResponse = summary('2026-11-02')
  wakeResponse = WAKE('pending')
  let resolvePost
  api.post.mockImplementation(() => new Promise((res) => { resolvePost = res }))
  await renderIt()
  await screen.findByText(/still arriving/)

  summaryResponse = summary('2026-11-02', { efficiency_pct: 94, resp_rate: 12.5, spo2_pct: 96.4,
                                            resting_hr_bpm: 49, awake_min: 15 })
  await act(async () => {
    resolvePost({ data: { wake_day: '2026-11-02', outcome: 'complete', status: {
      ...WAKE('pending'), complete: true, gaps: [], message: null,
      slots: Object.fromEntries(['sleep', 'efficiency', 'awake', 'spo2', 'rr', 'rhr'].map((k) => [k, { state: 'filled' }])) } } })
  })

  await waitFor(() => expect(screen.queryByText(/still arriving/)).toBeNull())
  await waitFor(() => expect(screen.getByText('96.4')).toBeTruthy())
  expect(within(screen.getByText('Resting HR').parentElement).getByText('49')).toBeTruthy()
  expect(screen.getByText('94%')).toBeTruthy()
})

test('a user with no Garmin connection sees no capture status and the old dash', async () => {
  summaryResponse = summary('2026-11-02')
  wakeResponse = { connected: false, wake_day: '2026-11-02' }
  await renderIt()
  await screen.findByText('Resting HR')
  expect(screen.queryByRole('status')).toBeNull()
  expect(within(screen.getByText('SpO2').parentElement).getByText('—')).toBeTruthy()
})

test('SpO2 renders the mean and the night\'s minimum together: "96.5% · min 91%"', async () => {
  summaryResponse = summary('2026-11-02', { spo2_pct: 96.5, spo2_min_pct: 91 })
  wakeResponse = { connected: true, wake_day: '2026-11-02', window_open: true, slots: {}, gaps: [], message: null }
  await renderIt()
  await screen.findByText('SpO2')
  expect(screen.getByText('SpO2').parentElement.textContent).toContain('96.5% · min 91%')
})

test('a mean with no minimum shows the mean alone, never a placeholder minimum', async () => {
  summaryResponse = summary('2026-11-02', { spo2_pct: 95, spo2_min_pct: null })
  wakeResponse = { connected: true, wake_day: '2026-11-02', window_open: true, slots: {}, gaps: [], message: null }
  await renderIt()
  await screen.findByText('SpO2')
  const text = screen.getByText('SpO2').parentElement.textContent
  expect(text).toContain('95.0%')
  expect(text).not.toMatch(/min/)
  expect(text).not.toContain('—')
})

test('no mean: the slot word stands and no minimum is invented', async () => {
  summaryResponse = summary('2026-11-02', { spo2_pct: null, spo2_min_pct: null })
  wakeResponse = WAKE('pending')
  await renderIt()
  await screen.findByText(/still arriving/)
  const text = screen.getByText('SpO2').parentElement.textContent
  expect(text).toContain('pending')
  expect(text).not.toMatch(/min \d/)
})
