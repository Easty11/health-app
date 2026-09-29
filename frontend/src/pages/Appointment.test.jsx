// @vitest-environment jsdom
//
// The appointment brief page (#345). Gates:
//   - /appointments/:key renders ONLY its own surface (the brief sections, in the order the server
//     gave), never hub tiles; the hub renders no brief — the RouteSurfaces discipline (FEEDBACK §41);
//   - "Leave with" is in normal flow (never sticky, never an inner scroll box) and is a compact
//     pointer list linking to Asks, with no tick boxes; ticks live only under Asks, are local-only
//     (localStorage), never POSTed, and a blocked storage never breaks the page;
//   - each row once, statements in full, "option → implication", and a quiet "linked row not
//     found" under an ask whose resolves row the brief could not show (#348);
//   - neutral framing (#349): every constraint/finding row shows who set it, voiced per audience;
//   - print mode: Print / Save PDF calls window.print; header, chat and scroll containers are
//     released for print; the screen layout is print:hidden and the dedicated print document
//     (#350, BriefPrint — its own tests) is print-only; no tick box reaches paper;
//   - audience `clinician` drops the tick boxes and uses the fuller headings;
//   - the hub lists `planned` appointments as doorways to their briefs, and nothing when none.
// Fixture is SYNTHETIC (placeholder text) and shaped like the backend's brief.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { act } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

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
    { module: 'leave_with', items: [{ id: 'a1', short: 'Ask one short', priority: 1 }], total: 1 },
    { module: 'since', since: '2025-12-01', injuries: [], findings: [], constraints: [
      { key: 'c2', type: 'constraint', text: 'CAP — movement B', change: 'confirmed', on: '2025-12-03' }] },
    { module: 'changes_vs_history', since: '2025-12-01', injuries: [], findings: [
      { key: 'f1', type: 'finding', text: 'Statement v2', as_of: '2025-12-05', status: 'open',
        asserted_by: 'user', authority: 'set by you',
        previous: [{ id: 3, statement: 'Statement v1', as_of: '2025-11-01', asserted_by: 'user', authority: 'set by you' }] }] },
    { module: 'asks', authored: [
      { id: 'a1', text: 'Ask one short. And the rest of ask one.', priority: 1, folded: [],
        resolves: { entry_key: null, note: null, row: null, unresolved: false } }],
    derived: [{ rule: 'undated_exit', entry_key: 'c1', source: 'ledger',
      text: 'Does this condition still apply? condition A',
      row: { key: 'c1', type: 'constraint', text: 'CAP — movement A', exit: 'when condition A', review_by: '2026-03-01',
        asserted_by: 'user', authority: 'set by you' } }] },
    { module: 'current_constraints', items: [
      { key: 'c1', type: 'constraint', tier: 'advisory', kind: 'cap', text: 'CAP — movement A',
        exit: 'when condition A', review_by: '2026-03-01', asserted_by: 'user', authority: 'set by you' },
      { key: 'c3', type: 'constraint', tier: 'advisory', kind: 'cap', text: 'CAP — movement C',
        exit: 'on 2026-04-01', review_by: '2026-03-01', asserted_by: 'clinician', authority: 'set by your clinician' }] },
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

  test('the header lists the scope by ledger key, flagging a missing one', async () => {
    api.get.mockImplementation(() => Promise.resolve({ data: { ...BRIEF, scope: {
      parent_keys: ['injury_part_a_left', 'injury_gone'], missing_parent_keys: ['injury_gone'], hops: 1 } } }))
    await act(async () => { renderAt('/appointments/appt_a') })
    const header = await screen.findByRole('region', { name: 'Appointment' })
    const scope = within(header).getByLabelText('Scope')
    expect(within(scope).getByText('injury_part_a_left').tagName).toBe('CODE')
    expect(within(scope).getByText('injury_gone (not found)')).toBeTruthy()
  })

  test('Leave with is in normal flow: not sticky, no inner scroll, at any width', async () => {
    await act(async () => { renderAt('/appointments/appt_a') })
    const lw = await screen.findByRole('region', { name: 'Leave with' })
    for (const el of [lw, ...lw.querySelectorAll('*')]) {
      expect(el.className).not.toMatch(/(^|\s|:)(sticky|fixed|overflow-(y-)?(auto|scroll)|max-h-)/)
    }
    // It is the first section after the header, in the page's own flow.
    const regions = screen.getAllByRole('region').map((r) => r.getAttribute('aria-label'))
    expect(regions.indexOf('Leave with')).toBe(1)
  })

  test('Leave with is a compact pointer list: short text, linked to its ask, no tick boxes', async () => {
    await act(async () => { renderAt('/appointments/appt_a') })
    const lw = await screen.findByRole('region', { name: 'Leave with' })
    expect(within(lw).queryAllByRole('checkbox')).toHaveLength(0)
    const link = within(lw).getByRole('link', { name: 'Ask one short' })
    expect(link.getAttribute('href')).toBe('#ask-a1')
    expect(within(lw).queryByText(/the rest of ask one/)).toBeNull()
    // The link target is the full ask under Asks, which carries the one tick box.
    const target = document.getElementById('ask-a1')
    expect(screen.getByRole('region', { name: 'Asks' }).contains(target)).toBe(true)
    expect(within(target).getByText(/the rest of ask one/)).toBeTruthy()
    expect(within(target).getAllByRole('checkbox')).toHaveLength(1)
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
    const asks = await screen.findByRole('region', { name: 'Asks' })
    const box = within(asks).getAllByRole('checkbox')[0]
    fireEvent.click(box)
    expect(box.checked).toBe(true)
    expect(JSON.parse(localStorage.getItem('appointment-ticks:appt_a'))).toEqual(['a1'])
    expect(api.post).not.toHaveBeenCalled()
  })

  test('blocked storage never breaks the page', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    await act(async () => { renderAt('/appointments/appt_a') })
    const asks = await screen.findByRole('region', { name: 'Asks' })
    const box = within(asks).getAllByRole('checkbox')[0]
    fireEvent.click(box)
    expect(box.checked).toBe(true)
  })
})

// Shaped like the first real brief (prod row 107: nine authored asks, ask 1 linked to a row the
// brief cannot show, options, a statement longer than the chat's 280-char cap). SYNTHETIC text.
const LONG = `Synthetic imaging statement, possible lesion at level A ${'x'.repeat(300)} END-OF-STATEMENT`
const NINE = Array.from({ length: 9 }, (_, i) => ({
  id: `q${i + 1}`, text: `Ask ${i + 1} full text. Detail for ask ${i + 1}.`, priority: i + 1, folded: [],
  resolves: i === 0
    ? { entry_key: 'constraint_gone_a', note: null, row: null, unresolved: true }
    : { entry_key: null, note: null, row: null, unresolved: false },
}))
const REAL = {
  ...BRIEF,
  sections: [
    BRIEF.sections[0],
    { module: 'leave_with', total: 9,
      items: NINE.slice(0, 5).map((a) => ({ id: a.id, short: `Ask ${a.priority} full text.`, priority: a.priority })) },
    { module: 'changes_vs_history', since: '2025-12-01', injuries: [
      { key: 'injury_cervical_spine', text: 'cervical spine', before: 'active', after: 'resolved 2025-12-20', on: '2025-12-20' }],
    findings: [{ key: 'f1', type: 'finding', text: LONG, as_of: '2025-12-05', status: 'open', previous: [] }] },
    { module: 'asks', authored: NINE, derived: [] },
    { module: 'options_prep', items: [{ ask_id: 'q2', text: 'Ask 2 full text.',
      options: [{ option: 'Cleared with conditions', implication: 'Technique change A' }] }] },
  ],
}

describe('first real use (row-107 shape)', () => {
  beforeEach(() => {
    api.get.mockImplementation(() => Promise.resolve({ data: REAL }))
  })

  test('each ask appears in full once; Leave with carries five pointers and a count', async () => {
    await act(async () => { renderAt('/appointments/appt_a') })
    const lw = await screen.findByRole('region', { name: 'Leave with' })
    expect(within(lw).getAllByRole('link').map((a) => a.getAttribute('href'))).toEqual(
      ['#ask-q1', '#ask-q2', '#ask-q3', '#ask-q4', '#ask-q5'])
    expect(within(lw).getByText('+ 4 more under Asks')).toBeTruthy()
    // On screen (the print document, print-only, carries its own copy — #350).
    const onScreen = within(screen.getByTestId('appointment-brief'))
    for (let i = 1; i <= 9; i += 1) {
      expect(onScreen.getAllByText(`Ask ${i} full text. Detail for ask ${i}.`)).toHaveLength(1)
    }
    expect(within(screen.getByRole('region', { name: 'Asks' })).getAllByRole('checkbox')).toHaveLength(9)
  })

  test('an ask whose linked row is not found says so, quietly, under that ask', async () => {
    await act(async () => { renderAt('/appointments/appt_a') })
    await screen.findByRole('region', { name: 'Asks' })
    const q1 = document.getElementById('ask-q1')
    expect(q1.textContent).toContain('linked row not found: constraint_gone_a')
    expect(document.getElementById('ask-q2').textContent).not.toContain('linked row not found')
  })

  test('statements render in full; options read "option → implication"', async () => {
    await act(async () => { renderAt('/appointments/appt_a') })
    const changes = await screen.findByRole('region', { name: 'Changes since last visit' })
    expect(within(changes).getByText(/END-OF-STATEMENT/)).toBeTruthy()
    expect(within(changes).getByText(/cervical spine/)).toBeTruthy()
    const opts = screen.getByRole('region', { name: 'If the answer is…' })
    expect(within(opts).getByText('Cleared with conditions → Technique change A')).toBeTruthy()
    expect(within(opts).queryByText(/then likely/)).toBeNull()
  })
})

describe('print mode', () => {
  test('Print / Save PDF calls the browser print', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    await act(async () => { renderAt('/appointments/appt_a') })
    fireEvent.click(await screen.findByRole('button', { name: 'Print / Save PDF' }))
    expect(print).toHaveBeenCalledTimes(1)
  })

  test('print shows only the print document: chrome and screen layout hidden, no tick boxes', async () => {
    api.get.mockImplementation(() => Promise.resolve({ data: REAL }))
    let view
    await act(async () => { view = renderAt('/appointments/appt_a') })
    const asks = await screen.findByRole('region', { name: 'Asks' })
    const { container } = view
    // App chrome: the header (and its Chat button) and the chat rail/sheet are print:hidden.
    const header = container.querySelector('header')
    expect(header.className).toMatch(/(^|\s)print:hidden(\s|$)/)
    expect(within(header).getByText(/Chat/)).toBeTruthy()
    expect(container.querySelector('aside').className).toMatch(/(^|\s)print:hidden(\s|$)/)
    expect(screen.getByRole('button', { name: 'Print / Save PDF' }).parentElement.className).toMatch(/print:hidden/)
    // The screen layout is print:hidden; the print document is print-only (#350).
    const brief = screen.getByTestId('appointment-brief')
    expect(brief.className).toMatch(/(^|\s)print:hidden(\s|$)/)
    const doc = screen.getByTestId('brief-print')
    expect(doc.className).toMatch(/(^|\s)hidden(\s|$)/)
    expect(doc.className).toMatch(/(^|\s)print:block(\s|$)/)
    // Every scroll container between the page and the print document is released for print.
    for (let el = doc.parentElement; el && el !== container; el = el.parentElement) {
      if (/overflow-(y-)?(auto|scroll|hidden)/.test(el.className)) expect(el.className).toMatch(/print:overflow-visible/)
      if (/(^|\s)(md:)?h-screen/.test(el.className)) expect(el.className).toMatch(/print:h-auto/)
    }
    for (const el of doc.querySelectorAll('*')) {
      expect(el.className?.toString() ?? '').not.toMatch(/(^|\s)(sticky|max-h-\S+|overflow-(y-)?(auto|scroll))(\s|$)/)
    }
    // Ticks stay on screen: no tick box or print square in the print document, even when ticked.
    fireEvent.click(within(asks).getAllByRole('checkbox')[0])
    expect(asks.querySelectorAll('li[id^="ask-"]')).toHaveLength(9)
    expect(doc.querySelectorAll('input, [data-print-tick]')).toHaveLength(0)
    // The screen layout keeps its black-on-white print rule (#348); the print document is exempt.
    expect(brief.className).toMatch(/brief-print/)
    expect(brief.contains(doc)).toBe(false)
    const indexCss = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'index.css'), 'utf8')
    expect(indexCss).toMatch(/@media print[\s\S]*\.brief-print[\s\S]*color: #000[\s\S]*background: #fff/)
  })
})

describe('neutral framing: authority is visible on every row', () => {
  test('linked, derived, current and changed rows each say who set them', async () => {
    await act(async () => { renderAt('/appointments/appt_a') })
    const asks = await screen.findByRole('region', { name: 'Asks' })
    const derived = within(asks).getByText('Does this condition still apply? condition A').closest('li')
    expect(within(derived).getByText('set by you')).toBeTruthy()
    const current = screen.getByRole('region', { name: 'Current constraints' })
    const mine = within(current).getByText('CAP — movement A').closest('li')
    const theirs = within(current).getByText('CAP — movement C').closest('li')
    expect(within(mine).getByText('set by you')).toBeTruthy()
    expect(within(theirs).getByText('set by your clinician')).toBeTruthy()
    expect(within(mine).queryByText(/clinician/)).toBeNull()
    const changes = screen.getByRole('region', { name: 'Changes since last visit' })
    expect(within(changes).getAllByText('set by you')).toHaveLength(2)
    const since = screen.getByRole('region', { name: 'Since last visit' })
    expect(within(since).queryAllByText(/set by/)).toHaveLength(0) // fixture row carries no asserted_by
  })

  test('the clinician audience reads the operator in the first person, never "set by you"', async () => {
    await act(async () => { renderAt('/appointments/appt_c') })
    const current = await screen.findByRole('region', { name: HEADINGS.current_constraints.clinician })
    expect(within(within(current).getByText('CAP — movement A').closest('li')).getByText('set by me')).toBeTruthy()
    expect(within(within(current).getByText('CAP — movement C').closest('li')).getByText('set by my clinician')).toBeTruthy()
    expect(screen.queryAllByText('set by you')).toHaveLength(0)
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
    await waitFor(() => expect(screen.getByRole('navigation', { name: 'Appointments' })).toBeTruthy())
    const links = screen.getAllByRole('link').filter((a) => a.getAttribute('href') === '/appointments/appt_a')
    expect(links).toHaveLength(1)
    expect(links[0].textContent).toContain('Clinician A')
    // The hub renders no brief.
    expect(screen.queryByRole('region', { name: 'Leave with' })).toBeNull()
  })

  test('a planned appointment whose time has passed reads "Awaiting report", a future one does not', async () => {
    api.get.mockImplementation((url) => (url === '/appointments'
      ? Promise.resolve({ data: [
        { key: 'appt_past', clinician: 'Clinician P', at: '2020-01-01T09:00', kind: 'follow_up', status: 'planned' },
        { key: 'appt_next', clinician: 'Clinician N', at: '2099-01-01T09:00', kind: 'follow_up', status: 'planned' },
      ] })
      : Promise.resolve({ data: {} })))
    await act(async () => { render(<MemoryRouter><Dashboard /></MemoryRouter>) })
    const nav = await screen.findByRole('navigation', { name: 'Appointments' })
    const past = within(nav).getByText(/Clinician P/).closest('li')
    const next = within(nav).getByText(/Clinician N/).closest('li')
    expect(within(past).getByText(/^Awaiting report · \d+ days$/)).toBeTruthy()
    expect(within(next).queryByText(/Awaiting report/)).toBeNull()
    // Still a doorway to its brief — surfacing only, no status change.
    expect(within(past).getByRole('link').getAttribute('href')).toBe('/appointments/appt_past')
    expect(api.post).not.toHaveBeenCalled()
  })

  test('renders nothing when none is planned', async () => {
    await act(async () => { render(<MemoryRouter><Dashboard /></MemoryRouter>) })
    await waitFor(() => expect(screen.getByText('Labs')).toBeTruthy())
    expect(screen.queryByRole('navigation', { name: 'Appointments' })).toBeNull()
  })
})
