// The group's shared levers, rendered in-card beside the markers they act on
// (present-marker). An already-in-play lever is LABELLED, never dropped (#49).
// Non-interactive this increment — tap is increment 3.

import { leverAnchorId } from './sections'

export default function LeverStrip({ group }) {
  if (group.shared_levers.length === 0) return null

  return (
    <div className="border-t border-gray-200 bg-gray-50 px-5 py-3 space-y-2">
      <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">Levers</p>
      {group.shared_levers.map((lever) => (
        <div
          key={lever.lever_key}
          id={leverAnchorId(group.group_key, lever.lever_key)}
          className="scroll-mt-16 space-y-1"
        >
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="text-sm font-medium text-gray-900">{lever.label}</span>
            <span className="text-xs text-gray-500 border border-gray-200 rounded-full px-2 py-0.5">
              {lever.grade}
            </span>
            {lever.status === 'already_in_play' && (
              <span className="text-xs text-gray-600 bg-gray-200 rounded-full px-2 py-0.5">
                already in play
              </span>
            )}
          </div>
          <p className="text-xs text-gray-600">{lever.mechanism_summary}</p>
          {lever.already_in_play_reason && (
            <p className="text-xs text-gray-500">{lever.already_in_play_reason}</p>
          )}
        </div>
      ))}
    </div>
  )
}
