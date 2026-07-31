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

// ---------- stored results read-back (#59 consumer; #47 raw values only) ----------
// Deliberately NOT the confirm ResultRow: no confidence, no computed_flag, no
// suspect-classification — those are extraction QA. This is the user's own data,
// shown as values / lab reference ranges / lab-asserted flags only. Interpreted
// meaning (deltas, mechanisms, levers) is the 4b view, not this surface (#49).

function StoredResultRow({ r }) {
  return (
    <tr className={r.lab_flag ? 'bg-yellow-50' : ''}>
      <td className="px-3 py-2 text-sm text-gray-800">{r.marker_name_raw}</td>
      <td className="px-3 py-2 text-sm font-medium text-gray-900 tabular-nums">{formatValue(r)}</td>
      <td className="px-3 py-2 text-xs text-gray-500">{r.unit_canonical || '—'}</td>
      <td className="px-3 py-2 text-xs text-gray-500 tabular-nums">{formatRefRange(r)}</td>
      <td className="px-3 py-2 text-xs">
        {r.lab_flag && <span className="font-semibold text-orange-600">{r.lab_flag}</span>}
      </td>
    </tr>
  )
}

function StoredReportCard({ report }) {
  // A report with no rows previously rendered as column headings above nothing, which reads
  // as "this report had no results" — legitimate emptiness — rather than "something went
  // wrong". Same failure shape as a masked band change: absence presenting as a normal
  // state. An empty report is never normal; a lab report that produced no stored marker is
  // a fault, and says so instead of rendering a table it has no rows for.
  const empty = report.results.length === 0
  return (
    <div className={`bg-white border rounded-2xl overflow-hidden ${empty ? 'border-red-200' : 'border-gray-200'}`}>
      <div className="px-4 py-3 border-b border-gray-100 flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900 truncate">{report.panel_name_raw}</p>
          <p className="text-xs text-gray-500 truncate">{report.lab_name}</p>
        </div>
        <p className="text-xs text-gray-400 tabular-nums shrink-0">{formatDate(report.collected_date)}</p>
      </div>
      {empty ? (
        <div className="px-4 py-3 bg-red-50 space-y-1">
          <p className="text-xs font-semibold text-red-800">No results stored for this report</p>
          <p className="text-xs text-red-700">
            The report was filed but no marker was saved against it. This usually means every
            marker was already recorded for {formatDate(report.collected_date)} and the upload
            was a repeat — your values are held on the earlier report, not here.
          </p>
        </div>
      ) : (
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-3 py-2 text-xs font-medium text-gray-500">Marker</th>
              <th className="px-3 py-2 text-xs font-medium text-gray-500">Value</th>
              <th className="px-3 py-2 text-xs font-medium text-gray-500">Unit</th>
              <th className="px-3 py-2 text-xs font-medium text-gray-500">Ref range</th>
              <th className="px-3 py-2 text-xs font-medium text-gray-500">Flag</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {report.results.map((r, i) => <StoredResultRow key={i} r={r} />)}
          </tbody>
        </table>
      </div>
      )}
    </div>
  )
}

// ---------- what the save actually wrote ----------
// /labs/confirm has always reported `result_count` (rows WRITTEN), `duplicates` and
// `unmapped`. The client discarded the response and showed an unconditional "Report saved",
// so a save that wrote ZERO rows was indistinguishable from one that wrote twelve. That
// silence is the reason ten empty reports accumulated unnoticed across a backfill. The
// server was never the quiet one — this surface is.

function fmtNum(v) {
  return v === null || v === undefined ? '—' : String(v)
}

function CollisionRow({ d }) {
  // A byte-identical re-upload is housekeeping. A CHANGED value is a corrected result being
  // discarded, which is the case worth shouting about — `skip` drops it and the stored value
  // stands. Both values are carried in the response precisely so this is distinguishable.
  const corrected =
    d.existing_value_num !== null && d.incoming_value_num !== null &&
    d.existing_value_num !== d.incoming_value_num
  return (
    <tr className={corrected ? 'bg-red-50' : ''}>
      <td className="px-3 py-1.5 text-xs text-gray-800">{d.marker}</td>
      <td className="px-3 py-1.5 text-xs text-gray-600 tabular-nums">{fmtNum(d.existing_value_num)}</td>
      <td className="px-3 py-1.5 text-xs text-gray-600 tabular-nums">{fmtNum(d.incoming_value_num)}</td>
      <td className="px-3 py-1.5 text-xs">
        {corrected
          ? <span className="text-red-700 font-semibold">differs — not saved</span>
          : <span className="text-gray-400">already recorded</span>}
      </td>
    </tr>
  )
}

function SaveOutcome({ outcome, onDismiss }) {
  const { panel, result_count, duplicates = [], unmapped = [] } = outcome
  const nothingWritten = result_count === 0
  const anyCorrected = duplicates.some(
    (d) => d.existing_value_num !== null && d.incoming_value_num !== null &&
           d.existing_value_num !== d.incoming_value_num
  )

  const tone = nothingWritten || anyCorrected
    ? 'bg-red-50 border-red-200'
    : duplicates.length > 0
      ? 'bg-amber-50 border-amber-200'
      : 'bg-emerald-50 border-emerald-200'

  return (
    <div className={`border rounded-2xl p-4 space-y-3 ${tone}`}>
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-semibold text-gray-900">
          {nothingWritten
            ? 'Nothing was saved from this report'
            : `Saved ${result_count} result${result_count === 1 ? '' : 's'}`}
          {panel ? <span className="font-normal text-gray-500"> · {panel}</span> : null}
        </p>
        <button onClick={onDismiss} className="text-xs text-gray-500 hover:text-gray-800 shrink-0">
          Dismiss
        </button>
      </div>

      {nothingWritten && (
        <p className="text-xs text-gray-700">
          Every marker in this report is already recorded for this collection date, so no new
          rows were written. The report itself was still filed.
          {/* "nothing was lost" is only true when the incoming values MATCH. If one differs,
              a reading was in fact discarded, and the reassurance would be a lie — the exact
              species of reassurance this whole branch exists to remove. */}
          {anyCorrected
            ? ' One incoming value differs from what is stored — see below.'
            : ' Your existing values are unchanged, and nothing was lost.'}
        </p>
      )}

      {duplicates.length > 0 && (
        <div className="bg-white/70 border border-black/5 rounded-xl overflow-x-auto">
          <table className="w-full text-left">
            <thead className="border-b border-gray-200">
              <tr>
                <th className="px-3 py-1.5 text-[11px] font-medium text-gray-500">Marker</th>
                <th className="px-3 py-1.5 text-[11px] font-medium text-gray-500">Stored</th>
                <th className="px-3 py-1.5 text-[11px] font-medium text-gray-500">In this report</th>
                <th className="px-3 py-1.5 text-[11px] font-medium text-gray-500">Outcome</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {duplicates.map((d, i) => <CollisionRow key={i} d={d} />)}
            </tbody>
          </table>
        </div>
      )}

      {anyCorrected && (
        <p className="text-xs text-red-800">
          A marker above carries a different value to the one already stored. This report may be
          a corrected result — the stored value was kept and the new one discarded. Re-upload
          with “keep both” if the new value is the right one.
        </p>
      )}

      {unmapped.length > 0 && (
        <p className="text-xs text-gray-600">
          Stored without a canonical marker (they will not appear in trends until mapped):{' '}
          <span className="text-gray-800">{unmapped.join(', ')}</span>
        </p>
      )}
    </div>
  )
}

// ---------- main ----------

export default function Metrics() {
  const [stage, setStage] = useState(STAGE.IDLE)
  const [extraction, setExtraction] = useState(null)
  const [canonicalMap, setCanonicalMap] = useState({})
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [outcome, setOutcome] = useState(null) // what the last save actually wrote
  const [storedReports, setStoredReports] = useState(null) // null=loading, []=none
  const fileInputRef = useRef(null)

  function loadStored() {
    api.get('/labs/results').then((res) => setStoredReports(res.data)).catch(() => setStoredReports([]))
  }

  useEffect(() => {
    api.get('/labs/canonical-map').then((res) => setCanonicalMap(res.data)).catch(() => {})
    loadStored()
  }, [])

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
      const panel = extraction.report?.panel_name_raw
      const res = await api.post('/labs/confirm', extraction)
      // The response is the only account of what was written. Reporting "saved" without
      // reading it is what let ten zero-row reports pass for successful uploads.
      setOutcome({ panel, ...res.data })
      reset()
      loadStored() // the just-saved report joins the read-back
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

        {stage === STAGE.IDLE && outcome && (
          <SaveOutcome outcome={outcome} onDismiss={() => setOutcome(null)} />
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

        {stage === STAGE.IDLE && storedReports && storedReports.length > 0 && (
          <div className="space-y-4">
            <div className="flex items-baseline justify-between gap-3">
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">Your results</p>
              <p className="text-[11px] text-gray-400 text-right">Values and lab reference ranges as reported — no interpretation.</p>
            </div>
            {storedReports.map((rep) => (
              <StoredReportCard key={rep.report_id} report={rep} />
            ))}
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

    </div>
  )
}
