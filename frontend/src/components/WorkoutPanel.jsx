import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'

function WorkoutCard({ workout }) {
  const title = workout.title || workout.name || 'Untitled'
  const date = (workout.start_time || workout.created_at || '').slice(0, 10)
  const exercises = workout.exercises || []
  const names = [...new Set(exercises.map((e) => e.title || e.exercise_template_id).filter(Boolean))]

  return (
    <div className="border border-gray-100 rounded-xl p-3 bg-gray-50">
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
  )
}

export default function WorkoutPanel() {
  const [data, setData] = useState(null)
  const [notConnected, setNotConnected] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

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
            {/* Workout count stat */}
            <div className="bg-indigo-50 rounded-xl p-4 text-center">
              <p className="text-3xl font-bold text-indigo-700">{data.count}</p>
              <p className="text-xs text-indigo-500 font-medium mt-0.5">Total Workouts</p>
            </div>

            {/* Recent workouts */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                Recent Sessions
              </p>
              {data.workouts.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-4">No workouts found</p>
              ) : (
                <div className="space-y-2">
                  {data.workouts.map((w, i) => (
                    <WorkoutCard key={w.id ?? i} workout={w} />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
