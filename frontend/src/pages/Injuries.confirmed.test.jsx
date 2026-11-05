// @vitest-environment jsdom
//
// Injuries page — confirmed rows visible and resolvable at any time (GH#622). A CONFIRMED constraint
// (or an open / confirmed finding) from GET /knowledge/confirmed renders on its parent injury's card
// with its kind, scope, exit, review date and who set it; a row whose parent is not an active injury
// renders under "Attached to no active injury". Each carries Resolve — the SAME retire route and basis
// form the review sweep uses (basis and an authority required) — and no Keep: re-dating stays with
// the sweep, which is unchanged. Fixtures are SYNTHETIC.

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
  { id: 2, type: 'injury', key: 'injury_part_b_right', active: false, source: 'api', added_at: '2025-10-01',
    expires_at: null, notes: null, superseded_by: null,
    value: { body_part: 'part b', side: 'right', resolution: { basis: 'x', resolved_by: 'user', resolved_on: '2025-12-01' } } },
]

// Confirmed, parented to the active injury, NOT yet due (review a long way off): invisible before GH#622.
const PARENTED = {
  id: 40, type: 'constraint', key: 'constraint_part_a_cap', active: true, source: 'api', added_at: '2025-12-01',
  value: { scope: { tier: 'advisory', text: 'synthetic cap on movement A' }, kind: 'cap', parent_key: 'injury_part_a_left',
    exit: { on_condition: 'the clinician reviews it' }, review_by: '2999-01-01', status: 'confirmed',
    asserted_by: 'clinician', confirmed_on: '2025-12-02' },
}
// Confirmed with no parent at all.
const ORPHAN = {
  id: 41, type: 'constraint', key: 'constraint_general_block', active: true, source: 'api', added_at: '2025-12-01',
  value: { scope: { tier: 'engine', region_keys: ['hinge'], side: 'left' }, kind: 'block', parent_key: null,
    exit: { on_date: '2999-06-01' }, review_by: '2999-01-01', status: 'confirmed', asserted_by: 'user' },
}
// Confirmed under a RESOLVED injury (parent not active).
const PARENT_GONE = {
  id: 42, type: 'constraint', key: 'constraint_part_b_old', active: true, source: 'chat', added_at: '2025-12-01',
  value: { scope: { tier: 'advisory', text: 'synthetic limit of a resolved injury' }, kind: 'block', parent_key: 'injury_part_b_right',
    exit: { on_condition: 'never' }, review_by: '2999-01-01', status: 'confirmed', asserted_by: 'user' },
}
const FINDING = {
  id: 43, type: 'finding', key: 'finding_part_a', active: true, source: 'chat', added_at: '2025-12-01',
  value: { statement: 'Synthetic confirmed finding A', domain: 'injury', status: 'confirmed', parent_key: 'injury_part_a_left',
    as_of: '2025-12-01', basis: { text: 'x' }, derived_from_labs: false, asserted_by: 'user', confirmed_on: '2025-12-02' },
}

const DUE = {
  as_of: '2026-11-02', withheld_labs: 0,
  items: [
    { id: 30, type: 'constraint', key: 'c_due', what: 'BLOCK (advisory — not engine-enforced) — synthetic limit due',
      tags: ['review due'], parent_key: 'injury_part_a_left', authority: 'clinician', status: 'confirmed',
      review_by: '2026-10-26', exit_on_date: null, days_overdue: 7 },
  ],
}

function routeGets({ confirmed = [PARENTED, ORPHAN, PARENT_GONE, FINDING], due = DUE } = {}) {
  api.get.mockImplementation((url) => {
    if (url === '/knowledge/injuries') return Promise.resolve({ data: INJURIES })
    if (url === '/knowledge/proposals') return Promise.resolve({ data: [] })
    if (url === '/knowledge/review-due') return Promise.resolve({ data: due })
    if (url === '/knowledge/confirmed') return confirmed instanceof Error ? Promise.reject(confirmed) : Promise.resolve({ data: confirmed })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

async function renderView() {
  await act(async () => { render(<MemoryRouter><Injuries /></MemoryRouter>) })
  await waitFor(() => expect(screen.getByText('Part a (left)')).toBeTruthy())
}

const card = () => screen.getByText('Part a (left)').closest('.rounded-2xl')
const unattached = () => screen.getByRole('region', { name: 'Attached to no active injury' })
const rowOf = (scope, text) => within(scope).getByText(text, { exact: false }).closest('li')

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  routeGets()
})
afterEach(cleanup)

describe('confirmed rows are listed', () => {
  test('a confirmed row renders on its parent card with kind, scope, exit, review date and who set it', async () => {
    await renderView()
    const li = rowOf(card(), 'synthetic cap on movement A')
    expect(within(li).getByText('confirmed constraint')).toBeTruthy()
    expect(within(li).getByText(/CAP \(advisory\) — synthetic cap on movement A — ends when the clinician reviews it — review by 2999-01-01/)).toBeTruthy()
    expect(within(li).getByText(/set by your clinician · confirmed 2025-12-02 · re: injury_part_a_left/)).toBeTruthy()
    expect(within(li).getByText('constraint_part_a_cap')).toBeTruthy()
    // a confirmed finding sits there too, through the findings' own chip
    expect(within(rowOf(card(), 'Synthetic confirmed finding A')).getByText('confirmed finding')).toBeTruthy()
  })

  test('an unparented row, and one whose parent is resolved, render under "Attached to no active injury"', async () => {
    await renderView()
    expect(within(unattached()).getByText(/BLOCK \(engine\) — regions: hinge, left side/)).toBeTruthy()
    expect(within(unattached()).getByText(/synthetic limit of a resolved injury/)).toBeTruthy()
    expect(within(card()).queryByText(/regions: hinge/)).toBeNull()
    expect(within(card()).queryByText(/limit of a resolved injury/)).toBeNull()
    expect(within(rowOf(unattached(), 'regions: hinge')).getByText(/^set by you ·/)).toBeTruthy()
  })

  test('no confirmed rows: no list and no unattached section; a failed load says so and never hides the ledger', async () => {
    routeGets({ confirmed: [] })
    await renderView()
    expect(screen.queryByText('In force')).toBeNull()
    expect(screen.queryByRole('region', { name: 'Attached to no active injury' })).toBeNull()
    cleanup()
    routeGets({ confirmed: new Error('down') })
    await renderView()
    expect(screen.getByText('Could not load the confirmed constraints and findings.')).toBeTruthy()
    expect(screen.getByText('Part a (left)')).toBeTruthy()
  })
})

describe('Resolve on a confirmed row, before its review date', () => {
  test('needs a basis of 15+ characters and an authority, then POSTs the existing resolve route; the row leaves the list', async () => {
    await renderView()
    const li = rowOf(card(), 'synthetic cap on movement A')
    expect(within(li).queryByRole('button', { name: /Keep/ })).toBeNull()          // Keep stays with the sweep
    await act(async () => { within(li).getByRole('button', { name: 'Resolve…' }).click() })
    const submit = within(li).getByRole('button', { name: 'Confirm resolution' })
    expect(submit.disabled).toBe(true)                                              // no basis: refused client-side
    fireEvent.change(within(li).getByLabelText(/why is this no longer needed/), { target: { value: 'overtaken by the v2 cap the clinician set' } })
    expect(submit.disabled).toBe(true)                                              // still no authority
    await act(async () => { within(li).getByRole('button', { name: 'Clinician' }).click() })
    expect(submit.disabled).toBe(false)
    api.post.mockResolvedValue({ data: {} })
    routeGets({ confirmed: [ORPHAN, PARENT_GONE, FINDING] })                        // the server no longer lists it
    await act(async () => { submit.click() })
    expect(api.post).toHaveBeenCalledWith('/knowledge/constraints/40/resolve',
      { basis: 'overtaken by the v2 cap the clinician set', resolved_by: 'clinician' })
    expect(api.get).toHaveBeenCalledWith('/knowledge/confirmed')                    // reloaded
    await waitFor(() => expect(within(card()).queryByText(/synthetic cap on movement A/)).toBeNull())
  })

  test('a confirmed finding is retracted through its own route', async () => {
    await renderView()
    const li = rowOf(card(), 'Synthetic confirmed finding A')
    await act(async () => { within(li).getByRole('button', { name: 'Resolve…' }).click() })
    fireEvent.change(within(li).getByLabelText(/why is this no longer needed/), { target: { value: 'superseded by the later scan' } })
    await act(async () => { within(li).getByRole('button', { name: 'User' }).click() })
    api.post.mockResolvedValue({ data: {} })
    await act(async () => { within(li).getByRole('button', { name: 'Confirm resolution' }).click() })
    expect(api.post).toHaveBeenCalledWith('/knowledge/findings/43/retract',
      { basis: 'superseded by the later scan', resolved_by: 'user' })
  })

  test('a server refusal is shown verbatim and the typed basis is kept', async () => {
    await renderView()
    const li = rowOf(unattached(), 'regions: hinge')
    await act(async () => { within(li).getByRole('button', { name: 'Resolve…' }).click() })
    fireEvent.change(within(li).getByLabelText(/why is this no longer needed/), { target: { value: 'the general block is no longer wanted' } })
    await act(async () => { within(li).getByRole('button', { name: 'User' }).click() })
    api.post.mockRejectedValue({ response: { status: 422, data: { detail: 'basis is required — a resolution must state its grounds' } } })
    await act(async () => { within(li).getByRole('button', { name: 'Confirm resolution' }).click() })
    expect(within(li).getByText('basis is required — a resolution must state its grounds')).toBeTruthy()
    expect(within(li).getByLabelText(/why is this no longer needed/).value).toBe('the general block is no longer wanted')
  })
})

describe('the review sweep is unchanged', () => {
  test('a due row still renders in "Review due" with Resolve and Keep, and is not duplicated by the confirmed list', async () => {
    await renderView()
    const group = screen.getByRole('region', { name: 'Review due' })
    const due = within(group).getByText(/synthetic limit due/).closest('li')
    expect(within(due).getByRole('button', { name: 'Resolve…' })).toBeTruthy()
    expect(within(due).getByRole('button', { name: /Keep — review again on/ })).toBeTruthy()
    expect(within(group).queryByText(/synthetic cap on movement A/)).toBeNull()
    expect(api.get).toHaveBeenCalledWith('/knowledge/review-due')
  })
})
