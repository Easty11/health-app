// @vitest-environment jsdom
//
// Missed-PM catch-up card on the AM check-in. Pinned: the card renders only when the prefill
// carries `missed_pm` and posts `for_date`; Save is independent of the AM submit; Skip hides it
// with no request at all; the nap field follows `missed_pm.cbti_block_open` with blank -> 0 under an
// open block and null otherwise (the NightlyCloseOut contract); a 409 hides the card with a quiet
// note; any other failure keeps it so the entry is not lost.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import CheckInAM from './CheckInAM'

const YDAY = '2031-06-14'
const BASE = { hrv_ms: null, hrv_state: 'absent', sleep_min: null, existing: null,
               cbti: { block_open: false }, diary_prefill: {}, missed_pm: null }
const withMissed = (blockOpen) => ({ ...BASE, missed_pm: { date: YDAY, cbti_block_open: blockOpen } })

let prefill
const pmPosts = () => api.post.mock.calls.filter(([u]) => u === '/checkin-v2/pm')
const amPosts = () => api.post.mock.calls.filter(([u]) => u === '/checkin-v2/am')

beforeEach(() => {
  prefill = BASE
  api.get.mockImplementation(() => Promise.resolve({ data: prefill }))
  api.post.mockImplementation((url) => {
    if (url === '/integrations/garmin/refresh') return Promise.resolve({ data: { skipped: true } })
    return Promise.resolve({ data: {} })
  })
})
afterEach(() => { cleanup(); vi.clearAllMocks() })

const renderIt = () => render(<MemoryRouter><CheckInAM /></MemoryRouter>)
const saveBtn = () => screen.getByRole('button', { name: 'Save yesterday' })

test('no missed_pm -> no card', async () => {
  renderIt()
  await screen.findByText('Morning Check-in')
  expect(screen.queryByText(/Close out yesterday/)).toBeNull()
  expect(screen.queryByRole('button', { name: 'Skip' })).toBeNull()
})

test('missed_pm -> card renders at the top with the dated heading, above the AM form', async () => {
  prefill = withMissed(false)
  const { container } = renderIt()
  const heading = await screen.findByText(/Close out yesterday \(/)
  expect(heading.textContent).toMatch(/Jun/)
  const form = container.querySelector('form')
  expect(form.contains(heading)).toBe(false)   // outside the AM form: its buttons can never submit it
  // document order: the card precedes the AM form
  expect(heading.compareDocumentPosition(form) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

test('Save posts /checkin-v2/pm with for_date and the PM fields, and never touches /am', async () => {
  prefill = withMissed(false)
  renderIt()
  await screen.findByText(/Close out yesterday/)
  fireEvent.click(screen.getByTitle('Poor'))                        // day rating -> 2
  fireEvent.change(screen.getByLabelText(/Notes \(optional\)/), { target: { value: 'forgot' } })
  fireEvent.click(saveBtn())
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(pmPosts()[0][1]).toEqual({
    for_date: YDAY, today_rating: 2, trained_today: false,
    session_quality: null, session_rpe: null, pm_notes: 'forgot', naps_min: null,
  })
  expect(amPosts()).toHaveLength(0)                                 // independent of the AM submit
})

test('trained yesterday sends session quality and RPE', async () => {
  prefill = withMissed(false)
  renderIt()
  await screen.findByText(/Close out yesterday/)
  fireEvent.click(screen.getByRole('switch', { name: 'Trained yesterday' }))
  fireEvent.click(screen.getAllByTitle('Above plan')[0])
  fireEvent.change(screen.getByLabelText('Session RPE'), { target: { value: '8' } })
  fireEvent.click(saveBtn())
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(pmPosts()[0][1]).toMatchObject({ trained_today: true, session_quality: 4, session_rpe: 8 })
})

test('Save hides the card and says so; the AM form is still there and still submits', async () => {
  prefill = withMissed(false)
  renderIt()
  await screen.findByText(/Close out yesterday/)
  fireEvent.click(saveBtn())
  await screen.findByText(/Yesterday's close-out saved/)
  expect(screen.queryByText(/Close out yesterday/)).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Save Check-in' }))
  await waitFor(() => expect(amPosts()).toHaveLength(1))
})

test('Skip hides the card with no request at all', async () => {
  prefill = withMissed(true)
  renderIt()
  await screen.findByText(/Close out yesterday/)
  fireEvent.click(screen.getByRole('button', { name: 'Skip' }))
  expect(screen.queryByText(/Close out yesterday/)).toBeNull()
  expect(pmPosts()).toHaveLength(0)
  expect(api.post.mock.calls.every(([u]) => u === '/integrations/garmin/refresh')).toBe(true)
})

test('nap field is hidden when no block was open yesterday', async () => {
  prefill = withMissed(false)
  renderIt()
  await screen.findByText(/Close out yesterday/)
  expect(screen.queryByLabelText(/Naps yesterday/)).toBeNull()
})

test('nap field shows under an open block; blank submits 0, never null', async () => {
  prefill = withMissed(true)
  renderIt()
  await screen.findByText(/Close out yesterday/)
  expect(screen.getByLabelText(/Naps yesterday/)).toBeTruthy()
  fireEvent.click(saveBtn())
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(pmPosts()[0][1].naps_min).toBe(0)
  expect(pmPosts()[0][1].naps_min).not.toBeNull()
})

test('a typed nap is sent as that number', async () => {
  prefill = withMissed(true)
  renderIt()
  await screen.findByText(/Close out yesterday/)
  fireEvent.change(screen.getByLabelText(/Naps yesterday/), { target: { value: '45' } })
  fireEvent.click(saveBtn())
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(pmPosts()[0][1].naps_min).toBe(45)
})

test('the nap gate follows missed_pm, not the AM screen\'s own block state', async () => {
  // today's block is open but yesterday's was not: the field must follow missed_pm
  prefill = { ...BASE, cbti: { block_open: true }, missed_pm: { date: YDAY, cbti_block_open: false } }
  renderIt()
  await screen.findByText(/Close out yesterday/)
  expect(screen.queryByLabelText(/Naps yesterday/)).toBeNull()
  fireEvent.click(saveBtn())
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(pmPosts()[0][1].naps_min).toBeNull()
})

test('a 409 hides the card with a quiet note', async () => {
  prefill = withMissed(false)
  api.post.mockImplementation((url) => {
    if (url === '/integrations/garmin/refresh') return Promise.resolve({ data: { skipped: true } })
    return Promise.reject({ response: { status: 409, data: { detail: 'That day\'s close-out is already recorded.' } } })
  })
  renderIt()
  await screen.findByText(/Close out yesterday/)
  fireEvent.click(saveBtn())
  await screen.findByText(/already closed out/)
  expect(screen.queryByText(/Close out yesterday/)).toBeNull()
  expect(screen.queryByText(/Failed to save/)).toBeNull()
})

test('any other failure keeps the card and the entered values', async () => {
  prefill = withMissed(false)
  api.post.mockImplementation((url) => {
    if (url === '/integrations/garmin/refresh') return Promise.resolve({ data: { skipped: true } })
    return Promise.reject({ response: { status: 500, data: {} } })
  })
  renderIt()
  await screen.findByText(/Close out yesterday/)
  fireEvent.change(screen.getByLabelText(/Notes \(optional\)/), { target: { value: 'keep me' } })
  fireEvent.click(saveBtn())
  await screen.findByText('Failed to save close-out')
  expect(screen.getByText(/Close out yesterday/)).toBeTruthy()
  expect(screen.getByLabelText(/Notes \(optional\)/).value).toBe('keep me')
})

test('the card also shows when this morning\'s AM is already saved', async () => {
  prefill = { ...withMissed(false), existing: { am_timestamp: 'x', naive_baseline: 6 } }
  renderIt()
  await screen.findByText('Morning check-in saved')
  expect(screen.getByText(/Close out yesterday/)).toBeTruthy()
})
