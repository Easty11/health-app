// @vitest-environment jsdom
//
// The close-out asks for sRPE only for the sessions no app rated per session (`/today.srpe_needed`):
// shown when needed or when /today does not say (fail open to asking), hidden when every counted session was
// rated by an app. A hidden slider never sends its untouched default: it sends what the record already holds.
// Same contract on the missed-PM catch-up card (`missed_pm.srpe_needed`).

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import MissedPMCard from '../components/MissedPMCard'
import NightlyCloseOut from './NightlyCloseOut'

let today
beforeEach(() => {
  today = { cbti: { block_open: false } }
  api.get.mockImplementation(() => Promise.resolve({ data: today }))
  api.post.mockImplementation(() => Promise.resolve({ data: {} }))
})
afterEach(() => { cleanup(); vi.clearAllMocks() })

const pmPosts = () => api.post.mock.calls.filter(([u]) => u === '/checkin-v2/pm')
const rpeSlider = (container) => container.querySelector('input[type=range]')

async function openCloseOut(over = {}) {
  today = { ...today, ...over }
  const view = render(<MemoryRouter><NightlyCloseOut /></MemoryRouter>)
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/checkin-v2/today'))
  // /today carries session_quality when the record already says trained; otherwise toggle it on.
  if (!over.session_quality) {
    fireEvent.click(screen.getByText('Trained today?').parentElement.querySelector('button'))
  }
  await waitFor(() => expect(screen.getByText('Session quality (planned vs actual)')).toBeTruthy())
  return view
}

test('srpe_needed true -> the slider and the copy are shown', async () => {
  const { container } = await openCloseOut({ srpe_needed: true })
  await waitFor(() => expect(rpeSlider(container)).not.toBeNull())
  expect(screen.getByText("Rate the sessions your apps didn't.")).toBeTruthy()
})

test('srpe_needed absent -> the slider is shown (fail open to asking)', async () => {
  const { container } = await openCloseOut({})
  expect(rpeSlider(container)).not.toBeNull()
})

test('srpe_needed false -> no slider, a quiet note, session quality still asked', async () => {
  const { container } = await openCloseOut({ srpe_needed: false })
  await waitFor(() => expect(screen.getByText(/Your apps rated every session today/)).toBeTruthy())
  expect(rpeSlider(container)).toBeNull()
  expect(screen.getByText('Session quality (planned vs actual)')).toBeTruthy()
})

test('hidden slider sends the stored whole-day value, not the untouched default 7', async () => {
  await openCloseOut({ srpe_needed: false, session_rpe: 4, session_quality: 3 })
  fireEvent.click(screen.getByRole('button', { name: /Save & Close the Day/ }))
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(pmPosts()[0][1]).toMatchObject({ trained_today: true, session_quality: 3, session_rpe: 4 })
})

test('hidden slider with nothing stored sends null', async () => {
  await openCloseOut({ srpe_needed: false })
  fireEvent.click(screen.getByRole('button', { name: /Save & Close the Day/ }))
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(pmPosts()[0][1]).toMatchObject({ trained_today: true, session_rpe: null })
})

test('shown slider sends what was set', async () => {
  const { container } = await openCloseOut({ srpe_needed: true })
  fireEvent.change(rpeSlider(container), { target: { value: '9' } })
  fireEvent.click(screen.getByRole('button', { name: /Save & Close the Day/ }))
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(pmPosts()[0][1]).toMatchObject({ trained_today: true, session_rpe: 9 })
})

test('a day not trained sends no RPE whatever srpe_needed says', async () => {
  today = { ...today, srpe_needed: true }
  render(<MemoryRouter><NightlyCloseOut /></MemoryRouter>)
  await waitFor(() => expect(api.get).toHaveBeenCalled())
  fireEvent.click(screen.getByRole('button', { name: /Save & Close the Day/ }))
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(pmPosts()[0][1]).toMatchObject({ trained_today: false, session_rpe: null })
})

// -- the catch-up card ---------------------------------------------------------------------------------

const renderCard = (missedPm) => render(<MissedPMCard missedPm={missedPm} />)
const trainSwitch = () => fireEvent.click(screen.getByRole('switch', { name: 'Trained yesterday' }))

test('card: srpe_needed false hides the RPE slider and sends null', async () => {
  renderCard({ date: '2031-06-14', cbti_block_open: false, srpe_needed: false })
  trainSwitch()
  expect(screen.queryByLabelText('Session RPE')).toBeNull()
  expect(screen.getByText(/Your apps rated every session yesterday/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Save yesterday' }))
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(pmPosts()[0][1]).toMatchObject({ for_date: '2031-06-14', trained_today: true, session_rpe: null })
})

test('card: srpe_needed true shows the slider with the copy and sends the value', async () => {
  renderCard({ date: '2031-06-14', cbti_block_open: false, srpe_needed: true })
  trainSwitch()
  expect(screen.getByText("Rate the sessions your apps didn't.")).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Session RPE'), { target: { value: '5' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save yesterday' }))
  await waitFor(() => expect(pmPosts()).toHaveLength(1))
  expect(pmPosts()[0][1]).toMatchObject({ session_rpe: 5 })
})

test('card: srpe_needed absent asks', () => {
  renderCard({ date: '2031-06-14', cbti_block_open: false })
  trainSwitch()
  expect(screen.getByLabelText('Session RPE')).toBeTruthy()
})
