// The Injuries doorway (DECISIONS_LOG "Proposals and reviews due render on the AM check-in saved
// screen", C3): the plain tile gains one line when non-zero — "n proposals · m reviews due" — from the
// same two reads the saved screen uses (/knowledge/proposals, /knowledge/review-due), one fetch each
// on mount. Zero on both, or a failed read, leaves the tile exactly as it was. A doorway, not a
// dashboard: it counts, it does not act (the actions are on the Injuries page and the morning screen).

import { useEffect, useState } from 'react'
import Tile from './Tile'
import api from '../../api'

const DETAIL = 'Active injury ledger and resolution'

function plural(n, word) {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

export function pendingLine({ proposals, due }) {
  if (!(proposals > 0 || due > 0)) return null
  return `${plural(proposals, 'proposal')} · ${plural(due, 'review')} due`
}

export default function InjuriesTile() {
  const [counts, setCounts] = useState(null)

  useEffect(() => {
    Promise.allSettled([api.get('/knowledge/proposals'), api.get('/knowledge/review-due')])
      .then(([p, d]) => setCounts({
        proposals: p.status === 'fulfilled' && Array.isArray(p.value?.data)
          ? p.value.data.filter((x) => x.type === 'constraint' || x.type === 'finding').length : 0,
        due: d.status === 'fulfilled' && Array.isArray(d.value?.data?.items) ? d.value.data.items.length : 0,
      }))
  }, [])

  const line = counts ? pendingLine(counts) : null
  return (
    <Tile to="/injuries" icon="🩹" label="Injuries" detail={DETAIL}>
      {line ? (
        <span className="text-xs text-gray-500 leading-snug">
          {DETAIL}
          <span className="block text-amber-700 font-medium mt-0.5">{line}</span>
        </span>
      ) : undefined}
    </Tile>
  )
}
