import { useCallback, useEffect, useState } from 'react'
import api from '../../api'

// Per-session sRPE for the close-out and the AM catch-up: one CR-10 per counted session, written as the app's own
// rating (`in_app`, the top of the hierarchy). A session a device already rated shows that rating read-only with an
// Override; an unrated one asks. There is no whole-day question and no default value: a rating exists only because it
// was tapped, so an untouched card never records anything.
//
// The server owns what a session is, its label, and the backfill bound (GET /checkin-v2/srpe/sessions and
// /earlier). A failed read costs the ask, never the close-out: the card still saves. Ratings are posted before the
// card's own save (`saveToday`); the earlier-sessions backfill saves on its own button, so it never forces a close-out.

const BASE = '/checkin-v2/srpe'
export const keyOf = (s) => `${s.kind}:${s.id}`
const asList = (data) => (Array.isArray(data?.sessions) ? data.sessions : [])

function omit(obj, keys) {
  const out = { ...obj }
  keys.forEach((k) => { delete out[k] })
  return out
}

/**
 * Loads the day's counted sessions and the unrated earlier ones, and holds the values picked so far.
 * `day` is an ISO date (the catch-up's missed day); undefined means today, which the server resolves.
 * `enabled: false` loads nothing (a card that is not showing).
 */
export function useSessionRatings(day, { enabled = true } = {}) {
  const [sessions, setSessions] = useState(null)   // null = loading
  const [earlier, setEarlier] = useState([])
  const [loadFailed, setLoadFailed] = useState(false)
  const [pending, setPending] = useState({})       // key -> 0..10, picked and not yet saved
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // Promise callbacks, not an async body: state is only ever set once the reads have answered.
  const load = useCallback(() => {
    if (!enabled) return Promise.resolve()
    return Promise.all([
      api.get(`${BASE}/sessions`, { params: day ? { since: day, until: day } : {} }),
      api.get(`${BASE}/earlier`, { params: day ? { before: day } : {} }),
    ]).then(([s, e]) => {
      setSessions(asList(s.data))
      setEarlier(asList(e.data))
      setLoadFailed(false)
    }).catch(() => {
      setSessions([])
      setEarlier([])
      setLoadFailed(true)
    })
  }, [day, enabled])

  useEffect(() => { load() }, [load])

  const pick = (key, n) => { setPending((p) => ({ ...p, [key]: n })); setError('') }
  const unpick = (key) => setPending((p) => omit(p, [key]))

  const save = async (rows) => {
    const ratings = rows.filter((s) => keyOf(s) in pending)
      .map((s) => ({ kind: s.kind, id: s.id, rpe: pending[keyOf(s)] }))
    if (ratings.length === 0) return true
    setSaving(true)
    setError('')
    try {
      await api.post(`${BASE}/ratings`, { ratings })
      setPending((p) => omit(p, rows.map(keyOf)))
      await load()
      return true
    } catch (err) {
      setError(err?.response?.data?.detail || 'Failed to save ratings')
      return false
    } finally {
      setSaving(false)
    }
  }

  const todayRows = sessions || []
  return {
    sessions, earlier, loadFailed, pending, saving, error, pick, unpick,
    saveToday: () => save(todayRows),
    saveEarlier: () => save(earlier),
    pendingToday: todayRows.filter((s) => keyOf(s) in pending).length,
    pendingEarlier: earlier.filter((s) => keyOf(s) in pending).length,
  }
}

