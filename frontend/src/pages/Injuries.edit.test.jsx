// @vitest-environment jsdom
//
// Edit on the injury card (DECISIONS_LOG "The injury row has a closed shape"): a same-key rewrite
// through POST /knowledge/entry with `source: "api"`, the legacy restrictions carried byte-identical,
// blank optional fields omitted, and the proposals group refetched afterwards (the write path's hook
// re-proposes engine defaults on a side change, #487). Fixtures are SYNTHETIC vocabulary parts.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import Injuries from './Injuries'

const ROW = {
  id: 119, type: 'injury', key: 'injury_knee_left', active: true, source: 'api', added_at: '2026-10-01',
  expires_at: null, notes: null, superseded_by: null,
  value: { body_part: 'knee', side: 'left', signal_type: 'mechanical', restrictions: ['deep loaded knee flexion'],
    detail: 'Left knee, intra-articular.', mechanism: 'contact' },
}
const LEGACY = {
  id: 163, type: 'injury', key: 'injury_pigeon_foot_left', active: true, source: 'api', added_at: '2026-10-01',
  expires_at: null, notes: null, superseded_by: null,
  value: { body_part: 'foot/hip', side: 'left', signal_type: 'mechanical' },
}

function routeGets(rows = [ROW]) {
  api.get.mockImplementation((url) => {
    if (url === '/knowledge/injuries') return Promise.resolve({ data: rows })
    if (url === '/knowledge/proposals') return Promise.resolve({ data: [] })
    if (url === '/knowledge/review-due') return Promise.resolve({ data: { items: [], withheld_labs: 0 } })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

async function renderView(rows) {
  routeGets(rows)
  await act(async () => { render(<MemoryRouter><Injuries /></MemoryRouter>) })
  await waitFor(() => expect(screen.getAllByText(/\(left\)/).length).toBeGreaterThan(0))
}

const card = (title) => screen.getByText(title).closest('.rounded-2xl')
const proposalGets = () => api.get.mock.calls.filter(([u]) => u === '/knowledge/proposals').length

beforeEach(() => { api.get.mockReset(); api.post.mockReset() })
afterEach(cleanup)

test('the form is hidden until Edit; a side change POSTs the rewrite with restrictions carried and refetches proposals', async () => {
  await renderView()
  const c = within(card('Knee (left)'))
  expect(screen.queryByLabelText('Edit injury')).toBeNull()
  expect(screen.queryByText(/onset/i)).toBeNull()                      // the view's own claim stands
  await act(async () => { c.getByRole('button', { name: 'Edit…' }).click() })
  const before = proposalGets()
  fireEvent.change(c.getByLabelText('Side'), { target: { value: 'right' } })
  fireEvent.change(c.getByLabelText('Course'), { target: { value: 'acute' } })
  fireEvent.change(c.getByLabelText('Onset date'), { target: { value: '2026-10-20' } })
  api.post.mockResolvedValue({ data: {} })
  await act(async () => { c.getByRole('button', { name: 'Save injury' }).click() })
  expect(api.post).toHaveBeenCalledTimes(1)
  expect(api.post).toHaveBeenCalledWith('/knowledge/entry', {
    type: 'injury', key: 'injury_knee_left', source: 'api',
    value: {
      body_part: 'knee', side: 'right', signal_type: 'mechanical',
      restrictions: ['deep loaded knee flexion'],                     // byte-identical, never grown
      detail: 'Left knee, intra-articular.', mechanism: 'contact',    // api-only field rides along
      course: 'acute', onset_on: '2026-10-20',                        // diagnosis_status blank → omitted
    },
  })
  await waitFor(() => expect(proposalGets()).toBe(before + 1))
  expect(screen.queryByLabelText('Edit injury')).toBeNull()
})

test('the body-part select offers exactly the vocabulary, and a legacy part stays selectable as recorded', async () => {
  await renderView([ROW, LEGACY])
  const knee = within(card('Knee (left)'))
  await act(async () => { knee.getByRole('button', { name: 'Edit…' }).click() })
  const options = Array.from(knee.getByLabelText('Body part').options).map((o) => o.value)
  expect(options[0]).toBe('hamstring')
  expect(options).toContain('knee')
  expect(options).toContain('rib')
  expect(options).not.toContain('foot/hip')
  const legacy = within(card('Foot/hip (left)'))
  await act(async () => { legacy.getByRole('button', { name: 'Edit…' }).click() })
  const legacyOptions = Array.from(legacy.getByLabelText('Body part').options).map((o) => o.value)
  expect(legacyOptions[0]).toBe('foot/hip')
  expect(legacy.getByLabelText('Body part').value).toBe('foot/hip')
  api.post.mockResolvedValue({ data: {} })
  await act(async () => { legacy.getByRole('button', { name: 'Save injury' }).click() })
  expect(api.post.mock.calls[0][1].value.body_part).toBe('foot/hip')
})

test('a refusal is shown verbatim and the form stays open', async () => {
  await renderView()
  const c = within(card('Knee (left)'))
  await act(async () => { c.getByRole('button', { name: 'Edit…' }).click() })
  api.post.mockRejectedValue({ response: { status: 422, data: { detail: 'SERVER SAYS NO' } } })
  await act(async () => { c.getByRole('button', { name: 'Save injury' }).click() })
  expect(c.getByText('SERVER SAYS NO')).toBeTruthy()
  expect(c.getByLabelText('Edit injury')).toBeTruthy()
})

test('Cancel closes the form with no request', async () => {
  await renderView()
  const c = within(card('Knee (left)'))
  await act(async () => { c.getByRole('button', { name: 'Edit…' }).click() })
  await act(async () => { c.getByRole('button', { name: 'Cancel' }).click() })
  expect(screen.queryByLabelText('Edit injury')).toBeNull()
  expect(api.post).not.toHaveBeenCalled()
})
