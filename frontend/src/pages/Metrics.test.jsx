// @vitest-environment jsdom
//
// Metrics on-demand load refresh (#297). The charts render cached /series/load on first paint;
// on open the page fires POST /load/refresh (server-gated) and the Refresh affordance forces.
// What is proven: the mount refresh is issued, first paint is not blocked on it, a real run
// re-fetches /series/load, and the Refresh button sends ?force=true.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import Metrics from './Metrics'

beforeEach(() => {
  vi.clearAllMocks()
  api.get.mockResolvedValue({ data: [] })          // every chart's mount fetch -> empty state
  api.post.mockResolvedValue({ data: { skipped: true, reason: 'fresh' } })
})
afterEach(cleanup)

test('renders the load chart on first paint, then fires POST /load/refresh (server-gated)', async () => {
  await act(async () => { render(<MemoryRouter><Metrics /></MemoryRouter>) })
  // first paint: the load chart region is present (cached render, not blocked on the refresh)
  await waitFor(() => expect(screen.getByRole('region', { name: 'Training load' })).toBeTruthy())
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/load/refresh', null, undefined))
})

test('a real run re-fetches /series/load; a skip does not', async () => {
  // fresh -> skipped: the load series is fetched once (mount) and not re-fetched
  await act(async () => { render(<MemoryRouter><Metrics /></MemoryRouter>) })
  await waitFor(() => expect(api.post).toHaveBeenCalled())
  const seriesCalls = () => api.get.mock.calls.filter((c) => c[0] === '/series/load').length
  await waitFor(() => expect(seriesCalls()).toBeGreaterThanOrEqual(1))
  const afterMount = seriesCalls()

  // the Refresh button forces; a real run (not skipped) re-fetches /series/load. Both the
  // LoadChart and the FormChart read that endpoint, so the reload bumps two fetches.
  api.post.mockResolvedValue({ data: { users_attempted: 1, users_succeeded: 1 } })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Refresh' })) })
  await waitFor(() =>
    expect(api.post).toHaveBeenLastCalledWith('/load/refresh', null, { params: { force: true } }))
  await waitFor(() => expect(seriesCalls()).toBe(afterMount + 2))
})
