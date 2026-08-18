// @vitest-environment jsdom
//
// The confirmation-screen canonical bind (#220, fulfilling #50).
//
// Like `EvaluationOffer.test.jsx`, the assertions here are mostly about the NETWORK: what
// gets posted, and what the operator is shown when the server refuses. Two properties are
// worth a render-and-click test rather than a unit test:
//
//   1. The empty unit field must post `null`, not `""`. An empty string would be a unit
//      claim of zero length for the over-collapse guard to compare against, where the
//      operator meant "this marker has no established unit" (§6). The coercion lives in
//      the submit handler, so only exercising the handler can protect it.
//   2. A guard refusal must render the server's own `detail` verbatim. The 409 and 422
//      texts name the exact clashing marker/unit — that specificity IS the affordance,
//      and a generic "bind failed" banner would throw away the only actionable part.
//
// Interaction uses the repo's existing `act` + native-event idiom rather than
// `@testing-library/user-event`, which is not a dependency here.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { act } from 'react'

vi.mock('../api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

import api from '../api'
import { BindControl } from './Metrics'

const RAW = 'Lipoprotein(a)'

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  cleanup()
})

async function click(name) {
  await act(async () => { screen.getByRole('button', { name }).click() })
}

async function type(label, value) {
  await act(async () => {
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
  })
}

async function openForm() {
  await click(/not a known marker/i)
}

test('posts the exact operator-supplied binding and refreshes the map', async () => {
  const onBound = vi.fn().mockResolvedValue(undefined)
  api.post.mockResolvedValue({
    data: { marker_name_raw: RAW, marker_canonical: 'lipoprotein_a', unit_established: 'nmol/L', backfilled_rows: 3 },
  })

  await act(async () => { render(<BindControl rawName={RAW} onBound={onBound} />) })
  await openForm()
  await type(`Canonical name for ${RAW}`, 'lipoprotein_a')
  await type(`Established unit for ${RAW}`, 'nmol/L')
  await click('Bind')

  expect(api.post).toHaveBeenCalledTimes(1)
  expect(api.post).toHaveBeenCalledWith('/labs/canonical/bind', {
    marker_name_raw: RAW,
    marker_canonical: 'lipoprotein_a',
    unit_established: 'nmol/L',
  })
  // The map must be re-read, or the row the operator just bound still reads unmapped at confirm.
  expect(onBound).toHaveBeenCalledTimes(1)
})

test('reports how much history the bind promoted', async () => {
  api.post.mockResolvedValue({
    data: { marker_name_raw: RAW, marker_canonical: 'lipoprotein_a', unit_established: 'nmol/L', backfilled_rows: 3 },
  })

  await act(async () => {
    render(<BindControl rawName={RAW} onBound={vi.fn().mockResolvedValue(undefined)} />)
  })
  await openForm()
  await type(`Canonical name for ${RAW}`, 'lipoprotein_a')
  await click('Bind')

  // Promotion is the reason a bind is worth doing (#159) — it has to be visible.
  expect(screen.getByText(/3 historical rows promoted/)).toBeTruthy()
})

test('an empty unit posts null, not an empty string', async () => {
  api.post.mockResolvedValue({
    data: { marker_name_raw: 'Some Ratio', marker_canonical: 'some_ratio', unit_established: null, backfilled_rows: 0 },
  })

  await act(async () => {
    render(<BindControl rawName="Some Ratio" onBound={vi.fn().mockResolvedValue(undefined)} />)
  })
  await openForm()
  await type('Canonical name for Some Ratio', 'some_ratio')
  await click('Bind')

  expect(api.post).toHaveBeenCalledTimes(1)
  expect(api.post.mock.calls[0][1].unit_established).toBeNull()
})

test('an over-collapse 422 renders the server reason verbatim', async () => {
  const detail =
    "Over-collapse guard: canonical 'testosterone' is already established in unit 'nmol/L' " +
    "(via 'Testosterone'), but this bind establishes 'pmol/L' — refusing to merge two analytes into one series."
  api.post.mockRejectedValue({ response: { status: 422, data: { detail } } })

  await act(async () => { render(<BindControl rawName="Free Testosterone" onBound={vi.fn()} />) })
  await openForm()
  await type('Canonical name for Free Testosterone', 'testosterone')
  await type('Established unit for Free Testosterone', 'pmol/L')
  await click('Bind')

  expect(screen.getByRole('alert').textContent).toBe(detail)
})

test('an already-mapped 409 renders legibly and leaves the form open to correct', async () => {
  const detail =
    "'Sodium' is already mapped to 'sodium' — binding an already-mapped marker is not an update path. " +
    'Change it via a governed map edit, not a bind.'
  api.post.mockRejectedValue({ response: { status: 409, data: { detail } } })

  await act(async () => { render(<BindControl rawName="Sodium" onBound={vi.fn()} />) })
  await openForm()
  await type('Canonical name for Sodium', 'sodium')
  await click('Bind')

  expect(screen.getByRole('alert').textContent).toBe(detail)
  // A refusal must not close the form or claim success — the operator has to be able to retry.
  expect(screen.getByRole('button', { name: 'Bind' })).toBeTruthy()
  expect(screen.queryByText(/Bound to/)).toBeNull()
})

test('a transport failure with no detail falls back to a named message', async () => {
  api.post.mockRejectedValue(new Error('network down'))

  await act(async () => { render(<BindControl rawName={RAW} onBound={vi.fn()} />) })
  await openForm()
  await type(`Canonical name for ${RAW}`, 'lipoprotein_a')
  await click('Bind')

  expect(screen.getByRole('alert').textContent).toMatch(/no reason/i)
})
