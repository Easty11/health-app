// Hub doorway to planned appointments (#345) — one link per `planned` appointment, soonest first,
// each to its brief at /appointments/:key. Renders nothing when none is planned, so the hub is
// unchanged for a user with no appointment.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../api'

function fmtWhen(at) {
  const d = new Date(at)
  if (Number.isNaN(d.getTime())) return at
  return d.toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export default function AppointmentsDoorway() {
  const [appts, setAppts] = useState([])

  useEffect(() => {
    api.get('/appointments', { params: { status: 'planned' } })
      .then(({ data }) => setAppts(Array.isArray(data) ? data : []))
      .catch(() => setAppts([]))
  }, [])

  if (appts.length === 0) return null

  return (
    <nav aria-label="Upcoming appointments" className="bg-white border border-gray-200 rounded-2xl p-4 space-y-2">
      <p className="text-sm font-semibold text-gray-900">Upcoming appointments</p>
      <ul className="space-y-1">
        {appts.map((a) => (
          <li key={a.key}>
            <Link to={`/appointments/${encodeURIComponent(a.key)}`}
              className="text-sm text-indigo-700 hover:text-indigo-900">
              🩺 {a.clinician} — {fmtWhen(a.at)}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  )
}
