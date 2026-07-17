// A stable group: the axis-verdict one-liner only. Nothing moved, so the
// members stay folded away — but the group is still read, never dropped.

export default function GroupCollapsed({ group }) {
  return (
    <section className="bg-white border border-gray-200 rounded-2xl px-5 py-4 space-y-1">
      <div className="flex items-baseline gap-2 flex-wrap">
        <h3 className="text-sm font-medium text-gray-900">{group.display_name}</h3>
        <span className="text-xs text-gray-500 border border-gray-200 rounded-full px-2 py-0.5">
          {group.axis_verdict.verdict}
        </span>
        <span className="text-xs text-gray-400">{group.axis_verdict.confidence}</span>
      </div>
      <p className="text-xs text-gray-600">{group.axis_verdict.text}</p>
    </section>
  )
}
