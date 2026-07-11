import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'

// ── helpers ────────────────────────────────────────────────────────────────────

function epley1RM(weightKg, reps) {
  if (!weightKg || !reps || weightKg <= 0 || reps <= 0) return null
  return Math.round(weightKg * (1 + reps / 30))
}

function fmtDuration(start, end) {
  if (!start || !end) return null
  try {
    const mins = Math.round((new Date(end) - new Date(start)) / 60000)
    const h = Math.floor(mins / 60)
    const m = mins % 60
    return h > 0 ? `${h}h ${m}m` : `${m}m`
  } catch { return null }
}

function fmtSeconds(secs) {
  if (!secs) return null
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function fmtDate(iso) {
  if (!iso) return '—'
  return iso.slice(0, 10)
}

function sportColour(sport) {
  const s = (sport || '').toLowerCase()
  if (s.includes('run')) return 'border-green-400 bg-green-50'
  if (s.includes('cycl') || s.includes('bike')) return 'border-blue-400 bg-blue-50'
  if (s.includes('swim')) return 'border-cyan-400 bg-cyan-50'
  if (s.includes('row')) return 'border-teal-400 bg-teal-50'
  if (s.includes('ski')) return 'border-indigo-400 bg-indigo-50'
  if (s.includes('strength') || s.includes('weight')) return 'border-orange-400 bg-orange-50'
  if (s.includes('fitness') || s.includes('functional') || s.includes('crossfit') || s.includes('aerobic')) return 'border-red-400 bg-red-50'
  return 'border-gray-300 bg-gray-50'
}

function formatHevyMessage(workout) {
  const title = workout.title || workout.name || 'Untitled'
  const date = (workout.start_time || '').slice(0, 10)
  const duration = fmtDuration(workout.start_time, workout.end_time)
  const durationStr = duration ? ` (${duration})` : ''
  let totalVolume = 0
  let totalSets = 0
  const lines = []
  for (const ex of workout.exercises || []) {
    const exTitle = ex.title || ex.exercise_template_id || 'Unknown'
    const workingSets = (ex.sets || []).filter(s => s.type !== 'warmup')
    const setDescs = workingSets.map(s => {
      const rm = epley1RM(s.weight_kg, s.reps)
      const rmStr = rm ? ` (est. 1RM: ${rm}kg)` : ''
      if (s.weight_kg && s.reps) { totalVolume += s.weight_kg * s.reps; totalSets++ }
      return s.weight_kg && s.reps ? `${s.reps}×${s.weight_kg}kg${rmStr}` : null
    }).filter(Boolean)
    if (setDescs.length) lines.push(`${exTitle}: ${setDescs.join(', ')}`)
  }
  return [
    `Can you give me feedback on this session?`,
    ``,
    `${title} — ${date}${durationStr}`,
    ``,
    ...lines,
    ``,
    `Total volume: ${Math.round(totalVolume)}kg across ${totalSets} sets`,
  ].join('\n')
}

// aerobic_sessions schema → shape the Polar card/detail components consume
function normalizePolar(s) {
  return {
    id: s.id,
    sport: s.sport_name || 'Session',
    start_time: s.start_time || s.session_date,
    duration_seconds: s.duration_minutes != null ? Math.round(s.duration_minutes * 60) : null,
    avg_hr: s.hr_avg,
    max_hr: s.hr_max,
    calories: s.calories,
    cardio_load: s.cardio_load,
    recovery_hours: s.recovery_hours,
    hr_zones: {
      z1_seconds: s.z1_seconds, z2_seconds: s.z2_seconds, z3_seconds: s.z3_seconds,
      z4_seconds: s.z4_seconds, z5_seconds: s.z5_seconds,
    },
  }
}

function formatPolarMessage(session) {
  const sport = session.sport || 'Session'
  const date = fmtDate(session.start_time)
  const duration = fmtSeconds(session.duration_seconds)
  const parts = [
    `Can you give me feedback on this aerobic session?`,
    ``,
    `${sport} — ${date}${duration ? ` (${duration})` : ''}`,
  ]
  if (session.avg_hr) parts.push(`Avg HR: ${session.avg_hr} bpm`)
  if (session.max_hr) parts.push(`Max HR: ${session.max_hr} bpm`)
  if (session.calories) parts.push(`Calories: ${session.calories}`)
  if (session.cardio_load != null) parts.push(`Cardio load: ${Math.round(session.cardio_load)}`)
  if (session.recovery_hours != null) parts.push(`Recovery: ${Math.round(session.recovery_hours)}h`)
  const z = session.hr_zones || {}
  const zones = ['z1_seconds','z2_seconds','z3_seconds','z4_seconds','z5_seconds']
    .map((k, i) => z[k] ? `Z${i+1}: ${fmtSeconds(z[k])}` : null).filter(Boolean)
  if (zones.length) parts.push(`HR Zones: ${zones.join(', ')}`)
  return parts.join('\n')
}

// ── Hevy components ────────────────────────────────────────────────────────────

function WorkoutCard({ workout, onSelect }) {
  const title = workout.title || workout.name || 'Untitled'
  const date = fmtDate(workout.start_time || workout.created_at)
  const names = [...new Set((workout.exercises || []).map(e => e.title || e.exercise_template_id).filter(Boolean))]
  return (
    <div
      onClick={() => onSelect(workout)}
      className="border border-gray-100 rounded-xl p-3 bg-gray-50 cursor-pointer hover:bg-indigo-50 hover:border-indigo-200 transition-colors flex items-start justify-between gap-2"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <span className="text-sm font-medium text-gray-800">{title}</span>
          {date && <span className="text-xs text-gray-400 shrink-0">{date}</span>}
        </div>
        {names.length > 0 && (
          <p className="text-xs text-gray-500 mt-1 leading-relaxed">
            {names.slice(0, 5).join(' · ')}{names.length > 5 ? ` +${names.length - 5} more` : ''}
          </p>
        )}
      </div>
      <span className="text-gray-300 text-lg leading-none shrink-0">›</span>
    </div>
  )
}

function SetRow({ set, idx }) {
  const isWarmup = set.type === 'warmup'
  const rm = !isWarmup ? epley1RM(set.weight_kg, set.reps) : null
  return (
    <tr className={`text-xs ${isWarmup ? 'text-gray-400' : 'text-gray-700'}`}>
      <td className="py-0.5 pr-2 tabular-nums">{idx + 1}</td>
      <td className="py-0.5 pr-2 capitalize">{set.type || 'normal'}</td>
      <td className="py-0.5 pr-2 tabular-nums">{set.weight_kg != null ? `${set.weight_kg}kg` : '—'}</td>
      <td className="py-0.5 pr-2 tabular-nums">
        {set.reps != null ? set.reps : set.duration_seconds != null ? `${set.duration_seconds}s` : '—'}
      </td>
      <td className="py-0.5 tabular-nums">{rm != null ? `${rm}kg` : '—'}</td>
    </tr>
  )
}

function WorkoutDetail({ workout, onBack, onFeedback }) {
  const [analysis, setAnalysis] = useState(undefined)
  const [analysing, setAnalysing] = useState(false)
  const workoutId = workout.id || workout.workout_id || String(workout.start_time || '')

  useEffect(() => {
    if (!workoutId) { setAnalysis(null); return }
    api.get(`/health/session-analysis/${encodeURIComponent(workoutId)}`)
      .then(({ data }) => setAnalysis(data))
      .catch(() => setAnalysis(null))
  }, [workoutId])

  const title = workout.title || workout.name || 'Untitled'
  const date = fmtDate(workout.start_time)
  const duration = fmtDuration(workout.start_time, workout.end_time)
  let totalVolume = 0; let totalSets = 0
  for (const ex of workout.exercises || [])
    for (const s of ex.sets || []) {
      if (s.type === 'warmup') continue
      totalSets++
      if (s.weight_kg && s.reps) totalVolume += s.weight_kg * s.reps
    }

  async function handleFeedback() {
    setAnalysing(true)
    try { await api.post('/health/analyse-session', { workout_id: workoutId, workout_data: workout }) }
    catch { /* optional */ }
    onFeedback(formatHevyMessage(workout))
    onBack()
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-none px-4 py-3 border-b border-gray-200 bg-white">
        <button onClick={onBack} className="text-xs text-indigo-600 hover:text-indigo-800 font-medium mb-1">← Back</button>
        <h2 className="text-sm font-semibold text-gray-800">{title}</h2>
        <p className="text-xs text-gray-400 mt-0.5">{date}{duration ? ` · ${duration}` : ''}</p>
      </div>
      <div className="flex-none px-4 pt-3 pb-2 space-y-2 border-b border-gray-100">
        <div className="bg-indigo-50 rounded-xl p-3 grid grid-cols-3 gap-2 text-center">
          <div><p className="text-base font-bold text-indigo-700">{totalSets}</p><p className="text-xs text-indigo-400">Working sets</p></div>
          <div><p className="text-base font-bold text-indigo-700">{Math.round(totalVolume)}kg</p><p className="text-xs text-indigo-400">Volume</p></div>
          <div><p className="text-base font-bold text-indigo-700">{duration ?? '—'}</p><p className="text-xs text-indigo-400">Duration</p></div>
        </div>
        {analysis && (
          <div className="bg-gray-50 border border-gray-100 rounded-xl p-3 space-y-1">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Session Analysis</p>
            <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-gray-600">
              <span>Volume {analysis.total_volume_kg}kg</span>
              {analysis.readiness_context?.hrv_ms != null && <span>HRV at session: {analysis.readiness_context.hrv_ms}ms</span>}
            </div>
            {analysis.top_1rm && Object.keys(analysis.top_1rm).length > 0 && (
              <div className="text-xs text-gray-500 mt-1">
                {Object.entries(analysis.top_1rm).slice(0, 3).map(([ex, rm]) => (
                  <span key={ex} className="mr-3">{ex} {rm}kg 1RM</span>
                ))}
              </div>
            )}
          </div>
        )}
        <button onClick={handleFeedback} disabled={analysing}
          className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded-xl py-2.5 transition-colors">
          {analysing ? 'Analysing…' : 'Get AI Feedback'}
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        {(workout.exercises || []).map((ex, ei) => (
          <div key={ei}>
            <p className="text-xs font-semibold text-gray-800 mb-1.5">{ex.title || ex.exercise_template_id || 'Unknown'}</p>
            <table className="w-full">
              <thead>
                <tr className="text-xs text-gray-400 border-b border-gray-100">
                  <th className="text-left py-0.5 pr-2 font-normal">#</th>
                  <th className="text-left py-0.5 pr-2 font-normal">Type</th>
                  <th className="text-left py-0.5 pr-2 font-normal">Weight</th>
                  <th className="text-left py-0.5 pr-2 font-normal">Reps</th>
                  <th className="text-left py-0.5 font-normal">Est 1RM</th>
                </tr>
              </thead>
              <tbody>{(ex.sets || []).map((s, si) => <SetRow key={si} set={s} idx={si} />)}</tbody>
            </table>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Polar components ───────────────────────────────────────────────────────────

function PolarSessionCard({ session, onSelect }) {
  const colour = sportColour(session.sport)
  const duration = fmtSeconds(session.duration_seconds)
  return (
    <div
      onClick={() => onSelect(session)}
      className={`border-l-4 rounded-xl p-3 cursor-pointer hover:opacity-80 transition-opacity flex items-start justify-between gap-2 ${colour}`}
    >
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-800 capitalize">{session.sport || 'Session'}</p>
        <p className="text-xs text-gray-400 mt-0.5">{fmtDate(session.start_time)}</p>
        {(session.avg_hr || session.max_hr) && (
          <p className="text-xs text-gray-500 mt-1">
            {session.avg_hr ? `Avg ${session.avg_hr} bpm` : ''}
            {session.avg_hr && session.max_hr ? ' · ' : ''}
            {session.max_hr ? `Max ${session.max_hr} bpm` : ''}
          </p>
        )}
      </div>
      <div className="text-right text-xs text-gray-500 shrink-0 space-y-0.5">
        {duration && <p className="font-medium">{duration}</p>}
        {session.calories && <p>{session.calories} kcal</p>}
        <span className="text-gray-300 text-lg leading-none">›</span>
      </div>
    </div>
  )
}

function HRZoneBar({ zones }) {
  const keys = ['z1_seconds','z2_seconds','z3_seconds','z4_seconds','z5_seconds']
  const values = keys.map(k => zones[k] || 0)
  const total = values.reduce((a, b) => a + b, 0)
  if (!total) return null
  const colours = ['bg-blue-300','bg-green-400','bg-yellow-400','bg-orange-400','bg-red-500']
  const labels = ['Z1','Z2','Z3','Z4','Z5']
  return (
    <div>
      <div className="flex rounded-full overflow-hidden h-3 gap-0.5">
        {values.map((v, i) => v > 0 ? (
          <div key={i} className={`${colours[i]} h-full`} style={{ width: `${(v / total) * 100}%` }} />
        ) : null)}
      </div>
      <div className="flex gap-3 mt-1.5 flex-wrap">
        {values.map((v, i) => v > 0 ? (
          <span key={i} className="text-xs text-gray-500">
            <span className={`inline-block w-2 h-2 rounded-full mr-1 ${colours[i]}`} />
            {labels[i]} {fmtSeconds(v)}
          </span>
        ) : null)}
      </div>
    </div>
  )
}

function PolarDetail({ session, onBack, onFeedback }) {
  const [sending, setSending] = useState(false)
  const colour = sportColour(session.sport)
  const duration = fmtSeconds(session.duration_seconds)
  const zones = session.hr_zones || {}

  async function handleFeedback() {
    setSending(true)
    onFeedback(formatPolarMessage(session))
    onBack()
  }

  return (
    <div className="flex flex-col h-full">
      <div className={`flex-none px-4 py-3 border-b border-gray-200 border-l-4 ${colour}`}>
        <button onClick={onBack} className="text-xs text-indigo-600 hover:text-indigo-800 font-medium mb-1">← Back</button>
        <h2 className="text-sm font-semibold text-gray-800 capitalize">{session.sport || 'Session'}</h2>
        <p className="text-xs text-gray-400 mt-0.5">{fmtDate(session.start_time)}{duration ? ` · ${duration}` : ''}</p>
      </div>

      <div className="flex-none px-4 pt-3 pb-3 space-y-3 border-b border-gray-100">
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="bg-red-50 rounded-xl p-3">
            <p className="text-base font-bold text-red-600">{session.avg_hr ?? '—'}</p>
            <p className="text-xs text-red-400">Avg HR</p>
          </div>
          <div className="bg-red-50 rounded-xl p-3">
            <p className="text-base font-bold text-red-600">{session.max_hr ?? '—'}</p>
            <p className="text-xs text-red-400">Max HR</p>
          </div>
          <div className="bg-gray-50 rounded-xl p-3">
            <p className="text-base font-bold text-gray-700">{session.calories ?? '—'}</p>
            <p className="text-xs text-gray-400">kcal</p>
          </div>
        </div>

        {(session.cardio_load != null || session.recovery_hours != null) && (
          <div className="grid grid-cols-2 gap-2 text-center">
            <div className="bg-indigo-50 rounded-xl p-3">
              <p className="text-base font-bold text-indigo-700">
                {session.cardio_load != null ? Math.round(session.cardio_load) : '—'}
              </p>
              <p className="text-xs text-indigo-400">Cardio load</p>
            </div>
            <div className="bg-emerald-50 rounded-xl p-3">
              <p className="text-base font-bold text-emerald-700">
                {session.recovery_hours != null ? `${Math.round(session.recovery_hours)}h` : '—'}
              </p>
              <p className="text-xs text-emerald-400">Recovery</p>
            </div>
          </div>
        )}

        {Object.values(zones).some(v => v > 0) && (
          <div className="bg-gray-50 rounded-xl p-3 space-y-2">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">HR Zones</p>
            <HRZoneBar zones={zones} />
          </div>
        )}

        <button onClick={handleFeedback} disabled={sending}
          className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded-xl py-2.5 transition-colors">
          {sending ? 'Sending…' : 'Get AI Feedback'}
        </button>
      </div>
    </div>
  )
}

// ── Main export ────────────────────────────────────────────────────────────────

export default function WorkoutPanel({ onFeedback }) {
  // view state machine
  const [view, setView] = useState('list')       // list | hevy-history | hevy-detail | polar-history | polar-detail
  const [selectedWorkout, setSelectedWorkout] = useState(null)
  const [selectedPolar, setSelectedPolar] = useState(null)
  const [detailBack, setDetailBack] = useState('list')

  // list-view data
  const [hevyCount, setHevyCount] = useState(null)
  const [latestHevy, setLatestHevy] = useState(null)
  const [latestPolar, setLatestPolar] = useState(null)
  const [latestAnalysis, setLatestAnalysis] = useState(null)
  const [notConnected, setNotConnected] = useState(false)
  const [loading, setLoading] = useState(true)

  // history-view data
  const [hevyWorkouts, setHevyWorkouts] = useState([])
  const [polarSessions, setPolarSessions] = useState([])
  const [polarSyncing, setPolarSyncing] = useState(false)

  const loadList = useCallback(async () => {
    setLoading(true)
    try {
      const [countRes, workoutsRes, polarRes] = await Promise.all([
        api.get('/integrations/hevy/workout-count'),
        api.get('/integrations/hevy/workouts?page=1&page_size=1'),
        api.get('/integrations/polar/aerobic-sessions?limit=1').catch(() => ({ data: [] })),
      ])
      setHevyCount(countRes.data.workout_count ?? countRes.data.count ?? 0)
      setLatestHevy((workoutsRes.data.workouts || [])[0] || null)
      setLatestPolar(polarRes.data[0] ? normalizePolar(polarRes.data[0]) : null)
      setNotConnected(false)
    } catch (err) {
      if (err.response?.status === 404) setNotConnected(true)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadList() }, [loadList])

  useEffect(() => {
    api.get('/health/latest-session-analysis')
      .then(({ data }) => setLatestAnalysis(data))
      .catch(() => {})
  }, [])

  function openHevyDetail(workout, back = 'list') {
    setSelectedWorkout(workout)
    setDetailBack(back)
    setView('hevy-detail')
  }

  function openPolarDetail(session, back = 'list') {
    setSelectedPolar(session)
    setDetailBack(back)
    setView('polar-detail')
  }

  async function openHevyHistory() {
    if (hevyWorkouts.length === 0) {
      // "See all" = genuinely all workouts. The backend loops every Hevy /workouts
      // page (pageSize caps at 10) and returns the full history in one response.
      const res = await api.get('/integrations/hevy/workouts/all')
      setHevyWorkouts(res.data.workouts || [])
    }
    setView('hevy-history')
  }

  async function openPolarHistory() {
    if (polarSessions.length === 0) {
      const res = await api.get('/integrations/polar/aerobic-sessions?limit=200').catch(() => ({ data: [] }))
      setPolarSessions(res.data.map(normalizePolar))
    }
    setView('polar-history')
  }

  async function handlePolarSync() {
    setPolarSyncing(true)
    try {
      await api.post('/integrations/polar/sync')
      const res = await api.get('/integrations/polar/aerobic-sessions?limit=200').catch(() => ({ data: [] }))
      const norm = res.data.map(normalizePolar)
      setPolarSessions(norm)
      if (norm.length) setLatestPolar(norm[0])
    } catch { /* ignore */ }
    finally { setPolarSyncing(false) }
  }

  // ── hevy detail ──
  if (view === 'hevy-detail' && selectedWorkout) {
    return (
      <WorkoutDetail
        workout={selectedWorkout}
        onBack={() => setView(detailBack)}
        onFeedback={onFeedback ?? (() => {})}
      />
    )
  }

  // ── polar detail ──
  if (view === 'polar-detail' && selectedPolar) {
    return (
      <PolarDetail
        session={selectedPolar}
        onBack={() => setView(detailBack)}
        onFeedback={onFeedback ?? (() => {})}
      />
    )
  }

  // ── hevy history ──
  if (view === 'hevy-history') {
    return (
      <div className="flex flex-col h-full">
        <div className="flex-none px-4 py-3 border-b border-gray-200 bg-white">
          <button onClick={() => setView('list')} className="text-xs text-indigo-600 hover:text-indigo-800 font-medium mb-1">← Back</button>
          <h2 className="text-sm font-semibold text-gray-800">Hevy History</h2>
          <p className="text-xs text-gray-400 mt-0.5">{hevyCount != null ? `${hevyCount} total workouts` : ''}</p>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2">
          {hevyWorkouts.map((w, i) => (
            <WorkoutCard key={w.id ?? i} workout={w} onSelect={w => openHevyDetail(w, 'hevy-history')} />
          ))}
        </div>
      </div>
    )
  }

  // ── polar history ──
  if (view === 'polar-history') {
    return (
      <div className="flex flex-col h-full">
        <div className="flex-none px-4 py-3 border-b border-gray-200 bg-white flex items-start justify-between">
          <div>
            <button onClick={() => setView('list')} className="text-xs text-indigo-600 hover:text-indigo-800 font-medium mb-1">← Back</button>
            <h2 className="text-sm font-semibold text-gray-800">Polar History</h2>
            <p className="text-xs text-gray-400 mt-0.5">{polarSessions.length} sessions</p>
          </div>
          <button onClick={handlePolarSync} disabled={polarSyncing}
            className="text-xs text-indigo-600 hover:text-indigo-800 font-medium disabled:opacity-40 mt-5">
            {polarSyncing ? 'Syncing…' : 'Sync'}
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-2">
          {polarSessions.length === 0
            ? <p className="text-xs text-gray-400 text-center py-6">No sessions yet — tap Sync.</p>
            : polarSessions.map(s => (
                <PolarSessionCard key={s.id} session={s} onSelect={s => openPolarDetail(s, 'polar-history')} />
              ))
          }
        </div>
      </div>
    )
  }

  // ── list (default) ──
  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 bg-white">
        <h2 className="text-sm font-semibold text-gray-800">Training Data</h2>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {latestAnalysis && (
          <div className="bg-gray-50 border border-gray-100 rounded-xl px-3 py-2 text-xs text-gray-500 leading-relaxed">
            <span className="font-semibold text-gray-600 uppercase tracking-wide text-[10px]">Last Analysis</span>
            {' · '}{latestAnalysis.workout_title}
            {latestAnalysis.workout_date ? ` · ${latestAnalysis.workout_date}` : ''}
            {latestAnalysis.total_volume_kg != null ? ` · Volume ${latestAnalysis.total_volume_kg}kg` : ''}
            {latestAnalysis.readiness_context?.hrv_ms != null ? ` · HRV ${latestAnalysis.readiness_context.hrv_ms}ms` : ''}
          </div>
        )}

        {notConnected && (
          <div className="text-center py-10">
            <p className="text-3xl mb-3">🏋️</p>
            <p className="text-sm text-gray-600 font-medium mb-1">No training data yet</p>
            <p className="text-xs text-gray-400 mb-4">Connect Hevy in Settings to see your workouts here.</p>
            <Link to="/settings" className="inline-block bg-indigo-600 text-white text-xs font-medium rounded-lg px-4 py-2 hover:bg-indigo-700 transition-colors">
              Go to Settings
            </Link>
          </div>
        )}

        {/* Hevy section */}
        {!notConnected && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                Strength {hevyCount != null ? `· ${hevyCount} total` : ''}
              </p>
              <button onClick={openHevyHistory} className="text-xs text-indigo-600 hover:text-indigo-800 font-medium">
                See all →
              </button>
            </div>
            {loading
              ? <p className="text-xs text-gray-400">Loading…</p>
              : latestHevy
                ? <WorkoutCard workout={latestHevy} onSelect={w => openHevyDetail(w, 'list')} />
                : <p className="text-xs text-gray-400">No workouts found</p>
            }
          </div>
        )}

        {/* Polar section */}
        {latestPolar !== undefined && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Aerobic</p>
              <button onClick={openPolarHistory} className="text-xs text-indigo-600 hover:text-indigo-800 font-medium">
                See all →
              </button>
            </div>
            {latestPolar
              ? <PolarSessionCard session={latestPolar} onSelect={s => openPolarDetail(s, 'list')} />
              : <p className="text-xs text-gray-400">No sessions yet</p>
            }
          </div>
        )}
      </div>
    </div>
  )
}
