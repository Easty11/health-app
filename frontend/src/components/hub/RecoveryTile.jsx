// Recovery tile — a doorway to /recovery whose subtitle turns amber when an overnight Garmin lane has failed or a
// wake-day closed its capture window without data (S2). The server decides (GET /integrations/garmin/wake-day ->
// `alerts`, per user) and the tile shows it as sent: it names the lane or the figure and the date or age
// ("SpO2 missing 2026-11-01"). A wake-day still inside its capture window is never in `alerts`, so the tile is never
// amber for the morning's data still arriving. Fail-soft: if the read fails the tile keeps its plain subtitle; the
// Recovery page itself carries the capture status.

import { useEffect, useState } from 'react'
import api from '../../api'
import Tile from './Tile'

export default function RecoveryTile() {
  const [alerts, setAlerts] = useState([])

  useEffect(() => {
    let cancelled = false
    api.get('/integrations/garmin/wake-day')
      .then((res) => {
        if (!cancelled && res?.data?.connected) setAlerts(res.data.alerts ?? [])
      })
      .catch(() => {}) // the plain subtitle stands
    return () => { cancelled = true }
  }, [])

  const first = alerts[0]
  return (
    <Tile to="/recovery" icon="🌙" label="Recovery" detail="HRV, sleep and overnight vitals">
      {first ? (
        <span data-testid="recovery-amber" className="text-xs leading-snug text-amber-600 font-medium">
          {first.message}{alerts.length > 1 ? ` (+${alerts.length - 1} more)` : ''}
        </span>
      ) : undefined}
    </Tile>
  )
}
