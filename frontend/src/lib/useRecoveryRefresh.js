import { useCallback, useEffect, useRef, useState } from 'react'
import api from '../api'

// Client for the on-demand Garmin wake-day capture (#299, widened) — the freshness leg that resolves Q155.
// The server now fetches the whole wake-day (sleep, resting HR, SpO2, HRV and the DI epoch night), not HRV alone.
// Garmin has no ingestion trigger, so overnight HRV reached the store only by a hand-run
// backfill and the Recovery card restaled each morning. This hook fires the pull on card open;
// the nightly 02:00 sweep (load_sweep) is the guarantee for mornings the card is never opened.
//
// SERVER-AUTHORITATIVE. The 30-min staleness gate lives on the backend
// (POST /integrations/garmin/refresh). This hook always calls on mount and lets the server
// decide: a fresh user gets {skipped:true} (no Garmin pull), a stale one gets a real run. There
// is deliberately NO client-side gate to drift from the server's. `force` (pull-to-refresh)
// bypasses it.
//
// `onFreshRun` fires ONLY on a real run (not a skip), so the card can re-fetch /health/summary
// exactly then — never on a skip, which changed nothing. It is held in a ref (updated in an
// effect, not during render) so an inline callback does not re-trigger the mount refresh.
//
// NON-BLOCKING / FAIL-SOFT. The refresh runs in the background off render, so it never blocks
// first paint; a failure is swallowed, because a background refresh must never break a card that
// is already showing its cached data. (The endpoint itself also never errors — a dead Garmin
// token returns a skipped-shaped payload — but the .catch is kept as belt-and-braces.)
// `refreshing` starts true (the mount always refreshes) and clears only in the async settle.
// `via` names the surface ('checkin' | 'recovery') so the server can report the landing path. `onSettled(data)` fires
// on EVERY response (a skip too) so a surface can re-read the slot `status` the server returns with it.
export default function useRecoveryRefresh({ onFreshRun, onSettled, via } = {}) {
  const [refreshing, setRefreshing] = useState(true)
  const onFreshRunRef = useRef(onFreshRun)
  const onSettledRef = useRef(onSettled)
  useEffect(() => { onFreshRunRef.current = onFreshRun; onSettledRef.current = onSettled }, [onFreshRun, onSettled])

  const post = useCallback((force) => {
    const params = {}
    if (via) params.via = via
    if (force) params.force = true
    return api
      .post('/integrations/garmin/refresh', null, Object.keys(params).length ? { params } : undefined)
      .then((res) => {
        if (!res.data?.skipped) onFreshRunRef.current?.(res.data)
        onSettledRef.current?.(res.data)
      })
      .catch(() => {}) // a background refresh failure must never break the card
  }, [via])

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
