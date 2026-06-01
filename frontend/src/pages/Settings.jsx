import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'

const CATEGORIES = [
  'Injury History',
  'Training Background',
  'Goals',
  'Constraints',
  'Nutrition',
  'Recovery',
  'Other',
]

// ─── Integration row ──────────────────────────────────────────────────────────

function IntegrationRow({ label, description, connected, onConnect, onDisconnect, connecting, disconnecting }) {
  const [key, setKey] = useState('')

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-4">
      <div className="flex items-center gap-3 mb-3">
        <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${connected ? 'bg-green-500' : 'bg-gray-300'}`} />
        <div className="flex-1">
          <p className="text-sm font-semibold text-gray-900">{label}</p>
          <p className="text-xs text-gray-400">{description}</p>
        </div>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${connected ? 'bg-green-50 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
          {connected ? 'Connected' : 'Not connected'}
        </span>
      </div>
      {connected ? (
        <button onClick={onDisconnect} disabled={disconnecting}
          className="w-full text-xs text-red-600 hover:text-red-800 border border-red-200 hover:border-red-400 rounded-lg py-2 transition-colors disabled:opacity-40">
          {disconnecting ? 'Disconnecting…' : 'Disconnect'}
        </button>
      ) : (
        <div className="flex gap-2">
          <input type="text" value={key} onChange={(e) => setKey(e.target.value)}
            placeholder="Paste API key…"
            className="flex-1 text-xs rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500" />
          <button onClick={() => { onConnect(key); setKey('') }} disabled={connecting || !key.trim()}
            className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white text-xs font-medium rounded-lg px-4 py-2 transition-colors shrink-0">
            {connecting ? 'Saving…' : 'Connect'}
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Knowledge entry form (add / edit) ───────────────────────────────────────

function KnowledgeForm({ initial, onSave, onCancel, saving }) {
  const [category, setCategory] = useState(initial?.category || CATEGORIES[0])
  const [content, setContent] = useState(initial?.content || '')

  function handleSubmit(e) {
    e.preventDefault()
    if (content.trim()) onSave({ category, content: content.trim() })
  }

  return (
    <form onSubmit={handleSubmit} className="bg-indigo-50 border border-indigo-100 rounded-xl p-3 space-y-2">
      <select value={category} onChange={(e) => setCategory(e.target.value)}
        className="w-full text-xs rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white">
        {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
      </select>
      <textarea rows={3} value={content} onChange={(e) => setContent(e.target.value)}
        placeholder="e.g. Left knee tendinopathy — avoid heavy leg press"
        className="w-full text-xs rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
      <div className="flex gap-2 justify-end">
        <button type="button" onClick={onCancel}
          className="text-xs text-gray-500 hover:text-gray-700 px-3 py-1.5">
          Cancel
        </button>
        <button type="submit" disabled={saving || !content.trim()}
          className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white text-xs font-medium rounded-lg px-4 py-1.5 transition-colors">
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </form>
  )
}

// ─── Knowledge entry row ──────────────────────────────────────────────────────

function KnowledgeEntry({ entry, onEdit, onDelete, deleting }) {
  return (
    <div className="bg-white border border-gray-100 rounded-xl p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <span className="inline-block text-xs font-medium text-indigo-700 bg-indigo-50 rounded-full px-2 py-0.5 mb-1">
            {entry.category}
          </span>
          <p className="text-xs text-gray-700 leading-relaxed">{entry.content}</p>
        </div>
        <div className="flex gap-1 shrink-0">
          <button onClick={onEdit}
            className="text-gray-400 hover:text-indigo-600 transition-colors p-1" title="Edit">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </button>
          <button onClick={onDelete} disabled={deleting}
            className="text-gray-400 hover:text-red-500 transition-colors p-1 disabled:opacity-40" title="Delete">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Main Settings page ───────────────────────────────────────────────────────

export default function Settings() {
  const [integrations, setIntegrations] = useState([])
  const [intLoading, setIntLoading] = useState(true)
  const [busy, setBusy] = useState({})

  const [knowledge, setKnowledge] = useState([])
  const [knLoading, setKnLoading] = useState(true)
  const [showAddForm, setShowAddForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [savingKn, setSavingKn] = useState(false)
  const [deletingId, setDeletingId] = useState(null)

  const [toast, setToast] = useState('')

  // ── integrations ──
  async function loadIntegrations() {
    try {
      const { data } = await api.get('/integrations')
      setIntegrations(data)
    } catch { /* 401 handled globally */ } finally { setIntLoading(false) }
  }

  // ── knowledge ──
  async function loadKnowledge() {
    try {
      const { data } = await api.get('/knowledge')
      setKnowledge(data)
    } catch { /* ignore */ } finally { setKnLoading(false) }
  }

  useEffect(() => { loadIntegrations(); loadKnowledge() }, [])

  function showToast(msg) { setToast(msg); setTimeout(() => setToast(''), 3000) }

  async function connect(provider, apiKey) {
    setBusy((b) => ({ ...b, [provider]: 'connecting' }))
    try {
      await api.post(`/integrations/${provider}`, { api_key: apiKey })
      showToast(`${provider} connected`)
      await loadIntegrations()
    } catch (err) { showToast(err.response?.data?.detail || 'Failed to connect') }
    finally { setBusy((b) => ({ ...b, [provider]: null })) }
  }

  async function disconnect(provider) {
    setBusy((b) => ({ ...b, [provider]: 'disconnecting' }))
    try {
      await api.delete(`/integrations/${provider}`)
      showToast(`${provider} disconnected`)
      await loadIntegrations()
    } catch (err) { showToast(err.response?.data?.detail || 'Failed to disconnect') }
    finally { setBusy((b) => ({ ...b, [provider]: null })) }
  }

  async function saveKnowledge(data, id = null) {
    setSavingKn(true)
    try {
      if (id) {
        await api.put(`/knowledge/${id}`, data)
        showToast('Entry updated')
      } else {
        await api.post('/knowledge', data)
        showToast('Entry added')
      }
      setShowAddForm(false)
      setEditingId(null)
      await loadKnowledge()
    } catch (err) { showToast(err.response?.data?.detail || 'Failed to save') }
    finally { setSavingKn(false) }
  }

  async function deleteKnowledge(id) {
    setDeletingId(id)
    try {
      await api.delete(`/knowledge/${id}`)
      showToast('Entry deleted')
      await loadKnowledge()
    } catch (err) { showToast(err.response?.data?.detail || 'Failed to delete') }
    finally { setDeletingId(null) }
  }

  function isConnected(provider) {
    return integrations.find((i) => i.provider === provider)?.connected ?? false
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3 sticky top-0 z-10">
        <Link to="/dashboard" className="text-gray-400 hover:text-gray-700 transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <span className="text-sm font-bold text-gray-900">Settings</span>
      </header>

      <div className="max-w-lg mx-auto px-4 py-6 space-y-8">

        {/* ── Integrations ── */}
        <section className="space-y-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900 mb-1">Integrations</h2>
            <p className="text-xs text-gray-500">Connect your fitness apps so Claude can give you personalised insights.</p>
          </div>
          {intLoading ? (
            <div className="text-center py-6 text-gray-400 text-sm">Loading…</div>
          ) : (
            <div className="space-y-3">
              <IntegrationRow
                label="Hevy" description="Strength training workouts and exercise history"
                connected={isConnected('hevy')}
                connecting={busy.hevy === 'connecting'} disconnecting={busy.hevy === 'disconnecting'}
                onConnect={(key) => connect('hevy', key)} onDisconnect={() => disconnect('hevy')}
              />
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
        </section>

        {/* ── Knowledge Base ── */}
        <section className="space-y-3">
          <div className="flex items-end justify-between">
            <div>
              <h2 className="text-base font-semibold text-gray-900 mb-1">Knowledge Base</h2>
              <p className="text-xs text-gray-500">
                Tell Claude about your background, injuries, goals, and constraints.
                This context is included in every conversation.
              </p>
            </div>
            {!showAddForm && (
              <button onClick={() => { setShowAddForm(true); setEditingId(null) }}
                className="shrink-0 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium rounded-lg px-3 py-1.5 transition-colors">
                + Add
              </button>
            )}
          </div>

          {showAddForm && (
            <KnowledgeForm
              onSave={(data) => saveKnowledge(data)}
              onCancel={() => setShowAddForm(false)}
              saving={savingKn}
            />
          )}

          {knLoading ? (
            <div className="text-center py-6 text-gray-400 text-sm">Loading…</div>
          ) : knowledge.length === 0 && !showAddForm ? (
            <div className="text-center py-8 text-gray-400">
              <p className="text-2xl mb-2">📋</p>
              <p className="text-xs">No entries yet. Add your first one above.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {knowledge.map((entry) =>
                editingId === entry.id ? (
                  <KnowledgeForm key={entry.id} initial={entry}
                    onSave={(data) => saveKnowledge(data, entry.id)}
                    onCancel={() => setEditingId(null)}
                    saving={savingKn}
                  />
                ) : (
                  <KnowledgeEntry key={entry.id} entry={entry}
                    onEdit={() => { setEditingId(entry.id); setShowAddForm(false) }}
                    onDelete={() => deleteKnowledge(entry.id)}
                    deleting={deletingId === entry.id}
                  />
                )
              )}
            </div>
          )}
        </section>

      </div>

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-gray-900 text-white text-xs font-medium rounded-xl px-4 py-2.5 shadow-lg z-50">
          {toast}
        </div>
      )}
    </div>
  )
}
