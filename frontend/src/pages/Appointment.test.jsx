// @vitest-environment jsdom
//
// The appointment brief page (#345). Gates:
//   - /appointments/:key renders ONLY its own surface (the brief sections, in the order the server
//     gave), never hub tiles; the hub renders no brief — the RouteSurfaces discipline (FEEDBACK §41);
//   - "Leave with" is pinned at the top; ticks are local-only (localStorage), never POSTed, and a
//     blocked storage never breaks the page;
//   - audience `clinician` drops the tick boxes and uses the fuller headings;
//   - the hub lists `planned` appointments as doorways to their briefs, and nothing when none.
// Fixture is SYNTHETIC (placeholder text) and shaped like the backend's brief.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { act } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import Appointment from './Appointment'
import { HEADINGS } from '../components/appointment/headings'
import Dashboard from './Dashboard'

const BRIEF = {
  key: 'appt_a', kind: 'follow_up', audience: 'operator', status: 'planned',
  scope: { parent_keys: ['injury_part_a_left'], missing_parent_keys: [], hops: 1 },
  limits: ['Scope is one hop.'],
  sections: [
    { module: 'header', clinician: 'Clinician A', practice: 'Practice A', at: '2026-01-15T13:00',
      date: '2026-01-15', time: '13:00', status: 'planned', kind: 'follow_up', audience: 'operator', detail: null },
    { module: 'leave_with', items: [{ id: 'a1', text: 'Ask one', priority: 1 }], total: 1 },
    { module: 'since', since: '2025-12-01', injuries: [], findings: [], constraints: [] },
    { module: 'changes_vs_history', since: '2025-12-01', injuries: [], findings: [
      { key: 'f1', type: 'finding', text: 'Statement v2', as_of: '2025-12-05', status: 'open',
        previous: [{ id: 3, statement: 'Statement v1', as_of: '2025-11-01' }] }] },
    { module: 'asks', authored: [
      { id: 'a1', text: 'Ask one', priority: 1, folded: [],
        resolves: { entry_key: null, note: null, row: null } }],
    derived: [{ rule: 'undated_exit', entry_key: 'c1', source: 'ledger',
      text: 'Confirm or date the exit condition: condition A',
      row: { key: 'c1', type: 'constraint', text: 'CAP — movement A', exit: 'when condition A', review_by: '2026-03-01' } }] },
    { module: 'current_constraints', items: [
      { key: 'c1', type: 'constraint', tier: 'advisory', kind: 'cap', text: 'CAP — movement A',
        exit: 'when condition A', review_by: '2026-03-01', authority: 'set by you' }] },
    { module: 'logistics', items: ['Bring report A'] },
  ],
}

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="/appointments/:key" element={<Appointment />} /></Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  api.get.mockImplementation((url) => {
    if (url === '/appointments/appt_a/brief') return Promise.resolve({ data: BRIEF })
    if (url === '/appointments/appt_c/brief') return Promise.resolve({ data: { ...BRIEF, audience: 'clinician' } })
    if (url === '/appointments') return Promise.resolve({ data: [] })
    return Promise.resolve({ data: {} })
  })
  api.post.mockResolvedValue({ data: {} })
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('/appointments/:key renders the brief and only the brief', () => {
  test('sections render in the server order with the operator headings', async () => {
    await act(async () => { renderAt('/appointments/appt_a') })
    await waitFor(() => expect(screen.getByText('Clinician A')).toBeTruthy())
    expect(api.get).toHaveBeenCalledWith('/appointments/appt_a/brief')
    const regions = screen.getAllByRole('region').map((r) => r.getAttribute('aria-label'))
    expect(regions).toEqual(['Appointment', 'Leave with', 'Since last visit', 'Changes since last visit',
      'Asks', 'Current constraints', 'Logistics'])
    // The flag-against-history pairing: the new statement beside the one it replaced.
    const changes = screen.getByRole('region', { name: 'Changes since last visit' })
    expect(within(changes).getByText(/Statement v2/)).toBeTruthy()
    expect(within(changes).getByText(/Statement v1/)).toBeTruthy()
    // A derived ask is labelled as coming from the ledger.
    expect(within(screen.getByRole('region', { name: 'Asks' })).getByText('from ledger')).toBeTruthy()
  })

  test('Leave with is pinned', async () => {
    await act(async () => { renderAt('/appointments/appt_a') })
    await waitFor(() => expect(screen.getByRole('region', { name: 'Leave with' })).toBeTruthy())
    expect(screen.getByRole('region', { name: 'Leave with' }).className).toContain('sticky')
  })

  test('no hub tiles bleed through', async () => {
    await act(async () => { renderAt('/appointments/appt_a') })
    await waitFor(() => expect(screen.getByText('Clinician A')).toBeTruthy())
    expect(screen.queryByText('Labs')).toBeNull()
    expect(screen.queryByText('Injuries')).toBeNull()
    expect(screen.queryByText('Morning check-in')).toBeNull()
  })

  test('a missing appointment says so', async () => {
    api.get.mockImplementation(() => Promise.reject({ response: { status: 404 } }))
    await act(async () => { renderAt('/appointments/nope') })
    await waitFor(() => expect(screen.getByText('No appointment with this key.')).toBeTruthy())
  })
})

describe('ticks are local-only', () => {
  test('a tick persists in localStorage and is never written back', async () => {
    await act(async () => { renderAt('/appointments/appt_a') })
    await waitFor(() => expect(screen.getByRole('region', { name: 'Leave with' })).toBeTruthy())
    const box = within(screen.getByRole('region', { name: 'Leave with' })).getByRole('checkbox')
    fireEvent.click(box)
    expect(box.checked).toBe(true)
    expect(JSON.parse(localStorage.getItem('appointment-ticks:appt_a'))).toEqual(['a1'])
    // The same ask is ticked in the full Asks list too.
    expect(within(screen.getByRole('region', { name: 'Asks' })).getAllByRole('checkbox')[0].checked).toBe(true)
    expect(api.post).not.toHaveBeenCalled()
  })

  test('blocked storage never breaks the page', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    await act(async () => { renderAt('/appointments/appt_a') })
    await waitFor(() => expect(screen.getByRole('region', { name: 'Leave with' })).toBeTruthy())
    const box = within(screen.getByRole('region', { name: 'Leave with' })).getByRole('checkbox')
    fireEvent.click(box)
    expect(box.checked).toBe(true)
  })
})

describe('audience clinician', () => {
  test('drops the tick boxes and uses the fuller headings', async () => {
    await act(async () => { renderAt('/appointments/appt_c') })
    await waitFor(() => expect(screen.getByText('Clinician A')).toBeTruthy())
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0)
    expect(screen.getByRole('region', { name: HEADINGS.leave_with.clinician })).toBeTruthy()
    expect(screen.queryByRole('region', { name: 'Leave with' })).toBeNull()
  })
})

describe('the hub doorway', () => {
  test('lists planned appointments, each linking to its brief', async () => {
    api.get.mockImplementation((url, opts) => {
      if (url === '/appointments') {
        expect(opts).toEqual({ params: { status: 'planned' } })
        return Promise.resolve({ data: [{ key: 'appt_a', clinician: 'Clinician A', at: '2026-01-15T13:00',
          kind: 'follow_up', status: 'planned' }] })
      }
      return Promise.resolve({ data: {} })
    })
    await act(async () => { render(<MemoryRouter><Dashboard /></MemoryRouter>) })
    await waitFor(() => expect(screen.getByRole('navigation', { name: 'Upcoming appointments' })).toBeTruthy())
    const links = screen.getAllByRole('link').filter((a) => a.getAttribute('href') === '/appointments/appt_a')
    expect(links).toHaveLength(1)
    expect(links[0].textContent).toContain('Clinician A')
    // The hub renders no brief.
    expect(screen.queryByRole('region', { name: 'Leave with' })).toBeNull()
  })

  test('renders nothing when none is planned', async () => {
    await act(async () => { render(<MemoryRouter><Dashboard /></MemoryRouter>) })
    await waitFor(() => expect(screen.getByText('Labs')).toBeTruthy())
    expect(screen.queryByRole('navigation', { name: 'Upcoming appointments' })).toBeNull()
  })
})
