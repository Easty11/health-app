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

// #346 additions: each card shows its LEDGER KEY (`injury_<part>_<side>`, the value an
// appointment's `scope.parent_keys` needs), copyable — distinct from the soreness key below it. And
// PROPOSED constraints / findings (chat writes proposals only; every reader skips them) are listed
// under their parent injury with one Confirm action each, POSTing the existing /confirm route with
// an authority tier. Nothing else about a proposal is editable here.

// Q191 / "Engine blocks are rows" additions: a "Review due" group at the top lists what is past its
// date (GET /knowledge/review-due — surfacing only) with two actions per row, Resolve (the existing
// resolve / retract route, basis required) and Keep (POST .../review, which re-dates in place and
// touches nothing else). A CONSTRAINT proposal also gains Decline — the existing resolve route with a
// basis — so an engine default the operator does not want is declined, never silently ignored.

// Injury shape additions (DECISIONS_LOG "The injury row has a closed shape"): each active card gains
// Edit — body part (a select from the mirrored vocabulary), side, signal type, RA flare, detail, and
// three of the optional injury-model fields (course, onset date, diagnosis status) — submitted as a
// same-key REWRITE through POST /knowledge/entry with `source: "api"`. No new route: the existing
// write path validates it, and its hook re-proposes the engine defaults when the signature changes
// (#487), so a re-sided injury shows its new proposals on this page after the refetch. The row's
// legacy `restrictions[]`, `trajectory` and the api-only optional fields ride along unchanged.

import { useEffect, useState } from 'react'
import HubLayout from '../components/HubLayout'
import InjurySweep from '../components/InjurySweep'
import api from '../api'
import {
  INJURY_BODY_PARTS, INJURY_COURSES, INJURY_DIAGNOSIS_STATUSES, INJURY_SIDES, INJURY_SIGNAL_TYPES,
} from '../lib/injuryVocabulary'

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
// A successful resolve hands the row to onResolved, which opens its clearance sweep: resolving
// retires the ledger row, but copies elsewhere keep re-imposing the injury until cleared by hand.

const BASIS_MIN = 15

function ResolvePanel({ row, onDone, onResolved }) {
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
      onResolved(row)
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

// --- ledger key -------------------------------------------------------------------------------

function LedgerKey({ entryKey }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(entryKey)
      setCopied(true)
    } catch {
      setCopied(false) // clipboard blocked — the key is still selectable text
    }
  }
  return (
    <p className="text-[11px] text-gray-500 mt-1 flex items-center gap-1.5">
      <span>Ledger key</span>
      <code className="select-all font-mono text-[11px] text-gray-800 bg-gray-100 rounded px-1 py-0.5">{entryKey}</code>
      <button type="button" onClick={copy} aria-label={`Copy ${entryKey}`}
        className="text-[11px] font-medium text-indigo-600 hover:text-indigo-800">
        {copied ? 'Copied' : 'Copy'}
      </button>
    </p>
  )
}

// --- proposals — confirm only ------------------------------------------------------------------
//
// A proposal is shown with the one action the operator owns: Confirm, with an authority tier chosen
// each time (nothing pre-selected). The route stamps `confirmed_on`; refusals are shown verbatim.

function proposalText(p) {
  const v = p.value || {}
  if (p.type === 'finding') return `${v.statement} (as of ${v.as_of})`
  const scope = v.scope || {}
  const what = scope.tier === 'engine'
    ? `${String(v.kind || '').toUpperCase()} (engine) — regions: ${(scope.region_keys || []).join(', ')}${scope.side && scope.side !== 'bilateral' ? `, ${scope.side} side` : ''}`
    : `${String(v.kind || '').toUpperCase()} (advisory) — ${scope.text}`
  const ex = v.exit || {}
  const exits = [
    ex.on_date && `on ${ex.on_date}`,
    ex.on_condition && `when ${ex.on_condition}`,
    ex.with_parent === true && 'when the injury is resolved',
  ].filter(Boolean).join(' or ')
  return `${what} — ends ${exits} — review by ${v.review_by}`
}

// A basis + an authority tier, nothing defaulted (same discipline as the resolve panel). `onSubmit`
// resolves to an error string, or null when it succeeded (the parent reloads and this unmounts).
function BasisForm({ prompt, submitLabel, busyLabel, onSubmit, onCancel }) {
  const [basis, setBasis] = useState('')
  const [by, setBy] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const ready = basis.trim().length >= BASIS_MIN && !!by && !busy

  async function submit() {
    if (!ready) return
    setBusy(true)
    setError('')
    const err = await onSubmit({ basis, resolved_by: by })
    if (err) { setError(err); setBusy(false) }
  }

  return (
    <div className="space-y-2 border-t border-gray-100 pt-2">
      <label className="block text-[11px] font-medium text-gray-500 uppercase tracking-wide">{prompt}</label>
      <textarea value={basis} onChange={(e) => setBasis(e.target.value)} rows={2} aria-label={prompt}
        className="w-full text-xs rounded-lg border border-gray-300 px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-400 resize-y" />
      <p className="text-[11px] text-gray-400">
        {basis.trim().length < BASIS_MIN
          ? `At least ${BASIS_MIN} characters (${basis.trim().length}/${BASIS_MIN}).` : 'Grounds recorded verbatim.'}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {['user', 'clinician'].map((v) => (
          <button key={v} type="button" onClick={() => setBy(v)} aria-pressed={by === v}
            className={`text-[11px] font-medium rounded px-2 py-1 border ${
              by === v ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-gray-600 border-gray-300'}`}>
            {titleCase(v)}
          </button>
        ))}
        <button type="button" onClick={submit} disabled={!ready}
          className="text-[11px] font-semibold rounded px-2 py-1 bg-indigo-600 text-white disabled:opacity-40">
          {busy ? busyLabel : submitLabel}
        </button>
        <button type="button" onClick={onCancel} disabled={busy} className="text-[11px] text-gray-500">Cancel</button>
      </div>
      {error && <p className="text-[11px] text-red-600">{error}</p>}
    </div>
  )
}

function errorText(err, fallback) {
  const detail = err?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

function ProposalItem({ p, onDone }) {
  const [by, setBy] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [declining, setDeclining] = useState(false)

  // Decline = the existing resolve route with a basis (its docstring covers a declined proposal).
  // Constraints only: a finding proposal stays confirm-only here.
  async function decline(body) {
    try {
      await api.post(`/knowledge/constraints/${p.id}/resolve`, body)
      onDone()
      return null
    } catch (err) {
      if (err?.response?.status === 409) onDone()
      return errorText(err, 'Could not decline. Try again.')
    }
  }

  async function confirm() {
    if (!by || busy) return
    setBusy(true)
    setError('')
    try {
      await api.post(`/knowledge/${p.type}s/${p.id}/confirm`, { asserted_by: by })
      onDone()
    } catch (err) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'Could not confirm. Try again.')
      if (err?.response?.status === 409) onDone()
      setBusy(false)
    }
  }

  return (
    <li className="rounded-lg border border-dashed border-amber-300 bg-amber-50/50 px-3 py-2 space-y-2">
      <p className="text-xs text-gray-800">
        <Chip tone="amber">proposed {p.type}</Chip>{' '}{proposalText(p)}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {['user', 'clinician'].map((v) => (
          <button key={v} type="button" onClick={() => setBy(v)} aria-pressed={by === v}
            className={`text-[11px] font-medium rounded px-2 py-1 border ${
              by === v ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-gray-600 border-gray-300'}`}>
            {titleCase(v)}
          </button>
        ))}
        <button type="button" onClick={confirm} disabled={!by || busy}
          className="text-[11px] font-semibold rounded px-2 py-1 bg-indigo-600 text-white disabled:opacity-40">
          {busy ? 'Confirming…' : 'Confirm proposal'}
        </button>
        {p.type === 'constraint' && !declining && (
          <button type="button" onClick={() => setDeclining(true)}
            className="text-[11px] font-medium text-gray-500 hover:text-gray-800">
            Decline…
          </button>
        )}
      </div>
      {error && <p className="text-[11px] text-red-600">{error}</p>}
      {declining && (
        <BasisForm prompt="Basis — why decline this proposal?" submitLabel="Decline proposal"
          busyLabel="Declining…" onSubmit={decline} onCancel={() => setDeclining(false)} />
      )}
    </li>
  )
}

function ProposalList({ items, onDone }) {
  if (!items || items.length === 0) return null
  return (
    <div className="space-y-1.5">
      <p className="text-[11px] uppercase tracking-wide text-amber-700">Awaiting your confirmation</p>
      <ul className="space-y-2">
        {items.map((p) => <ProposalItem key={p.id} p={p} onDone={onDone} />)}
      </ul>
    </div>
  )
}

// --- review due — the standing sweep (Q191) ----------------------------------------------------
//
// SURFACING ONLY (#223): nothing here lifts, retires or re-dates by itself. Each row has the two
// actions the operator owns. Resolve retires it through its own route with a basis; Keep sets
// `review_by` to a date the operator types (never defaulted) and nothing else on the row.

function todayISO() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function DueItem({ item, onDone }) {
  const [mode, setMode] = useState(null)        // null | 'resolve' | 'keep'
  const [date, setDate] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const route = item.type === 'finding' ? 'findings' : 'constraints'

  async function resolve(body) {
    try {
      await api.post(item.type === 'finding' ? `/knowledge/findings/${item.id}/retract`
        : `/knowledge/constraints/${item.id}/resolve`, body)
      onDone()
      return null
    } catch (err) {
      if (err?.response?.status === 409) onDone()
      return errorText(err, 'Could not resolve. Try again.')
    }
  }

  async function keep() {
    if (!date || date <= todayISO() || busy) return
    setBusy(true)
    setError('')
    try {
      await api.post(`/knowledge/${route}/${item.id}/review`, { review_by: date })
      onDone()
    } catch (err) {
      setError(errorText(err, 'Could not re-date. Try again.'))
      if (err?.response?.status === 409) onDone()
      setBusy(false)
    }
  }

  const overdue = item.days_overdue == null ? 'its parent injury is resolved'
    : item.days_overdue === 0 ? 'due today' : `${item.days_overdue} day${item.days_overdue === 1 ? '' : 's'} overdue`

  return (
    <li className="rounded-lg border border-amber-300 bg-amber-50/50 px-3 py-2 space-y-2">
      <p className="text-xs text-gray-800">
        {item.tags.map((t) => <span key={t} className="mr-1"><Chip tone="amber">{t}</Chip></span>)}
        {item.what}
      </p>
      <p className="text-[11px] text-gray-500">
        {overdue}
        {item.authority ? ` · asserted by ${item.authority}` : ''}
        {item.parent_key ? ` · re: ${item.parent_key}` : ''}
        {item.review_by ? ` · review by ${item.review_by}` : ''}
        {item.exit_on_date ? ` · exit ${item.exit_on_date}` : ''}
      </p>
      {mode === null && (
        <div className="flex gap-3">
          <button type="button" onClick={() => setMode('resolve')}
            className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800">Resolve…</button>
          <button type="button" onClick={() => setMode('keep')}
            className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800">Keep — review again on…</button>
        </div>
      )}
      {mode === 'resolve' && (
        <BasisForm prompt="Basis — why is this no longer needed?" submitLabel="Confirm resolution"
          busyLabel="Resolving…" onSubmit={resolve} onCancel={() => setMode(null)} />
      )}
      {mode === 'keep' && (
        <div className="flex flex-wrap items-center gap-2 border-t border-gray-100 pt-2">
          <label className="text-[11px] text-gray-500" htmlFor={`keep-${item.type}-${item.id}`}>Review again on</label>
          <input id={`keep-${item.type}-${item.id}`} type="date" value={date} min={todayISO()}
            onChange={(e) => setDate(e.target.value)}
            className="text-xs rounded border border-gray-300 px-2 py-1" />
          <button type="button" onClick={keep} disabled={!date || date <= todayISO() || busy}
            className="text-[11px] font-semibold rounded px-2 py-1 bg-indigo-600 text-white disabled:opacity-40">
            {busy ? 'Saving…' : 'Keep'}
          </button>
          <button type="button" onClick={() => setMode(null)} disabled={busy} className="text-[11px] text-gray-500">Cancel</button>
        </div>
      )}
      {error && <p className="text-[11px] text-red-600">{error}</p>}
    </li>
  )
}

function ReviewDue({ items, withheldLabs, onDone }) {
  if ((!items || items.length === 0) && !withheldLabs) return null
  return (
    <section aria-label="Review due" className="bg-white border border-gray-200 rounded-xl p-4 space-y-2">
      <p className="text-xs font-semibold text-amber-700 uppercase tracking-wide">Review due</p>
      <p className="text-[11px] text-gray-500">
        Past its review or exit date, or its injury is resolved. Nothing lifts on its own — resolve it or keep it.
      </p>
      {items && items.length > 0 && (
        <ul className="space-y-2">
          {items.map((i) => <DueItem key={`${i.type}-${i.id}`} item={i} onDone={onDone} />)}
        </ul>
      )}
      {withheldLabs > 0 && (
        <p className="text-[11px] text-gray-500">
          {withheldLabs} lab-derived finding{withheldLabs === 1 ? '' : 's'} past review — lab results are not
          interpreted here; see Labs.
        </p>
      )}
    </section>
  )
}

// --- edit — a same-key rewrite through the api source ------------------------------------------
//
// Every field here is one the validator closes (`validate_injury`); the selects offer exactly the
// mirrored vocabulary, so the only refusal the server can still return is one the card could not
// know (a dangling key, a row that moved underneath). A legacy body part the vocabulary cannot name
// (user 9's `foot/hip`) stays selectable AS RECORDED: the server accepts it byte-for-byte on a
// rewrite and nothing else. Blank optional fields are OMITTED from the value, never sent as "".

function SelectField({ id, label, value, onChange, options, blank }) {
  return (
    <div className="space-y-0.5">
      <label htmlFor={id} className="block text-[11px] font-medium text-gray-500 uppercase tracking-wide">{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}
        className="w-full text-xs rounded-lg border border-gray-300 px-2 py-1.5 bg-white">
        {blank && <option value="">{blank}</option>}
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  )
}

function InjuryEditForm({ row, onSaved, onCancel }) {
  const v = row.value || {}
  const [bodyPart, setBodyPart] = useState(String(v.body_part ?? ''))
  const [side, setSide] = useState(String(v.side ?? 'bilateral'))
  const [signalType, setSignalType] = useState(String(v.signal_type ?? 'mechanical'))
  const [raFlare, setRaFlare] = useState(v.ra_flare === true)
  const [detail, setDetail] = useState(v.detail ?? '')
  const [course, setCourse] = useState(v.course ?? '')
  const [onsetOn, setOnsetOn] = useState(v.onset_on ?? '')
  const [diagnosis, setDiagnosis] = useState(v.diagnosis_status ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const partOptions = v.body_part && !INJURY_BODY_PARTS.includes(v.body_part)
    ? [v.body_part, ...INJURY_BODY_PARTS] : INJURY_BODY_PARTS
  const idp = `inj-${row.id}`

  async function save() {
    if (busy) return
    const value = { ...v, body_part: bodyPart, side, signal_type: signalType }
    if (raFlare || 'ra_flare' in v) value.ra_flare = raFlare
    if (detail.trim()) value.detail = detail; else delete value.detail
    if (course) value.course = course; else delete value.course
    if (onsetOn) value.onset_on = onsetOn; else delete value.onset_on
    if (diagnosis) value.diagnosis_status = diagnosis; else delete value.diagnosis_status
    setBusy(true)
    setError('')
    try {
      await api.post('/knowledge/entry', {
        type: 'injury', key: row.key, value, source: 'api',
        ...(row.notes != null ? { notes: row.notes } : {}),
        ...(row.expires_at != null ? { expires_at: row.expires_at } : {}),
      })
      onSaved()
    } catch (err) {
      setError(errorText(err, 'Could not save the injury. Try again.'))
      setBusy(false)
    }
  }

  return (
    <div className="border-t border-gray-100 pt-3 space-y-2" aria-label="Edit injury">
      <div className="grid grid-cols-2 gap-2">
        <SelectField id={`${idp}-part`} label="Body part" value={bodyPart} onChange={setBodyPart} options={partOptions} />
        <SelectField id={`${idp}-side`} label="Side" value={side} onChange={setSide} options={INJURY_SIDES} />
        <SelectField id={`${idp}-signal`} label="Signal type" value={signalType} onChange={setSignalType} options={INJURY_SIGNAL_TYPES} />
        <SelectField id={`${idp}-course`} label="Course" value={course} onChange={setCourse} options={INJURY_COURSES} blank="not stated" />
        <div className="space-y-0.5">
          <label htmlFor={`${idp}-onset`} className="block text-[11px] font-medium text-gray-500 uppercase tracking-wide">Onset date</label>
          <input id={`${idp}-onset`} type="date" value={onsetOn} onChange={(e) => setOnsetOn(e.target.value)}
            className="w-full text-xs rounded-lg border border-gray-300 px-2 py-1.5" />
        </div>
        <SelectField id={`${idp}-dx`} label="Diagnosis status" value={diagnosis} onChange={setDiagnosis}
          options={INJURY_DIAGNOSIS_STATUSES} blank="not stated" />
      </div>
      <label className="flex items-center gap-2 text-xs text-gray-700">
        <input type="checkbox" checked={raFlare} onChange={(e) => setRaFlare(e.target.checked)} />
        RA flare
      </label>
      <div className="space-y-0.5">
        <label htmlFor={`${idp}-detail`} className="block text-[11px] font-medium text-gray-500 uppercase tracking-wide">Detail</label>
        <textarea id={`${idp}-detail`} value={detail} onChange={(e) => setDetail(e.target.value)} rows={3}
          className="w-full text-xs rounded-lg border border-gray-300 px-2 py-1.5 resize-y" />
      </div>
      {error && <p className="text-[11px] text-red-600">{error}</p>}
      <div className="flex items-center gap-3">
        <button type="button" onClick={save} disabled={busy || !bodyPart}
          className="text-xs font-semibold rounded-lg px-3 py-1.5 bg-indigo-600 text-white disabled:opacity-40">
          {busy ? 'Saving…' : 'Save injury'}
        </button>
        <button type="button" onClick={onCancel} disabled={busy} className="text-xs text-gray-500 hover:text-gray-700">Cancel</button>
      </div>
    </div>
  )
}

// --- active row --------------------------------------------------------------------------------

function ActiveRow({ row, onRecord, onDone, onResolved, proposals }) {
  const value = row.value || {}
  const key = sorenessKey(value)
  const [editing, setEditing] = useState(false)
  const restrictions = Array.isArray(value.restrictions) ? value.restrictions : []
  // Restrictions → proposals (DECISIONS_LOG "Restrictions become constraint proposals from the injury
  // card"): one POST turns each legacy restriction into a PROPOSED advisory constraint parented to this
  // injury (the retired S6 seed script as a card action; idempotent). The response names every
  // restriction's state — proposed / confirmed / declined by matching the planner's text key — which is
  // shown beside the chip; the proposals group then refetches so the new rows appear below with their
  // Confirm / Decline. The injury row itself is untouched. The button appears only while a restriction
  // has no state yet (this visit; a fresh load asks again, and asking again creates nothing).
  const [restrictionStates, setRestrictionStates] = useState(null)
  const [proposing, setProposing] = useState(false)
  const [proposeError, setProposeError] = useState('')
  const allPlaced = restrictionStates !== null && restrictions.every((r) => restrictionStates[r])

  async function proposeFromRestrictions() {
    if (proposing) return
    setProposing(true)
    setProposeError('')
    try {
      const { data } = await api.post(`/knowledge/injuries/${row.id}/propose-constraints`)
      const states = {}
      for (const p of data.planned || []) states[p.text] = 'proposed'
      for (const e of data.existing || []) states[e.text] = e.state
      for (const s of data.skipped || []) states[s.text] = 'skipped'
      setRestrictionStates(states)
      onDone()
    } catch (err) {
      setProposeError(errorText(err, 'Could not propose constraints. Try again.'))
    } finally {
      setProposing(false)
    }
  }
  // signal_type belongs on screen: it decides which engine blocks the injury write path PROPOSES
  // (a spinal row typed neural/radicular is offered the radicular set; a proposal blocks nothing
  // until it is confirmed here). HAZARD, do NOT "correct" the data to match the prose: the
  // right-hamstring row's `detail` states the current limiter is NEURAL while signal_type reads
  // "mechanical" — a mismatch that was deliberate while typing it "neural" fired the radicular
  // block across hinge/rotation/carry/gait and removed the SL-RDL that IS the desensitisation
  // lane. The injury-keyed block maps are retired (DECISIONS_LOG #486), so the type no longer
  // gates anything on its own; it is still displayed, never asserted to gate anything.
  const signalType = String(value.signal_type || 'mechanical').toLowerCase()

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-900">{injuryTitle(value)}</h3>
          <LedgerKey entryKey={row.key} />
          {value.detail && (
            <p className="text-xs text-gray-500 mt-0.5">{value.detail}</p>
          )}
        </div>
        {row.expires_at && <Chip tone="amber">expires {fmtDate(row.expires_at)}</Chip>}
      </div>

      {/* Effect readout. The one thing every active row DOES that is true of it as it stands: it
          puts an item in every morning check-in. It does NOT contraindicate anything by itself: the
          engine blocks only on confirmed engine-tier constraint rows and profile hard-stops (the
          injury-keyed block maps retired, DECISIONS_LOG #486), and a row's confirmed blocks are the
          constraint rows shown with it. `restrictions[]` is free text surfaced to session context
          (mcp_server.py prints "(avoid: …)"); it gates nothing, and is labelled as such. */}
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
              {restrictions.map((r) => (
                <Chip key={r} tone={restrictionStates?.[r] === 'confirmed' ? 'indigo' : restrictionStates?.[r] === 'proposed' ? 'amber' : 'gray'}>
                  {r}{restrictionStates?.[r] ? ` · ${restrictionStates[r]}` : ''}
                </Chip>
              ))}
            </div>
            {!allPlaced && (
              <button type="button" onClick={proposeFromRestrictions} disabled={proposing}
                className="mt-1.5 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 disabled:opacity-40">
                {proposing ? 'Proposing…' : 'Propose constraints from restrictions'}
              </button>
            )}
            {proposeError && <p className="text-[11px] text-red-600 mt-1">{proposeError}</p>}
          </div>
        )}
      </div>

      <ProposalList items={proposals} onDone={onDone} />

      {editing && (
        <InjuryEditForm row={row} onSaved={() => { setEditing(false); onDone() }} onCancel={() => setEditing(false)} />
      )}

      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-gray-400">On record since</p>
          <p className="text-sm font-medium text-gray-800">
            {fmtDate(onRecord)} <span className="text-xs font-normal text-gray-400">· {row.source}</span>
          </p>
          <p className="text-[11px] text-gray-400">earliest date on the ledger for this injury</p>
        </div>
        <div className="flex items-center gap-3">
          {!editing && (
            <button type="button" onClick={() => setEditing(true)}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 transition-colors">
              Edit…
            </button>
          )}
          <ResolvePanel row={row} onDone={onDone} onResolved={onResolved} />
        </div>
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

function HistoryRow({ row, onSweep }) {
  const value = row.value || {}
  const resolution = value.resolution
  const isResolved = row.superseded_by == null

  return (
    <div className="bg-white border border-gray-200 rounded-xl px-4 py-3 space-y-1.5 opacity-90">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-medium text-gray-700">{injuryTitle(value)}</h3>
          <LedgerKey entryKey={row.key} />
        </div>
        {isResolved
          ? <Chip tone="indigo">resolved</Chip>
          : <Chip>superseded → #{row.superseded_by}</Chip>}
      </div>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] text-gray-400">
          #{row.id} · {row.source} · added {fmtDate(row.added_at)}
        </p>
        {/* Resolved rows only: a superseded row's injury lives on in its successor, so its
            copies are not stale. */}
        {isResolved && (
          <button onClick={() => onSweep(row)}
            className="text-[11px] font-medium text-indigo-600 hover:text-indigo-800 transition-colors">
            Sweep again
          </button>
        )}
      </div>
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
  // The open clearance sweep: { id, title, loading, data, error } or null. One at a time.
  const [sweep, setSweep] = useState(null)
  const [proposals, setProposals] = useState([])
  const [proposalError, setProposalError] = useState('')
  const [due, setDue] = useState({ items: [], withheld_labs: 0 })
  const [dueError, setDueError] = useState('')

  function load() {
    // ONE injuries request. include_resolved=true always — the toggle only controls display.
    api.get('/knowledge/injuries', { params: { include_resolved: true } })
      .then(({ data }) => { setRows(data); setError('') })
      .catch(() => setError('Could not load injuries.'))
    // Proposals are a separate resource; a failure here never hides the ledger.
    api.get('/knowledge/proposals')
      .then(({ data }) => {
        setProposals(Array.isArray(data) ? data.filter((p) => p.type === 'constraint' || p.type === 'finding') : [])
        setProposalError('')
      })
      .catch(() => setProposalError('Could not load proposals awaiting confirmation.'))
    // The review sweep is its own resource too; a failure here never hides the ledger either.
    api.get('/knowledge/review-due')
      .then(({ data }) => {
        setDue({ items: Array.isArray(data?.items) ? data.items : [], withheld_labs: data?.withheld_labs || 0 })
        setDueError('')
      })
      .catch(() => setDueError('Could not load the review sweep.'))
  }

  useEffect(() => { load() }, [])

  function runSweep(row) {
    const id = row.id
    setSweep({ id, title: `${injuryTitle(row.value)} · #${id}`, loading: true, data: null, error: '' })
    api.get(`/knowledge/injuries/${id}/sweep`)
      // A slower earlier sweep must not overwrite a later one — apply only to the sweep still open.
      .then(({ data }) => setSweep((s) => (s && s.id === id ? { ...s, loading: false, data } : s)))
      .catch(() => setSweep((s) => (s && s.id === id
        ? { ...s, loading: false, error: 'Could not run the sweep. Try again.' } : s)))
  }

  const all = rows || []
  const predecessorOf = new Map()
  for (const r of all) {
    if (r.superseded_by != null) predecessorOf.set(r.superseded_by, r)
  }

  const active = all
    .filter((r) => r.active)
    .map((r) => ({ row: r, onRecord: chainEarliest(r, predecessorOf) }))
    .sort((a, b) => (a.onRecord < b.onRecord ? -1 : a.onRecord > b.onRecord ? 1 : 0))

  // Proposals under their ACTIVE parent injury; anything else (no parent, or a parent that is not an
  // active injury) is listed on its own below, so no proposal is unreachable.
  const activeKeys = new Set(all.filter((r) => r.active).map((r) => r.key))
  const proposalsFor = (key) => proposals.filter((p) => p.value?.parent_key === key)
  const otherProposals = proposals.filter((p) => !activeKeys.has(p.value?.parent_key))

  const history = all
    .filter((r) => !r.active)
    .sort((a, b) => (a.added_at > b.added_at ? -1 : a.added_at < b.added_at ? 1 : 0))

  return (
    <HubLayout title="Injuries" back="/dashboard">
      <div className="max-w-lg mx-auto px-4 py-5 space-y-4">
        {error && <div className="bg-red-50 text-red-700 text-sm rounded-lg px-3 py-2">{error}</div>}

        {sweep && (
          <InjurySweep
            title={sweep.title}
            state={sweep}
            onAgain={() => runSweep({ id: sweep.id, value: all.find((r) => r.id === sweep.id)?.value })}
            onClose={() => setSweep(null)}
          />
        )}

        {dueError && <p className="text-xs text-red-600">{dueError}</p>}
        <ReviewDue items={due.items} withheldLabs={due.withheld_labs} onDone={load} />

        {rows && active.length === 0 && !error && (
          <p className="text-sm text-gray-500 text-center py-8">No active injuries.</p>
        )}

        {active.map(({ row, onRecord }) => (
          <ActiveRow key={row.id} row={row} onRecord={onRecord} onDone={load} onResolved={runSweep}
            proposals={proposalsFor(row.key)} />
        ))}

        {proposalError && <p className="text-xs text-red-600">{proposalError}</p>}
        {otherProposals.length > 0 && (
          <section aria-label="Other proposals" className="bg-white border border-gray-200 rounded-xl p-4 space-y-2">
            <p className="text-xs text-gray-500">Not attached to an active injury</p>
            <ProposalList items={otherProposals} onDone={load} />
          </section>
        )}

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
                {history.map((row) => <HistoryRow key={row.id} row={row} onSweep={runSweep} />)}
              </div>
            )}
          </div>
        )}
      </div>
    </HubLayout>
  )
}
