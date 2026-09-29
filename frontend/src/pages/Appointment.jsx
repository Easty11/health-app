// /appointments/:key — the appointment brief, read in the room (#345).
//
// The reader is the OPERATOR, not the clinician: an agenda of asks, not a clinical synthesis. The
// brief is assembled server-side (GET /appointments/{key}/brief — the same object the MCP tool
// returns); this page only lays it out. It renders the brief's `sections` in the order given, one
// renderer per module; the appointment's `kind` decided which modules are there.
//
// Phone-first: one column, large type. "Leave with" renders in normal flow at the top — never
// sticky, never its own scroll box (a pinned, inner-scrolling box trapped the desktop page scroll).
// It is a compact numbered list: each ask's first sentence, linking down to the full ask. Each row
// renders ONCE: the full text and the tick box live only under Asks. Ticks are LOCAL ONLY
// (localStorage, per appointment) and are never written back in v1. Audience `clinician` drops the
// tick boxes and uses the fuller headings; the content is never rewritten.
//
// Neutral framing (#349): every constraint and finding shows who set it (`Authority`), so a row the
// operator set is never read as a clinician's order.
//
// Print / Save PDF is the browser's own (window.print), and prints a DEDICATED document (#350,
// `BriefPrint`) built from the same brief object — not this screen layout, which is print:hidden.
// Paper has no tick boxes and always speaks in the clinician voice. HubLayout's print: classes still
// drop the app header, the chat and every scroll container around it.

import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import HubLayout from '../components/HubLayout'
import api from '../api'
import { AUTHORITY, HEADINGS } from '../components/appointment/headings'
import BriefPrint from '../components/appointment/BriefPrint'

const tickKey = (key) => `appointment-ticks:${key}`

function loadTicks(key) {
  try {
    const raw = localStorage.getItem(tickKey(key))
    const parsed = raw ? JSON.parse(raw) : []
    return new Set(Array.isArray(parsed) ? parsed : [])
  } catch {
    return new Set() // storage blocked or corrupt — ticks are a convenience, never state
  }
}

function saveTicks(key, ticks) {
  try {
    localStorage.setItem(tickKey(key), JSON.stringify([...ticks]))
  } catch {
    // storage blocked — the tick still shows for this visit
  }
}

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
}

function Empty({ children = 'Nothing here.' }) {
  return <p className="text-base text-gray-400">{children}</p>
}

const askAnchor = (id) => `ask-${id}`

function Tick({ id, ticks, onToggle, label }) {
  return (
    <input
      type="checkbox"
      className="mt-1 h-6 w-6 flex-none accent-indigo-600"
      checked={ticks.has(id)}
      onChange={() => onToggle(id)}
      aria-label={`Done: ${label}`}
    />
  )
}

function AskLine({ id, anchor, text, ctx, children, badge }) {
  return (
    <li id={anchor} className="flex gap-3 items-start scroll-mt-16 break-inside-avoid">
      {ctx.showTicks && <Tick id={id} ticks={ctx.ticks} onToggle={ctx.toggle} label={text} />}
      <div className="min-w-0">
        <p className={`text-lg leading-snug ${ctx.ticks.has(id) ? 'text-gray-400 line-through print:no-underline' : 'text-gray-900'}`}>
          {text}
          {badge && <span className="ml-2 align-middle text-xs font-medium text-amber-700 bg-amber-100 rounded px-1.5 py-0.5">{badge}</span>}
        </p>
        {children}
      </div>
    </li>
  )
}

// Who set a row, as a visible tag. Null for rows with no authority (injuries).
function Authority({ row, audience }) {
  const label = AUTHORITY[audience]?.[row?.asserted_by] ?? row?.authority
  if (!label) return null
  return (
    <span data-authority className="ml-1.5 whitespace-nowrap text-xs font-medium text-gray-600 border border-gray-300 rounded px-1 py-px align-middle">
      {label}
    </span>
  )
}

function RowInline({ row, audience }) {
  if (!row) return null
  return (
    <p className="text-sm text-gray-600 mt-1">
      {row.text}
      {row.exit && <> — ends {row.exit}</>}
      {row.review_by && <> — review by {row.review_by}</>}
      {row.status && row.type !== 'constraint' && <> — {row.status}</>}
      <Authority row={row} audience={audience} />
    </p>
  )
}

const RENDERERS = {
  header: (s) => (
    <div className="space-y-1">
      <p className="text-2xl font-bold text-gray-900">{s.clinician}</p>
      {s.practice && <p className="text-base text-gray-600">{s.practice}</p>}
      <p className="text-lg text-gray-800">{fmtDate(s.date)} · {s.time}</p>
      <p className="text-sm text-gray-500">Status: {s.status}</p>
      {s.detail && <p className="text-base text-gray-700">{s.detail}</p>}
    </div>
  ),

  leave_with: (s) => (
    s.items.length === 0 ? <Empty>No asks written yet.</Empty> : (
      <div>
        <ol className="list-decimal pl-6 space-y-1 text-base text-gray-900">
          {s.items.map((a) => (
            <li key={a.id}>
              <a href={`#${askAnchor(a.id)}`} className="text-indigo-800 hover:underline">{a.short}</a>
            </li>
          ))}
        </ol>
        {s.total > s.items.length && (
          <p className="mt-2 text-sm text-gray-500">+ {s.total - s.items.length} more under Asks</p>
        )}
      </div>
    )
  ),

  asks: (s, ctx) => (
    s.authored.length === 0 && s.derived.length === 0 ? <Empty>No asks.</Empty> : (
      <ul className="space-y-4">
        {s.authored.map((a) => (
          <AskLine key={a.id} id={a.id} anchor={askAnchor(a.id)} text={a.text} ctx={ctx}>
            <RowInline row={a.resolves.row} audience={ctx.audience} />
            {a.resolves.unresolved && (
              <p className="text-xs text-gray-400 mt-1">linked row not found: <code className="font-mono">{a.resolves.entry_key}</code></p>
            )}
            {a.resolves.note && <p className="text-sm text-gray-600 mt-1">{a.resolves.note}</p>}
            {a.folded.map((d) => (
              <p key={`${d.rule}:${d.entry_key}`} className="text-sm text-amber-800 mt-1">From ledger: {d.text}</p>
            ))}
          </AskLine>
        ))}
        {s.derived.map((d) => (
          <AskLine key={`${d.rule}:${d.entry_key}`} id={`ledger:${d.rule}:${d.entry_key}`} text={d.text}
            ctx={ctx} badge="from ledger">
            <RowInline row={d.row} audience={ctx.audience} />
          </AskLine>
        ))}
      </ul>
    )
  ),

  options_prep: (s) => (
    <ul className="space-y-4">
      {s.items.map((a) => (
        <li key={a.ask_id} className="break-inside-avoid">
          <p className="text-lg font-medium text-gray-900">{a.text}</p>
          <ul className="mt-1 space-y-1">
            {a.options.map((o, i) => (
              <li key={i} className="text-base text-gray-700">{o.option} → {o.implication}</li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  ),

  since: (s, ctx) => (
    s.since === null ? <Empty>{s.note}</Empty> : (
      <div className="space-y-3 text-base text-gray-800">
        <p className="text-sm text-gray-500">Since {fmtDate(s.since)}</p>
        {s.injuries.length + s.findings.length + s.constraints.length === 0 && <Empty>No changes recorded.</Empty>}
        {s.injuries.map((i) => (
          <p key={`i:${i.key}`}>{i.text}: {i.change} {fmtDate(i.on)}{i.basis ? ` — ${i.basis}` : ''}</p>
        ))}
        {s.findings.map((f) => (
          <p key={`f:${f.key}`}>Finding ({f.status}, {fmtDate(f.as_of)}): {f.text}<Authority row={f} audience={ctx.audience} /></p>
        ))}
        {s.constraints.map((c) => (
          <p key={`c:${c.key}:${c.change}`}>Constraint {c.change} {fmtDate(c.on)}: {c.text}{c.basis ? ` — ${c.basis}` : ''}<Authority row={c} audience={ctx.audience} /></p>
        ))}
      </div>
    )
  ),

  changes_vs_history: (s, ctx) => (
    s.since === null ? <Empty>{s.note}</Empty> : (
      <div className="space-y-4 text-base">
        {s.findings.length + s.injuries.length === 0 && <Empty>No changes recorded.</Empty>}
        {s.findings.map((f) => (
          <div key={`f:${f.key}`}>
            <p className="text-gray-900">Now ({fmtDate(f.as_of)}): {f.text}<Authority row={f} audience={ctx.audience} /></p>
            {f.previous.length === 0
              ? <p className="text-sm text-gray-500">New — nothing recorded before.</p>
              : f.previous.map((p) => (
                <p key={p.id} className="text-sm text-gray-500">Was ({fmtDate(p.as_of)}): {p.statement}<Authority row={p} audience={ctx.audience} /></p>
              ))}
          </div>
        ))}
        {s.injuries.map((i) => (
          <div key={`i:${i.key}`}>
            <p className="text-gray-900">{i.text} ({fmtDate(i.on)})</p>
            <p className="text-sm text-gray-500">Before: {i.before}</p>
            <p className="text-sm text-gray-700">After: {i.after}</p>
          </div>
        ))}
      </div>
    )
  ),

  current_constraints: (s, ctx) => (
    s.items.length === 0 ? <Empty>No confirmed constraints.</Empty> : (
      <ul className="space-y-3">
        {s.items.map((c) => (
          <li key={c.key} className="text-base text-gray-800">
            <p>{c.text}</p>
            <p className="text-sm text-gray-500">Ends {c.exit} — review by {c.review_by}<Authority row={c} audience={ctx.audience} /></p>
          </li>
        ))}
      </ul>
    )
  ),

  background: (s, ctx) => (
    <div className="space-y-3 text-base text-gray-800">
      {s.injuries.map((i) => (
        <div key={i.key}>
          <p className="font-medium">{i.text} — {i.status}{i.resolved_on ? ` ${fmtDate(i.resolved_on)}` : ''}</p>
          {i.detail && <p className="text-sm text-gray-600">{i.detail}</p>}
        </div>
      ))}
      {s.findings.map((f) => <p key={f.key}>Confirmed ({fmtDate(f.as_of)}): {f.text}<Authority row={f} audience={ctx.audience} /></p>)}
      <p className="text-sm text-gray-400">{s.note}</p>
    </div>
  ),

  imaging_timeline: (s) => (
    <div className="space-y-2 text-base text-gray-800">
      {s.items.length === 0 ? <Empty>No documents referenced.</Empty> : s.items.map((d, i) => (
        <p key={i}>{d.ref} <span className="text-sm text-gray-500">(cited {fmtDate(d.as_of)})</span></p>
      ))}
      <p className="text-sm text-gray-400">{s.note}</p>
    </div>
  ),

  request: (s) => (
    <div className="space-y-2 text-base text-gray-800">
      <p className="text-lg font-medium text-gray-900">{s.ask}</p>
      <p>{s.justification}</p>
      {s.evidence.map((e, i) => <p key={i} className="text-sm text-gray-600">Evidence: {e.ref}</p>)}
      {s.alternatives.length > 0 && <p className="text-sm text-gray-600">Alternatives: {s.alternatives.join('; ')}</p>}
    </div>
  ),

  logistics: (s) => (
    s.items.length === 0 ? <Empty /> : (
      <ul className="list-disc pl-5 space-y-1 text-base text-gray-800">
        {s.items.map((l, i) => <li key={i}>{l}</li>)}
      </ul>
    )
  ),
}

// The injuries this brief is about, by LEDGER KEY (monospace, selectable) — the values the row's
// `scope.parent_keys` holds, so what the brief reads can be checked against /injuries (#346).
function ScopeKeys({ scope }) {
  const keys = scope?.parent_keys || []
  const missing = new Set(scope?.missing_parent_keys || [])
  if (keys.length === 0) return null
  return (
    <div aria-label="Scope" className="text-sm text-gray-600 flex flex-wrap items-center gap-1.5">
      <span>Injuries in scope:</span>
      {keys.map((k) => (
        <code key={k} className={`select-all font-mono text-xs rounded px-1.5 py-0.5 ${
          missing.has(k) ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-800'}`}>
          {k}{missing.has(k) ? ' (not found)' : ''}
        </code>
      ))}
    </div>
  )
}

export default function Appointment() {
  const { key } = useParams()
  const [brief, setBrief] = useState(undefined) // undefined = loading, null = failed
  const [error, setError] = useState(null)
  const [ticks, setTicks] = useState(() => loadTicks(key))

  useEffect(() => {
    api.get(`/appointments/${encodeURIComponent(key)}/brief`)
      .then(({ data }) => setBrief(data))
      .catch((err) => {
        setError(err.response?.status === 404 ? 'No appointment with this key.' : 'Could not load the brief.')
        setBrief(null)
      })
  }, [key])

  function toggle(id) {
    setTicks((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      saveTicks(key, next)
      return next
    })
  }

  const audience = brief?.audience === 'clinician' ? 'clinician' : 'operator'
  const ctx = { ticks, toggle, showTicks: audience === 'operator', audience }

  return (
    <HubLayout title="Appointment brief" back="/dashboard">
      <div className="brief-print max-w-2xl mx-auto px-4 py-5 space-y-6 print:hidden" data-testid="appointment-brief">
        {brief === undefined && <p className="text-base text-gray-400">Loading…</p>}
        {brief === null && <p className="text-base text-red-600">{error}</p>}
        {brief && (
          <div className="flex justify-end print:hidden">
            <button
              type="button"
              onClick={() => window.print()}
              className="text-sm font-medium text-indigo-700 border border-indigo-200 rounded-lg px-3 py-1.5 hover:bg-indigo-50"
            >
              Print / Save PDF
            </button>
          </div>
        )}
        {brief && !brief.sections.some((s) => s.module === 'header') && <ScopeKeys scope={brief.scope} />}
        {brief && brief.sections.map((s) => {
          const render = RENDERERS[s.module]
          if (!render) return null
          // Normal flow at every width: no sticky, no max-height, no inner scroll (the desktop bug).
          const lead = s.module === 'leave_with'
          return (
            <section
              key={s.module}
              aria-label={HEADINGS[s.module][audience]}
              className={lead
                ? 'bg-indigo-50 border border-indigo-200 rounded-2xl p-4'
                : 'bg-white border border-gray-200 rounded-2xl p-4'}
            >
              <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500 mb-3 break-after-avoid">
                {HEADINGS[s.module][audience]}
              </h2>
              {render(s, ctx)}
              {s.module === 'header' && <div className="mt-3"><ScopeKeys scope={brief.scope} /></div>}
            </section>
          )
        })}
        {brief && brief.limits?.length > 0 && (
          <footer className="text-xs text-gray-400 space-y-1">
            {brief.limits.map((l, i) => <p key={i}>{l}</p>)}
          </footer>
        )}
      </div>
      {brief && <BriefPrint brief={brief} />}
    </HubLayout>
  )
}
