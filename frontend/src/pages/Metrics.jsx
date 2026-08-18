import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import { formatApiError } from '../lib/apiError'
import { confidencePct, isClinicalFlag, isSuspect, rowTier } from './labRowClassification'

const STAGE = { IDLE: 'IDLE', EXTRACTING: 'EXTRACTING', CONFIRM: 'CONFIRM' }

// ---------- row formatting (LAB_EXTRACTION_SCHEMA v0.3 §6) ----------
// Classification (isSuspect / isClinicalFlag / rowTier / confidencePct) lives in
// ./labRowClassification — pure, JSX-free, and unit-tested there.

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

function formatDate(iso) {
  if (!iso) return null
  return iso.slice(0, 10)
}

// ---------- inline canonical bind (#NEXT, fulfilling #50) ----------
// The affordance is PRE-write, at CONFIRM. It used to be post-write flat text in
// `SaveOutcome`, which named the problem after the moment it could be fixed — the row was
// already stored with a null canonical, and fixing it meant a hand-edited JSON plus a
// backfill script run. Binding here promotes the marker's history too, so the series is
// whole the moment the operator presses confirm.
//
// Binding stays OPTIONAL. An unbound row still stores its raw name with a null canonical
// (#58/#155 retain-raw) — making a bind mandatory to confirm would turn a "we don't know
// this marker yet" into a blocked upload.

export function BindControl({ rawName, onBound }) {
  const [open, setOpen] = useState(false)
  const [canonical, setCanonical] = useState('')
  const [unit, setUnit] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [bound, setBound] = useState(null)

  async function submit(e) {
    e.preventDefault()
    if (!canonical.trim()) return
    setBusy(true)
    setError(null)
    try {
      const res = await api.post('/labs/canonical/bind', {
        marker_name_raw: rawName,
        marker_canonical: canonical.trim(),
        // Empty means NOT ESTABLISHED, which is a real state for a unitless marker (§6) —
        // so it is sent as null, never as an empty string the guard would compare against.
        unit_established: unit.trim() || null,
      })
      setBound(res.data)
      await onBound()
    } catch (err) {
      // The guard refusals (409 already-mapped, 422 over-collapse) carry a string `detail`
      // that names the exact clash. It must reach the operator intact — a generic "bind
      // failed" would hide the one thing that makes the refusal actionable.
      setError(formatApiError(err, 'Could not bind this marker — the server gave no reason.'))
    } finally {
      setBusy(false)
    }
  }

  if (bound) {
    return (
      <div className="mt-1 text-xs text-emerald-700">
        Bound to <span className="font-mono font-medium">{bound.marker_canonical}</span>
        {bound.backfilled_rows > 0 && ` — ${bound.backfilled_rows} historical ${bound.backfilled_rows === 1 ? 'row' : 'rows'} promoted`}
      </div>
    )
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-1 text-xs text-amber-700 underline hover:text-amber-900"
      >
        Not a known marker — bind it
      </button>
    )
  }

  return (
    <form onSubmit={submit} className="mt-2 space-y-1">
      <input
        autoFocus
        value={canonical}
        onChange={(e) => setCanonical(e.target.value)}
        placeholder="canonical id (e.g. lipoprotein_a)"
        aria-label={`Canonical name for ${rawName}`}
        className="w-full rounded border border-gray-300 px-2 py-1 text-xs font-mono"
      />
      <input
        value={unit}
        onChange={(e) => setUnit(e.target.value)}
        placeholder="established unit (blank if unitless)"
        aria-label={`Established unit for ${rawName}`}
        className="w-full rounded border border-gray-300 px-2 py-1 text-xs"
      />
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={busy || !canonical.trim()}
          className="rounded bg-amber-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
        >
          {busy ? 'Binding…' : 'Bind'}
        </button>
        <button
          type="button"
          onClick={() => { setOpen(false); setError(null) }}
          className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-600"
        >
          Cancel
        </button>
      </div>
      {error && (
        <p role="alert" className="rounded bg-red-50 px-2 py-1 text-xs text-red-700">{error}</p>
      )}
    </form>
  )
}


// ---------- row component ----------

function ResultRow({ r, canonicalMap, onBound }) {
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
      <td className="px-3 py-2 text-sm text-gray-800">
        {r.marker_name_raw}
        {!canonicalMap[r.marker_name_raw] && (
          <BindControl rawName={r.marker_name_raw} onBound={onBound} />
        )}
      </td>
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
          <p className="text-xs font-semibold text-red-800">
            {report.zero_row_reason === 'no_values_extracted'
              ? 'No values could be read from this document'
              : 'No results stored for this report'}
          </p>
          <p className="text-xs text-red-700">
            {report.zero_row_reason === 'no_values_extracted'
              ? 'The document was ingested but carried no extractable results — a chart or scan with no results table will do this. Nothing from it has been recorded. Re-upload the document that contains the results table.'
              : 'The report was filed but no marker was saved against it, and no reason was recorded. Check the upload history.'}
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

// ---------- upload history ----------
// Every report the app has ingested, including the ones that contributed no values. This is the
// manifest answering "which of my documents went in" — nothing previously could. It renders from
// `GET /labs/results`, which the page already fetches; VERIFIED that no new endpoint was needed
// once the projection carried `source_doc_filename` and `zero_row_reason`.
//
// Deliberately a flat list: no search, no filtering, no drill-down, no editing. If it grows any
// of those it has become a module and should be planned as one.

function contributionNote(report) {
  const n = report.results.length
  if (n > 0) return { text: `${n} marker${n === 1 ? '' : 's'}`, tone: 'text-gray-600' }
  switch (report.zero_row_reason) {
    case 'all_markers_declined':
      // #156 working. Not a fault — the values are on an earlier report from the same draw.
      return { text: 'No new values — all markers already recorded', tone: 'text-gray-500' }
    case 'no_values_extracted':
      // A fault, and the whole reason the results filter keys on this field rather than on
      // row count: filtering by count alone would hide this exactly as readily as the above.
      return { text: 'No values could be read from this document', tone: 'text-red-700 font-medium' }
    default:
      return { text: 'No values recorded', tone: 'text-gray-500' }
  }
}

function UploadHistory({ reports }) {
  const ordered = [...reports].sort(
    (a, b) => (a.collected_date < b.collected_date ? 1 : a.collected_date > b.collected_date ? -1 : b.report_id - a.report_id)
  )
  return (
    <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100">
        <p className="text-sm font-semibold text-gray-900">Upload history</p>
        <p className="text-xs text-gray-500">Every report ingested, including those that added no values.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-3 py-2 text-xs font-medium text-gray-500">Collected</th>
              <th className="px-3 py-2 text-xs font-medium text-gray-500">Panel</th>
              <th className="px-3 py-2 text-xs font-medium text-gray-500">Lab</th>
              <th className="px-3 py-2 text-xs font-medium text-gray-500">Document</th>
              <th className="px-3 py-2 text-xs font-medium text-gray-500">Contributed</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {ordered.map((rep) => {
              const note = contributionNote(rep)
              return (
                <tr key={rep.report_id} className={rep.zero_row_reason === 'no_values_extracted' ? 'bg-red-50' : ''}>
                  <td className="px-3 py-2 text-xs text-gray-600 tabular-nums whitespace-nowrap">{formatDate(rep.collected_date)}</td>
                  <td className="px-3 py-2 text-xs text-gray-800">{rep.panel_name_raw}</td>
                  <td className="px-3 py-2 text-xs text-gray-500">{rep.lab_name}</td>
                  <td className="px-3 py-2 text-xs text-gray-500 break-all">{rep.source_doc_filename || '—'}</td>
                  <td className={`px-3 py-2 text-xs ${note.tone}`}>{note.text}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
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

// ---------- collision pre-check (before the write, at the decision point) ----------
// The write-time guard (#156, `labs.py`) is unchanged and is what actually protects the series.
// This is the INTERFACE to it: the operator previously committed and only then learned every
// marker was already stored. No endpoint is needed — `GET /labs/results` already returns every
// stored report with its `collected_date`, `marker_canonical` and `marker_name_raw`, and
// `GET /labs/canonical-map` resolves an extracted raw label the same way the server does. Both
// are already fetched on mount for the results table.

function incomingKey(rawName, canonicalMap) {
  // mirrors `_duplicate_key`: canonical id where mapped, `raw:<label>` where not. Extraction
  // leaves `marker_canonical` null by design, so the map is the only resolver on this side.
  const canonical = canonicalMap[rawName]?.marker_canonical
  return canonical || `raw:${rawName}`
}

function storedKeysAtDate(storedReports, collectedDate) {
  const at = new Map()
  for (const rep of storedReports || []) {
    if (formatDate(rep.collected_date) !== collectedDate) continue
    for (const r of rep.results) {
      const key = r.marker_canonical || `raw:${r.marker_name_raw}`
      if (!at.has(key)) {
        at.set(key, { reportId: rep.report_id, panel: rep.panel_name_raw, value: r.value_num })
      }
    }
  }
  return at
}

function precheckCollisions(extraction, storedReports, canonicalMap) {
  const collectedDate = formatDate(extraction?.report?.dates?.collected)
  if (!collectedDate || !storedReports) return null
  const at = storedKeysAtDate(storedReports, collectedDate)
  if (at.size === 0) return null

  const hits = []
  for (const r of extraction.results) {
    const prior = at.get(incomingKey(r.marker_name_raw, canonicalMap))
    if (prior) hits.push({ marker: r.marker_name_raw, incoming: r.value_num, ...prior })
  }
  if (hits.length === 0) return null
  return {
    hits,
    total: extraction.results.length,
    all: hits.length === extraction.results.length,
    collectedDate,
    reportIds: [...new Set(hits.map((h) => h.reportId))],
  }
}

function PrecheckPanel({ precheck }) {
  const { hits, total, all, collectedDate, reportIds } = precheck
  const changed = hits.filter((h) => h.value !== null && h.incoming !== null && h.value !== h.incoming)
  return (
    <div className={`border rounded-2xl p-4 space-y-2 ${all ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'}`}>
      <p className="text-sm font-semibold text-gray-900">
        {all
          ? 'Every marker in this report is already stored'
          : `${hits.length} of ${total} markers are already stored`}
      </p>
      <p className="text-xs text-gray-700">
        {all
          ? `${total === 1 ? 'Its single marker was' : `All ${total} markers were`} already recorded for ${collectedDate} on report${reportIds.length === 1 ? '' : 's'} ${reportIds.join(', ')}. Saving would file an upload that contributes no values. Cancel unless you mean to keep a second copy.`
          : `Already recorded for ${collectedDate} on report${reportIds.length === 1 ? '' : 's'} ${reportIds.join(', ')}. Saving writes the ${total - hits.length} new marker${total - hits.length === 1 ? '' : 's'} and skips these.`}
      </p>
      <div className="bg-white/70 border border-black/5 rounded-xl overflow-x-auto">
        <table className="w-full text-left">
          <thead className="border-b border-gray-200">
            <tr>
              <th className="px-3 py-1.5 text-[11px] font-medium text-gray-500">Marker</th>
              <th className="px-3 py-1.5 text-[11px] font-medium text-gray-500">Stored</th>
              <th className="px-3 py-1.5 text-[11px] font-medium text-gray-500">In this report</th>
              <th className="px-3 py-1.5 text-[11px] font-medium text-gray-500">On report</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {hits.map((h, i) => {
              const differs = h.value !== null && h.incoming !== null && h.value !== h.incoming
              return (
                <tr key={i} className={differs ? 'bg-red-50' : ''}>
                  <td className="px-3 py-1.5 text-xs text-gray-800">{h.marker}</td>
                  <td className="px-3 py-1.5 text-xs text-gray-600 tabular-nums">{fmtNum(h.value)}</td>
                  <td className={`px-3 py-1.5 text-xs tabular-nums ${differs ? 'text-red-700 font-semibold' : 'text-gray-600'}`}>
                    {fmtNum(h.incoming)}
                  </td>
                  <td className="px-3 py-1.5 text-xs text-gray-500">#{h.reportId} {h.panel}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {changed.length > 0 && (
        <p className="text-xs text-red-800">
          A value above differs from what is stored. If this document is a corrected result, keep
          both — saving normally would skip it and leave the old value standing.
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

  // Named (not inlined in the effect) because a successful bind must re-read it: the row
  // the operator just bound has to resolve BEFORE they press confirm, or confirm writes
  // the null they were trying to avoid.
  function loadCanonicalMap() {
    return api.get('/labs/canonical-map').then((res) => setCanonicalMap(res.data)).catch(() => {})
  }

  useEffect(() => {
    loadCanonicalMap()
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
      setError(formatApiError(err, 'Failed to read report'))
      setStage(STAGE.IDLE)
    }
  }

  async function handleConfirm(onDuplicate = 'skip') {
    setSaving(true)
    setError('')
    try {
      const panel = extraction.report?.panel_name_raw
      const res = await api.post('/labs/confirm', extraction, { params: { on_duplicate: onDuplicate } })
      // The response is the only account of what was written. Reporting "saved" without
      // reading it is what let ten zero-row reports pass for successful uploads.
      setOutcome({ panel, ...res.data })
      reset()
      loadStored() // the just-saved report joins the read-back
    } catch (err) {
      // A rejection here is frequently a Pydantic 422 raised BEFORE confirm_lab_report
      // runs, whose `detail` is a list of `{loc, msg, type}` — the shape this used to
      // discard. `formatApiError` names the refused field; see its header.
      setError(formatApiError(err, 'Failed to save report'))
    } finally {
      setSaving(false)
    }
  }

  const missingCollected = stage === STAGE.CONFIRM && !extraction?.report?.dates?.collected

  const sortedResults = extraction
    ? [...extraction.results].sort((a, b) => rowTier(a, canonicalMap) - rowTier(b, canonicalMap))
    : []

  // "Your results" carries VALUES. A report whose markers were all declined as already-stored
  // duplicates contributed none, so it is an upload event and belongs in the history instead.
  //
  // Keyed on `zero_row_reason`, NEVER on row count. Those are not the same filter: a report that
  // yielded nothing extractable also has zero rows, and hiding it would be the same
  // absence-as-emptiness failure one layer along — a fault disappearing behind a green check.
  // Only the decline is hidden; anything else with no rows stays visible as a fault.
  const resultReports = (storedReports || []).filter(
    (r) => !(r.results.length === 0 && r.zero_row_reason === 'all_markers_declined')
  )

  // Runs on data already in hand — no request, and nothing is written until the operator acts.
  const precheck = stage === STAGE.CONFIRM
    ? precheckCollisions(extraction, storedReports, canonicalMap)
    : null
  const allAlreadyStored = !!precheck?.all

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

        {stage === STAGE.IDLE && resultReports.length > 0 && (
          <div className="space-y-4">
            <div className="flex items-baseline justify-between gap-3">
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">Your results</p>
              <p className="text-[11px] text-gray-400 text-right">Values and lab reference ranges as reported — no interpretation.</p>
            </div>
            {resultReports.map((rep) => (
              <StoredReportCard key={rep.report_id} report={rep} />
            ))}
          </div>
        )}

        {stage === STAGE.IDLE && storedReports && storedReports.length > 0 && (
          <UploadHistory reports={storedReports} />
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

            {precheck && <PrecheckPanel precheck={precheck} />}

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
                        <ResultRow key={i} r={r} canonicalMap={canonicalMap} onBound={loadCanonicalMap} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* When every marker is already stored, CANCEL is the default action and `keep_both`
                is the deliberate one (#156 — the resolution is operator-chosen, never inferred).
                Cancelling issues no request: no LabReport row, no history entry. An abandoned
                upload is not an upload. */}
            <div className="flex gap-3">
              <button
                onClick={reset}
                className={`flex-1 font-semibold rounded-2xl py-3 text-sm transition-colors ${
                  allAlreadyStored
                    ? 'bg-indigo-600 hover:bg-indigo-700 text-white'
                    : 'bg-white border border-gray-200 hover:bg-gray-50 text-gray-700'
                }`}
              >
                {allAlreadyStored ? 'Cancel — nothing to add' : 'Discard'}
              </button>
              {allAlreadyStored ? (
                <button
                  onClick={() => handleConfirm('keep_both')}
                  disabled={saving || missingCollected}
                  className="flex-1 bg-white border border-red-200 hover:bg-red-50 disabled:opacity-50 text-red-700 font-semibold rounded-2xl py-3 text-sm transition-colors"
                >
                  {saving ? 'Saving…' : 'Save anyway (keep both)'}
                </button>
              ) : (
                <button
                  onClick={() => handleConfirm('skip')}
                  disabled={saving || missingCollected}
                  className="flex-1 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold rounded-2xl py-3 text-sm transition-colors"
                >
                  {saving ? 'Saving…' : 'Confirm & Save'}
                </button>
              )}
            </div>
          </>
        )}
      </div>

    </div>
  )
}
