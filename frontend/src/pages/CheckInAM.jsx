import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'

const READINESS_LABELS = ['Very tired', 'Tired', 'Okay', 'Good', 'Great']
const SORENESS_LABELS = ['None', 'Mild', 'Moderate', 'Sore', 'Very sore']

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

function PassiveCard({ hrv, hrvVsBaseline, sleepMin }) {
  if (!hrv && !sleepMin) return null
  const sign = hrvVsBaseline >= 0 ? '+' : ''
  const colour = hrvVsBaseline > 2
    ? 'text-green-600'
    : hrvVsBaseline < -5
    ? 'text-red-500'
    : 'text-amber-500'

  const h = sleepMin ? Math.floor(sleepMin / 60) : null
  const m = sleepMin ? sleepMin % 60 : null

  return (
    <div className="bg-gray-50 border border-gray-100 rounded-xl p-3 mb-5 flex gap-4">
      {hrv != null && (
        <div className="flex-1 text-center">
          <p className="text-xs text-gray-400">Ring HRV</p>
          <p className="text-lg font-bold text-gray-800">{hrv} <span className="text-xs font-normal text-gray-400">ms</span></p>
          {hrvVsBaseline != null && (
            <p className={`text-xs font-medium ${colour}`}>{sign}{hrvVsBaseline} vs 7d mean</p>
          )}
        </div>
      )}
      {sleepMin != null && (
        <div className="flex-1 text-center">
          <p className="text-xs text-gray-400">Sleep</p>
          <p className="text-lg font-bold text-gray-800">{h}h {m}m</p>
        </div>
      )}
    </div>
  )
}

export default function CheckInAM() {
  const navigate = useNavigate()

  const [prefill, setPrefill] = useState(null)
  const [submitted, setSubmitted] = useState(false)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  // Form state
  const [morningReadiness, setMorningReadiness] = useState(3)
  const [sleepQuality, setSleepQuality] = useState(3)
  const [fatigue, setFatigue] = useState(5)
  const [motivation, setMotivation] = useState(5)
  const [lifeLoad, setLifeLoad] = useState(3)
  const [soreness, setSoreness] = useState({ shoulder: 2, hamstring: 1 })
  const [drankLastNight, setDrankLastNight] = useState(false)
  const [alcoholUnits, setAlcoholUnits] = useState(2)
  const [alcoholFinishTime, setAlcoholFinishTime] = useState('22:00')

  useEffect(() => {
    api.get('/checkin-v2/prefill')
      .then(({ data }) => {
        setPrefill(data)
        if (data.existing?.am_timestamp) {
          setSubmitted(true)
          setResult(data.existing)
        } else {
          setMorningReadiness(data.morning_readiness ?? 3)
          setSleepQuality(data.sleep_quality ?? 3)
          setFatigue(data.fatigue ?? 5)
          setMotivation(data.motivation ?? 5)
          setLifeLoad(data.life_load ?? 3)
          if (data.soreness) setSoreness({ ...soreness, ...data.soreness })
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  function setSorenessRegion(region, val) {
    setSoreness(prev => ({ ...prev, [region]: val }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const { data } = await api.post('/checkin-v2/am', {
        morning_readiness: morningReadiness,
        sleep_quality: sleepQuality,
        fatigue,
        motivation,
        life_load: lifeLoad,
        soreness,
        drank_last_night: drankLastNight,
        alcohol_units: drankLastNight ? alcoholUnits : null,
        alcohol_finish_time: drankLastNight ? alcoholFinishTime : null,
      })
      setResult(data)
      setSubmitted(true)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save check-in')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-pulse text-gray-400 text-sm">Loading…</div>
      </div>
    )
  }

  if (submitted && result) {
    const nb = result.naive_baseline
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center py-10 px-4">
        <div className="w-full max-w-sm">
          <div className="text-center mb-6">
            <p className="text-3xl mb-2">✓</p>
            <h1 className="text-lg font-semibold text-gray-800">Morning check-in saved</h1>
          </div>

          {nb != null && (
            <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4 mb-4 text-center">
              <p className="text-xs text-indigo-400 uppercase tracking-wide mb-1">Readiness baseline</p>
              <p className="text-3xl font-bold text-indigo-700">{nb.toFixed(1)}<span className="text-base font-normal text-indigo-400">/10</span></p>
              <p className="text-xs text-indigo-400 mt-1">Trend indicator only — not a prescription</p>
            </div>
          )}

          <div className="space-y-2">
            <button
              onClick={() => navigate('/dashboard')}
              className="w-full bg-indigo-600 text-white rounded-xl py-3 text-sm font-medium hover:bg-indigo-700 transition-colors"
            >
              Go to Dashboard
            </button>
            <button
              onClick={() => navigate('/nightly')}
              className="w-full bg-white border border-gray-200 text-gray-600 rounded-xl py-3 text-sm font-medium hover:bg-gray-50 transition-colors"
            >
              Nightly Close-out →
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-sm mx-auto py-8 px-4">
        <div className="mb-6 flex items-center gap-3">
          <button onClick={() => navigate('/dashboard')} className="text-sm text-indigo-600 hover:text-indigo-800">← Back</button>
          <h1 className="text-lg font-semibold text-gray-800">Morning Check-in</h1>
        </div>

        {prefill && (
          <PassiveCard
            hrv={prefill.hrv_ms}
            hrvVsBaseline={prefill.hrv_vs_baseline}
            sleepMin={prefill.sleep_min}
          />
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Morning readiness */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700">How do you feel right now?</label>
            <TapSelect value={morningReadiness} onChange={setMorningReadiness} labels={READINESS_LABELS} />
            <p className="text-xs text-gray-400 text-center">{READINESS_LABELS[morningReadiness - 1]}</p>
          </div>

          {/* Sleep quality */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700">Sleep quality last night</label>
            <TapSelect value={sleepQuality} onChange={setSleepQuality} />
            <div className="flex justify-between text-xs text-gray-400"><span>Poor</span><span>Great</span></div>
          </div>

          {/* Fatigue */}
          <SliderField label="Fatigue (0 = fresh, 10 = exhausted)" value={fatigue} onChange={setFatigue} />

          {/* Motivation */}
          <SliderField label="Motivation (0 = none, 10 = fired up)" value={motivation} onChange={setMotivation} />

          {/* Life load */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-gray-700">Life/work stress yesterday</label>
            <TapSelect value={lifeLoad} onChange={setLifeLoad} />
            <div className="flex justify-between text-xs text-gray-400"><span>Very low</span><span>Very high</span></div>
          </div>

          {/* Soreness */}
          <div className="space-y-3">
            <label className="text-sm font-medium text-gray-700">Soreness</label>
            {Object.entries(soreness).map(([region, val]) => (
              <div key={region} className="space-y-1">
                <div className="flex justify-between text-xs text-gray-500">
                  <span className="capitalize">{region}</span>
                  <span className="font-medium text-gray-700">{SORENESS_LABELS[val - 1]}</span>
                </div>
                <TapSelect value={val} onChange={v => setSorenessRegion(region, v)} />
              </div>
            ))}
          </div>

          {/* Alcohol */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-gray-700">Drank last night?</label>
              <button
                type="button"
                onClick={() => setDrankLastNight(v => !v)}
                className={`w-11 h-6 rounded-full transition-colors relative ${drankLastNight ? 'bg-indigo-600' : 'bg-gray-200'}`}
              >
                <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${drankLastNight ? 'translate-x-5' : ''}`} />
              </button>
            </div>
            {drankLastNight && (
              <div className="space-y-2 pl-1">
                <SliderField label={`Units (${alcoholUnits})`} value={alcoholUnits} onChange={setAlcoholUnits} min={1} max={15} />
                <div className="space-y-1">
                  <label className="text-xs text-gray-500">Last drink time</label>
                  <input
                    type="time"
                    value={alcoholFinishTime}
                    onChange={e => setAlcoholFinishTime(e.target.value)}
                    className="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
              </div>
            )}
          </div>

          {error && (
            <div className="bg-red-50 text-red-600 text-sm rounded-lg px-3 py-2">{error}</div>
          )}

          <button
            type="submit"
            disabled={saving}
            className="w-full bg-indigo-600 text-white rounded-xl py-3 text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save Check-in'}
          </button>
        </form>
      </div>
    </div>
  )
}
