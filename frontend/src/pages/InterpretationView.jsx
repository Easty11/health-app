// Lab interpretation — three-section render of the contract v0.4 §2 object.
//
// Increment 1: STATIC. The source is the committed fixture, not a producer;
// there is no LLM pass, no tap, no register. The fixture IS the contract's
// worked example, so this view cannot drift from what the producer will emit.

import { Link } from 'react-router-dom'
import interpretationExample from '../fixtures/interpretationExample.json'
import { splitSections } from '../components/interpretation/sections'
import GroupCard from '../components/interpretation/GroupCard'
import GroupCollapsed from '../components/interpretation/GroupCollapsed'
import MechanismsIndex from '../components/interpretation/MechanismsIndex'

function formatDate(iso) {
  return iso ? iso.slice(0, 10) : '—'
}

export default function InterpretationView() {
  const interpretation = interpretationExample
  const { meta } = interpretation
  const { moved, stable } = splitSections(interpretation)

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
          <div className="flex flex-wrap gap-1.5 pt-1">
            {meta.protocol_context_snapshot.map((factor) => (
              <span
                key={factor.factor}
                className="text-xs text-gray-600 bg-gray-100 rounded-full px-2 py-0.5"
              >
                {factor.detail}
              </span>
            ))}
          </div>
        </div>

        <section className="space-y-3">
          <h2 className="text-sm font-bold text-gray-900">What Moved</h2>
          {moved.length === 0 ? (
            <p className="text-xs text-gray-500">Nothing moved on this panel.</p>
          ) : (
            moved.map((group) => <GroupCard key={group.group_key} group={group} />)
          )}
        </section>

        <section className="space-y-3">
          <h2 className="text-sm font-bold text-gray-900">Stable</h2>
          {stable.length === 0 ? (
            <p className="text-xs text-gray-500">No stable groups on this panel.</p>
          ) : (
            stable.map((group) => <GroupCollapsed key={group.group_key} group={group} />)
          )}
        </section>

        <MechanismsIndex movedGroups={moved} />
      </div>
    </div>
  )
}
