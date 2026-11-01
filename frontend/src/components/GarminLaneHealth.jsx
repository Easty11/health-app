// Garmin lane health for Settings -> Integrations (S3): per lane the last success (age) and outcome, and the
// Personal API key's days to expiry. The server decides every severity (GET /integrations/garmin/lanes, the same
// thresholds as the load card's alerts: amber at 30 days or less, red at 7 or less, when expired, and when the
// token exchange is refused) and this shows them as sent. Renders nothing for a user with no Garmin connection.

import { useEffect, useState } from 'react'
import api from '../api'
import { formatAge } from '../lib/formatAge'

const OUTCOME_WORDS = {
  ok: 'ok', empty: 'ok (nothing to read)', auth_failed: 'key refused', rate_limited: 'rate-limited',
  error: 'error', skipped_needs_refresh: 'needs refresh',
}
const DOT = { ok: 'bg-green-500', amber: 'bg-amber-500', red: 'bg-red-500', none: 'bg-gray-300' }
const TEXT = { ok: 'text-gray-500', amber: 'text-amber-600', red: 'text-red-600', none: 'text-gray-400' }

export default function GarminLaneHealth() {
  const [view, setView] = useState(null)

  useEffect(() => {
    let cancelled = false
    api.get('/integrations/garmin/lanes')
      .then((res) => { if (!cancelled && res?.data) setView(res.data) })
      .catch(() => {}) // additive: the integration rows above stand without it
    return () => { cancelled = true }
  }, [])

  if (!view?.connected) return null
  const key = view.key

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-4" data-testid="garmin-lanes">
      <p className="text-sm font-semibold text-gray-900">Garmin</p>
      <p className="text-xs text-gray-400 mb-3">Overnight data lanes and the Personal API key</p>

      {key && (
        <div className="flex items-start gap-2 mb-3" data-testid="garmin-key" data-severity={key.severity}>
          <span className={`w-2.5 h-2.5 rounded-full shrink-0 mt-1 ${DOT[key.severity] ?? DOT.none}`} />
          <p className={`text-xs ${key.severity === 'ok' ? 'text-gray-700' : `${TEXT[key.severity]} font-medium`}`}>
            Personal API key · {key.message}{key.expires_on ? ` (${key.expires_on})` : ''}
          </p>
        </div>
      )}

      <ul className="space-y-2">
        {view.lanes.map((l) => (
          <li key={l.lane} className="flex items-start gap-2" data-testid={`lane-${l.lane}`} data-severity={l.severity}>
            <span className={`w-2.5 h-2.5 rounded-full shrink-0 mt-1 ${DOT[l.severity] ?? DOT.none}`} />
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-800">{l.label}</p>
              <p className={`text-[11px] ${TEXT[l.severity] ?? TEXT.none}`}>
                {l.outcome === null ? 'no run yet' : OUTCOME_WORDS[l.outcome] ?? l.outcome}
                {' · '}
                {l.last_success_at ? `last success ${formatAge(l.success_age_hours)}` : 'never succeeded'}
                {l.reason ? ` · ${l.reason}` : ''}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
