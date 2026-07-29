import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'

// Read-back of submitted daily check-ins (frontend consumer of the existing
// GET /checkin-v2/history — DailyRecordOut, user-scoped). Display only: no edit,
// no audit trail (that is the ROADMAP NOW "mutable post-submission" item). Shows
// what was entered, AM and PM, per day — the "can't see my own check-ins" gap.

const DAY_LABELS = ['', 'Terrible', 'Poor', 'Okay', 'Good', 'Great']

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
}

function fmtTime(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

function Stat({ label, value }) {
  if (value === null || value === undefined || value === '') return null
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-gray-400">{label}</span>
      <span className="text-sm font-medium text-gray-800 tabular-nums">{value}</span>
    </div>
  )
}

function sorenessSummary(s) {
  if (!s || typeof s !== 'object') return null
  const entries = Object.entries(s).filter(([, v]) => v != null)
  if (entries.length === 0) return null
  return entries.map(([k, v]) => `${k} ${v}`).join(', ')
}

function DayCard({ rec }) {
  const am = !!rec.am_timestamp
  const pm = !!rec.pm_timestamp
  return (
    <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100 flex items-baseline justify-between">
        <span className="text-sm font-semibold text-gray-900">{fmtDate(rec.date)}</span>
        <span className="text-xs text-gray-400">
          {am ? `☀ ${fmtTime(rec.am_timestamp)}` : ''}{am && pm ? ' · ' : ''}{pm ? `🌙 ${fmtTime(rec.pm_timestamp)}` : ''}
        </span>
      </div>

      {am && (
        <div className="px-4 py-3 border-b border-gray-50">
          <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wide mb-2">Morning</p>
          <div className="grid grid-cols-3 gap-y-3 gap-x-2">
            <Stat label="Readiness" value={rec.morning_readiness != null ? `${rec.morning_readiness}/5` : null} />
            <Stat label="Sleep qual" value={rec.sleep_quality != null ? `${rec.sleep_quality}/5` : null} />
            <Stat label="Fatigue" value={rec.fatigue != null ? `${rec.fatigue}/10` : null} />
            <Stat label="Motivation" value={rec.motivation != null ? `${rec.motivation}/10` : null} />
            <Stat label="Life load" value={rec.life_load != null ? `${rec.life_load}/5` : null} />
            <Stat label="Alcohol" value={rec.alcohol_units != null ? `${rec.alcohol_units}u${rec.alcohol_finish_time ? ` @ ${rec.alcohol_finish_time}` : ''}` : null} />
          </div>
          {sorenessSummary(rec.soreness) && (
            <p className="mt-2 text-xs text-gray-500">Soreness: {sorenessSummary(rec.soreness)}</p>
          )}
          {rec.am_notes && <p className="mt-2 text-xs text-gray-500 italic">“{rec.am_notes}”</p>}
        </div>
      )}

      {pm && (
        <div className="px-4 py-3">
          <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wide mb-2">Evening</p>
          <div className="grid grid-cols-3 gap-y-3 gap-x-2">
            <Stat label="Day" value={rec.today_rating != null ? `${DAY_LABELS[rec.today_rating] || rec.today_rating}` : null} />
            <Stat label="Session qual" value={rec.session_quality != null ? `${rec.session_quality}/5` : null} />
            <Stat label="Session RPE" value={rec.session_rpe != null ? `${rec.session_rpe}` : null} />
            <Stat label="Mindfulness" value={rec.mindfulness_occurred ? `${rec.mindfulness_duration_min ?? ''} min`.trim() : (rec.mindfulness_occurred === false ? 'No' : null)} />
          </div>
          {rec.pm_notes && <p className="mt-2 text-xs text-gray-500 italic">“{rec.pm_notes}”</p>}
        </div>
      )}
    </div>
  )
}

export default function CheckInHistory() {
  const [records, setRecords] = useState(null) // null=loading
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/checkin-v2/history', { params: { days: 30 } })
      .then(({ data }) => setRecords(data))
      .catch(() => setError('Could not load check-in history'))
  }, [])

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3 sticky top-0 z-10">
        <Link to="/dashboard" className="text-gray-400 hover:text-gray-700 transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <span className="text-sm font-bold text-gray-900">Check-in history</span>
      </header>

      <div className="max-w-lg mx-auto px-4 py-5 space-y-4">
        {error && <div className="bg-red-50 text-red-700 text-sm rounded-lg px-3 py-2">{error}</div>}
        {records && records.length === 0 && (
          <p className="text-sm text-gray-500 text-center py-10">No check-ins logged yet.</p>
        )}
        {records && records.map((rec) => <DayCard key={rec.id} rec={rec} />)}
      </div>
    </div>
  )
}
