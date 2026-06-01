import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import api from '../api'

const SLIDERS = [
  {
    key: 'sleep_quality', label: 'Sleep Quality', min: 1, max: 10,
    lowLabel: 'Poor', highLabel: 'Great', source: 'manual',
  },
  {
    key: 'fatigue', label: 'Fatigue', min: 1, max: 10,
    lowLabel: 'Fresh', highLabel: 'Exhausted', source: 'manual',
  },
  {
    key: 'shoulder_pain', label: 'Shoulder Pain', min: 0, max: 10,
    lowLabel: 'None', highLabel: 'Severe', source: 'manual', isPain: true,
  },
  {
    key: 'motivation', label: 'Motivation', min: 1, max: 10,
    lowLabel: 'Low', highLabel: 'High', source: 'manual',
  },
]

function readinessScore(v) {
  return Math.max(1, Math.min(10, Math.round(
    v.sleep_quality * 0.3 + (10 - v.fatigue) * 0.3 +
    (10 - v.shoulder_pain) * 0.2 + v.motivation * 0.2
  )))
}

function scoreColour(n) {
  if (n >= 8) return 'text-green-600'
  if (n >= 6) return 'text-yellow-500'
  if (n >= 4) return 'text-orange-500'
  return 'text-red-600'
}

function scoreLabel(n) {
  if (n >= 8) return 'Full prescribed loads'
  if (n >= 6) return 'Reduce 10-20%, RPE cap 7'
  if (n >= 4) return 'Reduce 20-30%, RPE cap 6'
  return 'Recovery only'
}

// ─── Slider ──────────────────────────────────────────────────────────────────
function ScoreSlider({ field, value, onChange }) {
  const pct = ((value - field.min) / (field.max - field.min)) * 100
  const isPain = field.isPain
  const colour = isPain
    ? value >= 7 ? 'text-red-600' : value >= 4 ? 'text-orange-500' : 'text-green-600'
    : value >= 7 ? 'text-green-600' : value >= 4 ? 'text-orange-500' : 'text-red-500'

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <label className="text-sm font-medium text-gray-800">{field.label}</label>
          <span className="text-xs text-gray-400 bg-gray-100 rounded-full px-1.5 py-0.5">manual</span>
        </div>
        <span className={`text-2xl font-bold tabular-nums ${colour}`}>{value}</span>
      </div>
      <input
        type="range" min={field.min} max={field.max} value={value}
        onChange={(e) => onChange(field.key, Number(e.target.value))}
        className="w-full h-3 rounded-lg appearance-none cursor-pointer"
        style={{ background: `linear-gradient(to right, #4f46e5 ${pct}%, #e5e7eb ${pct}%)` }}
      />
      <div className="flex justify-between text-xs text-gray-400">
        <span>{field.lowLabel}</span><span>{field.highLabel}</span>
      </div>
    </div>
  )
}

// ─── Already checked in summary ───────────────────────────────────────────────
function CheckInSummary({ checkin }) {
  const score = checkin.readiness_score
  return (
    <div className="space-y-4">
      <div className="bg-green-50 border border-green-200 rounded-2xl p-5 text-center space-y-2">
        <p className="text-xs font-medium text-green-700 uppercase tracking-wide">Today's readiness</p>
        <p className={`text-6xl font-black ${scoreColour(score)}`}>{score}<span className="text-2xl text-gray-400">/10</span></p>
        <p className="text-sm font-medium text-gray-600">{scoreLabel(score)}</p>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {[
          { label: 'Sleep', value: `${checkin.sleep_quality}/10` },
          { label: 'Fatigue', value: `${checkin.fatigue}/10` },
          { label: 'Shoulder', value: `${checkin.shoulder_pain}/10` },
          { label: 'Motivation', value: `${checkin.motivation}/10` },
        ].map(({ label, value }) => (
          <div key={label} className="bg-white border border-gray-100 rounded-xl p-3 text-center">
            <p className="text-xs text-gray-400">{label}</p>
            <p className="text-lg font-bold text-gray-800">{value}</p>
          </div>
        ))}
      </div>
      {checkin.rugby_session_yesterday && (
        <p className="text-xs text-center text-indigo-600 font-medium">🏉 Rugby session yesterday logged</p>
      )}
      {checkin.notes && (
        <p className="text-xs text-center text-gray-500 italic">"{checkin.notes}"</p>
      )}
      <Link to="/dashboard"
        className="block w-full text-center bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-2xl py-4 text-sm transition-colors">
        Back to dashboard
      </Link>
    </div>
  )
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function CheckIn() {
  const navigate = useNavigate()
  const [existing, setExisting] = useState(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [prefillMeta, setPrefillMeta] = useState(null) // rugby title, last session

  const [values, setValues] = useState({
    sleep_quality: 7,
    fatigue: 4,
    shoulder_pain: 2,
    motivation: 7,
    rugby_session_yesterday: false,
    notes: '',
  })

  useEffect(() => {
    // Load today's check-in and prefill data in parallel
    Promise.all([
      api.get('/checkin/today').catch(() => ({ data: null })),
      api.get('/checkin/prefill').catch(() => ({ data: null })),
    ]).then(([todayRes, prefillRes]) => {
      if (todayRes.data) {
        setExisting(todayRes.data)
      } else if (prefillRes.data) {
        const p = prefillRes.data
        setValues((v) => ({ ...v, rugby_session_yesterday: p.rugby_session_yesterday }))
        setPrefillMeta({
          rugby_session_title: p.rugby_session_title,
          last_session_title: p.last_session_title,
          last_session_date: p.last_session_date,
        })
      }
    }).finally(() => setLoading(false))
  }, [])

  function setField(key, val) {
    setValues((v) => ({ ...v, [key]: val }))
  }

  const liveScore = readinessScore(values)

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await api.post('/checkin', values)
      navigate('/dashboard')
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to submit')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-400 text-sm">Loading…</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3 sticky top-0 z-10">
        <Link to="/dashboard" className="text-gray-400 hover:text-gray-700 transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <span className="text-sm font-bold text-gray-900">Morning Check-In</span>
      </header>

      <div className="max-w-lg mx-auto px-4 py-5">
        {existing ? (
          <CheckInSummary checkin={existing} />
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">

            {/* Live readiness score */}
            <div className="bg-white border border-gray-200 rounded-2xl p-4 text-center">
              <p className="text-xs text-gray-400 mb-1">Readiness score</p>
              <p className={`text-5xl font-black ${scoreColour(liveScore)}`}>
                {liveScore}<span className="text-xl text-gray-400">/10</span>
              </p>
              <p className="text-xs font-medium text-gray-500 mt-1">{scoreLabel(liveScore)}</p>
            </div>

            {error && (
              <div className="bg-red-50 text-red-700 text-sm rounded-lg px-3 py-2">{error}</div>
            )}

            {/* Last session context */}
            {prefillMeta?.last_session_title && (
              <div className="bg-indigo-50 border border-indigo-100 rounded-xl px-4 py-3 text-xs text-indigo-700">
                Last session: <span className="font-medium">{prefillMeta.last_session_title}</span>
                {prefillMeta.last_session_date && ` — ${prefillMeta.last_session_date}`}
              </div>
            )}

            {/* Sliders */}
            <div className="bg-white border border-gray-200 rounded-2xl p-5 space-y-6">
              <p className="text-xs text-gray-400">
                💡 Health Connect auto-fill coming soon — adjust sliders manually for now.
              </p>
              {SLIDERS.map((field) => (
                <ScoreSlider key={field.key} field={field} value={values[field.key]} onChange={setField} />
              ))}
            </div>

            {/* Rugby toggle — auto-populated from Hevy */}
            <div className="bg-white border border-gray-200 rounded-2xl p-4">
              <label className="flex items-center justify-between cursor-pointer">
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-gray-800">🏉 Rugby session yesterday?</p>
                    {prefillMeta?.rugby_session_title ? (
                      <span className="text-xs bg-indigo-100 text-indigo-700 rounded-full px-1.5 py-0.5 font-medium">
                        auto
                      </span>
                    ) : (
                      <span className="text-xs bg-gray-100 text-gray-400 rounded-full px-1.5 py-0.5">
                        manual
                      </span>
                    )}
                  </div>
                  {prefillMeta?.rugby_session_title && (
                    <p className="text-xs text-indigo-500 mt-0.5">
                      Detected: {prefillMeta.rugby_session_title}
                    </p>
                  )}
                  {!prefillMeta?.rugby_session_title && (
                    <p className="text-xs text-gray-400 mt-0.5">Match or training</p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setField('rugby_session_yesterday', !values.rugby_session_yesterday)}
                  className={`relative inline-flex h-7 w-12 items-center rounded-full transition-colors ${
                    values.rugby_session_yesterday ? 'bg-indigo-600' : 'bg-gray-200'
                  }`}
                >
                  <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
                    values.rugby_session_yesterday ? 'translate-x-6' : 'translate-x-1'
                  }`} />
                </button>
              </label>
            </div>

            {/* Notes */}
            <div className="bg-white border border-gray-200 rounded-2xl p-4">
              <label className="block text-sm font-medium text-gray-800 mb-2">Notes (optional)</label>
              <textarea
                rows={2}
                value={values.notes}
                onChange={(e) => setField('notes', e.target.value)}
                placeholder="Stiffness, mood, anything worth noting…"
                className="w-full text-sm rounded-lg border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none text-gray-700"
              />
            </div>

            <button
              type="submit" disabled={submitting}
              className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-bold rounded-2xl py-4 text-base transition-colors"
            >
              {submitting ? 'Saving…' : 'Confirm Check-In'}
            </button>

          </form>
        )}
      </div>
    </div>
  )
}
