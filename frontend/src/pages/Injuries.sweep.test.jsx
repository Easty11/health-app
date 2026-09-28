// @vitest-environment jsdom
//
// The clearance sweep on /injuries (G2): a successful resolve runs the sweep and renders its hits
// with each store's EXISTING action; "none" reads "manual"; resolved history rows carry "Sweep
// again". No new write action: the only thing the card can do is re-read.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

import api from '../api'
import Injuries from './Injuries'

const ROWS = [
  { id: 29, type: 'injury', key: 'injury_hamstring_right', source: 'system', added_at: '2026-07-13',
    expires_at: null, active: true, notes: null, superseded_by: null,
    value: { body_part: 'hamstring', side: 'right', signal_type: 'mechanical',
      restrictions: ['striding', 'sprinting', 'static end-range hamstring stretching'] } },
  { id: 18, type: 'injury', key: 'injury_hamstring_left', source: 'system', added_at: '2026-06-22',
    expires_at: null, active: false, notes: null, superseded_by: null,
    value: { body_part: 'hamstring', side: 'left', signal_type: 'mechanical',
      resolution: { resolved_on: '2026-08-19', basis: 'Velocity provocation cleared', resolved_by: 'user' } } },
  { id: 17, type: 'injury', key: 'injury_shoulder_right', source: 'system', added_at: '2026-06-22',
    expires_at: null, active: false, notes: null, superseded_by: 78,
    value: { body_part: 'shoulder', side: 'right', signal_type: 'mechanical' } },
  { id: 78, type: 'injury', key: 'injury_shoulder_right', source: 'api', added_at: '2026-08-20',
    expires_at: null, active: true, notes: null, superseded_by: null,
    value: { body_part: 'shoulder', side: 'right', signal_type: 'mechanical' } },
]

// Shaped as GET /knowledge/injuries/{id}/sweep returns it.
const SWEEP = {
  entry_id: 29, key: 'injury_hamstring_right', body_part: 'hamstring', side: 'right', active: false,
  terms: ['hamstring', 'semimembranosus', 'semitendinosus', 'biceps femoris'],
  restriction_terms: ['strid', 'sprint', 'stretch'],
  restriction_audit: [
    { restriction: 'sprinting', match_stems: ['sprint'], covered_by_basis: false, rehomed_to: [],
      rehomed_to_constraints: [], status: 'orphan', suggested_action: 'propose as constraint',
      dies_with_parent: [{ entry_id: 201, key: 'constraint_no_sprinting', kind: 'block', tier: 'advisory',
        parent_key: 'injury_hamstring_right' }] },
    { restriction: 'static stretching', match_stems: ['static'], covered_by_basis: false, rehomed_to: [],
      rehomed_to_constraints: [], dies_with_parent: [], status: 'orphan',
      suggested_action: 're-parent or resolve — constraint keeps enforcing',
      parent_resolved_survives: [{ entry_id: 203, key: 'constraint_no_static', kind: 'block', tier: 'advisory',
        parent_key: 'injury_hamstring_right' }] },
    { restriction: 'striding', match_stems: ['strid'], covered_by_basis: false, rehomed_to: [],
      rehomed_to_constraints: [{ entry_id: 202, key: 'constraint_no_striding', kind: 'block', tier: 'advisory',
        parent_key: null }], dies_with_parent: [], status: 'rehomed', suggested_action: null },
    { restriction: 'static end-range hamstring stretching', match_stems: ['stretch'], covered_by_basis: false,
      status: 'rehomed',
      rehomed_to: [{ entry_id: 94, key: 'injury_lumbar_spine', body_part: 'lumbar', signal_type: 'neural',
        radicular_warning: { signal_type: 'neural', fires: ['hinge'],
          message: "'injury_lumbar_spine' is a spinal row typed 'neural': RADICULAR-WARNING-TEXT" } }] },
  ],
  restrictions_note: 'Restriction strings are chat-rendered only.',
  stores: [
    { store: 'user_knowledge', status: 'searched', hits: 1 },
    { store: 'user_knowledge_entries', status: 'searched', hits: 0 },
    { store: 'hevy_routines', status: 'searched', hits: 1 },
  ],
  hits: [
    { store: 'user_knowledge', row_id: 2, line_index: 0, location: 'category: Injury History',
      snippet: 'Tweaked hamstring during a sprint at rugby training on 04 June 2026',
      matched_terms: ['hamstring'], restriction_terms: ['sprint'], sides_mentioned: [],
      opposite_side: false, marked_resolved: false,
      other_injuries: [{ entry_id: 94, key: 'injury_lumbar_spine', active: true, matched_terms: ['lumbar'] }],
      reaches_context: 'yes', action: 'edit', action_route: 'PUT /knowledge/2' },
    { store: 'hevy_routines', row_id: 'rt-1', line_index: 0, location: "routine 'Lower A' · Nordic Curl · notes",
      snippet: 'Right hamstring: stop at 7 RPE', matched_terms: ['hamstring'], restriction_terms: [],
      sides_mentioned: ['right'], opposite_side: false, marked_resolved: false, other_injuries: [],
      reaches_context: 'conditional', action: 'none', action_route: null },
  ],
  manual_checklist: [
    { store: 'project_knowledge_files', where: 'Claude project knowledge', why: 'Outside the app.' },
    { store: 'claude_memory', where: 'Claude memory', why: 'Outside the app.' },
    { store: 'browser_chat_history', where: 'The in-app chat panel', why: 'Browser only.' },
  ],
}

function routeGets({ sweep = SWEEP } = {}) {
  api.get.mockImplementation((url) => {
    if (url === '/knowledge/injuries') return Promise.resolve({ data: ROWS })
    if (/^\/knowledge\/injuries\/\d+\/sweep$/.test(url)) {
      return sweep instanceof Error ? Promise.reject(sweep) : Promise.resolve({ data: sweep })
    }
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

async function renderView() {
  await act(async () => { render(<MemoryRouter><Injuries /></MemoryRouter>) })
  await waitFor(() => expect(screen.getByText('Hamstring (right)')).toBeTruthy())
}

async function resolveHamstring({ fail = false } = {}) {
  const c = within(screen.getByText('Hamstring (right)').closest('.rounded-2xl'))
  await act(async () => { c.getByRole('button', { name: /resolve…/i }).click() })
  await act(async () => {
    fireEvent.change(c.getByPlaceholderText(/state the grounds/i),
      { target: { value: 'no issues running due to the tear' } })
  })
  await act(async () => { c.getByRole('button', { name: 'User' }).click() })
  if (fail) api.post.mockRejectedValue({ response: { status: 500 } })
  else api.post.mockResolvedValue({ data: {} })
  await act(async () => { c.getByRole('button', { name: /confirm resolution/i }).click() })
}

function sweepCalls() {
  return api.get.mock.calls.map(([url]) => url).filter((u) => u.endsWith('/sweep'))
}

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  routeGets()
})
afterEach(cleanup)


describe('resolve → sweep', () => {
  test('a successful resolve runs the sweep for that row and renders its hits', async () => {
    await renderView()
    expect(sweepCalls()).toEqual([])
    await resolveHamstring()
    expect(sweepCalls()).toEqual(['/knowledge/injuries/29/sweep'])

    const card = within(await screen.findByRole('region', { name: /clearance sweep/i }))
    expect(card.getByText(/Clearance sweep — Hamstring \(right\) · #29/)).toBeTruthy()
    expect(card.getAllByTestId('sweep-hit')).toHaveLength(2)
    expect(card.getByText(/Tweaked hamstring during a sprint/)).toBeTruthy()
    // the stale-order signal and the other-injury label, as the server computed them
    expect(card.getByText('restriction terms present: sprint')).toBeTruthy()
    expect(card.getByText(/also names #94 injury_lumbar_spine \(active\)/)).toBeTruthy()
  })

  test('the existing action is shown: edit links to Settings; there is no new write control', async () => {
    await renderView()
    await resolveHamstring()
    const card = within(await screen.findByRole('region', { name: /clearance sweep/i }))
    const edit = card.getByRole('link', { name: /edit in settings/i })
    expect(edit.getAttribute('href')).toBe('/settings')
    // The card's only buttons re-read or close — nothing writes.
    const labels = card.getAllByRole('button').map((b) => b.textContent)
    expect(labels.sort()).toEqual(['Close', 'Sweep again'])
    expect(api.post).toHaveBeenCalledTimes(1)   // the resolve itself, nothing after
  })

  test('the restriction audit shows orphans and a radicular warning', async () => {
    await renderView()
    await resolveHamstring()
    const card = within(await screen.findByRole('region', { name: /clearance sweep/i }))
    expect(card.getAllByTestId('sweep-audit')).toHaveLength(4)
    expect(card.getAllByText(/orphan — leaves chat context/)).toHaveLength(2)
    expect(card.getByText(/re-homed → #94 injury_lumbar_spine \(neural\)/)).toBeTruthy()
    expect(card.getByText(/RADICULAR-WARNING-TEXT/)).toBeTruthy()
  })

  test('constraints: a surviving one re-homes; one parented to this injury is named and the orphan stays', async () => {
    await renderView()
    await resolveHamstring()
    const card = within(await screen.findByRole('region', { name: /clearance sweep/i }))
    expect(card.getByText(/re-homed → constraint #202 constraint_no_striding \(advisory\)/)).toBeTruthy()
    expect(card.getByText(/constraint #201 constraint_no_sprinting ends with this injury/)).toBeTruthy()
    expect(card.getByText('suggested: propose as constraint (manual)')).toBeTruthy()
    // with_parent:false, parented here — it survives the resolution: its own label (G5 ruling 1).
    expect(card.getByText(/constraint #203 constraint_no_static outlives this injury/)).toBeTruthy()
    expect(card.getByText('suggested: re-parent or resolve — constraint keeps enforcing (manual)')).toBeTruthy()
    // Still surfacing only: no new control.
    expect(card.getAllByRole('button').map((b) => b.textContent).sort()).toEqual(['Close', 'Sweep again'])
  })

  test('a failed resolve runs no sweep', async () => {
    await renderView()
    await resolveHamstring({ fail: true })
    await waitFor(() => expect(screen.getByText(/could not resolve/i)).toBeTruthy())
    expect(sweepCalls()).toEqual([])
    expect(screen.queryByRole('region', { name: /clearance sweep/i })).toBeNull()
  })

  test('a failed sweep says so, and Sweep again retries', async () => {
    routeGets({ sweep: new Error('boom') })
    await renderView()
    await resolveHamstring()
    const card = within(await screen.findByRole('region', { name: /clearance sweep/i }))
    await waitFor(() => expect(card.getByText(/could not run the sweep/i)).toBeTruthy())
    routeGets()
    await act(async () => { card.getByRole('button', { name: 'Sweep again' }).click() })
    await waitFor(() => expect(card.getAllByTestId('sweep-hit')).toHaveLength(2))
    expect(sweepCalls()).toEqual(['/knowledge/injuries/29/sweep', '/knowledge/injuries/29/sweep'])
  })
})


describe('"manual" rows', () => {
  test('a hit with action none reads manual and is counted in the report', async () => {
    await renderView()
    await resolveHamstring()
    const card = within(await screen.findByRole('region', { name: /clearance sweep/i }))
    const hevy = card.getByText('Right hamstring: stop at 7 RPE').closest('[data-testid="sweep-hit"]')
    expect(within(hevy).getByText('manual')).toBeTruthy()
    expect(within(hevy).queryByRole('link')).toBeNull()
    expect(card.getByText(/2 copies found · 1 manual/)).toBeTruthy()
  })

  test('every out-of-app checklist item is listed as manual', async () => {
    await renderView()
    await resolveHamstring()
    const card = within(await screen.findByRole('region', { name: /clearance sweep/i }))
    const items = card.getAllByTestId('sweep-manual')
    expect(items).toHaveLength(3)
    for (const li of items) expect(within(li).getByText('manual')).toBeTruthy()
    expect(card.getByText(/in-app chat panel/)).toBeTruthy()
  })
})


describe('"Sweep again" on resolved history rows', () => {
  test('a resolved row carries Sweep again; a superseded row does not', async () => {
    await renderView()
    await act(async () => { screen.getByRole('button', { name: /show history/i }).click() })
    const resolved = screen.getByText('Hamstring (left)').closest('.rounded-xl')
    const superseded = screen.getByText('superseded → #78').closest('.rounded-xl')
    expect(within(resolved).getByRole('button', { name: 'Sweep again' })).toBeTruthy()
    expect(within(superseded).queryByRole('button', { name: 'Sweep again' })).toBeNull()
  })

  test('it sweeps that row by id and opens the card', async () => {
    await renderView()
    await act(async () => { screen.getByRole('button', { name: /show history/i }).click() })
    const resolved = screen.getByText('Hamstring (left)').closest('.rounded-xl')
    await act(async () => { within(resolved).getByRole('button', { name: 'Sweep again' }).click() })
    expect(sweepCalls()).toEqual(['/knowledge/injuries/18/sweep'])
    const card = within(await screen.findByRole('region', { name: /clearance sweep/i }))
    expect(card.getByText(/Hamstring \(left\) · #18/)).toBeTruthy()
    await act(async () => { card.getByRole('button', { name: 'Close' }).click() })
    expect(screen.queryByRole('region', { name: /clearance sweep/i })).toBeNull()
  })
})
