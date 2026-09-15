// @vitest-environment jsdom
//
// useRecoveryRefresh (#299) — the client for the server-authoritative on-demand Garmin HRV
// refresh. What is proven: it POSTs /integrations/garmin/refresh on mount (no force);
// `onFreshRun` fires on a real run and NOT on a server skip; `forceRefresh` sends ?force=true;
// `refreshing` toggles around the call; and a refresh failure is swallowed (never throws,
// `onFreshRun` not called).

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({ default: { post: vi.fn() } }))

import api from '../api'
import useRecoveryRefresh from './useRecoveryRefresh'

beforeEach(() => { api.post.mockReset() })
afterEach(cleanup)

test('POSTs /integrations/garmin/refresh on mount, without force', async () => {
  api.post.mockResolvedValue({ data: { skipped: true, reason: 'fresh' } })
  renderHook(() => useRecoveryRefresh())
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
  expect(api.post).toHaveBeenCalledWith('/integrations/garmin/refresh', null, undefined)
})

test('onFreshRun fires on a real run (not skipped)', async () => {
  const onFreshRun = vi.fn()
  api.post.mockResolvedValue({ data: { readings_upserted: 1, days_with_data: 1 } })
  renderHook(() => useRecoveryRefresh({ onFreshRun }))
  await waitFor(() => expect(onFreshRun).toHaveBeenCalledTimes(1))
  expect(onFreshRun).toHaveBeenCalledWith({ readings_upserted: 1, days_with_data: 1 })
})

test('onFreshRun does NOT fire on a server skip', async () => {
  const onFreshRun = vi.fn()
  api.post.mockResolvedValue({ data: { skipped: true, reason: 'fresh' } })
  renderHook(() => useRecoveryRefresh({ onFreshRun }))
  await waitFor(() => expect(api.post).toHaveBeenCalled())
  await Promise.resolve()
  expect(onFreshRun).not.toHaveBeenCalled()
})

test('onFreshRun does NOT fire on a graceful degrade (reconnect_required)', async () => {
  // the endpoint never errors the card: a dead token returns a skipped-shaped payload, so the
  // hook must treat it as a skip (no re-fetch).
  const onFreshRun = vi.fn()
  api.post.mockResolvedValue({ data: { skipped: true, reason: 'reconnect_required' } })
  renderHook(() => useRecoveryRefresh({ onFreshRun }))
  await waitFor(() => expect(api.post).toHaveBeenCalled())
  await Promise.resolve()
  expect(onFreshRun).not.toHaveBeenCalled()
})

test('forceRefresh sends ?force=true', async () => {
  api.post.mockResolvedValue({ data: { skipped: true } }) // mount call
  const { result } = renderHook(() => useRecoveryRefresh())
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))

  api.post.mockResolvedValue({ data: { readings_upserted: 1 } })
  await act(async () => { result.current.forceRefresh() })
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))
  expect(api.post).toHaveBeenLastCalledWith(
    '/integrations/garmin/refresh', null, { params: { force: true } })
})

test('refreshing toggles false after the call resolves', async () => {
  api.post.mockResolvedValue({ data: { skipped: true } })
  const { result } = renderHook(() => useRecoveryRefresh())
  await waitFor(() => expect(result.current.refreshing).toBe(false))
})

test('a refresh failure is swallowed (never throws, onFreshRun not called)', async () => {
  const onFreshRun = vi.fn()
  api.post.mockRejectedValue(new Error('network'))
  const { result } = renderHook(() => useRecoveryRefresh({ onFreshRun }))
  await waitFor(() => expect(result.current.refreshing).toBe(false)) // settled, no throw
  expect(onFreshRun).not.toHaveBeenCalled()
})
