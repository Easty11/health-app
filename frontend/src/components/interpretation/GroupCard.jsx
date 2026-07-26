// A moved group, rendered whole: axis-verdict header (monochrome — the verdict
// is a platform inference, so it never carries colour), every member line, then
// the in-card shared-levers strip.

import MemberLine from './MemberLine'
import LeverStrip from './LeverStrip'

export default function GroupCard({ group }) {
  return (
    <section className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
      <header className="px-5 py-4 space-y-1">
        <div className="flex items-baseline gap-2 flex-wrap">
          <h3 className="text-sm font-bold text-gray-900">{group.display_name}</h3>
          <span className="text-xs text-gray-500 border border-gray-200 rounded-full px-2 py-0.5">
            {group.axis_verdict.verdict}
          </span>
          <span className="text-xs text-gray-400">{group.axis_verdict.confidence}</span>
        </div>
        <p className="text-xs text-gray-600">{group.axis_verdict.text}</p>
      </header>

      {group.members.map((member) => (
        <MemberLine key={member.marker_canonical} member={member} />
      ))}

      <LeverStrip group={group} />
    </section>
  )
}
