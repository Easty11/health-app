import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import api from '../api'

const FIELDS = [
  { key: 'sleep_quality', label: 'Sleep Quality', min: 1, max: 10, lowLabel: 'Poor', highLabel: 'Great' },
  { key: 'fatigue', label: 'Fatigue', min: 1, max: 10, lowLabel: 'Fresh', highLabel: 'Exhausted' },
  { key: 'shoulder_pain', label: 'Shoulder Pain', min: 0, max: 10, lowLabel: 'None', highLabel: 'Severe' },
  { key: 'motivation', label: 'Motivation', min: 1, max: 10, lowLabel: 'Low', highLabel: 'High' },
]

function ScoreSlider({ field, value, onChange }) {
  const pct = ((value - field.min) / (field.max - field.min)) * 100

  // Colour: pain goes red at high end, others go green at high end
  const isPain = field.key === 'shoulder_pain'
  const colour = isPain
    ? value >= 7 ? 'text-red-600' : value >= 4 ? 'text-orange-500' : 'text-green-600'
    : value >= 7 ? 'text-green-600' : value >= 4 ? 'text-orange-500' : 'text-red-500'

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-gray-800">{field.label}</label>
        <span className={`text-xl font-bold ${colour}`}>{value}</span>
      </div>
      <input
        type="range"
        min={field.min}
        max={field.max}
        value={value}
        onChange={(e) => onChange(field.key, Number(e.target.value))}
        className="w-full h-2 rounded-lg appearance-none cursor-pointer accent-indigo-600"
        style={{
          background: `linear-gradient(to right, #4f46e5 ${pct}%, #e5e7eb ${pct}%)`,
        }}
      />
      <div className="flex justify-between text-xs text-gray-400">
        <span>{field.lowLabel}</span>
        <span>{field.highLabel}</span>
      </div>
    </div>
  )
}

function CheckInSummary({ checkin }) {
  return (
    <div className="bg-green-50 border border-green-200 rounded-2xl p-5 space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-xl">✅</span>
        <p className="text-sm font-semibold text-green-800">Checked in today</p>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {[
          { label: 'Sleep', value: `${checkin.sleep_quality}/10` },
          { label: 'Fatigue', value: `${checkin.fatigue}/10` },
          { label: 'Shoulder pain', value: `${checkin.shoulder_pain}/10` },
          { label: 'Motivation', value: `${checkin.motivation}/10` },
        ].map(({ label, value }) => (
          <div key={label} className="bg-white rounded-xl p-3 text-center">
            <p className="text-xs text-gray-400">{label}</p>
            <p className="text-lg font-bold text-gray-800">{value}</p>
          </div>
        ))}
      </div>
      {checkin.rugby_session_yesterday && (
        <p className="text-xs text-green-700 font-medium">🏉 Rugby session yesterday</p>
      )}
      {checkin.notes && (
        <p className="text-xs text-gray-600 italic">"{checkin.notes}"</p>
      )}
      <Link to="/dashboard" className="block text-center text-sm text-indigo-600 hover:underline font-medium pt-1">
        Back to dashboard
      </Link>
    </div>
  )
}

export default function CheckIn() {
  const navigate = useNavigate()
  const [existing, setExisting] = useState(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const [values, setValues] = useState({
    sleep_quality: 7,
    fatigue: 4,
    shoulder_pain: 2,
    motivation: 7,
    rugby_session_yesterday: false,
    notes: '',
  })

  useEffect(() => {
    api.get('/checkin/today')
      .then(({ data }) => { if (data) setExisting(data) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  function setField(key, val) {
    setValues((v) => ({ ...v, [key]: val }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await api.post('/checkin', values)
      navigate('/dashboard')
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to submit check-in')
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

      <div className="max-w-lg mx-auto px-4 py-6">
        {existing ? (
          <CheckInSummary checkin={existing} />
        ) : (
          <form onSubmit={handleSubmit} className="space-y-6">
            <p className="text-xs text-gray-500">
              Rate how you're feeling right now. This helps Claude tailor today's session.
            </p>

            {error && (
              <div className="bg-red-50 text-red-700 text-sm rounded-lg px-3 py-2">{error}</div>
            )}

            {/* Score sliders */}
            <div className="bg-white rounded-2xl border border-gray-200 p-5 space-y-6">
              {FIELDS.map((field) => (
                <ScoreSlider
                  key={field.key}
                  field={field}
                  value={values[field.key]}
                  onChange={setField}
                />
              ))}
            </div>

            {/* Rugby toggle */}
            <div className="bg-white rounded-2xl border border-gray-200 p-4">
              <label className="flex items-center justify-between cursor-pointer">
                <div>
                  <p className="text-sm font-medium text-gray-800">🏉 Rugby session yesterday?</p>
                  <p className="text-xs text-gray-400 mt-0.5">Match or training</p>
                </div>
                <button
                  type="button"
                  onClick={() => setField('rugby_session_yesterday', !values.rugby_session_yesterday)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    values.rugby_session_yesterday ? 'bg-indigo-600' : 'bg-gray-200'
                  }`}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                    values.rugby_session_yesterday ? 'translate-x-6' : 'translate-x-1'
                  }`} />
                </button>
              </label>
            </div>

            {/* Notes */}
            <div className="bg-white rounded-2xl border border-gray-200 p-4">
              <label className="block text-sm font-medium text-gray-800 mb-2">Notes (optional)</label>
              <textarea
                rows={3}
                value={values.notes}
                onChange={(e) => setField('notes', e.target.value)}
                placeholder="Anything else worth noting — sleep quality, stiffness, mood…"
                className="w-full text-sm rounded-lg border border-gray-200 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none text-gray-700"
              />
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold rounded-2xl py-4 text-sm transition-colors"
            >
              {submitting ? 'Submitting…' : 'Submit Check-In'}
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
