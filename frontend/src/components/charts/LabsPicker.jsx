// The marker picker for the lab visuals (Lab visuals, step 5). Presentational: the panel owns
// the index fetch and the selection; this renders the ordered list (most-recent draw first, as
// the endpoint returns it) and a "flagged" filter (D6 — show only markers with an out-of-range
// point). A flagged marker carries a small dot so the list reads at a glance.

const FLAG_DOT = { H: '#dc2626', L: '#d97706' }

export default function LabsPicker({ entries, selected, onSelect, flaggedOnly, onToggleFlagged }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">Markers</p>
        <button
          type="button"
          onClick={onToggleFlagged}
          aria-pressed={flaggedOnly}
          className={`rounded-lg px-2 py-1 text-xs font-medium transition-colors ${
            flaggedOnly ? 'bg-amber-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          Flagged only
        </button>
      </div>
      <div role="group" aria-label="Marker" className="flex flex-wrap gap-1">
        {entries.map((e) => (
          <button
            key={e.canonical}
            type="button"
            onClick={() => onSelect(e.canonical)}
            aria-pressed={e.canonical === selected}
            className={`flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium transition-colors ${
              e.canonical === selected
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {e.any_flagged && (
              <span
                aria-hidden="true"
                className="inline-block w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: FLAG_DOT[e.latest?.flag] || '#d97706' }}
              />
            )}
            {e.display_name || e.canonical}
          </button>
        ))}
      </div>
    </div>
  )
}
