// Training tile — data-backed, the same move the interpretation tile made (Q63 lineage). It
// REPLACES the static Training doorway in Dashboard.jsx: same route, same icon, same label, but the
// detail line now reads the exposure engine instead of a fixed string. The tile does NOT reproduce
// the recommendation; it routes to /training, which hosts the full ExposurePanel.
//
// FOUR VISIBLE STATES, as InterpretationTile has. The no-profile response was determined in-tree
// (GATE 2): GET /engine/next never 404s — with no fortification profile select_next returns 200
// with fortify.target = null (target_label collapses to "—"). So `empty` keys on EITHER a 404
// (defensive; the endpoint does not currently emit it) OR a 200 with no fortify.target. Anything
// else non-2xx is `error`. An error must never render as an empty or absent tile — absence is not
// emptiness.
//
// COST NOTE: /engine/next runs the selector per request (no cache); the hub now calls it on load.
// Acceptable for one user. If hub load gets slow the fix is a cached endpoint, not moving the
// arithmetic client-side.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../api'
import { exposureTileCopy } from './exposureTileCopy'

export default function ExposureTile() {
  const [copy, setCopy] = useState(null)
  const [status, setStatus] = useState('loading') // loading | ready | empty | error

  useEffect(() => {
    let cancelled = false
    api.get('/engine/next')
      .then((res) => {
        if (cancelled) return
        // A 200 with no fortify.target is the no-profile response, not a recommendation.
        if (!res.data?.fortify?.target) {
          setStatus('empty')
          return
        }
        setCopy(exposureTileCopy(res.data))
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setStatus(err.response?.status === 404 ? 'empty' : 'error')
      })
    return () => { cancelled = true }
  }, [])

  const detail = {
    loading: 'Reading the engine…',
    empty: 'No exposure profile yet',
    error: 'Could not load — this is a fault, not an empty result',
    ready: copy,
  }[status]

  return (
    <Link
      to="/training"
      className="bg-white border border-gray-200 rounded-2xl p-4 flex flex-col gap-1
        hover:border-indigo-300 hover:shadow-sm transition-all focus:outline-none
        focus:ring-2 focus:ring-indigo-400"
    >
      <span className="text-2xl leading-none" aria-hidden="true">🏋️</span>
      <span className="text-sm font-semibold text-gray-900 mt-1">Training</span>
      <span className={`text-xs leading-snug ${status === 'error' ? 'text-red-600' : 'text-gray-500'}`}>
        {detail}
      </span>
    </Link>
  )
}
