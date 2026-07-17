// The pooled Mechanisms index: NAVIGATION ONLY. A lever is authored once, in
// its group's card; this is a grade-ordered set of jump-links back to that
// in-card strip, so "worth understanding" stays a reading mode without the
// lever being rendered twice as a claim.

import { leverAnchorId, poolLevers } from './sections'

export default function MechanismsIndex({ movedGroups }) {
  const pooled = poolLevers(movedGroups)
  if (pooled.length === 0) return null

  return (
    <section className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
      <header className="px-5 py-4">
        <h2 className="text-sm font-bold text-gray-900">Mechanisms</h2>
        <p className="text-xs text-gray-500">
          Every lever above, ordered by strength of evidence. Each jumps back to where it reads.
        </p>
      </header>
      <ul className="divide-y divide-gray-100">
        {pooled.map(({ lever, groupKey }) => (
          <li key={lever.lever_key}>
            <a
              href={`#${leverAnchorId(groupKey, lever.lever_key)}`}
              className="flex items-baseline gap-2 flex-wrap px-5 py-3 hover:bg-gray-50 transition-colors"
            >
              <span className="text-sm text-gray-900">{lever.label}</span>
              <span className="text-xs text-gray-500 border border-gray-200 rounded-full px-2 py-0.5">
                {lever.grade}
              </span>
              {lever.status === 'already_in_play' && (
                <span className="text-xs text-gray-600 bg-gray-100 rounded-full px-2 py-0.5">
                  already in play
                </span>
              )}
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}
