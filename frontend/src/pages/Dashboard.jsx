import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import ChatPanel from '../components/ChatPanel'
import WorkoutPanel from '../components/WorkoutPanel'
import HealthPanel from '../components/HealthPanel'
import api from '../api'

function CheckInButtons() {
  const [record, setRecord] = useState(undefined) // undefined=loading

  useEffect(() => {
    api.get('/checkin-v2/today')
      .then(({ data }) => setRecord(data))
      .catch(() => setRecord(null))
  }, [])

  if (record === undefined) return null

  const amDone = !!record?.am_timestamp
  const pmDone = !!record?.pm_timestamp

  return (
    <div className="flex items-center gap-2">
      <Link
        to="/checkin-am"
        className={`flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-full transition-colors ${
          amDone
            ? 'bg-green-100 text-green-700 hover:bg-green-200'
            : 'bg-orange-100 text-orange-700 hover:bg-orange-200 animate-pulse'
        }`}
      >
        <span>{amDone ? '✓' : '☀'}</span>
        <span>AM</span>
      </Link>
      <Link
        to="/nightly"
        className={`flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-full transition-colors ${
          pmDone
            ? 'bg-green-100 text-green-700 hover:bg-green-200'
            : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
        }`}
      >
        <span>{pmDone ? '✓' : '🌙'}</span>
        <span>PM</span>
      </Link>
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const [pendingFeedback, setPendingFeedback] = useState(null)

  function logout() {
    localStorage.removeItem('token')
    navigate('/login')
  }

  function handleFeedback(message) {
    setPendingFeedback(message)
  }

  function handleFeedbackSent() {
    setPendingFeedback(null)
  }

  return (
    <div className="min-h-screen md:h-screen bg-gray-50 flex flex-col">
      {/* Top nav */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between sticky top-0 z-10">
        <span className="text-sm font-bold text-gray-900">Health &amp; Performance</span>
        <div className="flex items-center gap-3">
          <CheckInButtons />
          <Link to="/settings" className="text-xs text-gray-500 hover:text-gray-800 transition-colors">
            Settings
          </Link>
          <button
            onClick={logout}
            className="text-xs text-red-500 hover:text-red-700 transition-colors"
          >
            Sign out
          </button>
        </div>
      </header>

      {/* Two-panel layout */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* LEFT — Chat */}
        <div className="flex flex-col md:w-1/2 md:border-r border-gray-200 bg-white"
          style={{ minHeight: '60vh' }}>
          <ChatPanel
            pendingFeedback={pendingFeedback}
            onFeedbackSent={handleFeedbackSent}
          />
        </div>

        {/* RIGHT — Recovery + Training stacked */}
        <div className="md:w-1/2 flex flex-col overflow-hidden h-full border-t md:border-t-0 border-gray-200">
          <div className="flex-1 min-h-0 overflow-hidden border-b border-gray-200">
            <HealthPanel />
          </div>
          <div className="flex-1 min-h-0 overflow-hidden">
            <WorkoutPanel onFeedback={handleFeedback} />
          </div>
        </div>
      </div>
    </div>
  )
}
