// @vitest-environment jsdom
//
// useLoadRefresh (#297) — the client for the server-authoritative on-demand load refresh. What
// is proven: it POSTs /load/refresh on mount (no force); `onFreshRun` fires on a real run and
// NOT on a server skip; `forceRefresh` sends ?force=true; `refreshing` toggles around the call;
// and a refresh failure is swallowed (never throws, `onFreshRun` not called).

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'

vi.mock('../api', () => ({ default: { post: vi.fn() } }))

import api from '../api'
import useLoadRefresh from './useLoadRefresh'

beforeEach(() => { api.post.mockReset() })
afterEach(cleanup)

test('POSTs /load/refresh on mount, without force', async () => {
  api.post.mockResolvedValue({ data: { skipped: true, reason: 'fresh' } })
  renderHook(() => useLoadRefresh())
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))
  // no force on the mount call — signature is (url, body, config); config is undefined
  expect(api.post).toHaveBeenCalledWith('/load/refresh', null, undefined)
})

test('onFreshRun fires on a real run (not skipped)', async () => {
  const onFreshRun = vi.fn()
  api.post.mockResolvedValue({ data: { users_attempted: 1, users_succeeded: 1 } })
  renderHook(() => useLoadRefresh({ onFreshRun }))
  await waitFor(() => expect(onFreshRun).toHaveBeenCalledTimes(1))
  expect(onFreshRun).toHaveBeenCalledWith({ users_attempted: 1, users_succeeded: 1 })
})

test('onFreshRun does NOT fire on a server skip', async () => {
  const onFreshRun = vi.fn()
  api.post.mockResolvedValue({ data: { skipped: true, reason: 'fresh' } })
  renderHook(() => useLoadRefresh({ onFreshRun }))
  await waitFor(() => expect(api.post).toHaveBeenCalled())
  await Promise.resolve()
  expect(onFreshRun).not.toHaveBeenCalled()
})

test('forceRefresh sends ?force=true', async () => {
  api.post.mockResolvedValue({ data: { skipped: true } }) // mount call
  const { result } = renderHook(() => useLoadRefresh())
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1))

  api.post.mockResolvedValue({ data: { users_attempted: 1 } })
  await act(async () => { result.current.forceRefresh() })
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))
  expect(api.post).toHaveBeenLastCalledWith('/load/refresh', null, { params: { force: true } })
})

test('refreshing toggles false after the call resolves', async () => {
  api.post.mockResolvedValue({ data: { skipped: true } })
  const { result } = renderHook(() => useLoadRefresh())
  await waitFor(() => expect(result.current.refreshing).toBe(false))
})

test('a refresh failure is swallowed — no throw, onFreshRun not called', async () => {
  const onFreshRun = vi.fn()
  api.post.mockRejectedValue(new Error('boom'))
  const { result } = renderHook(() => useLoadRefresh({ onFreshRun }))
  await waitFor(() => expect(result.current.refreshing).toBe(false))
  expect(onFreshRun).not.toHaveBeenCalled()
})
