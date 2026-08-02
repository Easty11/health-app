// A hub tile — a plain doorway (#150 rule 4, and rule 3's scope note: shell tiles do NOT seed
// chat context. Seeding routes through the request-scoped find_marker -> render_asked_lab_value
// path and is a later feature; nothing here touches the standing prompt, per #59).

import { Link } from 'react-router-dom'

export default function Tile({ to, icon, label, detail, children }) {
  return (
    <Link
      to={to}
      className="bg-white border border-gray-200 rounded-2xl p-4 flex flex-col gap-1
        hover:border-indigo-300 hover:shadow-sm transition-all focus:outline-none
        focus:ring-2 focus:ring-indigo-400"
    >
      <span className="text-2xl leading-none" aria-hidden="true">{icon}</span>
      <span className="text-sm font-semibold text-gray-900 mt-1">{label}</span>
      {children ?? <span className="text-xs text-gray-500 leading-snug">{detail}</span>}
    </Link>
  )
}
