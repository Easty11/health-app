// Clearance sweep — the read-only report behind GET /knowledge/injuries/{id}/sweep
// (DECISIONS_LOG: injury resolution triggers a surfacing-only clearance sweep).
//
// The injury ledger is the only authority on injury state; every other store holding the injury
// is a COPY that the operator clears by hand. This card SHOWS the copies and each store's EXISTING
// action. It adds no write action of its own: "edit" links to the Settings knowledge editor that
// already exists, and anything the app cannot act on reads "manual". Nothing here clears anything.
//
// What each hit carries (all computed server-side; this view renders, it does not re-derive):
//   - matched_terms       why the line is a hit (names the injury: body part, alias, key, ?terms=)
//   - restriction_terms   restriction words also on the line — the stale-ORDER signal
//   - marked_resolved     the line says resolved/historical — history, not an order
//   - opposite_side       names only the other side — flagged, never dropped
//   - other_injuries      other ledger rows the line also names; active = still in use by a live
//                         injury, so edit the line rather than clear it

import { Link } from 'react-router-dom'

const STORE_LABEL = {
  user_knowledge: 'Knowledge base (free text)',
  user_knowledge_entries: 'Structured entry',
  hevy_routines: 'Hevy routine',
}

const STORE_STATUS = {
  searched: 'searched',
  not_connected: 'not connected — not searched',
  unavailable: 'did not respond — not searched',
  stale: 'searched (cached copy)',
}

function Tag({ children, tone = 'gray' }) {
  const tones = {
    gray: 'bg-gray-100 text-gray-600',
    amber: 'bg-amber-100 text-amber-800',
    indigo: 'bg-indigo-100 text-indigo-700',
    red: 'bg-red-100 text-red-700',
    green: 'bg-green-100 text-green-700',
  }
  return (
    <span className={`inline-block text-[11px] font-medium rounded px-1.5 py-0.5 ${tones[tone]}`}>
      {children}
    </span>
  )
}

function HitAction({ hit }) {
  if (hit.action === 'edit') {
    return (
      <Link to="/settings" className="text-xs font-semibold text-indigo-600 hover:text-indigo-800">
        Edit in Settings
      </Link>
    )
  }
  if (hit.action === 'resolve') {
    return <span className="text-xs text-gray-600">resolve · <code className="text-[11px]">{hit.action_route}</code></span>
  }
  return <Tag>manual</Tag>
}

function Hit({ hit }) {
  return (
    <li className="border border-gray-200 rounded-lg px-3 py-2 space-y-1.5" data-testid="sweep-hit">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] text-gray-500 min-w-0 truncate">
          {STORE_LABEL[hit.store] || hit.store} · #{hit.row_id} · line {hit.line_index}
          {hit.location ? <> · {hit.location}</> : null}
        </p>
        <HitAction hit={hit} />
      </div>
      <p className="text-xs text-gray-800 break-words">{hit.snippet}</p>
      <div className="flex flex-wrap gap-1">
        {hit.restriction_terms?.length > 0 && (
          <Tag tone="amber">restriction terms present: {hit.restriction_terms.join(', ')}</Tag>
        )}
        {hit.marked_resolved && <Tag tone="green">history</Tag>}
        {hit.opposite_side && <Tag tone="indigo">other side</Tag>}
        {(hit.other_injuries || []).map((o) => (
          <Tag key={o.entry_id} tone={o.active ? 'red' : 'gray'}>
            also names #{o.entry_id} {o.key}{o.active ? ' (active)' : ' (resolved)'}
          </Tag>
        ))}
        <Tag>in chat context: {hit.reaches_context}</Tag>
      </div>
    </li>
  )
}

function Audit({ audit, note }) {
  if (!audit?.length) return null
  return (
    <div className="space-y-1.5">
      <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wide">Restrictions on this row</p>
      <ul className="space-y-1.5">
        {audit.map((a) => (
          <li key={a.restriction} className="text-xs text-gray-700 space-y-1" data-testid="sweep-audit">
            <div className="flex flex-wrap items-center gap-1.5">
              <span>{a.restriction}</span>
              {a.status === 'orphan' && <Tag tone="amber">orphan — leaves chat context unless re-homed</Tag>}
              {a.status === 'covered' && <Tag tone="green">covered by the basis</Tag>}
              {a.status === 'rehomed' && a.rehomed_to.map((d) => (
                <Tag key={d.entry_id} tone="indigo">re-homed → #{d.entry_id} {d.key} ({d.signal_type})</Tag>
              ))}
            </div>
            {a.rehomed_to.filter((d) => d.radicular_warning).map((d) => (
              <p key={d.entry_id} className="text-[11px] text-red-700 bg-red-50 rounded px-2 py-1">
                {d.radicular_warning.message}
              </p>
            ))}
          </li>
        ))}
      </ul>
      {note && <p className="text-[11px] text-gray-400">{note}</p>}
    </div>
  )
}

export default function InjurySweep({ title, state, onAgain, onClose }) {
  const { loading, data, error } = state
  const valid = data && Array.isArray(data.hits)
  const hits = valid ? data.hits : []
  const manualCount = hits.filter((h) => h.action === 'none').length

  return (
    <section className="bg-white border border-amber-200 rounded-2xl p-4 space-y-3" aria-label="Clearance sweep">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">Clearance sweep — {title}</h2>
          <p className="text-[11px] text-gray-500">
            Copies of this injury outside the ledger. Read-only — nothing here is changed for you.
          </p>
        </div>
        <div className="flex gap-3 shrink-0">
          <button onClick={onAgain} disabled={loading}
            className="text-xs font-medium text-indigo-600 hover:text-indigo-800 disabled:opacity-40">
            Sweep again
          </button>
          <button onClick={onClose} className="text-xs text-gray-500 hover:text-gray-800">Close</button>
        </div>
      </div>

      {loading && <p className="text-xs text-gray-500">Sweeping…</p>}
      {error && <p className="text-xs text-red-600">{error}</p>}

      {valid && !loading && (
        <>
          <Audit audit={data.restriction_audit} note={data.restrictions_note} />

          <div className="space-y-1.5">
            <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wide">
              {hits.length} {hits.length === 1 ? 'copy' : 'copies'} found
              {manualCount > 0 ? ` · ${manualCount} manual` : ''}
            </p>
            {hits.length > 0 && <ul className="space-y-2">{hits.map((h) => (
              <Hit key={`${h.store}:${h.row_id}:${h.location}:${h.line_index}`} hit={h} />
            ))}</ul>}
            <p className="text-[11px] text-gray-400">
              {(data.stores || []).map((s) => `${STORE_LABEL[s.store] || s.store}: ${STORE_STATUS[s.status] || s.status}`).join(' · ')}
            </p>
          </div>

          <div className="space-y-1">
            <p className="text-[11px] font-medium text-gray-500 uppercase tracking-wide">Outside the app — check by hand</p>
            <ul className="space-y-1">
              {(data.manual_checklist || []).map((c) => (
                <li key={c.store} className="text-xs text-gray-700 flex items-start gap-2" data-testid="sweep-manual">
                  <Tag>manual</Tag>
                  <span><span className="font-medium">{c.where}</span> — {c.why}</span>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </section>
  )
}
