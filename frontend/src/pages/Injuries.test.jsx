// @vitest-environment jsdom
//
// The /injuries operator view, tested where the properties actually live: the FETCH, the CHAIN
// WALK, and the RESOLVE WIRING. The assertions track the brief's acceptance criteria, not cosmetics.
//
// The fixtures are the live prod rows for user 1 (#brief §1.2): five active, four inactive, one of
// each terminal state (id 18 resolved, ids 16/17/30 superseded). Dates are real so the chain walk
// is exercised against a row (id 77) whose raw added_at is WRONG and whose ancestor is right.

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

import api from '../api'
import Injuries from './Injuries'

// Prod ledger, user 1. value shapes are representative; only the fields the view reads matter.
const ROWS = [
  { id: 76, type: 'injury', key: 'injury_calf_left', source: 'api', added_at: '2026-08-20',
    expires_at: null, active: true, notes: null, superseded_by: null,
    value: { body_part: 'calf', side: 'left', signal_type: 'mechanical' } },
  { id: 16, type: 'injury', key: 'injury_finger_left', source: 'system', added_at: '2026-06-22',
    expires_at: null, active: false, notes: null, superseded_by: 77,
    value: { body_part: 'finger', side: 'left', signal_type: 'mechanical' } },
  { id: 77, type: 'injury', key: 'injury_finger_left', source: 'api', added_at: '2026-08-20',
    expires_at: null, active: true, notes: null, superseded_by: null,
    value: { body_part: 'finger', side: 'left', signal_type: 'mechanical' } },
  { id: 18, type: 'injury', key: 'injury_hamstring_left', source: 'system', added_at: '2026-06-22',
    expires_at: null, active: false, notes: null, superseded_by: null,
    value: { body_part: 'hamstring', side: 'left', signal_type: 'mechanical',
      resolution: { resolved_on: '2026-08-01', basis: 'full ROM, no pain on load for 6 weeks', resolved_by: 'user' } } },
  { id: 29, type: 'injury', key: 'injury_hamstring_right', source: 'system', added_at: '2026-07-13',
    expires_at: null, active: true, notes: null, superseded_by: null,
    value: { body_part: 'hamstring', side: 'right', signal_type: 'mechanical' } },
  { id: 30, type: 'injury', key: 'injury_pes_anserine_left', source: 'system', added_at: '2026-07-13',
    expires_at: null, active: false, notes: null, superseded_by: 75,
    value: { body_part: 'pes anserine', side: 'left', signal_type: 'mechanical' } },
  { id: 75, type: 'injury', key: 'injury_pes_anserine_left', source: 'api', added_at: '2026-08-20',
    expires_at: null, active: true, notes: null, superseded_by: null,
    value: { body_part: 'pes anserine', side: 'left', signal_type: 'mechanical' } },
  { id: 17, type: 'injury', key: 'injury_shoulder_right', source: 'system', added_at: '2026-06-22',
    expires_at: null, active: false, notes: null, superseded_by: 78,
    value: { body_part: 'shoulder', side: 'right', signal_type: 'mechanical' } },
  { id: 78, type: 'injury', key: 'injury_shoulder_right', source: 'api', added_at: '2026-08-20',
    expires_at: null, active: true, notes: null, superseded_by: null,
    value: { body_part: 'shoulder', side: 'right', signal_type: 'mechanical' } },
]

async function renderView(rows = ROWS) {
  api.get.mockResolvedValue({ data: rows })
  await act(async () => { render(<MemoryRouter><Injuries /></MemoryRouter>) })
  await waitFor(() => expect(screen.getByText('Finger (left)')).toBeTruthy())
}

// The active card is the nearest ancestor carrying rounded-2xl; the inner readouts are rounded-lg.
function card(title) {
  return screen.getByText(title).closest('.rounded-2xl')
}

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
})
afterEach(cleanup)


describe('the load is a single include_resolved fetch (AC#2)', () => {
  test('exactly one request, carrying include_resolved=true', async () => {
    await renderView()
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(api.get).toHaveBeenCalledWith('/knowledge/injuries', { params: { include_resolved: true } })
  })
})


describe('on record since is the chain-earliest added_at, never the raw row date (AC#4)', () => {
  // Dates render via toLocaleDateString, so the month/day ORDER is the runner's locale (Node
  // defaults to en-US → "Jun 22, 2026"). Assert on the parts that carry the claim — the ancestor's
  // month/year, and the absence of the row's own wrong month — not on a fixed field order.
  test('finger (id 77) shows its ancestor June date, not its own August date', async () => {
    await renderView()
    const c = within(card('Finger (left)'))
    expect(c.getByText(/Jun\b.*2026|2026.*Jun\b/)).toBeTruthy()
    expect(c.queryByText(/Aug/)).toBeNull()
  })

  test('a row with no ancestor (calf) keeps its own added_at', async () => {
    await renderView()
    expect(within(card('Calf (left)')).getByText(/Aug\b.*2026|2026.*Aug\b/)).toBeTruthy()
  })

  test('no date carries an onset or age label', async () => {
    await renderView()
    // The clarifier "record age floor — not injury onset" denies both labels; what must be absent
    // is a bare "Onset"/"Age" LABEL on a date, so anchor the match.
    expect(screen.queryByText(/^onset$/i)).toBeNull()
    expect(screen.queryByText(/^age$/i)).toBeNull()
    expect(screen.getAllByText(/On record since/)).toHaveLength(5) // one per active row
  })
})


describe('each active row states its effect (AC#3)', () => {
  test('contraindication, soreness key, on-record-since and source all show', async () => {
    await renderView()
    const c = within(card('Finger (left)'))
    expect(c.getByText(/Contraindicates training regions/)).toBeTruthy()
    // The SORENESS key derived from value (finger_left), not the entry key (injury_finger_left).
    expect(c.getByText('finger_left')).toBeTruthy()
    expect(c.getByText(/On record since/)).toBeTruthy()
    expect(c.getByText(/· api/)).toBeTruthy()
  })
})


describe('resolve is gated on both a floored basis and an authority (AC#6)', () => {
  async function openResolve(title) {
    const c = within(card(title))
    await act(async () => { c.getByRole('button', { name: /resolve…/i }).click() })
    return c
  }

  test('confirm stays unreachable until basis ≥15 chars AND a tier is chosen; then POSTs the body', async () => {
    await renderView()
    const c = await openResolve('Calf (left)')
    const confirm = () => c.getByRole('button', { name: /confirm resolution/i })
    const basis = c.getByPlaceholderText(/state the grounds/i)

    expect(confirm().disabled).toBe(true)

    await act(async () => { fireEvent.change(basis, { target: { value: 'too short' } }) })
    expect(confirm().disabled).toBe(true) // <15 chars

    await act(async () => { fireEvent.change(basis, { target: { value: 'clinician cleared full return to load' } }) })
    expect(confirm().disabled).toBe(true) // basis ok, no authority yet

    await act(async () => { c.getByRole('button', { name: 'User' }).click() })
    expect(confirm().disabled).toBe(false)

    api.post.mockResolvedValue({ data: {} })
    await act(async () => { confirm().click() })
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post).toHaveBeenCalledWith('/knowledge/injuries/76/resolve', {
      basis: 'clinician cleared full return to load',
      resolved_by: 'user',
    })
  })

  test('a failed resolve keeps the typed basis and shows an error (AC#7)', async () => {
    await renderView()
    const c = await openResolve('Calf (left)')
    const basis = c.getByPlaceholderText(/state the grounds/i)
    await act(async () => { fireEvent.change(basis, { target: { value: 'resolved after physio discharge note' } }) })
    await act(async () => { c.getByRole('button', { name: 'Clinician' }).click() })

    api.post.mockRejectedValue({ response: { status: 500 } })
    await act(async () => { c.getByRole('button', { name: /confirm resolution/i }).click() })
    await waitFor(() => expect(c.getByText(/could not resolve/i)).toBeTruthy())
    // the basis survives the failure — the operator does not retype it
    expect(c.getByPlaceholderText(/state the grounds/i).value).toBe('resolved after physio discharge note')
  })
})


describe('history distinguishes resolved from superseded (AC#8)', () => {
  test('id 18 is resolved with its verbatim block; ids 16/17/30 are superseded', async () => {
    await renderView()
    await act(async () => { screen.getByRole('button', { name: /show history/i }).click() })

    // resolved: null successor, resolution block shown verbatim
    expect(screen.getByText('resolved')).toBeTruthy()
    expect(screen.getByText(/full ROM, no pain on load for 6 weeks/)).toBeTruthy()

    // superseded: names the successor id
    expect(screen.getByText('superseded → #77')).toBeTruthy() // finger 16→77
    expect(screen.getByText('superseded → #78')).toBeTruthy() // shoulder 17→78
    expect(screen.getByText('superseded → #75')).toBeTruthy() // pes anserine 30→75
  })
})
