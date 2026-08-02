// Interpretation tile — structural counts, resolving Q63 to candidate (a).
//
// The tile does NOT reproduce the synthesis; it routes to /interpretation, which stays the one
// home for interpreted meaning (#150 Constraint C, #49). Counts and a collection date only.
//
// FOUR VISIBLE STATES, as the view has. `GET /interpretation` 404s when no lab report has been
// confirmed — a real, benign state, not a fault — and an error must not render as an empty or
// absent tile. Absence-as-emptiness is the failure this lane has already produced three times.
//
// COST NOTE: the endpoint runs the full producer per request (no cache), so the hub now builds an
// interpretation on load. Acceptable for one user; it is the first thing to revisit if hub load
// gets slow, and the fix is a cached or count-only endpoint, not moving the arithmetic client-side.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../api'
import { interpretationTileCopy } from './interpretationTileCopy'

export default function InterpretationTile() {
  const [copy, setCopy] = useState(null)
  const [status, setStatus] = useState('loading') // loading | ready | empty | error

  useEffect(() => {
    let cancelled = false
    api.get('/interpretation')
      .then((res) => {
        if (cancelled) return
        setCopy(interpretationTileCopy(res.data))
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setStatus(err.response?.status === 404 ? 'empty' : 'error')
      })
    return () => { cancelled = true }
  }, [])

  const detail = {
    loading: 'Reading your latest panel…',
    empty: 'No confirmed lab results yet',
    error: 'Could not load — this is a fault, not an empty result',
    ready: copy,
  }[status]

  return (
    <Link
      to="/interpretation"
      className="bg-white border border-gray-200 rounded-2xl p-4 flex flex-col gap-1
        hover:border-indigo-300 hover:shadow-sm transition-all focus:outline-none
        focus:ring-2 focus:ring-indigo-400"
    >
      <span className="text-2xl leading-none" aria-hidden="true">🔬</span>
      <span className="text-sm font-semibold text-gray-900 mt-1">Interpretation</span>
      <span className={`text-xs leading-snug ${status === 'error' ? 'text-red-600' : 'text-gray-500'}`}>
        {detail}
      </span>
    </Link>
  )
}
