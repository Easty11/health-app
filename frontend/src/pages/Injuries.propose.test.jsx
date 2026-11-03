// @vitest-environment jsdom
//
// Propose constraints from restrictions (DECISIONS_LOG "Restrictions become constraint proposals from
// the injury card"): the button appears only on a card with non-empty restrictions, one POST hits the
// type-scoped route, each restriction then shows the state the response named (proposed / confirmed /
// declined), the proposals group refetches, and the button disappears once every restriction has a
// state. Fixtures are SYNTHETIC vocabulary parts.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import Injuries from './Injuries'

const WITH = {
  id: 94, type: 'injury', key: 'injury_lumbar_spine', active: true, source: 'chat', added_at: '2026-09-27',
  expires_at: null, notes: null, superseded_by: null,
  value: { body_part: 'lumbar', side: 'bilateral', signal_type: 'mechanical',
    restrictions: ['restriction one', 'restriction two', 'restriction three'] },
}
const WITHOUT = {
  id: 118, type: 'injury', key: 'injury_shoulder_right', active: true, source: 'api', added_at: '2026-10-01',
  expires_at: null, notes: null, superseded_by: null,
  value: { body_part: 'shoulder', side: 'right', signal_type: 'mechanical', restrictions: [] },
}

function routeGets() {
  api.get.mockImplementation((url) => {
    if (url === '/knowledge/injuries') return Promise.resolve({ data: [WITH, WITHOUT] })
    if (url === '/knowledge/proposals') return Promise.resolve({ data: [] })
    if (url === '/knowledge/review-due') return Promise.resolve({ data: { items: [], withheld_labs: 0 } })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

async function renderView() {
  routeGets()
  await act(async () => { render(<MemoryRouter><Injuries /></MemoryRouter>) })
  await waitFor(() => expect(screen.getByText('Lumbar (bilateral)')).toBeTruthy())
}

const card = (title) => screen.getByText(title).closest('.rounded-2xl')
const BUTTON = /Propose constraints from restrictions/
const proposalGets = () => api.get.mock.calls.filter(([u]) => u === '/knowledge/proposals').length

beforeEach(() => { api.get.mockReset(); api.post.mockReset() })
afterEach(cleanup)

test('the button appears only on a card with non-empty restrictions', async () => {
  await renderView()
  expect(within(card('Lumbar (bilateral)')).getByRole('button', { name: BUTTON })).toBeTruthy()
  expect(within(card('Shoulder (right)')).queryByRole('button', { name: BUTTON })).toBeNull()
})

test('one POST to the type-scoped route; each restriction shows its state; proposals refetch; the button goes', async () => {
  await renderView()
  const c = within(card('Lumbar (bilateral)'))
  const before = proposalGets()
  api.post.mockResolvedValue({ data: {
    entry_id: 94, key: 'injury_lumbar_spine', review_by: '2026-12-02',
    planned: [{ key: 'constraint_injury_lumbar_spine_restriction_one', text: 'restriction one' }],
    created: [501],
    existing: [
      { text: 'restriction two', key: 'c2', id: 97, state: 'confirmed', status: 'confirmed', active: true },
      { text: 'restriction three', key: 'c3', id: 98, state: 'declined', status: 'proposed', active: false },
    ],
    skipped: [],
  } })
  await act(async () => { c.getByRole('button', { name: BUTTON }).click() })
  expect(api.post).toHaveBeenCalledTimes(1)
  expect(api.post).toHaveBeenCalledWith('/knowledge/injuries/94/propose-constraints')
  expect(c.getByText('restriction one · proposed')).toBeTruthy()
  expect(c.getByText('restriction two · confirmed')).toBeTruthy()
  expect(c.getByText('restriction three · declined')).toBeTruthy()
  await waitFor(() => expect(proposalGets()).toBe(before + 1))
  expect(c.queryByRole('button', { name: BUTTON })).toBeNull()
})

test('a restriction the route did not place keeps the button; a skipped token counts as placed', async () => {
  await renderView()
  const c = within(card('Lumbar (bilateral)'))
  api.post.mockResolvedValue({ data: {
    entry_id: 94, key: 'injury_lumbar_spine', review_by: '2026-12-02',
    planned: [{ key: 'k1', text: 'restriction one' }], created: [501],
    existing: [], skipped: [{ text: 'restriction two', why: 'key held by active row #7 of another shape' }],
  } })
  await act(async () => { c.getByRole('button', { name: BUTTON }).click() })
  expect(c.getByText('restriction two · skipped')).toBeTruthy()
  expect(c.getByText('restriction three')).toBeTruthy()           // no state: nothing came back for it
  expect(c.getByRole('button', { name: BUTTON })).toBeTruthy()
})

test('a refusal is shown verbatim and nothing on the card changes', async () => {
  await renderView()
  const c = within(card('Lumbar (bilateral)'))
  api.post.mockRejectedValue({ response: { status: 422, data: { detail: 'SERVER SAYS NO' } } })
  await act(async () => { c.getByRole('button', { name: BUTTON }).click() })
  expect(c.getByText('SERVER SAYS NO')).toBeTruthy()
  expect(c.getByText('restriction one')).toBeTruthy()
  expect(c.getByRole('button', { name: BUTTON })).toBeTruthy()
})
