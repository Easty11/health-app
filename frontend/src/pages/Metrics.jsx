import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'

const STAGE = { IDLE: 'IDLE', EXTRACTING: 'EXTRACTING', CONFIRM: 'CONFIRM' }

// ---------- row classification (LAB_EXTRACTION_SCHEMA v0.3 §6) ----------

function isSuspect(r, canonicalMap) {
  const conf = r.field_confidence
  if (conf && Object.values(conf).some((v) => v < 0.85)) return true
  if (r.flag_agreement === false) return true
  if (!canonicalMap[r.marker_name_raw]) return true // unmapped — no canonical entry
  const hasUnit = !!(r.unit_canonical || r.unit_raw)
  if (r.value_num == null && r.value_qualitative == null && hasUnit) return true
  return false
}

function isClinicalFlag(r) {
  return !!(r.lab_flag || r.computed_flag)
}

function rowTier(r, canonicalMap) {
  if (isSuspect(r, canonicalMap)) return 0
  if (isClinicalFlag(r)) return 1
  return 2
}

function formatValue(r) {
  if (r.value_num != null) return `${r.value_operator || ''}${r.value_num}`
  if (r.value_qualitative) return r.value_qualitative
  return '—'
}

function formatRefRange(r) {
  const { ref_low, ref_high, ref_low_exclusive, ref_high_exclusive } = r
  if (ref_low == null && ref_high == null) return '—'
  if (ref_low == null) return `${ref_high_exclusive ? '<' : '≤'}${ref_high}`
  if (ref_high == null) return `${ref_low_exclusive ? '>' : '≥'}${ref_low}`
  return `${ref_low}–${ref_high}`
}

function confidencePct(r) {
  const conf = r.field_confidence
  if (!conf) return null
  const values = Object.values(conf)
  return Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 100)
}

function formatDate(iso) {
  if (!iso) return null
  return iso.slice(0, 10)
}

// ---------- row component ----------

function ResultRow({ r, canonicalMap }) {
  const suspect = isSuspect(r, canonicalMap)
  const flagged = !suspect && isClinicalFlag(r)
  const rowClass = suspect
    ? 'border-l-4 border-amber-400 bg-amber-50'
    : flagged
      ? 'bg-yellow-50'
      : ''
  const pct = confidencePct(r)

  return (
    <tr className={rowClass}>
      <td className="px-3 py-2 text-sm text-gray-800">{r.marker_name_raw}</td>
      <td className="px-3 py-2 text-sm font-medium text-gray-900 tabular-nums">{formatValue(r)}</td>
      <td className="px-3 py-2 text-xs text-gray-500">{r.unit_canonical || r.unit_raw || '—'}</td>
      <td className="px-3 py-2 text-xs text-gray-500 tabular-nums">{formatRefRange(r)}</td>
      <td className="px-3 py-2 text-xs">
        {r.lab_flag && <span className="font-semibold text-orange-600">{r.lab_flag}</span>}
      </td>
      <td className="px-3 py-2 text-xs">
        {r.computed_flag && <span className="font-semibold text-orange-600">{r.computed_flag}</span>}
      </td>
      <td className="px-3 py-2 text-xs text-gray-400 tabular-nums">{pct != null ? `${pct}%` : '—'}</td>
    </tr>
  )
}

// ---------- main ----------

export default function Metrics() {
  const [stage, setStage] = useState(STAGE.IDLE)
  const [extraction, setExtraction] = useState(null)
  const [canonicalMap, setCanonicalMap] = useState({})
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [toast, setToast] = useState('')
  const fileInputRef = useRef(null)

  useEffect(() => {
    api.get('/labs/canonical-map').then((res) => setCanonicalMap(res.data)).catch(() => {})
  }, [])

  function showToast(msg) {
    setToast(msg)
    setTimeout(() => setToast(''), 3000)
  }

  function reset() {
    setStage(STAGE.IDLE)
    setExtraction(null)
    setError('')
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  async function handleFileSelected(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setError('')
    setStage(STAGE.EXTRACTING)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await api.post('/labs/extract', formData)
      setExtraction(res.data)
      setStage(STAGE.CONFIRM)
    } catch (err) {
      const detail = err.response?.data?.detail
      setError((typeof detail === 'string' ? detail : detail?.error) || 'Failed to read report')
      setStage(STAGE.IDLE)
    }
  }

  async function handleConfirm() {
    setSaving(true)
    setError('')
    try {
      await api.post('/labs/confirm', extraction)
      showToast('Report saved')
      reset()
    } catch (err) {
      const detail = err.response?.data?.detail
      setError((typeof detail === 'string' ? detail : detail?.error) || 'Failed to save report')
    } finally {
      setSaving(false)
    }
  }

  const missingCollected = stage === STAGE.CONFIRM && !extraction?.report?.dates?.collected

  const sortedResults = extraction
    ? [...extraction.results].sort((a, b) => rowTier(a, canonicalMap) - rowTier(b, canonicalMap))
    : []

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3 sticky top-0 z-10">
        <Link to="/dashboard" className="text-gray-400 hover:text-gray-700 transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <span className="text-sm font-bold text-gray-900">Metrics</span>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-5 space-y-4">
        {error && (
          <div className="bg-red-50 text-red-700 text-sm rounded-lg px-3 py-2">{error}</div>
        )}

        {stage === STAGE.IDLE && (
          <div className="bg-white border border-gray-200 rounded-2xl p-8 text-center space-y-4">
            <p className="text-sm text-gray-500">Attach a lab report (PDF or photo) to extract results.</p>
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf,image/*"
              className="hidden"
              onChange={handleFileSelected}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-2xl px-6 py-3 text-sm transition-colors"
            >
              Attach Lab Report
            </button>
          </div>
        )}

        {stage === STAGE.EXTRACTING && (
          <div className="bg-white border border-gray-200 rounded-2xl p-10 text-center space-y-3">
            <div className="w-8 h-8 mx-auto rounded-full border-2 border-gray-200 border-t-indigo-600 animate-spin" />
            <p className="text-sm text-gray-500">Reading report…</p>
          </div>
        )}

        {stage === STAGE.CONFIRM && extraction && (
          <>
            {missingCollected && (
              <div className="bg-amber-50 border border-amber-200 text-amber-800 text-xs rounded-lg px-3 py-2">
                Collection date is missing — this report cannot be saved until it is filled in.
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Left: report envelope summary */}
              <div className="bg-white border border-gray-200 rounded-2xl p-5 space-y-3 md:col-span-1">
                <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">Report</p>
                <div>
                  <p className="text-sm font-semibold text-gray-900">{extraction.report.lab_name}</p>
                  <p className="text-xs text-gray-500">{extraction.report.panel_name_raw}</p>
                </div>
                <div className="text-xs text-gray-500 space-y-1">
                  <p>Collected: {formatDate(extraction.report.dates?.collected) || '—'}</p>
                  {extraction.report.referrer?.name_raw && (
                    <p>Referrer: {extraction.report.referrer.name_raw}</p>
                  )}
                </div>
                <span className="inline-block text-xs bg-gray-100 text-gray-600 rounded-full px-2 py-0.5">
                  {extraction.report.source_completeness}
                </span>
                {extraction.report.report_comments?.length > 0 && (
                  <div className="text-xs text-gray-500 border-t border-gray-100 pt-2 space-y-1">
                    {extraction.report.report_comments.map((c, i) => (
                      <p key={i} className="break-words">{c}</p>
                    ))}
                  </div>
                )}
              </div>

              {/* Right: results table */}
              <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden md:col-span-2">
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead className="bg-gray-50 border-b border-gray-200">
                      <tr>
                        <th className="px-3 py-2 text-xs font-medium text-gray-500">Marker</th>
                        <th className="px-3 py-2 text-xs font-medium text-gray-500">Value</th>
                        <th className="px-3 py-2 text-xs font-medium text-gray-500">Unit</th>
                        <th className="px-3 py-2 text-xs font-medium text-gray-500">Ref range</th>
                        <th className="px-3 py-2 text-xs font-medium text-gray-500">Lab</th>
                        <th className="px-3 py-2 text-xs font-medium text-gray-500">Computed</th>
                        <th className="px-3 py-2 text-xs font-medium text-gray-500">Conf.</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {sortedResults.map((r, i) => (
                        <ResultRow key={i} r={r} canonicalMap={canonicalMap} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={reset}
                className="flex-1 bg-white border border-gray-200 hover:bg-gray-50 text-gray-700 font-semibold rounded-2xl py-3 text-sm transition-colors"
              >
                Discard
              </button>
              <button
                onClick={handleConfirm}
                disabled={saving || missingCollected}
                className="flex-1 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold rounded-2xl py-3 text-sm transition-colors"
              >
                {saving ? 'Saving…' : 'Confirm & Save'}
              </button>
            </div>
          </>
        )}
      </div>

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-gray-900 text-white text-xs font-medium rounded-xl px-4 py-2.5 shadow-lg z-50">
          {toast}
        </div>
      )}
    </div>
  )
}
