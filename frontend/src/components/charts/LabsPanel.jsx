import { useEffect, useMemo, useState } from 'react'
import api from '../../api'
import LabsPicker from './LabsPicker'
import LabChart from './LabChart'

// The lab-visuals mount (Lab visuals, step 5): the marker picker + the selected marker's trend,
// shown on /labs above the ingestion surface. Owns the ONE index fetch (`GET /series/labs`) and
// the selection; `LabChart` fetches its own per-marker series. Mirrors `ExerciseChart`'s
// derived-selection discipline — the effective marker is the explicit pick while it is still in
// the (possibly filtered) list, else the first entry — so toggling the flagged filter can't
// leave a now-hidden marker selected.

export default function LabsPanel({ width, height }) {
  const [index, setIndex] = useState(null) // null=loading, [] = none
  const [chosen, setChosen] = useState(null)
  const [flaggedOnly, setFlaggedOnly] = useState(false)

  useEffect(() => {
    let alive = true
    api.get('/series/labs')
      .then((res) => { if (alive) setIndex(res.data || []) })
      .catch(() => { if (alive) setIndex([]) })
    return () => { alive = false }
  }, [])

  const visible = useMemo(
    () => (index || []).filter((e) => !flaggedOnly || e.any_flagged),
    [index, flaggedOnly],
  )
  const canonicals = useMemo(() => visible.map((e) => e.canonical), [visible])
  const selected = chosen && canonicals.includes(chosen) ? chosen : (canonicals[0] ?? null)

  const loaded = index !== null
  const hasMarkers = loaded && (index?.length ?? 0) > 0

  return (
    <section aria-label="Lab markers" className="bg-white border border-gray-200 rounded-2xl p-4 space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-gray-900">Lab markers</h2>
        <p className="text-[11px] text-gray-400">A marker's history against its reference range · no interpretation.</p>
      </div>

      {index === null && (
        <p className="text-xs text-gray-400 py-8 text-center">Loading markers…</p>
      )}

      {loaded && !hasMarkers && (
        <p className="text-xs text-gray-400 py-8 text-center">
          No markers yet — confirm a lab report below and its markers will appear here.
        </p>
      )}

      {hasMarkers && (
        <>
          <LabsPicker
            entries={visible}
            selected={selected}
            onSelect={setChosen}
            flaggedOnly={flaggedOnly}
            onToggleFlagged={() => setFlaggedOnly((v) => !v)}
          />
          {selected
            ? <LabChart canonical={selected} width={width} height={height} />
            : <p className="text-xs text-gray-400 py-8 text-center">No flagged markers.</p>}
        </>
      )}
    </section>
  )
}
