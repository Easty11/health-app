import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'

function IntegrationRow({ name, label, description, connected, onConnect, onDisconnect, connecting, disconnecting }) {
  const [key, setKey] = useState('')

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-4">
      <div className="flex items-center gap-3 mb-3">
        <span
          className={`w-2.5 h-2.5 rounded-full shrink-0 ${connected ? 'bg-green-500' : 'bg-gray-300'}`}
        />
        <div className="flex-1">
          <p className="text-sm font-semibold text-gray-900">{label}</p>
          <p className="text-xs text-gray-400">{description}</p>
        </div>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
          connected ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'
        }`}>
          {connected ? 'Connected' : 'Not connected'}
        </span>
      </div>

      {connected ? (
        <button
          onClick={onDisconnect}
          disabled={disconnecting}
          className="w-full text-xs text-red-600 hover:text-red-800 border border-red-200 hover:border-red-400 rounded-lg py-2 transition-colors disabled:opacity-40"
        >
          {disconnecting ? 'Disconnecting…' : 'Disconnect'}
        </button>
      ) : (
        <div className="flex gap-2">
          <input
            type="text"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="Paste API key…"
            className="flex-1 text-xs rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <button
            onClick={() => { onConnect(key); setKey('') }}
            disabled={connecting || !key.trim()}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white text-xs font-medium rounded-lg px-4 py-2 transition-colors shrink-0"
          >
            {connecting ? 'Saving…' : 'Connect'}
          </button>
        </div>
      )}
    </div>
  )
}

export default function Settings() {
  const [integrations, setIntegrations] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState({})
  const [toast, setToast] = useState('')

  async function loadIntegrations() {
    try {
      const { data } = await api.get('/integrations')
      setIntegrations(data)
    } catch {
      // silently ignore — 401 handler in api.js will redirect
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadIntegrations() }, [])

  function showToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(''), 3000)
  }

  async function connect(provider, apiKey) {
    setBusy((b) => ({ ...b, [provider]: 'connecting' }))
    try {
      await api.post(`/integrations/${provider}`, { api_key: apiKey })
      showToast(`${provider} connected successfully`)
      await loadIntegrations()
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to connect')
    } finally {
      setBusy((b) => ({ ...b, [provider]: null }))
    }
  }

  async function disconnect(provider) {
    setBusy((b) => ({ ...b, [provider]: 'disconnecting' }))
    try {
      await api.delete(`/integrations/${provider}`)
      showToast(`${provider} disconnected`)
      await loadIntegrations()
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to disconnect')
    } finally {
      setBusy((b) => ({ ...b, [provider]: null }))
    }
  }

  function isConnected(provider) {
    return integrations.find((i) => i.provider === provider)?.connected ?? false
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top nav */}
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3 sticky top-0 z-10">
        <Link to="/dashboard" className="text-gray-400 hover:text-gray-700 transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <span className="text-sm font-bold text-gray-900">Settings</span>
      </header>

      <div className="max-w-lg mx-auto px-4 py-6 space-y-6">
        <div>
          <h2 className="text-base font-semibold text-gray-900 mb-1">Integrations</h2>
          <p className="text-xs text-gray-500">
            Connect your fitness apps so Claude can give you personalised insights.
          </p>
        </div>

        {loading ? (
          <div className="text-center py-10 text-gray-400 text-sm">Loading…</div>
        ) : (
          <div className="space-y-3">
            <IntegrationRow
              name="hevy"
              label="Hevy"
              description="Strength training workouts and exercise history"
              connected={isConnected('hevy')}
              connecting={busy.hevy === 'connecting'}
              disconnecting={busy.hevy === 'disconnecting'}
              onConnect={(key) => connect('hevy', key)}
              onDisconnect={() => disconnect('hevy')}
            />
            {/* Future integrations go here */}
            {['MyFitnessPal', 'Polar', 'GameTraka'].map((name) => (
              <div key={name} className="bg-white border border-gray-100 rounded-2xl p-4 opacity-50">
                <div className="flex items-center gap-3">
                  <span className="w-2.5 h-2.5 rounded-full bg-gray-200 shrink-0" />
                  <div>
                    <p className="text-sm font-semibold text-gray-700">{name}</p>
                    <p className="text-xs text-gray-400">Coming soon</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-gray-900 text-white text-xs font-medium rounded-xl px-4 py-2.5 shadow-lg z-50 transition-all">
          {toast}
        </div>
      )}
    </div>
  )
}
