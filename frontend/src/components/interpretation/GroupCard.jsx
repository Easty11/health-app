// A moved group, rendered whole: axis-frame header (monochrome — the frame is a platform
// statement, so it never carries colour), every member line, then the in-card shared-levers
// strip.
//
// `axis_verdict` is `{text}` and nothing else: `verdict` and `confidence` were removed from the
// contract by #152, and `protocol_phase` by #154. The header used to render a verdict chip and a
// confidence figure that no longer exist — they rendered as `undefined`.

import MemberLine from './MemberLine'
import LeverStrip from './LeverStrip'
import GroupAsOf from './GroupAsOf'

export default function GroupCard({ group, panelCollected }) {
  return (
    <section className="bg-white border border-gray-200 rounded-2xl overflow-hidden">
      <header className="px-5 py-4 space-y-1">
        <div className="flex items-baseline gap-2 flex-wrap">
          <h3 className="text-sm font-bold text-gray-900">{group.display_name}</h3>
          <GroupAsOf asOf={group.as_of} panelCollected={panelCollected} />
        </div>
        {group.axis_verdict?.text && (
          <p className="text-xs text-gray-600">{group.axis_verdict.text}</p>
        )}
      </header>

      {group.members.map((member) => (
        <MemberLine key={member.marker_canonical} member={member} panelCollected={panelCollected} />
      ))}

      <LeverStrip group={group} />
    </section>
  )
}
