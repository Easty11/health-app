// @vitest-environment jsdom
//
// PhaseHistory (increment 2, W3) — the read-only ledger. W5: collapsed by default (no fetch);
// expanding fetches exactly once (a re-expand does not refetch); rows render newest first as served;
// nothing is editable.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn() } }))

import api from '../../api'
import PhaseHistory from './PhaseHistory'
import history from '../../fixtures/phaseHistory.json'

beforeEach(() => { api.get.mockReset() })
afterEach(cleanup)

test('collapsed by default — no fetch, no rows', () => {
  api.get.mockResolvedValue({ data: history })
  render(<PhaseHistory />)
  expect(api.get).not.toHaveBeenCalled()
  expect(screen.queryByText('base build')).toBeNull()
  expect(screen.getByRole('button', { name: /phase history/i })).toBeTruthy()
})

test('expand fetches once; a re-expand does not refetch', async () => {
  api.get.mockResolvedValue({ data: history })
  render(<PhaseHistory />)
  const toggle = screen.getByRole('button', { name: /phase history/i })

  await act(async () => { fireEvent.click(toggle) })
  await waitFor(() => expect(screen.getByText('base build')).toBeTruthy())
  expect(api.get).toHaveBeenCalledTimes(1)
  expect(api.get).toHaveBeenCalledWith('/engine/phase/history')

  // collapse, then expand again — the rows are kept, no second request
  await act(async () => { fireEvent.click(toggle) })
  await act(async () => { fireEvent.click(toggle) })
  expect(api.get).toHaveBeenCalledTimes(1)
})

test('rows render newest first, as served', async () => {
  api.get.mockResolvedValue({ data: history })
  const { container } = render(<PhaseHistory />)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /phase history/i })) })
  await waitFor(() => expect(screen.getByText('decompression')).toBeTruthy())
  const items = [...container.querySelectorAll('li')]
  expect(items).toHaveLength(2)
  expect(items[0].textContent).toContain('decompression')
  expect(items[1].textContent).toContain('base build')
  // the open row shows "open"; the closed prior shows its close reason and "all" capacities
  expect(items[0].textContent).toContain('open')
  expect(items[1].textContent).toContain('progressed to decompression')
  expect(items[1].textContent).toContain('all')
})

test('no edit affordance — the ledger is read-only', async () => {
  api.get.mockResolvedValue({ data: history })
  render(<PhaseHistory />)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /phase history/i })) })
  await waitFor(() => expect(screen.getByText('base build')).toBeTruthy())
  expect(screen.queryByRole('textbox')).toBeNull()
  // the only control is the collapse toggle; no per-row edit/delete/save buttons
  expect(screen.queryByRole('button', { name: /edit|delete|save|remove/i })).toBeNull()
})
