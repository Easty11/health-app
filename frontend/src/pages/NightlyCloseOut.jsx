import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'

function TapSelect({ value, onChange, count = 5, labels }) {
  return (
    <div className="flex gap-2">
      {Array.from({ length: count }, (_, i) => i + 1).map(n => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          title={labels?.[n - 1]}
          className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-colors ${
            value === n
              ? 'bg-indigo-600 text-white border-indigo-600'
              : 'bg-white text-gray-500 border-gray-200 hover:border-indigo-300'
          }`}
        >
          {n}
        </button>
      ))}
    </div>
  )
}

function SliderField({ label, value, onChange, min = 0, max = 10 }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-500">
        <span>{label}</span>
        <span className="font-semibold text-gray-700">{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
        className="w-full accent-indigo-600"
      />
    </div>
  )
}

const DAY_LABELS = ['Terrible', 'Poor', 'Okay', 'Good', 'Great']
const SESSION_LABELS = ['Very poor', 'Below plan', 'As planned', 'Above plan', 'Exceptional']

export default function NightlyCloseOut() {
  const navigate = useNavigate()

  const [todayRating, setTodayRating] = useState(3)
  const [trainedToday, setTrainedToday] = useState(false)
  const [sessionQuality, setSessionQuality] = useState(3)
  const [sessionRpe, setSessionRpe] = useState(7)

  const [submitted, setSubmitted] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [alreadyDone, setAlreadyDone] = useState(false)

  useEffect(() => {
    api.get('/checkin-v2/today')
      .then(({ data }) => {
        if (data?.pm_timestamp) setAlreadyDone(true)
        if (data?.session_quality) {
          setTrainedToday(true)
          setSessionQuality(data.session_quality)
        }
        if (data?.today_rating) setTodayRating(data.today_rating)
        if (data?.session_rpe != null) setSessionRpe(data.session_rpe)
      })
      .catch(() => {})
  }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await api.post('/checkin-v2/pm', {
        today_rating: todayRating,
        trained_today: trainedToday,
        session_quality: trainedToday ? sessionQuality : null,
        session_rpe: trainedToday ? sessionRpe : null,
      })
      setSubmitted(true)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save close-out')
    } finally {
      setSaving(false)
    }
  }

  if (submitted || alreadyDone) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center py-10 px-4">
        <div className="w-full max-w-sm text-center">
          <p className="text-3xl mb-3">🌙</p>
          <h1 className="text-lg font-semibold text-gray-800 mb-1">
            {alreadyDone && !submitted ? 'Already logged tonight' : 'Close-out saved'}
          </h1>
          <p className="text-sm text-gray-500 mb-6">
            Wind down — offload + gratitude (paper or your meditation app).
          </p>
          <p className="text-xs text-gray-400 mb-6">
            Mindfulness session will be read from Health Connect automatically.
          </p>
          <button
            onClick={() => navigate('/dashboard')}
            className="w-full bg-indigo-600 text-white rounded-xl py-3 text-sm font-medium hover:bg-indigo-700 transition-colors"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-sm mx-auto py-8 px-4">
        <div className="mb-6 flex items-center gap-3">
          <button onClick={() => navigate('/dashboard')} className="text-sm text-indigo-600 hover:text-indigo-800">← Back</button>
          <h1 className="text-lg font-semibold text-gray-800">Nightly Close-out</h1>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Today rating */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700">How did today land?</label>
            <TapSelect value={todayRating} onChange={setTodayRating} labels={DAY_LABELS} />
            <p className="text-xs text-gray-400 text-center">{DAY_LABELS[todayRating - 1]}</p>
          </div>

          {/* Trained today */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-gray-700">Trained today?</label>
              <button
                type="button"
                onClick={() => setTrainedToday(v => !v)}
                className={`w-11 h-6 rounded-full transition-colors relative ${trainedToday ? 'bg-indigo-600' : 'bg-gray-200'}`}
              >
                <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${trainedToday ? 'translate-x-5' : ''}`} />
              </button>
            </div>

            {trainedToday && (
              <div className="space-y-4 pl-1">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-gray-700">Session quality (planned vs actual)</label>
                  <TapSelect value={sessionQuality} onChange={setSessionQuality} labels={SESSION_LABELS} />
                  <p className="text-xs text-gray-400 text-center">{SESSION_LABELS[sessionQuality - 1]}</p>
                </div>
                <SliderField
                  label={`Session RPE (${sessionRpe})`}
                  value={sessionRpe}
                  onChange={setSessionRpe}
                />
              </div>
            )}
          </div>

          <div className="bg-blue-50 border border-blue-100 rounded-xl p-3 text-xs text-blue-500">
            Wind-down ritual (offload + gratitude) happens <em>after</em> this — borrow your meditation app or use paper. Not logged here.
          </div>

          {error && (
            <div className="bg-red-50 text-red-600 text-sm rounded-lg px-3 py-2">{error}</div>
          )}

          <button
            type="submit"
            disabled={saving}
            className="w-full bg-indigo-600 text-white rounded-xl py-3 text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save & Close the Day'}
          </button>
        </form>
      </div>
    </div>
  )
}
