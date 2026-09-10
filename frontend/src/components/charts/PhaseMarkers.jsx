import { useEffect, useState } from 'react'
import { ReferenceLine } from 'recharts'
import api from '../../api'

// Training-phase boundaries, overlaid on every /metrics chart (Visuals increment 3, D4).
//
// These markers are what make the page the PLATFORM's view rather than a Hevy clone: a phase
// boundary drawn across the e1RM line is the read that matters — "e1RM fell here, that's when
// Decompression started." One fetch of the phase ledger per page (`usePhaseMarkers`), threaded
// into LoadChart / FormChart / ReadinessChart / ExerciseChart through TimeSeriesChart's
// `markers` prop.
//
// The ledger is reused, NOT re-endpointed: `GET /engine/phase/history` already returns every
// phase with `entered_on`, `closed_on` and `label`, so the brief's "don't add a route that
// duplicates one" is honoured — there is no `/series/phases`.
//
// WHY SNAPPING. A chart x-axis here is CATEGORICAL (one slot per day that carries data); a
// Recharts ReferenceLine only renders at an x that is an actual category. A phase boundary
// rarely lands exactly on a session/observation day, so `referenceLinesFor` snaps each boundary
// to the first category on or AFTER it — the first day the new phase's effect is visible in the
// series — and drops a boundary that falls before the window's first category (a phase that
// began before the range: its start is off-screen, D4's "in range" only). Boundaries that snap
// to the same category collapse to one line (a close/open handoff shares a day).

// The boundaries a phase contributes: its start, and its end when closed (D4 — entered_on AND
// closed_on, each labelled with the phase name; baseline, a null phase, contributes nothing).
export function phaseBoundaries(history) {
  const out = []
  for (const p of history || []) {
    if (!p || !p.label) continue
    if (p.entered_on) out.push({ date: p.entered_on, label: p.label })
    if (p.closed_on) out.push({ date: p.closed_on, label: p.label })
  }
  return out
}

// One fetch per page. Returns the boundary list ([] until resolved / on error — markers are an
// overlay, never the reason a chart fails to draw).
export function usePhaseMarkers() {
  const [markers, setMarkers] = useState([])
  useEffect(() => {
    let alive = true
    api.get('/engine/phase/history')
      .then((res) => { if (alive) setMarkers(phaseBoundaries(res.data?.history || [])) })
      .catch(() => { if (alive) setMarkers([]) })
    return () => { alive = false }
  }, [])
  return markers
}

// Snap a boundary date to the first category (a data row's `xKey`) on or after it. Null when
// the boundary PRECEDES the window's first category (a phase that began before the range — its
// start is off-screen, D4's "in range" only; snapping it onto the first visible day would
// falsely read as a change AT window-start), or when nothing falls on or after it.
export function snapToCategory(categories, boundary) {
  if (!categories.length || boundary < categories[0]) return null
  for (const c of categories) {
    if (c >= boundary) return c
  }
  return null
}

// Build the ReferenceLine elements for a set of markers against the chart's actual categories.
// Returned as a plain array so TimeSeriesChart can spread them as DIRECT children of the Recharts
// chart (Recharts only registers reference lines it finds as direct children; a wrapper component
// would be ignored). Snapped boundaries that collapse onto one category draw a single line.
export function referenceLinesFor(markers, data, xKey) {
  if (!markers?.length || !data?.length) return []
  const categories = data.map((row) => row[xKey])
  const seen = new Set()
  const lines = []
  for (const m of markers) {
    const at = snapToCategory(categories, m.date)
    if (at == null || seen.has(at)) continue
    seen.add(at)
    lines.push(
      <ReferenceLine
        key={`phase-${at}`}
        x={at}
        className="phase-marker"
        stroke="#9ca3af"
        strokeDasharray="4 3"
        ifOverflow="extendDomain"
        label={{ value: m.label, position: 'insideTopRight', fontSize: 10, fill: '#6b7280' }}
      />,
    )
  }
  return lines
}
