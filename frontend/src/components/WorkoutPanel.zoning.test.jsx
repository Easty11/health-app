// @vitest-environment jsdom
//
// Design 0010 §6: one provenance line under the zone bar on an aerobic session's detail — the class, the basis
// and the anchors that produced the zones (from the server's derived `zoning`), or that the row keeps Polar's
// own zones, or that no anchor was in force. Rendered as sent; nothing is derived client-side.
//
// Fixtures are synthetic placeholders.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import WorkoutPanel, { zoningLine } from './WorkoutPanel'

const HEVY = { id: 'hv1', title: 'Lower', start_time: '2026-09-28T21:00:00+00:00', end_time: '2026-09-28T22:10:00+00:00', exercises: [] }

const row = (id, sport, zoning, extra = {}) => ({
  id, source: 'health_connect', session_date: '2026-09-28', start_time: '2026-09-27T22:01:00Z', sport_name: sport,
  duration_minutes: 45, hr_avg: 134, hr_max: 151, calories: null, z1_seconds: 0, z2_seconds: 1500, z3_seconds: 900,
  z4_seconds: 0, z5_seconds: 0, canonical: true, zoning, ...extra,
})

const LTHR = { class: 'lthr', class_label: 'cycling', basis: 'lthr', basis_label: '% of LTHR (Friel)', anchors: { lthr: 158 }, edges_bpm: [0, 128, 143, 149, 158], reason: null }
const HRR = { class: 'hrr', class_label: 'other sports', basis: 'hrr', basis_label: '% of heart-rate reserve (Karvonen)', anchors: { hrmax: 179, rhr: 51 }, edges_bpm: [115, 128, 141, 154, 167], reason: null }
const VENDOR = { class: 'lthr', class_label: 'cycling', basis: 'vendor', basis_label: "Polar's own zones (not re-zoned)", anchors: {}, edges_bpm: null, reason: 'polar_vendor_fallback' }
const NONE = { class: 'hrr', class_label: 'other sports', basis: null, basis_label: null, anchors: {}, edges_bpm: null, reason: 'no_anchor' }

function mockApi(aerobic) {
  api.get.mockImplementation((url) => {
    if (url === '/integrations/hevy/workout-count') return Promise.resolve({ data: { workout_count: 1 } })
    if (url.startsWith('/integrations/hevy/workouts')) return Promise.resolve({ data: { workouts: [HEVY] } })
    if (url.startsWith('/integrations/polar/aerobic-sessions')) return Promise.resolve({ data: aerobic })
    return Promise.resolve({ data: null })
  })
  api.post.mockResolvedValue({ data: {} })
}

async function openDetail(sport) {
  await act(async () => { render(<WorkoutPanel onFeedback={vi.fn()} />) })
  await waitFor(() => expect(screen.getByText(sport)).toBeTruthy())
  await act(async () => { fireEvent.click(screen.getByText(sport)) })
  await waitFor(() => expect(screen.getByText('Session feedback')).toBeTruthy())
}

beforeEach(() => { api.get.mockReset(); api.post.mockReset() })
afterEach(cleanup)

test('a cycling row says it was zoned on %LTHR with its anchor', async () => {
  mockApi([row(1, 'Biking Stationary', LTHR)])
  await openDetail('Biking Stationary')
  const line = screen.getByTestId('zoning-line')
  expect(line.dataset.basis).toBe('lthr')
  expect(line.textContent).toBe('Zoned on %LTHR (cycling class) · LTHR 158 bpm')
})

test('another sport says %HRR with both anchors', async () => {
  mockApi([row(2, 'Walking', HRR)])
  await openDetail('Walking')
  expect(screen.getByTestId('zoning-line').textContent).toBe('Zoned on %HRR (other sports class) · RHR 51 · HRmax 179 bpm')
})

test("a Polar row keeping Polar's own zones says so", async () => {
  mockApi([row(3, 'Indoor cycling', VENDOR, { source: 'polar_v4' })])
  await openDetail('Indoor cycling')
  const line = screen.getByTestId('zoning-line')
  expect(line.dataset.basis).toBe('vendor')
  expect(line.textContent).toContain("Polar's own zones")
})

test('a withheld row with no anchor in force says which anchor is missing', async () => {
  mockApi([row(4, 'Walking', NONE, { z1_seconds: null, z2_seconds: null, z3_seconds: null, z4_seconds: null, z5_seconds: null })])
  await openDetail('Walking')
  expect(screen.getByTestId('zoning-line').textContent).toContain('no RHR / HRmax anchor in force')
})

test('a row Garmin also recorded shows vendor-labelled Garmin tiles as sent', async () => {
  const garmin = { vendor: 'Garmin', garmin_activity_id: 1, calories: 612.4, te_aerobic: 5, te_anaerobic: 2.1,
                   training_load: 276.3, te_label: 'VO2MAX' }
  mockApi([row(6, 'Indoor cycling', LTHR, { garmin_metrics: garmin })])
  await openDetail('Indoor cycling')
  const tiles = screen.getByTestId('garmin-tiles')
  expect(tiles.textContent).toContain('Garmin')
  expect(tiles.textContent).toContain('612kcal')
  expect(tiles.textContent).toContain('5.0TE aerobic')
  expect(tiles.textContent).toContain('2.1TE anaerobic')
  expect(tiles.textContent).toContain('276Garmin load')
  expect(tiles.textContent).toContain("Garmin's label: VO2MAX")
})

test('a missing Garmin field shows a dash, and a row with no Garmin activity shows no tiles', async () => {
  mockApi([row(7, 'Indoor cycling', LTHR, { garmin_metrics: { vendor: 'Garmin', calories: 300, te_aerobic: null, te_anaerobic: null, training_load: null } })])
  await openDetail('Indoor cycling')
  expect(screen.getByTestId('garmin-tiles').textContent).toContain('—TE aerobic')
  cleanup()
  mockApi([row(8, 'Walking', HRR)])
  await openDetail('Walking')
  expect(screen.queryByTestId('garmin-tiles')).toBeNull()
})

test('a row without the field renders no line (older payloads)', async () => {
  mockApi([row(5, 'Walking', undefined)])
  await openDetail('Walking')
  expect(screen.queryByTestId('zoning-line')).toBeNull()
  expect(zoningLine(null)).toBeNull()
  expect(zoningLine({ class: 'lthr', class_label: 'cycling', basis: null, reason: 'withheld' })).toBeNull()
})
