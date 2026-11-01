// @vitest-environment jsdom
//
// The Recovery tile's amber (S2): the server's per-user `alerts` are shown as sent, naming the lane or figure and
// the date or age; no alerts (and a wake-day still inside its capture window never produces one) leaves the plain
// subtitle; a failed read leaves the plain subtitle too. The tile stays one doorway to /recovery.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
import RecoveryTile from './RecoveryTile'

const renderIt = async () => { await act(async () => { render(<MemoryRouter><RecoveryTile /></MemoryRouter>) }) }
beforeEach(() => { vi.clearAllMocks() })
afterEach(cleanup)

test('a failed SpO2 lane makes the subtitle amber, naming lane and age', async () => {
  api.get.mockResolvedValue({ data: { connected: true, amber: true, alerts: [
    { code: 'lane_failed', lane: 'di_spo2', message: 'Garmin epoch SpO2 lane failed 8 h ago (error)' }] } })
  await renderIt()
  const amber = await screen.findByTestId('recovery-amber')
  expect(amber.textContent).toBe('Garmin epoch SpO2 lane failed 8 h ago (error)')
  expect(amber.className).toMatch(/amber/)
})

test('a closed wake-day without data names the figure and the date, and counts the rest', async () => {
  api.get.mockResolvedValue({ data: { connected: true, amber: true, alerts: [
    { code: 'missing', message: 'SpO2 missing 2026-11-01' }, { code: 'missing', message: 'HRV missing 2026-11-01' }] } })
  await renderIt()
  expect((await screen.findByTestId('recovery-amber')).textContent).toBe('SpO2 missing 2026-11-01 (+1 more)')
})

test('no alerts (a wake-day inside its capture window is never one): the plain subtitle, no amber', async () => {
  api.get.mockResolvedValue({ data: { connected: true, amber: false, alerts: [] } })
  await renderIt()
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/integrations/garmin/wake-day'))
  expect(screen.getByText('HRV, sleep and overnight vitals')).toBeTruthy()
  expect(screen.queryByTestId('recovery-amber')).toBeNull()
})

test('a failed read keeps the plain subtitle and the doorway', async () => {
  api.get.mockRejectedValue(new Error('boom'))
  await renderIt()
  expect(screen.getByText('HRV, sleep and overnight vitals')).toBeTruthy()
  expect(screen.getByRole('link').getAttribute('href')).toBe('/recovery')
})

test('a user with no Garmin connection is never amber', async () => {
  api.get.mockResolvedValue({ data: { connected: false, alerts: [{ message: 'should not show' }] } })
  await renderIt()
  await waitFor(() => expect(api.get).toHaveBeenCalled())
  expect(screen.queryByTestId('recovery-amber')).toBeNull()
})
