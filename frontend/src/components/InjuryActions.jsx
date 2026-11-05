// Shared injury actions — the confirm / decline / keep / resolve components the Injuries page and the
// AM check-in's saved screen both render (DECISIONS_LOG "Proposals and reviews due render on the AM
// check-in saved screen"). Extracted from pages/Injuries.jsx UNCHANGED in behaviour: the four Injuries
// test files pass with zero diff, which is the gate that the extraction moved nothing. One definition
// per action, so the morning screen cannot drift from the Injuries page (the #68 lesson).

import { useState } from 'react'
import api from '../api'

function titleCase(s) {
  const t = String(s ?? '').trim()
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : ''
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

const BASIS_MIN = 15

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

// --- edit a proposal (GH#617) ------------------------------------------------------------------
//
// Before Confirm or Decline, the operator can correct a proposal: the form is prefilled from the row
// and POSTs the typed /edit route, which writes a SUPERSEDING proposal through the one upsert and every
// validator (the coach's original stays beneath it). A refusal is the validator's text, verbatim (a
// wrong region key is refused with the valid set named). Edit never confirms: after the save the
// parent re-reads and the card shows the successor, still awaiting confirmation. The editable fields
// mirror the backend's `PROPOSAL_EDITABLE_FIELDS`; the enums mirror `routers/knowledge.py`
// (`CONSTRAINT_KINDS`, `CONSTRAINT_SIDES`) and are pinned by a backend test.

const CONSTRAINT_KINDS = ['block', 'cap', 'caution']
const CONSTRAINT_SIDES = ['left', 'right', 'bilateral']

function Field({ id, label, children }) {
  return (
    <div className="space-y-0.5">
      <label htmlFor={id} className="block text-[11px] font-medium text-gray-500 uppercase tracking-wide">{label}</label>
      {children}
    </div>
  )
}

const inputCls = 'w-full text-xs rounded-lg border border-gray-300 px-2 py-1.5 bg-white'

function ProposalEditForm({ p, onSaved, onCancel }) {
  const v = p.value || {}
  const scope = v.scope || {}
  const exit = v.exit || {}
  const isConstraint = p.type === 'constraint'
  const engine = scope.tier === 'engine'
  // constraint fields
  const [kind, setKind] = useState(String(v.kind ?? 'block'))
  const [regions, setRegions] = useState((scope.region_keys || []).join(', '))
  const [side, setSide] = useState(String(scope.side ?? 'bilateral'))
  const [text, setText] = useState(String(scope.text ?? ''))
  const [onDate, setOnDate] = useState(exit.on_date ?? '')
  const [onCondition, setOnCondition] = useState(exit.on_condition ?? '')
  const [withParent, setWithParent] = useState(exit.with_parent === true)
  const [reviewBy, setReviewBy] = useState(v.review_by ?? '')
  const [detail, setDetail] = useState(v.detail ?? '')
  // finding fields
  const [statement, setStatement] = useState(v.statement ?? '')
  const [asOf, setAsOf] = useState(v.as_of ?? '')
  const [basisText, setBasisText] = useState((v.basis || {}).text ?? '')
  // shared
  const [parentKey, setParentKey] = useState(v.parent_key ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const idp = `edit-${p.type}-${p.id}`

  function value() {
    const parent_key = parentKey.trim() ? parentKey.trim() : null
    if (!isConstraint) {
      return { statement, parent_key, as_of: asOf, basis: { ...(v.basis || {}), text: basisText } }
    }
    const nextScope = engine
      ? { tier: 'engine', region_keys: regions.split(',').map((s) => s.trim()).filter(Boolean),
          ...(side && side !== 'bilateral' ? { side } : {}), ...(scope.text ? { text: scope.text } : {}) }
      : { tier: 'advisory', text }
    const nextExit = {}
    if (onDate) nextExit.on_date = onDate
    if (onCondition.trim()) nextExit.on_condition = onCondition.trim()
    if (withParent) nextExit.with_parent = true
    const out = { kind, scope: nextScope, exit: nextExit, review_by: reviewBy, parent_key }
    if (detail.trim()) out.detail = detail.trim(); else out.detail = null
    return out
  }

  async function save() {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await api.post(`/knowledge/${p.type}s/${p.id}/edit`, { value: value() })
      onSaved()
    } catch (err) {
      setError(errorText(err, 'Could not save the edit. Try again.'))
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2 border-t border-gray-100 pt-2" aria-label={`Edit proposed ${p.type}`}>
      {isConstraint ? (
        <div className="grid grid-cols-2 gap-2">
          <Field id={`${idp}-kind`} label="Kind">
            <select id={`${idp}-kind`} value={kind} onChange={(e) => setKind(e.target.value)} className={inputCls}>
              {CONSTRAINT_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
            </select>
          </Field>
          {engine ? (
            <>
              <Field id={`${idp}-side`} label="Side">
                <select id={`${idp}-side`} value={side} onChange={(e) => setSide(e.target.value)} className={inputCls}>
                  {CONSTRAINT_SIDES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <div className="col-span-2">
                <Field id={`${idp}-regions`} label="Regions (keys, comma-separated)">
                  <input id={`${idp}-regions`} type="text" value={regions} onChange={(e) => setRegions(e.target.value)} className={inputCls} />
                </Field>
              </div>
            </>
          ) : (
            <div className="col-span-2">
              <Field id={`${idp}-text`} label="Instruction">
                <textarea id={`${idp}-text`} value={text} onChange={(e) => setText(e.target.value)} rows={2} className={`${inputCls} resize-y`} />
              </Field>
            </div>
          )}
          <Field id={`${idp}-on-date`} label="Ends on date">
            <input id={`${idp}-on-date`} type="date" value={onDate} onChange={(e) => setOnDate(e.target.value)} className={inputCls} />
          </Field>
          <Field id={`${idp}-review`} label="Review by">
            <input id={`${idp}-review`} type="date" value={reviewBy} onChange={(e) => setReviewBy(e.target.value)} className={inputCls} />
          </Field>
          <div className="col-span-2">
            <Field id={`${idp}-condition`} label="Ends when">
              <input id={`${idp}-condition`} type="text" value={onCondition} onChange={(e) => setOnCondition(e.target.value)} className={inputCls} />
            </Field>
          </div>
          <label className="col-span-2 flex items-center gap-2 text-xs text-gray-700">
            <input type="checkbox" checked={withParent} onChange={(e) => setWithParent(e.target.checked)} aria-label="Ends when the injury is resolved" />
            Ends when the injury is resolved (needs a parent injury)
          </label>
          <Field id={`${idp}-parent`} label="Parent injury key">
            <input id={`${idp}-parent`} type="text" value={parentKey} onChange={(e) => setParentKey(e.target.value)} placeholder="injury_…" className={`${inputCls} font-mono`} />
          </Field>
          <div className="col-span-2">
            <Field id={`${idp}-detail`} label="Detail">
              <textarea id={`${idp}-detail`} value={detail} onChange={(e) => setDetail(e.target.value)} rows={2} className={`${inputCls} resize-y`} />
            </Field>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <div className="col-span-2">
            <Field id={`${idp}-statement`} label="Statement">
              <textarea id={`${idp}-statement`} value={statement} onChange={(e) => setStatement(e.target.value)} rows={3} className={`${inputCls} resize-y`} />
            </Field>
          </div>
          <Field id={`${idp}-as-of`} label="As of">
            <input id={`${idp}-as-of`} type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className={inputCls} />
          </Field>
          <Field id={`${idp}-parent`} label="Parent injury key">
            <input id={`${idp}-parent`} type="text" value={parentKey} onChange={(e) => setParentKey(e.target.value)} placeholder="injury_…" className={`${inputCls} font-mono`} />
          </Field>
          <div className="col-span-2">
            <Field id={`${idp}-basis`} label="Basis">
              <textarea id={`${idp}-basis`} value={basisText} onChange={(e) => setBasisText(e.target.value)} rows={2} className={`${inputCls} resize-y`} />
            </Field>
          </div>
        </div>
      )}
      <p className="text-[11px] text-gray-400">
        Saves a corrected proposal; the coach's original is kept beneath it. Confirm is still a separate step.
      </p>
      <div className="flex items-center gap-2">
        <button type="button" onClick={save} disabled={busy}
          className="text-[11px] font-semibold rounded px-2 py-1 bg-indigo-600 text-white disabled:opacity-40">
          {busy ? 'Saving…' : 'Save edit'}
        </button>
        <button type="button" onClick={onCancel} disabled={busy} className="text-[11px] text-gray-500">Cancel</button>
      </div>
      {error && <p className="text-[11px] text-red-600">{error}</p>}
    </div>
  )
}

function ProposalItem({ p, onDone }) {
  const [by, setBy] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [declining, setDeclining] = useState(false)
  const [editing, setEditing] = useState(false)

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
        {!editing && (
          <button type="button" onClick={() => { setEditing(true); setDeclining(false) }}
            className="text-[11px] font-medium text-gray-500 hover:text-gray-800">
            Edit…
          </button>
        )}
        {p.type === 'constraint' && !declining && (
          <button type="button" onClick={() => { setDeclining(true); setEditing(false) }}
            className="text-[11px] font-medium text-gray-500 hover:text-gray-800">
            Decline…
          </button>
        )}
      </div>
      {error && <p className="text-[11px] text-red-600">{error}</p>}
      {editing && (
        <ProposalEditForm p={p} onSaved={() => { setEditing(false); onDone() }} onCancel={() => setEditing(false)} />
      )}
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

// The ONE retire route per type — the resolve route for a constraint, retract for a finding — shared
// by the due row and the confirmed row (GH#622), so "Resolve" cannot mean two things.
function retireUrl(type, id) {
  return type === 'finding' ? `/knowledge/findings/${id}/retract` : `/knowledge/constraints/${id}/resolve`
}

async function retire(type, id, body, onDone) {
  try {
    await api.post(retireUrl(type, id), body)
    onDone()
    return null
  } catch (err) {
    if (err?.response?.status === 409) onDone()
    return errorText(err, 'Could not resolve. Try again.')
  }
}

function DueItem({ item, onDone }) {
  const [mode, setMode] = useState(null)        // null | 'resolve' | 'keep'
  const [date, setDate] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const route = item.type === 'finding' ? 'findings' : 'constraints'

  const resolve = (body) => retire(item.type, item.id, body, onDone)

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

// --- confirmed rows — in force, resolvable at any time (GH#622) ---------------------------------
//
// What the engine and the coach read: a CONFIRMED constraint, or an open / confirmed finding, from
// GET /knowledge/confirmed. Each shows its kind, scope, exit, review date and who set it, and carries
// ONE action — Resolve, through the same retire route and BasisForm the due row uses (basis and an
// authority required, nothing defaulted). Keep is not here: re-dating belongs to the review sweep,
// which lists a row once it is due. SURFACING ONLY (#223): nothing lifts by itself.

const SET_BY = { user: 'set by you', clinician: 'set by your clinician', engine: 'set by the engine' }

function ConfirmedItem({ row, onDone }) {
  const [resolving, setResolving] = useState(false)
  const v = row.value || {}
  const setBy = SET_BY[v.asserted_by] || (v.asserted_by ? `set by ${v.asserted_by}` : 'no authority recorded')
  const status = v.status === 'open' ? 'open' : 'confirmed'

  return (
    <li className="rounded-lg border border-indigo-200 bg-indigo-50/40 px-3 py-2 space-y-2">
      <p className="text-xs text-gray-800">
        <Chip tone="indigo">{status} {row.type}</Chip>{' '}{proposalText(row)}
      </p>
      <p className="text-[11px] text-gray-500">
        {setBy}
        {v.confirmed_on ? ` · confirmed ${v.confirmed_on}` : ''}
        {v.parent_key ? ` · re: ${v.parent_key}` : ''}
        {' · '}<code className="font-mono">{row.key}</code>
      </p>
      {!resolving && (
        <button type="button" onClick={() => setResolving(true)}
          className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800">Resolve…</button>
      )}
      {resolving && (
        <BasisForm prompt="Basis — why is this no longer needed?" submitLabel="Confirm resolution"
          busyLabel="Resolving…" onSubmit={(body) => retire(row.type, row.id, body, onDone)}
          onCancel={() => setResolving(false)} />
      )}
    </li>
  )
}

function ConfirmedList({ items, onDone }) {
  if (!items || items.length === 0) return null
  return (
    <div className="space-y-1.5">
      <p className="text-[11px] uppercase tracking-wide text-indigo-700">In force</p>
      <ul className="space-y-2">
        {items.map((r) => <ConfirmedItem key={`${r.type}-${r.id}`} row={r} onDone={onDone} />)}
      </ul>
    </div>
  )
}


export { BASIS_MIN, BasisForm, CONSTRAINT_KINDS, CONSTRAINT_SIDES, Chip, ConfirmedItem, ConfirmedList, DueItem, ProposalEditForm, ProposalItem, ProposalList, ReviewDue, errorText, proposalText, retireUrl, titleCase, todayISO }
