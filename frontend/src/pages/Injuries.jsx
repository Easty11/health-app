// The /injuries operator view — the reachable half of the #222/#223 resolution loop.
//
// The injury ledger is write-only from the UI: chat, api and system all write injury rows and
// none of the app's routes could retire one. #222/#223 built GET /knowledge/injuries and
// POST /knowledge/injuries/{id}/resolve; this surface makes them reachable. Constraint cite: #232.
//
// This page READS the ledger, it does not reinterpret it (mirrors the endpoint's own contract):
//   - ONE fetch, with include_resolved=true. Supersession ancestors are the only recoverable
//     record-age source, so they must be in hand whether or not history is shown; the toggle is
//     display-only. (#brief §1.3.2)
//   - "On record since" is the chain-earliest added_at, walked back through superseded_by. It is a
//     record-age FLOOR — how long the ledger has held the row — NOT injury onset. No field holds
//     onset (added_at was rewritten for ids 75-78 by a source backfill), so nothing here is ever
//     labelled onset or age, and rows are not sorted on a raw date. (#brief §1.3)
//   - One row, one basis, one human. No multi-row resolve, no auto-resolve, no canned/defaulted
//     basis, no staleness heuristic. (#223/#228, #brief §4)
//
// The review/divergence badge (#232) is deferred: injury_trajectory.evaluate() is exposed only
// through mcp_server.py, never the REST payload, and no active row carries review_when today, so
// zero flags could fire. Re-implementing _review_message client-side is refused — a second copy of
// the exit-condition rule drifts from the one #222's gates pin. (#brief §1.4)

import { useEffect, useState } from 'react'
import HubLayout from '../components/HubLayout'
import api from '../api'

// Mirrors backend injury_trajectory.injury_soreness_key. Kept in sync deliberately: the endpoint
// returns `value` unmodified and never the computed key, so the only way to SHOW which morning
// soreness item a row generates is to derive it here. Same rule, punctuation NOT stripped — `-`
// and `/` survive into daily_records.soreness keys and must not be "tidied" (#brief §1.6).
function sorenessKey(value) {
  const bodyPart = String(value?.body_part ?? 'injury').trim().toLowerCase().replace(/ /g, '_')
  const side = String(value?.side ?? '').trim().toLowerCase()
  if (side === '' || side === 'bilateral' || side === 'both') return bodyPart
  return `${bodyPart}_${side}`
}

// Walk an active row back through its supersession chain and return the earliest added_at on it.
// superseded_by points FORWARD (a superseded row names its successor), so the predecessor of a row
// is whichever row carries superseded_by === this row's id. added_at is an ISO "YYYY-MM-DD" string,
// so lexical min is chronological min. `seen` guards a malformed self/loop reference.
function chainEarliest(row, predecessorOf) {
  let earliest = row.added_at
  let cur = row
  const seen = new Set([cur.id])
  for (;;) {
    const pred = predecessorOf.get(cur.id)
    if (!pred || seen.has(pred.id)) break
    seen.add(pred.id)
    if (pred.added_at < earliest) earliest = pred.added_at
    cur = pred
  }
  return earliest
}

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function titleCase(s) {
  const t = String(s ?? '').trim()
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : ''
}

function injuryTitle(value) {
  const part = titleCase(value?.body_part) || 'Injury'
  const side = String(value?.side ?? '').trim().toLowerCase()
  const sideLabel = side && side !== 'bilateral' && side !== 'both'
    ? side
    : (side ? 'bilateral' : '')
  return sideLabel ? `${part} (${sideLabel})` : part
}

function Chip({ children, tone = 'gray' }) {
  const tones = {
    gray: 'bg-gray-100 text-gray-600',
    amber: 'bg-amber-100 text-amber-700',
    indigo: 'bg-indigo-100 text-indigo-700',
  }
  return (
    <span className={`inline-block text-[11px] font-medium rounded px-1.5 py-0.5 ${tones[tone]}`}>
      {children}
    </span>
  )
}

// --- resolve panel — one row, one basis, one human ---------------------------------------------
//
// basis starts empty on every open (no defaulted, suggested, or carried-forward text — each is
// multi-row resolve in disguise). Submit is unreachable until a non-whitespace basis clears a ≥15-char
// client floor (a speed bump; the server floor is only non-empty) AND a resolved_by tier is chosen.
// resolved_on is omitted — the server defaults to today. On any failure the typed basis is kept.

const BASIS_MIN = 15

function ResolvePanel({ row, onDone }) {
  const [open, setOpen] = useState(false)
  const [basis, setBasis] = useState('')
  const [resolvedBy, setResolvedBy] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  function openPanel() {
    setBasis('')          // empty on open, every time
    setResolvedBy('')     // nothing pre-selected
    setError('')
    setOpen(true)
  }

  function cancel() {
    setOpen(false)
    setError('')
  }

  const ready = basis.trim().length >= BASIS_MIN && !!resolvedBy && !submitting

  async function submit() {
    if (!ready) return
    setSubmitting(true)
    setError('')
    try {
      await api.post(`/knowledge/injuries/${row.id}/resolve`, {
        basis,
        resolved_by: resolvedBy,
      })
      setOpen(false)
      onDone()
    } catch (err) {
      // Keep the typed basis on every failure. A 409 means the row is already inactive — the list
      // is stale and the resolve did NOT succeed — so surface it AND refetch.
      const status = err?.response?.status
      if (status === 409) {
        setError('Already resolved elsewhere — refreshing the list.')
        onDone()
      } else if (status === 422) {
        setError('Rejected: a basis and an authority are both required.')
      } else {
        setError('Could not resolve this injury. Try again.')
      }
      setSubmitting(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={openPanel}
        className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors"
      >
        Resolve…
      </button>
    )
  }

  return (
    <div className="mt-1 border-t border-gray-100 pt-3 space-y-3">
      <div>
        <label className="block text-[11px] font-medium text-gray-500 uppercase tracking-wide mb-1">
          Basis — why is this no longer true?
        </label>
        <textarea
          value={basis}
          onChange={(e) => setBasis(e.target.value)}
          rows={2}
          autoFocus
          placeholder="State the grounds. This is the audit trail — recorded, and read back in history."
          className="w-full text-sm rounded-lg border border-gray-300 px-3 py-2
            focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-y"
        />
        <p className="mt-1 text-[11px] text-gray-400">
          {basis.trim().length < BASIS_MIN
            ? `At least ${BASIS_MIN} characters (${basis.trim().length}/${BASIS_MIN}).`
            : 'Grounds recorded verbatim.'}
        </p>
      </div>

      <div>
        <span className="block text-[11px] font-medium text-gray-500 uppercase tracking-wide mb-1">
          Resolved by
        </span>
        <div className="flex gap-2">
          {['user', 'clinician'].map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setResolvedBy(v)}
              className={`text-xs font-medium rounded-lg px-3 py-1.5 border transition-colors ${
                resolvedBy === v
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white text-gray-600 border-gray-300 hover:border-indigo-300'
              }`}
            >
              {titleCase(v)}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      <div className="flex items-center gap-3">
        <button
          onClick={submit}
          disabled={!ready}
          className="text-xs font-semibold rounded-lg px-3 py-1.5 bg-indigo-600 text-white
            enabled:hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? 'Resolving…' : 'Confirm resolution'}
        </button>
        <button
          onClick={cancel}
          disabled={submitting}
          className="text-xs text-gray-500 hover:text-gray-700 transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// --- active row --------------------------------------------------------------------------------

function ActiveRow({ row, onRecord, onDone }) {
  const value = row.value || {}
  const key = sorenessKey(value)
  const restrictions = Array.isArray(value.restrictions) ? value.restrictions : []
  // signal_type is what decides whether the engine's radicular block can ever fire, so it belongs
  // on screen. HAZARD, do NOT "correct" the data to match the prose: the right-hamstring row's
  // `detail` states the current limiter is NEURAL while signal_type reads "mechanical". That
  // mismatch is deliberate and documented in seed_engine.py — typing it "neural" fires the
  // radicular block across hinge/rotation/carry/gait and removes the SL-RDL that IS the
  // desensitisation lane, silently deleting the treatment. This field is displayed, never asserted
  // to gate anything (whether a row contraindicates is a server-side computation absent here).
  const signalType = String(value.signal_type || 'mechanical').toLowerCase()

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-900">{injuryTitle(value)}</h3>
          {value.detail && (
            <p className="text-xs text-gray-500 mt-0.5">{value.detail}</p>
          )}
        </div>
        {row.expires_at && <Chip tone="amber">expires {fmtDate(row.expires_at)}</Chip>}
      </div>

      {/* Effect readout. The one thing every active row DOES that is true of it as it stands: it
          puts an item in every morning check-in. It does NOT unconditionally contraindicate — that
          is a server-side computation over engine tables (_ACUTE_TISSUE_BLOCKS etc.), absent from
          this payload and false for rows like pes anserine and finger that match no block key, so
          the view asserts it neither way. Reproducing those tables here is the same drift hazard as
          _review_message. `restrictions[]` is free text surfaced to session context (mcp_server.py
          prints "(avoid: …)"); it gates nothing, and is labelled as such. */}
      <div className="rounded-lg bg-gray-50 px-3 py-2 space-y-1.5">
        <p className="text-xs text-gray-700">
          <span className="font-medium">Signal type</span>
          <span className="text-gray-500"> · {signalType}</span>
          {value.ra_flare ? <span className="text-gray-500"> · RA flare</span> : null}
        </p>
        <p className="text-xs text-gray-700">
          Generates a morning soreness item ·{' '}
          <code className="text-[11px] bg-white border border-gray-200 rounded px-1 py-0.5">{key}</code>
        </p>
        {restrictions.length > 0 && (
          <div className="pt-0.5">
            <p className="text-[11px] text-gray-400 mb-1">Surfaced to sessions, not enforced</p>
            <div className="flex flex-wrap gap-1">
              {restrictions.map((r) => <Chip key={r}>{r}</Chip>)}
            </div>
          </div>
        )}
      </div>

      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-gray-400">On record since</p>
          <p className="text-sm font-medium text-gray-800">
            {fmtDate(onRecord)} <span className="text-xs font-normal text-gray-400">· {row.source}</span>
          </p>
          <p className="text-[11px] text-gray-400">earliest date on the ledger for this injury</p>
        </div>
        <ResolvePanel row={row} onDone={onDone} />
      </div>
    </div>
  )
}

// --- history row (display-only) ----------------------------------------------------------------
//
// A resolved row (superseded_by null, resolution block present) is retirement — "no longer true".
// A superseded row (superseded_by set) is replacement — "re-stated about the same thing". Both read
// active=false; superseded_by is the only signal that tells them apart, and a basis written and
// never read is a compliance gesture, so resolutions are shown verbatim.

function HistoryRow({ row }) {
  const value = row.value || {}
  const resolution = value.resolution
  const isResolved = row.superseded_by == null

  return (
    <div className="bg-white border border-gray-200 rounded-xl px-4 py-3 space-y-1.5 opacity-90">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium text-gray-700">{injuryTitle(value)}</h3>
        {isResolved
          ? <Chip tone="indigo">resolved</Chip>
          : <Chip>superseded → #{row.superseded_by}</Chip>}
      </div>
      <p className="text-[11px] text-gray-400">
        #{row.id} · {row.source} · added {fmtDate(row.added_at)}
      </p>
      {isResolved && resolution && (
        <div className="text-xs text-gray-600 rounded-lg bg-gray-50 px-3 py-2 space-y-0.5">
          <p><span className="text-gray-400">basis:</span> {resolution.basis}</p>
          <p>
            <span className="text-gray-400">resolved by:</span> {resolution.resolved_by}
            {resolution.resolved_on ? <> · <span className="text-gray-400">on</span> {resolution.resolved_on}</> : null}
          </p>
        </div>
      )}
    </div>
  )
}

// --- page --------------------------------------------------------------------------------------

export default function Injuries() {
  const [rows, setRows] = useState(null) // null = loading
  const [error, setError] = useState('')
  const [showHistory, setShowHistory] = useState(false)

  function load() {
    // ONE request. include_resolved=true always — the toggle only controls display.
    api.get('/knowledge/injuries', { params: { include_resolved: true } })
      .then(({ data }) => { setRows(data); setError('') })
      .catch(() => setError('Could not load injuries.'))
  }

  useEffect(() => { load() }, [])

  const all = rows || []
  const predecessorOf = new Map()
  for (const r of all) {
    if (r.superseded_by != null) predecessorOf.set(r.superseded_by, r)
  }

  const active = all
    .filter((r) => r.active)
    .map((r) => ({ row: r, onRecord: chainEarliest(r, predecessorOf) }))
    .sort((a, b) => (a.onRecord < b.onRecord ? -1 : a.onRecord > b.onRecord ? 1 : 0))

  const history = all
    .filter((r) => !r.active)
    .sort((a, b) => (a.added_at > b.added_at ? -1 : a.added_at < b.added_at ? 1 : 0))

  return (
    <HubLayout title="Injuries" back="/dashboard">
      <div className="max-w-lg mx-auto px-4 py-5 space-y-4">
        {error && <div className="bg-red-50 text-red-700 text-sm rounded-lg px-3 py-2">{error}</div>}

        {rows && active.length === 0 && !error && (
          <p className="text-sm text-gray-500 text-center py-8">No active injuries.</p>
        )}

        {active.map(({ row, onRecord }) => (
          <ActiveRow key={row.id} row={row} onRecord={onRecord} onDone={load} />
        ))}

        {rows && history.length > 0 && (
          <div className="pt-2">
            <button
              onClick={() => setShowHistory((v) => !v)}
              className="text-xs font-medium text-gray-500 hover:text-gray-800 transition-colors"
            >
              {showHistory ? '▾ Hide' : '▸ Show'} history ({history.length} inactive)
            </button>
            {showHistory && (
              <div className="mt-3 space-y-2">
                {history.map((row) => <HistoryRow key={row.id} row={row} />)}
              </div>
            )}
          </div>
        )}
      </div>
    </HubLayout>
  )
}
