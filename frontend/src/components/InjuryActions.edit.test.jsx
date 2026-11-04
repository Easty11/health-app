// @vitest-environment jsdom
//
// Edit on a proposed card (GH#617): before Confirm or Decline, the operator corrects a proposal in an
// inline form prefilled from the row; Save POSTs the typed /edit route with the editable fields and the
// parent re-reads, so the card shows the successor (same key, new id, still proposed). A validator
// refusal is shown verbatim. Edit never calls a /confirm route. The component is the shared one, so
// the AM check-in's "Needs your call" carries the same action (its own test asserts the affordance).
// Fixtures are SYNTHETIC.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import Injuries from '../pages/Injuries'

const INJURIES = [
  { id: 1, type: 'injury', key: 'injury_part_a_left', active: true, source: 'api', added_at: '2025-11-01',
    expires_at: null, notes: null, superseded_by: null,
    value: { body_part: 'part a', side: 'left', signal_type: 'mechanical', restrictions: [] } },
]

const ENGINE = { id: 10, type: 'constraint', key: 'c_engine', active: true, source: 'chat', added_at: '2025-12-01',
  value: { scope: { tier: 'engine', region_keys: ['squat', 'knee_flexion'], side: 'left' }, kind: 'block', parent_key: null,
    exit: { on_condition: 'cleared by the clinician' }, review_by: '2026-12-02', status: 'proposed', asserted_by: null,
    detail: 'ORIGINAL DETAIL' } }
const ADVISORY = { id: 11, type: 'constraint', key: 'c_adv', active: true, source: 'chat', added_at: '2025-12-01',
  value: { scope: { tier: 'advisory', text: 'cap on movement A' }, kind: 'cap', parent_key: 'injury_part_a_left',
    exit: { with_parent: true }, review_by: '2026-01-15', status: 'proposed', asserted_by: null } }
const FINDING = { id: 12, type: 'finding', key: 'f_prop', active: true, source: 'chat', added_at: '2025-12-01',
  value: { statement: 'Synthetic finding A', domain: 'injury', status: 'proposed', parent_key: null,
    as_of: '2025-12-01', basis: { text: 'basis A' }, derived_from_labs: false, asserted_by: null } }

let proposals
function routeGets() {
  api.get.mockImplementation((url) => {
    if (url === '/knowledge/injuries') return Promise.resolve({ data: INJURIES })
    if (url === '/knowledge/proposals') return Promise.resolve({ data: proposals })
    if (url === '/knowledge/review-due') return Promise.resolve({ data: { items: [], withheld_labs: 0 } })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

async function renderView() {
  await act(async () => { render(<MemoryRouter><Injuries /></MemoryRouter>) })
  await waitFor(() => expect(screen.getByText('Part a (left)')).toBeTruthy())
}

const itemFor = (re) => screen.getByText(re).closest('li')
const other = () => screen.getByRole('region', { name: 'Other proposals' })

beforeEach(() => {
  proposals = [ENGINE, ADVISORY, FINDING]
  api.get.mockReset()
  api.post.mockReset()
  routeGets()
})
afterEach(cleanup)

describe('Edit on a proposed card', () => {
  test('the form is prefilled from the row and Save POSTs the typed /edit route, then the successor shows', async () => {
    await renderView()
    const item = itemFor(/regions: squat, knee_flexion/)
    await act(async () => { within(item).getByRole('button', { name: 'Edit…' }).click() })
    const form = within(item).getByLabelText('Edit proposed constraint')
    expect(within(form).getByLabelText('Regions (keys, comma-separated)').value).toBe('squat, knee_flexion')
    expect(within(form).getByLabelText('Side').value).toBe('left')
    expect(within(form).getByLabelText('Kind').value).toBe('block')
    expect(within(form).getByLabelText('Ends when').value).toBe('cleared by the clinician')
    expect(within(form).getByLabelText('Review by').value).toBe('2026-12-02')
    expect(within(form).getByLabelText('Parent injury key').value).toBe('')
    expect(within(form).getByLabelText('Detail').value).toBe('ORIGINAL DETAIL')

    fireEvent.change(within(form).getByLabelText('Regions (keys, comma-separated)'), { target: { value: 'squat' } })
    fireEvent.change(within(form).getByLabelText('Parent injury key'), { target: { value: 'injury_part_a_left' } })
    fireEvent.change(within(form).getByLabelText('Detail'), { target: { value: 'deep loaded flexion only' } })

    api.post.mockResolvedValue({ data: {} })
    const successor = { ...ENGINE, id: 13, source: 'api', notes: 'edited in-app from #10',
      value: { ...ENGINE.value, scope: { tier: 'engine', region_keys: ['squat'], side: 'left' },
        parent_key: 'injury_part_a_left', detail: 'deep loaded flexion only' } }
    proposals = [successor, ADVISORY, FINDING]
    await act(async () => { within(form).getByRole('button', { name: 'Save edit' }).click() })
    expect(api.post).toHaveBeenCalledWith('/knowledge/constraints/10/edit', { value: {
      kind: 'block', scope: { tier: 'engine', region_keys: ['squat'], side: 'left' },
      exit: { on_condition: 'cleared by the clinician' }, review_by: '2026-12-02',
      parent_key: 'injury_part_a_left', detail: 'deep loaded flexion only' } })
    // The re-read shows the successor: same key, new id, on the parent card now, still proposed.
    await waitFor(() => expect(screen.queryByText(/regions: squat, knee_flexion/)).toBeNull())
    const card = screen.getByText('Part a (left)').closest('.rounded-2xl')
    const shown = within(card).getByText(/regions: squat, left side/).closest('li')
    expect(within(shown).getByRole('button', { name: 'Confirm proposal' })).toBeTruthy()
    expect(within(shown).queryByLabelText('Edit proposed constraint')).toBeNull()
    // Edit never confirms.
    expect(api.post.mock.calls.some(([url]) => url.includes('/confirm'))).toBe(false)
  })

  test('an advisory proposal edits its instruction, exit and review date', async () => {
    await renderView()
    const item = itemFor(/cap on movement A/)
    await act(async () => { within(item).getByRole('button', { name: 'Edit…' }).click() })
    const form = within(item).getByLabelText('Edit proposed constraint')
    expect(within(form).getByLabelText('Instruction').value).toBe('cap on movement A')
    expect(within(form).getByLabelText('Ends when the injury is resolved').checked).toBe(true)
    fireEvent.change(within(form).getByLabelText('Instruction'), { target: { value: 'cap on movement A at 9.5 kg' } })
    fireEvent.change(within(form).getByLabelText('Review by'), { target: { value: '2026-02-01' } })
    api.post.mockResolvedValue({ data: {} })
    await act(async () => { within(form).getByRole('button', { name: 'Save edit' }).click() })
    expect(api.post).toHaveBeenCalledWith('/knowledge/constraints/11/edit', { value: {
      kind: 'cap', scope: { tier: 'advisory', text: 'cap on movement A at 9.5 kg' }, exit: { with_parent: true },
      review_by: '2026-02-01', parent_key: 'injury_part_a_left', detail: null } })
  })

  test('a finding edits statement, parent, as-of and basis through the findings route', async () => {
    await renderView()
    const item = within(other()).getByText(/Synthetic finding A/).closest('li')
    await act(async () => { within(item).getByRole('button', { name: 'Edit…' }).click() })
    const form = within(item).getByLabelText('Edit proposed finding')
    expect(within(form).getByLabelText('Statement').value).toBe('Synthetic finding A')
    expect(within(form).getByLabelText('Basis').value).toBe('basis A')
    fireEvent.change(within(form).getByLabelText('Statement'), { target: { value: 'Edited statement' } })
    fireEvent.change(within(form).getByLabelText('Parent injury key'), { target: { value: 'injury_part_a_left' } })
    fireEvent.change(within(form).getByLabelText('As of'), { target: { value: '2025-12-05' } })
    api.post.mockResolvedValue({ data: {} })
    await act(async () => { within(form).getByRole('button', { name: 'Save edit' }).click() })
    expect(api.post).toHaveBeenCalledWith('/knowledge/findings/12/edit', { value: {
      statement: 'Edited statement', parent_key: 'injury_part_a_left', as_of: '2025-12-05', basis: { text: 'basis A' } } })
  })

  test('a refusal is shown verbatim on the card and the form stays open', async () => {
    await renderView()
    const item = itemFor(/regions: squat, knee_flexion/)
    await act(async () => { within(item).getByRole('button', { name: 'Edit…' }).click() })
    const form = within(item).getByLabelText('Edit proposed constraint')
    fireEvent.change(within(form).getByLabelText('Regions (keys, comma-separated)'), { target: { value: 'deep_squat' } })
    const detail = "constraint.scope.region_keys: unknown region key(s) ['deep_squat'] -- valid keys: ['squat', 'knee_flexion']"
    api.post.mockRejectedValue({ response: { status: 422, data: { detail } } })
    await act(async () => { within(form).getByRole('button', { name: 'Save edit' }).click() })
    expect(within(item).getByText(detail)).toBeTruthy()
    expect(within(item).getByLabelText('Edit proposed constraint')).toBeTruthy()
    expect(api.post).toHaveBeenCalledWith('/knowledge/constraints/10/edit', { value: expect.objectContaining({
      scope: { tier: 'engine', region_keys: ['deep_squat'], side: 'left' } }) })
  })

  test('Cancel closes the form without a write; Edit and Decline are exclusive', async () => {
    await renderView()
    const item = itemFor(/cap on movement A/)
    await act(async () => { within(item).getByRole('button', { name: 'Decline…' }).click() })
    expect(within(item).getByText(/why decline this proposal/)).toBeTruthy()
    await act(async () => { within(item).getByRole('button', { name: 'Edit…' }).click() })
    expect(within(item).queryByText(/why decline this proposal/)).toBeNull()
    await act(async () => { within(item).getByRole('button', { name: 'Cancel' }).click() })
    expect(within(item).queryByLabelText('Edit proposed constraint')).toBeNull()
    expect(api.post).not.toHaveBeenCalled()
  })
})
