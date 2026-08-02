// The hub (#150) — /dashboard is a module tile grid, not a panel composition.
//
// HealthPanel and WorkoutPanel left for /recovery and /training; ChatPanel left for the dock in
// HubLayout. Every destination the old header carried is now a tile or a shell control, and the
// two relocated panels became reachable surfaces rather than half a split screen.
//
// AM/PM is NOT a tile. It is the daily touchpoint and the reason the app is opened, so it sits
// above the grid at full size rather than being buried as one doorway among six.
//
// Tiles are plain doorways. None seeds chat context — that path is request-scoped
// (find_marker -> render_asked_lab_value) and out of scope here (#150 rule 3, #59).

import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import HubLayout from '../components/HubLayout'
import Tile from '../components/hub/Tile'
import InterpretationTile from '../components/hub/InterpretationTile'
import api from '../api'

function CheckInButtons() {
  const [record, setRecord] = useState(undefined) // undefined=loading

  useEffect(() => {
    api.get('/checkin-v2/today')
      .then(({ data }) => setRecord(data))
      .catch(() => setRecord(null))
  }, [])

  if (record === undefined) return null

  const amDone = !!record?.am_timestamp
  const pmDone = !!record?.pm_timestamp

  return (
    <div className="grid grid-cols-2 gap-3">
      <Link
        to="/checkin-am"
        className={`rounded-2xl px-4 py-3 flex items-center gap-2 font-semibold text-sm transition-colors ${
          amDone
            ? 'bg-green-100 text-green-700 hover:bg-green-200'
            : 'bg-orange-100 text-orange-700 hover:bg-orange-200 animate-pulse'
        }`}
      >
        <span className="text-lg">{amDone ? '✓' : '☀'}</span>
        <span>Morning check-in</span>
      </Link>
      <Link
        to="/nightly"
        className={`rounded-2xl px-4 py-3 flex items-center gap-2 font-semibold text-sm transition-colors ${
          pmDone
            ? 'bg-green-100 text-green-700 hover:bg-green-200'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
        }`}
      >
        <span className="text-lg">{pmDone ? '✓' : '🌙'}</span>
        <span>Evening close-out</span>
      </Link>
    </div>
  )
}

export default function Dashboard() {
  return (
    <HubLayout title="Health &amp; Performance">
      <div className="max-w-4xl mx-auto px-4 py-5 space-y-5">
        <CheckInButtons />

        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          <Tile to="/recovery" icon="🌙" label="Recovery" detail="HRV, sleep and overnight vitals" />
          <Tile to="/training" icon="🏋️" label="Training" detail="Strength and aerobic sessions" />
          <Tile to="/metrics" icon="🧪" label="Labs" detail="Blood panels and marker history" />
          <InterpretationTile />
          <Tile to="/checkin-history" icon="📅" label="History" detail="Past check-ins" />
          <Tile to="/settings" icon="⚙️" label="Settings" detail="Integrations and account" />
        </div>
      </div>
    </HubLayout>
  )
}
