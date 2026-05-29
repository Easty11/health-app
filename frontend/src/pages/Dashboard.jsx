import { useNavigate, Link } from 'react-router-dom'
import ChatPanel from '../components/ChatPanel'
import WorkoutPanel from '../components/WorkoutPanel'

export default function Dashboard() {
  const navigate = useNavigate()

  function logout() {
    localStorage.removeItem('token')
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Top nav */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center justify-between sticky top-0 z-10">
        <span className="text-sm font-bold text-gray-900">Health &amp; Performance</span>
        <div className="flex items-center gap-3">
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
          <ChatPanel />
        </div>

        {/* RIGHT — Data */}
        <div className="flex flex-col md:w-1/2 bg-white border-t md:border-t-0 border-gray-200"
          style={{ minHeight: '40vh' }}>
          <WorkoutPanel />
        </div>
      </div>
    </div>
  )
}
