// @vitest-environment jsdom
//
// Injuries page (#346): each injury card shows its LEDGER KEY (the value an appointment's
// scope.parent_keys takes — the #345 close-out claimed this page showed it when it did not), and
// PROPOSED constraints / findings are listed under their parent with one Confirm action each.
// Fixtures are SYNTHETIC (placeholder parts and text).

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react'
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

const PROPOSALS = [
  { id: 10, type: 'constraint', key: 'c_prop', active: true, source: 'chat', added_at: '2025-12-01',
    value: { scope: { tier: 'advisory', text: 'cap on movement A' }, kind: 'cap', parent_key: 'injury_part_a_left',
      exit: { on_condition: 'condition A' }, review_by: '2026-01-15', status: 'proposed', asserted_by: null } },
  { id: 11, type: 'finding', key: 'f_prop', active: true, source: 'chat', added_at: '2025-12-01',
    value: { statement: 'Synthetic finding A', domain: 'injury', status: 'proposed', parent_key: 'injury_part_a_left',
      as_of: '2025-12-01', basis: { text: 'x' }, derived_from_labs: false, asserted_by: null } },
  { id: 12, type: 'finding', key: 'f_orphan', active: true, source: 'chat', added_at: '2025-12-01',
    value: { statement: 'Orphan finding B', domain: 'training', status: 'proposed', parent_key: null,
      as_of: '2025-12-02', basis: { text: 'x' }, derived_from_labs: false, asserted_by: null } },
]

function routeGets(proposals = PROPOSALS) {
  api.get.mockImplementation((url) => {
    if (url === '/knowledge/injuries') return Promise.resolve({ data: INJURIES })
    if (url === '/knowledge/proposals') return Promise.resolve({ data: proposals })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

async function renderView() {
  await act(async () => { render(<MemoryRouter><Injuries /></MemoryRouter>) })
  await waitFor(() => expect(screen.getByText('Part a (left)')).toBeTruthy())
}

const card = () => screen.getByText('Part a (left)').closest('.rounded-2xl')

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  routeGets()
})
afterEach(cleanup)

describe('the ledger key is on the card', () => {
  test('active card shows its key, monospace and copyable', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    await renderView()
    const code = within(card()).getByText('injury_part_a_left')
    expect(code.tagName).toBe('CODE')
    expect(code.className).toContain('font-mono')
    await act(async () => { within(card()).getByRole('button', { name: 'Copy injury_part_a_left' }).click() })
    expect(writeText).toHaveBeenCalledWith('injury_part_a_left')
  })

  test('history rows show their key too', async () => {
    await renderView()
    await act(async () => { screen.getByText(/Show history/).click() })
    expect(screen.getByText('injury_part_b_right').tagName).toBe('CODE')
  })
})

describe('proposals are confirmable under their parent', () => {
  test('both proposals sit on the parent card; the orphan is listed separately', async () => {
    await renderView()
    expect(within(card()).getByText(/cap on movement A/)).toBeTruthy()
    expect(within(card()).getByText(/Synthetic finding A/)).toBeTruthy()
    expect(within(card()).queryByText(/Orphan finding B/)).toBeNull()
    expect(within(screen.getByRole('region', { name: 'Other proposals' })).getByText(/Orphan finding B/)).toBeTruthy()
  })

  test('Confirm needs an authority tier, then POSTs the typed /confirm route and reloads', async () => {
    await renderView()
    const item = within(card()).getByText(/cap on movement A/).closest('li')
    const btn = within(item).getByRole('button', { name: 'Confirm proposal' })
    expect(btn.disabled).toBe(true)
    await act(async () => { within(item).getByRole('button', { name: 'Clinician' }).click() })
    expect(btn.disabled).toBe(false)
    api.post.mockResolvedValue({ data: {} })
    routeGets(PROPOSALS.filter((p) => p.id !== 10))
    await act(async () => { btn.click() })
    expect(api.post).toHaveBeenCalledWith('/knowledge/constraints/10/confirm', { asserted_by: 'clinician' })
    await waitFor(() => expect(within(card()).queryByText(/cap on movement A/)).toBeNull())
  })

  test('a finding confirms through the findings route', async () => {
    await renderView()
    const item = within(card()).getByText(/Synthetic finding A/).closest('li')
    await act(async () => { within(item).getByRole('button', { name: 'User' }).click() })
    api.post.mockResolvedValue({ data: {} })
    await act(async () => { within(item).getByRole('button', { name: 'Confirm proposal' }).click() })
    expect(api.post).toHaveBeenCalledWith('/knowledge/findings/11/confirm', { asserted_by: 'user' })
  })

  test('a refusal is shown verbatim', async () => {
    await renderView()
    const item = within(card()).getByText(/cap on movement A/).closest('li')
    await act(async () => { within(item).getByRole('button', { name: 'User' }).click() })
    api.post.mockRejectedValue({ response: { status: 422, data: { detail: 'SERVER SAYS NO' } } })
    await act(async () => { within(item).getByRole('button', { name: 'Confirm proposal' }).click() })
    expect(within(item).getByText('SERVER SAYS NO')).toBeTruthy()
  })

  test('no proposals: no confirm affordance anywhere; a failed proposals load never hides the ledger', async () => {
    routeGets([])
    await renderView()
    expect(screen.queryByRole('button', { name: 'Confirm proposal' })).toBeNull()
    cleanup()
    api.get.mockImplementation((url) => (url === '/knowledge/injuries'
      ? Promise.resolve({ data: INJURIES }) : Promise.reject(new Error('down'))))
    await renderView()
    expect(screen.getByText('Could not load proposals awaiting confirmation.')).toBeTruthy()
  })
})
