import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import useRecoveryRefresh from '../lib/useRecoveryRefresh'

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

// Clock field for the sleep diary. `source` names the device that supplied this field's
// value (the operator confirms rather than recalls it) and is set ONLY for a field the
// prefill actually filled — an empty field is never labelled as device-supplied (S2).
// `manual` marks a field the device is systematically wrong about (latency/WASO), styled
// distinctly so the difference is legible rather than incidental (#117).
export function ClockField({ label, value, onChange, source }) {
  const prefilled = Boolean(source)
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-baseline">
        <label className="text-xs text-gray-500">{label}</label>
        {prefilled && <span className="text-[10px] text-indigo-400">from {source} · edit if wrong</span>}
      </div>
      <input
        type="time"
        value={value || ''}
        onChange={e => onChange(e.target.value)}
        className={`block w-full rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${
          prefilled
            ? 'border border-indigo-200 bg-indigo-50/40 focus:ring-indigo-300'
            : 'border border-gray-200 focus:ring-indigo-300'
        }`}
      />
    </div>
  )
}

function NumField({ label, value, onChange, hint, manual }) {
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-baseline">
        <label className="text-xs text-gray-500">{label}</label>
        {manual && <span className="text-[10px] text-amber-500">your recall — not the ring</span>}
      </div>
      <input
        type="number"
        inputMode="numeric"
        min={0}
        value={value}
        onChange={e => onChange(e.target.value)}
        className={`block w-full rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 ${
          manual
            ? 'border border-amber-200 bg-amber-50/40 focus:ring-amber-300'
            : 'border border-gray-200 focus:ring-indigo-300'
        }`}
      />
      {hint && <p className="text-[10px] text-gray-400">{hint}</p>}
    </div>
  )
}

// HRV is CURRENT wake-day only (server-side select_wakeday_hrv). No reading for today
// (absent / stale_withheld / config_error) renders "–" — an earlier night's value is never
// shown as today's. The source is labelled; a same-night pair shows the second device.
const HRV_STATES_WITH_VALUE = new Set(['value', 'pair'])

export function PassiveCard({ hrv, hrvVsBaseline, hrvState, hrvSource, hrvSecondaryMs, hrvSecondarySource, sleepMin }) {
  const hasHrv = hrv != null && HRV_STATES_WITH_VALUE.has(hrvState ?? 'value')
  const showHrvTile = hasHrv || hrvState != null
  if (!showHrvTile && sleepMin == null) return null
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
      {showHrvTile && (
        <div className="flex-1 text-center">
          <p className="text-xs text-gray-400">HRV{hasHrv && hrvSource ? ` · ${hrvSource}` : ''}</p>
          {hasHrv ? (
            <p className="text-lg font-bold text-gray-800">{hrv} <span className="text-xs font-normal text-gray-400">ms</span></p>
          ) : (
            <p className="text-lg font-bold text-gray-400" title="No HRV for today yet">–</p>
          )}
          {hasHrv && hrvVsBaseline != null && (
            <p className={`text-xs font-medium ${colour}`}>{sign}{hrvVsBaseline} vs baseline</p>
          )}
          {hasHrv && hrvSecondaryMs != null && (
            <p className="text-xs text-gray-400">{hrvSecondarySource}: {hrvSecondaryMs} ms</p>
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

// The passive tiles (HRV + sleep) — the ONLY prefill fields a background Garmin refresh may
// update. Everything else on the form is the user's, and a re-fetch never touches it.
const PASSIVE_KEYS = [
  'hrv_ms', 'hrv_vs_baseline', 'hrv_state', 'hrv_source',
  'hrv_secondary_ms', 'hrv_secondary_source', 'sleep_min',
]
const pickPassive = (data) =>
  Object.fromEntries(PASSIVE_KEYS.map((k) => [k, data?.[k] ?? null]))

export default function CheckInAM() {
  const navigate = useNavigate()

  const [prefill, setPrefill] = useState(null)
  // Passive tiles, held apart from `prefill` so the Garmin refresh can update them alone.
  const [passive, setPassive] = useState(null)
  // Set once a post-refresh re-fetch has landed, so a slower FIRST prefill load can never
  // overwrite the fresher tiles with its older snapshot.
  const refreshedRef = useRef(false)

  // Garmin HRV on-read refresh (#299 pattern, second surface): opening the check-in lands this
  // morning's night without the Recovery card being opened first. Background and fail-soft —
  // it never blocks render, input or Save. Only a REAL run (not {skipped:true}) re-fetches the
  // prefill, once, and applies the passive tiles only.
  const refetchPassive = useCallback(() => {
    api.get('/checkin-v2/prefill')
      .then(({ data }) => { refreshedRef.current = true; setPassive(pickPassive(data)) })
      .catch(() => {}) // tile stays as the first prefill had it
  }, [])
  useRecoveryRefresh({ onFreshRun: refetchPassive })
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
  const [soreness, setSoreness] = useState({})   // derived from active injuries via /prefill
  const [drankLastNight, setDrankLastNight] = useState(false)
  const [alcoholUnits, setAlcoholUnits] = useState(2)
  const [alcoholFinishTime, setAlcoholFinishTime] = useState('22:00')

  // CBT-I sleep diary (rendered only while a block is open). Clock fields are
  // prefilled from a same-day device reading; latency/WASO are always manual (#117).
  const [gotIntoBed, setGotIntoBed] = useState('')
  const [lightsOut, setLightsOut] = useState('')
  const [finalWake, setFinalWake] = useState('')
  const [outOfBed, setOutOfBed] = useState('')
  const [sleepLatency, setSleepLatency] = useState('')
  const [waso, setWaso] = useState('')
  const [nightWakings, setNightWakings] = useState('')
  const [wakeNocturia, setWakeNocturia] = useState('')
  const [wakePain, setWakePain] = useState('')
  const [wakeSpontaneous, setWakeSpontaneous] = useState('')
  const [amNotes, setAmNotes] = useState('')   // free-text; always available, not block-gated

  useEffect(() => {
    api.get('/checkin-v2/prefill')
      .then(({ data }) => {
        setPrefill(data)
        if (!refreshedRef.current) setPassive(pickPassive(data))
        if (data.existing?.am_timestamp) {
          setSubmitted(true)
          setResult(data.existing)
        } else {
          setMorningReadiness(data.morning_readiness ?? 3)
          setSleepQuality(data.sleep_quality ?? 3)
          setFatigue(data.fatigue ?? 5)
          setMotivation(data.motivation ?? 5)
          setLifeLoad(data.life_load ?? 3)
          if (data.soreness) setSoreness(data.soreness)
          // Prefill diary clock positions from the ring (empty when the sanity gate
          // rejected them). latency/WASO are never prefilled — left for manual entry.
          const dp = data.diary_prefill
          if (dp) {
            setGotIntoBed(dp.got_into_bed ?? '')
            setLightsOut(dp.lights_out ?? '')
            setFinalWake(dp.final_wake ?? '')
            setOutOfBed(dp.out_of_bed ?? '')
          }
          setAmNotes(data.existing?.am_notes ?? '')
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // Device label per diary field — only fields the prefill actually supplied (S2).
  const diarySources = prefill?.diary_prefill?.sources ?? {}

  function setSorenessRegion(region, val) {
    setSoreness(prev => ({ ...prev, [region]: val }))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    const num = v => (v === '' || v == null ? null : Number(v))
    const blockOpen = prefill?.cbti?.block_open
    const diary = blockOpen ? {
      got_into_bed: gotIntoBed || null,
      lights_out: lightsOut || null,
      sleep_latency_min: num(sleepLatency),
      waso_min: num(waso),
      night_wakings_n: num(nightWakings),
      final_wake: finalWake || null,
      out_of_bed: outOfBed || null,
      wakings_nocturia_n: num(wakeNocturia),
      wakings_pain_n: num(wakePain),
      wakings_spontaneous_n: num(wakeSpontaneous),
    } : {}
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
        am_notes: amNotes.trim() || null,
        ...diary,
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

        {passive && (
          <PassiveCard
            hrv={passive.hrv_ms}
            hrvVsBaseline={passive.hrv_vs_baseline}
            hrvState={passive.hrv_state}
            hrvSource={passive.hrv_source}
            hrvSecondaryMs={passive.hrv_secondary_ms}
            hrvSecondarySource={passive.hrv_secondary_source}
            sleepMin={passive.sleep_min}
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
            {Object.entries(soreness).length === 0 && (
              <p className="text-xs text-gray-400">No active injuries to track.</p>
            )}
            {Object.entries(soreness).map(([region, val]) => (
              <div key={region} className="space-y-1">
                <div className="flex justify-between text-xs text-gray-500">
                  <span className="capitalize">{region.replace(/_/g, ' ')}</span>
                  <span className="font-medium text-gray-700">{SORENESS_LABELS[val - 1]}</span>
                </div>
                <TapSelect value={val} onChange={v => setSorenessRegion(region, v)} />
              </div>
            ))}
          </div>

          {/* CBT-I sleep diary — only while a titration block is open */}
          {prefill?.cbti?.block_open && (
            <div className="space-y-3 border-t border-gray-100 pt-5">
              <div className="flex items-baseline justify-between">
                <label className="text-sm font-medium text-gray-700">Sleep diary</label>
                {prefill.cbti.prescribed_lights_out && (
                  <span className="text-xs text-gray-400">
                    window {prefill.cbti.prescribed_lights_out}–{prefill.cbti.wake_anchor}
                  </span>
                )}
              </div>

              {prefill.diary_prefill?.gate_rejected && (
                <p className="text-[11px] text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
                  Ring sleep times looked implausible and were not filled in — enter them manually.
                </p>
              )}

              <div className="grid grid-cols-2 gap-3">
                <ClockField label="Got into bed" value={gotIntoBed} onChange={setGotIntoBed} source={diarySources.got_into_bed} />
                <ClockField label="Lights out (tried to sleep)" value={lightsOut} onChange={setLightsOut} source={diarySources.lights_out} />
                <ClockField label="Final wake" value={finalWake} onChange={setFinalWake} source={diarySources.final_wake} />
                <ClockField label="Out of bed" value={outOfBed} onChange={setOutOfBed} source={diarySources.out_of_bed} />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <NumField label="Time to fall asleep (min)" value={sleepLatency} onChange={setSleepLatency} manual />
                <NumField label="Time awake in night (min)" value={waso} onChange={setWaso} manual />
              </div>

              {/* The cause split is MINUTES of the time awake above, not a count (#332) —
                  the columns are named *_n for history, but minutes is what was entered and
                  what separates nocturia from the insomnia signal. */}
              <p className="text-xs text-gray-500">
                Of that time awake, minutes by cause — need not add up exactly.
              </p>
              <div className="grid grid-cols-3 gap-3">
                <NumField label="Toilet (min)" value={wakeNocturia} onChange={setWakeNocturia} />
                <NumField label="Pain (min)" value={wakePain} onChange={setWakePain} />
                <NumField label="Other (min)" value={wakeSpontaneous} onChange={setWakeSpontaneous} />
              </div>

              <NumField label="Times woken" value={nightWakings} onChange={setNightWakings} />
            </div>
          )}

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

          {/* Free-text notes — always available, with or without a CBT-I block */}
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Notes (optional)</label>
            <textarea
              value={amNotes}
              onChange={e => setAmNotes(e.target.value)}
              rows={3}
              placeholder="Anything worth remembering about last night or this morning"
              className="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
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
