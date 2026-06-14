import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'

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

function formatMessage(workout) {
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
      if (s.weight_kg && s.reps) {
        totalVolume += s.weight_kg * s.reps
        totalSets++
        return `${s.reps}×${s.weight_kg}kg${rmStr}`
      }
      return null
    }).filter(Boolean)

    if (setDescs.length) {
      lines.push(`${exTitle}: ${setDescs.join(', ')}`)
    }
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

// ---------- WorkoutCard ----------

function WorkoutCard({ workout, onSelect }) {
  const title = workout.title || workout.name || 'Untitled'
  const date = (workout.start_time || workout.created_at || '').slice(0, 10)
  const exercises = workout.exercises || []
  const names = [...new Set(exercises.map(e => e.title || e.exercise_template_id).filter(Boolean))]

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

// ---------- SetRow ----------

function SetRow({ set, idx }) {
  const isWarmup = set.type === 'warmup'
  const rm = !isWarmup ? epley1RM(set.weight_kg, set.reps) : null
  const textClass = isWarmup ? 'text-gray-400' : 'text-gray-700'

  return (
    <tr className={`text-xs ${textClass}`}>
      <td className="py-0.5 pr-2 tabular-nums">{idx + 1}</td>
      <td className="py-0.5 pr-2 capitalize">{set.type || 'normal'}</td>
      <td className="py-0.5 pr-2 tabular-nums">
        {set.weight_kg != null ? `${set.weight_kg}kg` : '—'}
      </td>
      <td className="py-0.5 pr-2 tabular-nums">
        {set.reps != null ? set.reps : set.duration_seconds != null ? `${set.duration_seconds}s` : '—'}
      </td>
      <td className="py-0.5 tabular-nums">{rm != null ? `${rm}kg` : '—'}</td>
    </tr>
  )
}

// ---------- Detail view ----------

function WorkoutDetail({ workout, onBack, onFeedback }) {
  const [analysis, setAnalysis] = useState(undefined) // undefined=loading, null=none, obj=data
  const [analysing, setAnalysing] = useState(false)

  const workoutId = workout.id || workout.workout_id || String(workout.start_time || '')

  useEffect(() => {
    if (!workoutId) { setAnalysis(null); return }
    api.get(`/health/session-analysis/${encodeURIComponent(workoutId)}`)
      .then(({ data }) => setAnalysis(data))
      .catch(() => setAnalysis(null))
  }, [workoutId])

  const title = workout.title || workout.name || 'Untitled'
  const date = (workout.start_time || '').slice(0, 10)
  const duration = fmtDuration(workout.start_time, workout.end_time)

  // Volume summary
  let totalVolume = 0
  let totalSets = 0
  for (const ex of workout.exercises || []) {
    for (const s of ex.sets || []) {
      if (s.type === 'warmup') continue
      totalSets++
      if (s.weight_kg && s.reps) totalVolume += s.weight_kg * s.reps
    }
  }

  async function handleFeedback() {
    setAnalysing(true)
    try {
      await api.post('/health/analyse-session', {
        workout_id: workoutId,
        workout_data: workout,
      })
    } catch { /* analysis optional */ }
    const msg = formatMessage(workout)
    onFeedback(msg)
    onBack()
  }

  return (
    <div className="flex flex-col h-full">
      {/* Detail header */}
      <div className="flex-none px-4 py-3 border-b border-gray-200 bg-white">
        <button
          onClick={onBack}
          className="text-xs text-indigo-600 hover:text-indigo-800 font-medium mb-1"
        >
          ← Back
        </button>
        <h2 className="text-sm font-semibold text-gray-800">{title}</h2>
        <p className="text-xs text-gray-400 mt-0.5">
          {date}{duration ? ` · ${duration}` : ''}
        </p>
      </div>

      {/* Volume summary + analysis + button — pinned above the fold */}
      <div className="flex-none px-4 pt-3 pb-2 space-y-2 border-b border-gray-100">
        <div className="bg-indigo-50 rounded-xl p-3 grid grid-cols-3 gap-2 text-center">
          <div>
            <p className="text-base font-bold text-indigo-700">{totalSets}</p>
            <p className="text-xs text-indigo-400">Working sets</p>
          </div>
          <div>
            <p className="text-base font-bold text-indigo-700">{Math.round(totalVolume)}kg</p>
            <p className="text-xs text-indigo-400">Volume</p>
          </div>
          <div>
            <p className="text-base font-bold text-indigo-700">{duration ?? '—'}</p>
            <p className="text-xs text-indigo-400">Duration</p>
          </div>
        </div>

        {analysis && (
          <div className="bg-gray-50 border border-gray-100 rounded-xl p-3 space-y-1">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Session Analysis</p>
            <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-gray-600">
              <span>Volume {analysis.total_volume_kg}kg</span>
              {analysis.readiness_context?.hrv_ms != null && (
                <span>HRV at session: {analysis.readiness_context.hrv_ms}ms</span>
              )}
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

        <button
          onClick={handleFeedback}
          disabled={analysing}
          className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium rounded-xl py-2.5 transition-colors"
        >
          {analysing ? 'Analysing…' : 'Get AI Feedback'}
        </button>
      </div>

      {/* Exercises — scrollable reference section */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
        {(workout.exercises || []).map((ex, ei) => {
          const exTitle = ex.title || ex.exercise_template_id || 'Unknown'
          return (
            <div key={ei}>
              <p className="text-xs font-semibold text-gray-800 mb-1.5">{exTitle}</p>
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
                <tbody>
                  {(ex.sets || []).map((s, si) => (
                    <SetRow key={si} set={s} idx={si} />
                  ))}
                </tbody>
              </table>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ---------- Polar aerobic sessions ----------

const SPORT_COLOURS = {
  RUNNING: 'border-green-400 bg-green-50',
  CYCLING: 'border-blue-400 bg-blue-50',
  SWIMMING: 'border-cyan-400 bg-cyan-50',
  TRIATHLON: 'border-purple-400 bg-purple-50',
}

function fmtSeconds(secs) {
  if (!secs) return null
  const h = Math.floor(secs / 3600)
  const m = Math.floor((secs % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function fmtDistance(m) {
  if (m == null) return null
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${Math.round(m)} m`
}

function PolarSessionCard({ session }) {
  const sport = (session.sport || 'OTHER').toUpperCase()
  const colour = SPORT_COLOURS[sport] || 'border-gray-300 bg-gray-50'
  const date = session.start_time ? session.start_time.slice(0, 10) : '—'

  return (
    <div className={`border-l-4 rounded-xl p-3 ${colour}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold text-gray-800 capitalize">{sport.toLowerCase()}</p>
          <p className="text-xs text-gray-400 mt-0.5">{date}</p>
        </div>
        <div className="text-right text-xs text-gray-500 shrink-0 space-y-0.5">
          {session.duration_seconds != null && <p>{fmtSeconds(session.duration_seconds)}</p>}
          {session.distance_meters != null && <p>{fmtDistance(session.distance_meters)}</p>}
        </div>
      </div>
      {(session.avg_hr || session.max_hr) && (
        <div className="flex gap-3 mt-2 text-xs text-gray-500">
          {session.avg_hr && <span>Avg HR {session.avg_hr} bpm</span>}
          {session.max_hr && <span>Max {session.max_hr} bpm</span>}
        </div>
      )}
    </div>
  )
}

function PolarSessions() {
  const [sessions, setSessions] = useState(null)
  const [syncing, setSyncing] = useState(false)

  function load() {
    api.get('/integrations/polar/sessions')
      .then(({ data }) => setSessions(data))
      .catch(() => setSessions([]))
  }

  useEffect(load, [])

  async function handleSync() {
    setSyncing(true)
    try {
      await api.post('/integrations/polar/sync')
      load()
    } catch { /* ignore */ }
    finally { setSyncing(false) }
  }

  // Don't render anything until loaded; hide section if no sessions
  if (sessions === null || sessions.length === 0) return null

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Polar Sessions</p>
        <button
          onClick={handleSync}
          disabled={syncing}
          className="text-xs text-indigo-600 hover:text-indigo-800 font-medium disabled:opacity-40 transition-colors"
        >
          {syncing ? 'Syncing…' : 'Sync'}
        </button>
      </div>
      <div className="space-y-2">
        {sessions.map((s) => <PolarSessionCard key={s.id} session={s} />)}
      </div>
    </div>
  )
}

// ---------- Main export ----------

export default function WorkoutPanel({ onFeedback }) {
  const [data, setData] = useState(null)
  const [notConnected, setNotConnected] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedWorkout, setSelectedWorkout] = useState(null)
  const [latestAnalysis, setLatestAnalysis] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [countRes, workoutsRes] = await Promise.all([
        api.get('/integrations/hevy/workout-count'),
        api.get('/integrations/hevy/workouts?page=1&page_size=5'),
      ])
      setData({
        count: countRes.data.workout_count ?? countRes.data.count ?? 0,
        workouts: workoutsRes.data.workouts || [],
      })
      setNotConnected(false)
    } catch (err) {
      if (err.response?.status === 404) {
        setNotConnected(true)
      } else {
        setError(err.response?.data?.detail || 'Failed to load workout data')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    api.get('/health/latest-session-analysis')
      .then(({ data }) => setLatestAnalysis(data))
      .catch(() => {})
  }, [])

  if (selectedWorkout) {
    return (
      <WorkoutDetail
        workout={selectedWorkout}
        onBack={() => setSelectedWorkout(null)}
        onFeedback={onFeedback ?? (() => {})}
      />
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 bg-white flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-gray-800">Training Data</h2>
          <p className="text-xs text-gray-400 mt-0.5">Powered by Hevy</p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs text-indigo-600 hover:text-indigo-800 font-medium disabled:opacity-40 transition-colors"
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {/* Latest session analysis banner */}
        {latestAnalysis && (
          <div className="bg-gray-50 border border-gray-100 rounded-xl px-3 py-2 mb-3 text-xs text-gray-500 leading-relaxed">
            <span className="font-semibold text-gray-600 uppercase tracking-wide text-[10px]">Last Analysis</span>
            {' · '}{latestAnalysis.workout_title}
            {latestAnalysis.workout_date ? ` · ${latestAnalysis.workout_date}` : ''}
            {latestAnalysis.total_volume_kg != null ? ` · Volume ${latestAnalysis.total_volume_kg}kg` : ''}
            {latestAnalysis.readiness_context?.hrv_ms != null
              ? ` · HRV ${latestAnalysis.readiness_context.hrv_ms}ms`
              : ''}
            {latestAnalysis.top_1rm && Object.keys(latestAnalysis.top_1rm).length > 0
              ? ` · Top: ${Object.entries(latestAnalysis.top_1rm)[0][0]} ${Object.entries(latestAnalysis.top_1rm)[0][1]}kg 1RM`
              : ''}
          </div>
        )}

        {notConnected && (
          <div className="text-center py-10">
            <p className="text-3xl mb-3">🏋️</p>
            <p className="text-sm text-gray-600 font-medium mb-1">No training data yet</p>
            <p className="text-xs text-gray-400 mb-4">
              Connect Hevy in Settings to see your workouts here.
            </p>
            <Link
              to="/settings"
              className="inline-block bg-indigo-600 text-white text-xs font-medium rounded-lg px-4 py-2 hover:bg-indigo-700 transition-colors"
            >
              Go to Settings
            </Link>
          </div>
        )}

        {error && (
          <div className="bg-red-50 text-red-700 text-sm rounded-lg px-3 py-2">{error}</div>
        )}

        {data && !notConnected && (
          <div className="space-y-4">
            <div className="bg-indigo-50 rounded-xl p-4 text-center">
              <p className="text-3xl font-bold text-indigo-700">{data.count}</p>
              <p className="text-xs text-indigo-500 font-medium mt-0.5">Total Workouts</p>
            </div>

            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Recent Sessions
              </p>
              {data.workouts.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-4">No workouts found</p>
              ) : (
                <div className="space-y-2">
                  {data.workouts.map((w, i) => (
                    <WorkoutCard key={w.id ?? i} workout={w} onSelect={setSelectedWorkout} />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        <PolarSessions />
      </div>
    </div>
  )
}
