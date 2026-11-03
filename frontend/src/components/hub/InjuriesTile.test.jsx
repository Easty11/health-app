// @vitest-environment jsdom
//
// The Injuries doorway's one line (DECISIONS_LOG "Proposals and reviews due render on the AM check-in
// saved screen", C3): "n proposals · m reviews due" when non-zero, from one fetch each of the two reads
// on mount; absent when both are zero or a read fails. The tile stays the one link to /injuries.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../../api'
import InjuriesTile, { pendingLine } from './InjuriesTile'

function routeGets({ proposals, due, fail = false }) {
  api.get.mockImplementation((url) => {
    if (fail) return Promise.reject(new Error('down'))
    if (url === '/knowledge/proposals') return Promise.resolve({ data: proposals })
    if (url === '/knowledge/review-due') return Promise.resolve({ data: due })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}
const gets = (url) => api.get.mock.calls.filter(([u]) => u === url).length
const renderIt = async () => { await act(async () => { render(<MemoryRouter><InjuriesTile /></MemoryRouter>) }) }

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

test('non-zero counts: the line is present, one fetch each, still one link to /injuries', async () => {
  routeGets({ proposals: [{ id: 1, type: 'constraint' }, { id: 2, type: 'finding' }, { id: 3, type: 'preference' }],
              due: { items: [{ id: 5 }], withheld_labs: 0 } })
  await renderIt()
  await waitFor(() => expect(screen.getByText('2 proposals · 1 review due')).toBeTruthy())
  expect(screen.getByText('Active injury ledger and resolution')).toBeTruthy()
  expect(gets('/knowledge/proposals')).toBe(1)
  expect(gets('/knowledge/review-due')).toBe(1)
  expect(screen.getAllByRole('link').filter((a) => a.getAttribute('href') === '/injuries')).toHaveLength(1)
})

test('zero on both: no line', async () => {
  routeGets({ proposals: [], due: { items: [], withheld_labs: 0 } })
  await renderIt()
  await waitFor(() => expect(gets('/knowledge/review-due')).toBe(1))
  expect(screen.queryByText(/proposal/)).toBeNull()
  expect(screen.getByText('Active injury ledger and resolution')).toBeTruthy()
})

test('a failed read: no line, the tile intact', async () => {
  routeGets({ proposals: [], due: {}, fail: true })
  await renderIt()
  await waitFor(() => expect(gets('/knowledge/review-due')).toBe(1))
  expect(screen.queryByText(/proposal/)).toBeNull()
  expect(screen.getByText('Injuries')).toBeTruthy()
})

test('pendingLine pluralises and hides zero/zero', () => {
  expect(pendingLine({ proposals: 1, due: 0 })).toBe('1 proposal · 0 reviews due')
  expect(pendingLine({ proposals: 0, due: 2 })).toBe('0 proposals · 2 reviews due')
  expect(pendingLine({ proposals: 0, due: 0 })).toBeNull()
})
