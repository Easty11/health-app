// @vitest-environment jsdom
//
// Garmin lane health on Settings -> Integrations (S3). Per lane the last success age and the outcome; the
// Personal API key's days to expiry, amber at 30 days or less, red when expired or the token exchange is refused.
// The server decides each severity; the card shows them as sent and renders nothing for a user with no Garmin.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { act } from 'react'

vi.mock('../api', () => ({ default: { get: vi.fn() } }))

import api from '../api'
import GarminLaneHealth from './GarminLaneHealth'

const lane = (l, label, outcome, severity, extra = {}) => ({
  lane: l, label, outcome, severity, reason: null, last_attempt_at: '2026-11-02T00:00:00+00:00',
  last_success_at: outcome === 'ok' ? '2026-11-02T00:00:00+00:00' : null,
  success_age_hours: outcome === 'ok' ? 3 : null, ...extra,
})
const view = (key, lanes) => ({ connected: true, personal_api: true, di: false, key, lanes })
const KEY = (severity, message, days) => ({ expires_on: '2026-11-22', days_to_expiry: days, token_refused: false, severity, message })
const renderIt = async () => { await act(async () => { render(<GarminLaneHealth />) }) }

beforeEach(() => { vi.clearAllMocks() })
afterEach(cleanup)

test('a key 20 days from expiry is amber, with its date', async () => {
  api.get.mockResolvedValue({ data: view(KEY('amber', 'Expires in 20 days', 20), []) })
  await renderIt()
  const key = await screen.findByTestId('garmin-key')
  expect(key.dataset.severity).toBe('amber')
  expect(key.textContent).toContain('Expires in 20 days (2026-11-22)')
  expect(key.querySelector('p').className).toMatch(/amber/)
})

test('an expired key and a refused token exchange are red', async () => {
  api.get.mockResolvedValue({ data: view(KEY('red', 'Key EXPIRED 2 day(s) ago: attach a new key', -2), []) })
  await renderIt()
  const key = await screen.findByTestId('garmin-key')
  expect(key.dataset.severity).toBe('red')
  expect(key.querySelector('p').className).toMatch(/red/)
})

test('a healthy key is not coloured as a problem', async () => {
  api.get.mockResolvedValue({ data: view(KEY('ok', 'Expires in 200 days', 200), []) })
  await renderIt()
  expect((await screen.findByTestId('garmin-key')).dataset.severity).toBe('ok')
})

test('each lane shows its outcome and the age of its last success', async () => {
  api.get.mockResolvedValue({ data: view(KEY('ok', 'Expires in 200 days', 200), [
    lane('personal_hrv', 'HRV', 'ok', 'ok'),
    lane('personal_wellness', 'Sleep, heart rate and SpO2', 'error', 'amber', { reason: 'RuntimeError' }),
    lane('personal_selfeval', 'Self-evaluation (RPE)', null, 'none', { last_attempt_at: null }),
    lane('wake_day_fetch', 'Morning wake-day fetch', 'ok', 'ok', { reason: '2026-11-02 complete via=checkin' }),
  ]) })
  await renderIt()
  const hrv = await screen.findByTestId('lane-personal_hrv')
  expect(within(hrv).getByText(/ok · last success 3 h ago/)).toBeTruthy()
  const wellness = screen.getByTestId('lane-personal_wellness')
  expect(wellness.dataset.severity).toBe('amber')
  expect(within(wellness).getByText(/error · never succeeded · RuntimeError/)).toBeTruthy()
  expect(within(screen.getByTestId('lane-personal_selfeval')).getByText(/no run yet · never succeeded/)).toBeTruthy()
  expect(within(screen.getByTestId('lane-wake_day_fetch')).getByText(/2026-11-02 complete via=checkin/)).toBeTruthy()
})

test('a user with no Garmin connection sees no card, and a failed read leaves none', async () => {
  api.get.mockResolvedValue({ data: { connected: false, key: null, lanes: [] } })
  await renderIt()
  expect(screen.queryByTestId('garmin-lanes')).toBeNull()
  cleanup()
  api.get.mockRejectedValue(new Error('boom'))
  await renderIt()
  expect(screen.queryByTestId('garmin-lanes')).toBeNull()
})
