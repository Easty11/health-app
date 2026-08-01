// Lab interpretation — three-section render of the contract v0.4 §2 object.
//
// LIVE. The source is `GET /interpretation` (#158), not the committed fixture. The fixture
// remains the test artefact and the conformance oracle; nothing here reads it any more.
//
// Shape parity was verified against the DEPLOYED endpoint before switching: zero structural
// differences, every delta either a data-dependent optional key or the group `as_of` this
// increment adds. A null-audit over the live payload confirmed no field this view hard-reads is
// null there (15 grouped members, 51 ungrouped rows, 7 levers).
//
// THREE STATES A FIXTURE NEVER REQUIRED. A fixture is always present and always well-formed; an
// endpoint is neither. They are kept visibly distinct because an error that renders as an empty
// interpretation is the absence-as-emptiness failure this lane has now produced three times — an
// empty report card that read as "no results", a correctly-declined upload that read as a
// permanent fault, and a safety-band-only group folded into Stable. Loading is not empty, empty
// is not error, and error says so.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api'
import { splitSections } from '../components/interpretation/sections'
import GroupCard from '../components/interpretation/GroupCard'
import GroupCollapsed from '../components/interpretation/GroupCollapsed'
import UngroupedLine from '../components/interpretation/UngroupedLine'
import MechanismsIndex from '../components/interpretation/MechanismsIndex'

function formatDate(iso) {
  return iso ? iso.slice(0, 10) : '—'
}

function Shell({ children }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3 sticky top-0 z-10">
        <Link to="/dashboard" className="text-gray-400 hover:text-gray-700 transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <span className="text-sm font-bold text-gray-900">Interpretation</span>
      </header>
      <div className="max-w-4xl mx-auto px-4 py-5 space-y-6">{children}</div>
    </div>
  )
}

export default function InterpretationView() {
  const [interpretation, setInterpretation] = useState(null)
  const [status, setStatus] = useState('loading') // loading | ready | empty | error
  const [detail, setDetail] = useState('')

  useEffect(() => {
    let cancelled = false
    api.get('/interpretation')
      .then((res) => {
        if (cancelled) return
        setInterpretation(res.data)
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        // 404 is the documented "no lab reports confirmed yet" case — a real, benign state, and
        // NOT an error. Everything else is an error and says so rather than rendering nothing.
        if (err.response?.status === 404) {
          setStatus('empty')
          return
        }
        const d = err.response?.data?.detail
        setDetail(typeof d === 'string' ? d : err.message || 'Unknown error')
        setStatus('error')
      })
    return () => { cancelled = true }
  }, [])

  if (status === 'loading') {
    return (
      <Shell>
        <div className="bg-white border border-gray-200 rounded-2xl p-10 text-center space-y-3">
          <div className="w-8 h-8 mx-auto rounded-full border-2 border-gray-200 border-t-indigo-600 animate-spin" />
          <p className="text-sm text-gray-500">Reading your latest panel…</p>
        </div>
      </Shell>
    )
  }

  if (status === 'empty') {
    return (
      <Shell>
        <div className="bg-white border border-gray-200 rounded-2xl p-8 text-center space-y-3">
          <p className="text-sm font-semibold text-gray-900">No lab results yet</p>
          <p className="text-xs text-gray-500">
            There is nothing to interpret until a lab report has been confirmed. Add one from
            Metrics and this page will read your latest draw.
          </p>
          <Link
            to="/metrics"
            className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-2xl px-5 py-2.5 text-sm transition-colors"
          >
            Go to Metrics
          </Link>
        </div>
      </Shell>
    )
  }

  if (status === 'error') {
    return (
      <Shell>
        <div className="bg-red-50 border border-red-200 rounded-2xl p-6 space-y-2">
          <p className="text-sm font-semibold text-red-800">Could not load your interpretation</p>
          <p className="text-xs text-red-700">
            This is a fault, not an empty result — your data is unaffected and nothing has been
            changed. Reload to try again.
          </p>
          {detail && <p className="text-xs text-red-700/80 font-mono break-words">{detail}</p>}
        </div>
      </Shell>
    )
  }

  const { meta } = interpretation
  const { moved, stable } = splitSections(interpretation)
  const factors = meta.protocol_context_snapshot?.factors ?? []
  const panelCollected = meta.trigger_panel?.collected
  // Ungrouped rows are markers no authored group claims. The view had no section for them, so
  // wiring it to the producer would have silently dropped every one — on the live series that is
  // 51 of 66 markers (Q54).
  const ungrouped = interpretation.ungrouped ?? []

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-3 flex items-center gap-3 sticky top-0 z-10">
        <Link to="/dashboard" className="text-gray-400 hover:text-gray-700 transition-colors">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </Link>
        <span className="text-sm font-bold text-gray-900">Interpretation</span>
      </header>

      <div className="max-w-4xl mx-auto px-4 py-5 space-y-6">
        {/* Panel envelope — what was read, and what it was read against. */}
        <div className="bg-white border border-gray-200 rounded-2xl p-5 space-y-2">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">Panel</p>
          <p className="text-sm font-semibold text-gray-900">
            {meta.trigger_panel.panel_name_raw}{' '}
            <span className="font-normal text-gray-500">
              · collected {formatDate(meta.trigger_panel.collected)}
            </span>
          </p>
          <p className="text-xs text-gray-500">
            Compared against {meta.compared_against.panel_name_raw} ·{' '}
            {formatDate(meta.compared_against.collected)}
          </p>
          {/* `protocol_context_snapshot` is an OBJECT — `{as_of, factors[]}` — not a list. This
              called `.map` on it, which throws. Each factor carries `key` / `type` / `phase` /
              `assumable_present` / `relevant_date`; `detail` and `factor` no longer exist
              (`detail` is deliberately omitted upstream as unbounded free text). */}
          {factors.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {factors.map((factor) => (
                <span
                  key={factor.key}
                  className="text-xs text-gray-600 bg-gray-100 rounded-full px-2 py-0.5"
                >
                  {factor.key}
                  {factor.phase && <span className="text-gray-400"> · {factor.phase}</span>}
                </span>
              ))}
            </div>
          )}
        </div>

        <section className="space-y-3">
          <h2 className="text-sm font-bold text-gray-900">What Moved</h2>
          {moved.length === 0 ? (
            <p className="text-xs text-gray-500">Nothing moved on this panel.</p>
          ) : (
            moved.map((group) => (
              <GroupCard key={group.group_key} group={group} panelCollected={panelCollected} />
            ))
          )}
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-bold text-gray-900">Stable</h2>
          {stable.length === 0 ? (
            <p className="text-xs text-gray-500">No stable groups on this panel.</p>
          ) : (
            stable.map((group) => (
              <GroupCollapsed key={group.group_key} group={group} panelCollected={panelCollected} />
            ))
          )}
        </section>

        <section className="space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="text-sm font-bold text-gray-900">Ungrouped</h2>
            <p className="text-[11px] text-gray-400 text-right">
              Markers no authored group claims. Values and gates only — no relations, no levers.
            </p>
          </div>
          {ungrouped.length === 0 ? (
            <p className="text-xs text-gray-500">No ungrouped markers on this panel.</p>
          ) : (
            <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
              {ungrouped.map((row) => (
                <UngroupedLine key={row.marker_canonical} row={row} panelCollected={panelCollected} />
              ))}
            </div>
          )}
        </section>

        <MechanismsIndex movedGroups={moved} />
      </div>
    </div>
  )
}
