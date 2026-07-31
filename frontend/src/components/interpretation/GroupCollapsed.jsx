// A stable group: the axis-frame one-liner only. Nothing surfaced, so the members stay folded
// away — but the group is still read, never dropped.
//
// `verdict` / `confidence` removed with #152; see GroupCard.

export default function GroupCollapsed({ group }) {
  return (
    <section className="bg-white border border-gray-200 rounded-2xl px-5 py-4 space-y-1">
      <div className="flex items-baseline gap-2 flex-wrap">
        <h3 className="text-sm font-medium text-gray-900">{group.display_name}</h3>
      </div>
      {group.axis_verdict?.text && (
        <p className="text-xs text-gray-600">{group.axis_verdict.text}</p>
      )}
    </section>
  )
}
