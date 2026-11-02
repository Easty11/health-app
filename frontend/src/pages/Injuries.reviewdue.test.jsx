// @vitest-environment jsdom
//
// Injuries page — the "Review due" group (Q191) and the Decline action on engine-default proposals.
// SURFACING ONLY: the sweep lists, the operator acts — Resolve (the existing resolve / retract route,
// basis required) or Keep (POST .../review, a typed date, never defaulted). A constraint proposal can
// be declined (the existing resolve route + basis); a finding proposal stays confirm-only.
// Fixtures are SYNTHETIC.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import Injuries from './Injuries'

const INJURIES = [
  { id: 1, type: 'injury', key: 'injury_part_a_left', active: true, source: 'api', added_at: '2025-11-01',
    expires_at: null, notes: null, superseded_by: null,
    value: { body_part: 'part a', side: 'left', signal_type: 'mechanical', restrictions: [] } },
]

const ENGINE_PROPOSAL = {
  id: 20, type: 'constraint', key: 'constraint_engine_injury_part_a_left_hinge', active: true, source: 'system',
  added_at: '2025-12-01',
  value: { scope: { tier: 'engine', region_keys: ['hinge'], side: 'left', text: 'acute-tissue (part a): part a → Hinge (engine default)' },
    kind: 'block', parent_key: 'injury_part_a_left', exit: { with_parent: true }, review_by: '2026-12-14',
    status: 'proposed', asserted_by: null },
}
const FINDING_PROPOSAL = {
  id: 21, type: 'finding', key: 'f_prop', active: true, source: 'chat', added_at: '2025-12-01',
  value: { statement: 'Synthetic finding A', domain: 'injury', status: 'proposed', parent_key: 'injury_part_a_left',
    as_of: '2025-12-01', basis: { text: 'x' }, derived_from_labs: false, asserted_by: null },
}

const DUE = {
  as_of: '2026-11-02', withheld_labs: 0,
  items: [
    { id: 30, type: 'constraint', key: 'c_due', what: 'BLOCK (advisory — not engine-enforced) — synthetic limit A',
      tags: ['review due'], parent_key: 'injury_part_a_left', authority: 'clinician', status: 'confirmed',
      review_by: '2026-10-26', exit_on_date: null, days_overdue: 7 },
    { id: 31, type: 'finding', key: 'f_due', what: 'Synthetic finding past review', tags: ['review due'],
      parent_key: null, authority: 'user', status: 'open', review_by: '2026-10-30', exit_on_date: null, days_overdue: 3 },
    { id: 32, type: 'constraint', key: 'c_gone', what: 'BLOCK (advisory — not engine-enforced) — limit of a resolved injury',
      tags: ['exit due'], parent_key: 'injury_gone', authority: 'user', status: 'confirmed',
      review_by: '2026-12-01', exit_on_date: null, days_overdue: null },
  ],
}

function routeGets({ proposals = [ENGINE_PROPOSAL, FINDING_PROPOSAL], due = DUE } = {}) {
  api.get.mockImplementation((url) => {
    if (url === '/knowledge/injuries') return Promise.resolve({ data: INJURIES })
    if (url === '/knowledge/proposals') return Promise.resolve({ data: proposals })
    if (url === '/knowledge/review-due') return due instanceof Error ? Promise.reject(due) : Promise.resolve({ data: due })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

async function renderView() {
  await act(async () => { render(<MemoryRouter><Injuries /></MemoryRouter>) })
  await waitFor(() => expect(screen.getByText('Part a (left)')).toBeTruthy())
}

const group = () => screen.getByRole('region', { name: 'Review due' })
const itemOf = (text) => within(group()).getByText(text, { exact: false }).closest('li')

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  routeGets()
})
afterEach(cleanup)

describe('the Review due group', () => {
  test('lists every due row with its tags, days overdue, authority and parent — above the injury cards', async () => {
    await renderView()
    const items = within(group()).getAllByRole('listitem')
    expect(items).toHaveLength(3)
    expect(within(itemOf('synthetic limit A')).getByText('review due')).toBeTruthy()
    expect(within(itemOf('synthetic limit A')).getByText(/7 days overdue · asserted by clinician · re: injury_part_a_left · review by 2026-10-26/)).toBeTruthy()
    expect(within(itemOf('Synthetic finding past review')).getByText(/3 days overdue/)).toBeTruthy()
    expect(within(itemOf('limit of a resolved injury')).getByText('exit due')).toBeTruthy()
    expect(within(itemOf('limit of a resolved injury')).getByText(/its parent injury is resolved/)).toBeTruthy()
    // above the injury cards
    const card = screen.getByText('Part a (left)').closest('.rounded-2xl')
    expect(group().compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  test('nothing due: no group at all', async () => {
    routeGets({ due: { as_of: '2026-11-02', items: [], withheld_labs: 0 } })
    await renderView()
    expect(screen.queryByRole('region', { name: 'Review due' })).toBeNull()
  })

  test('a failed sweep load says so and never hides the ledger', async () => {
    routeGets({ due: new Error('boom') })
    await renderView()
    expect(screen.getByText('Could not load the review sweep.')).toBeTruthy()
    expect(screen.getByText('Part a (left)')).toBeTruthy()
  })

  test('withheld lab-derived findings are counted, never described', async () => {
    routeGets({ due: { as_of: '2026-11-02', items: [], withheld_labs: 2 } })
    await renderView()
    expect(within(group()).getByText(/2 lab-derived findings past review/)).toBeTruthy()
  })
})

describe('Resolve', () => {
  test('needs a basis of 15+ characters and an authority, then POSTs the constraint resolve route', async () => {
    await renderView()
    const li = itemOf('synthetic limit A')
    await act(async () => { within(li).getByRole('button', { name: 'Resolve…' }).click() })
    const submit = within(li).getByRole('button', { name: 'Confirm resolution' })
    expect(submit.disabled).toBe(true)
    fireEvent.change(within(li).getByLabelText(/why is this no longer needed/), { target: { value: 'cleared at the 6-week review' } })
    expect(submit.disabled).toBe(true)                       // still no authority
    await act(async () => { within(li).getByRole('button', { name: 'Clinician' }).click() })
    expect(submit.disabled).toBe(false)
    api.post.mockResolvedValue({ data: {} })
    await act(async () => { submit.click() })
    expect(api.post).toHaveBeenCalledWith('/knowledge/constraints/30/resolve',
      { basis: 'cleared at the 6-week review', resolved_by: 'clinician' })
    expect(api.get).toHaveBeenCalledWith('/knowledge/review-due')           // reloaded
  })

  test('a finding is retracted through its own route', async () => {
    await renderView()
    const li = itemOf('Synthetic finding past review')
    await act(async () => { within(li).getByRole('button', { name: 'Resolve…' }).click() })
    fireEvent.change(within(li).getByLabelText(/why is this no longer needed/), { target: { value: 'superseded by the later scan' } })
    await act(async () => { within(li).getByRole('button', { name: 'User' }).click() })
    api.post.mockResolvedValue({ data: {} })
    await act(async () => { within(li).getByRole('button', { name: 'Confirm resolution' }).click() })
    expect(api.post).toHaveBeenCalledWith('/knowledge/findings/31/retract',
      { basis: 'superseded by the later scan', resolved_by: 'user' })
  })

  test('a refusal is shown verbatim and the typed basis is kept', async () => {
    await renderView()
    const li = itemOf('synthetic limit A')
    await act(async () => { within(li).getByRole('button', { name: 'Resolve…' }).click() })
    fireEvent.change(within(li).getByLabelText(/why is this no longer needed/), { target: { value: 'cleared at the 6-week review' } })
    await act(async () => { within(li).getByRole('button', { name: 'User' }).click() })
    api.post.mockRejectedValue({ response: { status: 422, data: { detail: 'SERVER SAYS NO' } } })
    await act(async () => { within(li).getByRole('button', { name: 'Confirm resolution' }).click() })
    expect(within(li).getByText('SERVER SAYS NO')).toBeTruthy()
    expect(within(li).getByLabelText(/why is this no longer needed/).value).toBe('cleared at the 6-week review')
  })
})

describe('Keep', () => {
  test('the date is typed, never defaulted; Keep stays disabled until it is in the future', async () => {
    await renderView()
    const li = itemOf('synthetic limit A')
    await act(async () => { within(li).getByRole('button', { name: /Keep — review again on/ }).click() })
    const input = within(li).getByLabelText('Review again on')
    expect(input.value).toBe('')
    const keep = within(li).getByRole('button', { name: 'Keep' })
    expect(keep.disabled).toBe(true)
    fireEvent.change(input, { target: { value: '2020-01-01' } })
    expect(keep.disabled).toBe(true)                                         // past
    fireEvent.change(input, { target: { value: '2999-01-01' } })
    expect(keep.disabled).toBe(false)
  })

  test('POSTs the review route for a constraint and for a finding, with only the date', async () => {
    await renderView()
    api.post.mockResolvedValue({ data: {} })
    for (const [text, url] of [['synthetic limit A', '/knowledge/constraints/30/review'],
                               ['Synthetic finding past review', '/knowledge/findings/31/review']]) {
      const li = itemOf(text)
      await act(async () => { within(li).getByRole('button', { name: /Keep — review again on/ }).click() })
      fireEvent.change(within(li).getByLabelText('Review again on'), { target: { value: '2999-01-01' } })
      await act(async () => { within(li).getByRole('button', { name: 'Keep' }).click() })
      expect(api.post).toHaveBeenCalledWith(url, { review_by: '2999-01-01' })
    }
  })

  test('a refusal is shown verbatim', async () => {
    await renderView()
    const li = itemOf('synthetic limit A')
    await act(async () => { within(li).getByRole('button', { name: /Keep — review again on/ }).click() })
    fireEvent.change(within(li).getByLabelText('Review again on'), { target: { value: '2999-01-01' } })
    api.post.mockRejectedValue({ response: { status: 409, data: { detail: 'Constraint entry is inactive' } } })
    await act(async () => { within(li).getByRole('button', { name: 'Keep' }).click() })
    expect(within(itemOf('synthetic limit A')).getByText('Constraint entry is inactive')).toBeTruthy()
  })
})

describe('Decline on a proposal', () => {
  const proposal = () => within(screen.getByText('Part a (left)').closest('.rounded-2xl'))
    .getByText(/engine default|regions: hinge/).closest('li')

  test('an engine-tier proposal renders as engine-enforced, with its side', async () => {
    await renderView()
    expect(within(proposal()).getByText(/BLOCK \(engine\) — regions: hinge, left side/)).toBeTruthy()
  })

  test('Decline needs a basis and an authority, then POSTs the constraint resolve route', async () => {
    await renderView()
    const li = proposal()
    await act(async () => { within(li).getByRole('button', { name: 'Decline…' }).click() })
    const submit = within(li).getByRole('button', { name: 'Decline proposal' })
    expect(submit.disabled).toBe(true)
    fireEvent.change(within(li).getByLabelText(/why decline this proposal/), {
      target: { value: 'running plan has cutting from day one' } })
    // the card also carries the Confirm tier buttons: the Decline form's own are the last pair
    await act(async () => { within(li).getAllByRole('button', { name: 'User' }).at(-1).click() })
    api.post.mockResolvedValue({ data: {} })
    routeGets({ proposals: [FINDING_PROPOSAL] })
    await act(async () => { submit.click() })
    expect(api.post).toHaveBeenCalledWith('/knowledge/constraints/20/resolve',
      { basis: 'running plan has cutting from day one', resolved_by: 'user' })
    await waitFor(() => expect(screen.queryByText(/regions: hinge/)).toBeNull())
  })

  test('a finding proposal has no Decline — it stays confirm-only', async () => {
    await renderView()
    const li = within(screen.getByText('Part a (left)').closest('.rounded-2xl')).getByText(/Synthetic finding A/).closest('li')
    expect(within(li).queryByRole('button', { name: 'Decline…' })).toBeNull()
    expect(within(li).getByRole('button', { name: 'Confirm proposal' })).toBeTruthy()
  })

  test('Cancel closes the form without posting', async () => {
    await renderView()
    const li = proposal()
    await act(async () => { within(li).getByRole('button', { name: 'Decline…' }).click() })
    await act(async () => { within(li).getByRole('button', { name: 'Cancel' }).click() })
    expect(within(li).queryByRole('button', { name: 'Decline proposal' })).toBeNull()
    expect(api.post).not.toHaveBeenCalled()
  })
})
