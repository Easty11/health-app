import { useCallback, useEffect, useRef, useState } from 'react'
import api from '../api'

// Client for the on-demand load refresh (#297): the interaction trigger that runs the #296
// load chain for the current user so a session shows up on the next page open, not the next
// 02:00 nightly sweep.
//
// SERVER-AUTHORITATIVE. The 15-min staleness gate lives on the backend. This hook always calls
// POST /load/refresh on mount and lets the server decide: a fresh user gets {skipped:true} (no
// Hevy call), a stale one gets a real run. There is deliberately NO client-side 15-min logic to
// drift from the server's. `force` (pull-to-refresh) bypasses the gate.
//
// `onFreshRun` fires ONLY on a real run (not a skip), so a page that shows a load-derived surface
// can re-fetch it exactly then — never on a skip, which changed nothing. It is held in a ref
// (updated in an effect, not during render) so an inline callback does not re-trigger the mount
// refresh.
//
// NON-BLOCKING / FAIL-SOFT. The refresh runs in the background off render, so it never blocks
// first paint; a failure is swallowed, because a background refresh must never break a page that
// is already showing its cached data. `refreshing` starts true (the mount always refreshes) and
// is cleared only in the async settle — no setState runs synchronously in an effect body.
export default function useLoadRefresh({ onFreshRun } = {}) {
  const [refreshing, setRefreshing] = useState(true)
  const onFreshRunRef = useRef(onFreshRun)
  useEffect(() => { onFreshRunRef.current = onFreshRun }, [onFreshRun])

  const post = useCallback((force) => {
    return api
      .post('/load/refresh', null, force ? { params: { force: true } } : undefined)
      .then((res) => { if (!res.data?.skipped) onFreshRunRef.current?.(res.data) })
      .catch(() => {}) // a background refresh failure must never break the page
  }, [])

  // Refresh once on mount; the server decides whether it actually runs.
  useEffect(() => {
    let cancelled = false
    post(false).finally(() => { if (!cancelled) setRefreshing(false) })
    return () => { cancelled = true }
  }, [post])

  const forceRefresh = useCallback(() => {
    setRefreshing(true) // event handler — a synchronous setState here is fine
    post(true).finally(() => setRefreshing(false))
  }, [post])

  return { refreshing, forceRefresh }
}
