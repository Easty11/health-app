// Hub doorway to planned appointments (#345) — one link per `planned` appointment, soonest first,
// each to its brief at /appointments/:key. Renders nothing when none is planned, so the hub is
// unchanged for a user with no appointment.
//
// Late reports (#346): the operator often reports an appointment days after it happens. A `planned`
// appointment whose `at` has passed (Brisbane local) reads "Awaiting report · <n> days" instead of
// as upcoming, and stays listed until it is set `attended`/`closed`. Surfacing only — nothing here
// changes its status.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../api'
import { awaitingDays, awaitingLabel } from '../../lib/awaitingReport'

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
    <nav aria-label="Appointments" className="bg-white border border-gray-200 rounded-2xl p-4 space-y-2">
      <p className="text-sm font-semibold text-gray-900">Appointments</p>
      <ul className="space-y-1">
        {appts.map((a) => {
          const late = awaitingDays(a.at)
          return (
            <li key={a.key}>
              <Link to={`/appointments/${encodeURIComponent(a.key)}`}
                className="text-sm text-indigo-700 hover:text-indigo-900">
                🩺 {a.clinician} — {fmtWhen(a.at)}
              </Link>
              {late !== null && (
                <span className="ml-2 text-xs font-medium text-amber-800 bg-amber-100 rounded px-1.5 py-0.5">
                  {awaitingLabel(late)}
                </span>
              )}
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
