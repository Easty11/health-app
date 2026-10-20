import { useEffect, useState } from 'react'
import { ReferenceArea, ReferenceLine } from 'recharts'
import api from '../../api'

// Training-phase BANDS, shaded behind every /metrics chart, with a legend per card (R11).
//
// The earlier design drew a labelled dashed line at each ledger boundary and snapped it to the
// next data day; it misread (a label sat over the PRECEDING phase's bars) and dropped a phase
// that began after the last data day, so the chart showed no sign the phase had started. R11
// replaced it: a phase is a shaded span, its NAME lives in a legend outside the plot (no
// in-chart text), and a phase after the last data day is never dropped — it stays in the legend,
// marked "no data yet".
//
// One fetch of the phase ledger per page (`usePhaseMarkers`), threaded into LoadChart /
// FormChart / ReadinessChart / ExerciseChart through TimeSeriesChart's `markers` prop. The
// ledger is reused, NOT re-endpointed: `GET /engine/phase/history`.
//
// THE MODEL (R11 assumptions, confirmed as written):
//   * Colour is per phase NAME, an exact match on `label`, not per ledger row.
//   * Back-to-back rows with one name (a same-day correction, a re-entry straight after) are ONE
//     band, with a thin dashed line, no label, at each handoff.
//   * The same name entered again after another phase (or after a gap) is a SECOND band in the
//     same colour.
//   * A zero-length row (`closed_on` on or before `entered_on`, #379) never spanned a day: it
//     draws no band, no line and no legend entry.
// A row covers [entered_on, closed_on) — `closed_on` is the day the NEXT phase starts, which is
// what makes a same-day correction zero-length. An open row runs to the series end.
//
// A DAY IS A SLOT. Day d occupies [d - 0.5, d + 0.5], so a band edge is the boundary between two
// days and adjacent bands abut without a gap or overlap. On a time axis that is literal; on a
// category axis it is the band scale's slot (bars) — see TimeSeriesChart.

// The ONE place a band colour is written down. Assigned by NAME in the order each name first
// appears in the ledger, wrapping if there are more names than colours. Light theme only; there
// is no token layer (the app has no dark mode).
export const phaseBandPalette = ['#0ea5e9', '#f43f5e', '#10b981', '#8b5cf6', '#f59e0b', '#64748b']

// Low, so the bars and lines stay the focus.
export const phaseBandOpacity = 0.16

// Legend strings (#121: new code carries these two, greppable in the served bundle).
export const LEGEND_TITLE = 'Training phases'
export const NO_DATA_YET = 'no data yet'

const DAY_MS = 86400000

// Integer days since the epoch. A plain ISO date parses as UTC midnight, so this is exact and
// locale-independent; a number is already an epoch day (the time axis' x).
export function epochDayOf(v) {
  return typeof v === 'number' ? v : Math.round(Date.parse(v) / DAY_MS)
}

// The ledger rows → the spans the charts draw: ascending, zero-length rows dropped, back-to-back
// same-name rows merged (their handoff dates kept), each with its name's colour. Pure.
export function phaseSegments(history) {
  const rows = (history || [])
    .filter((p) => p && p.label && p.entered_on)
    .filter((p) => !(p.closed_on != null && p.closed_on <= p.entered_on))
    .sort((a, b) => (
      a.entered_on < b.entered_on ? -1 : a.entered_on > b.entered_on ? 1 : (a.id ?? 0) - (b.id ?? 0)
    ))
  const colourOf = new Map()
  const segments = []
  for (const p of rows) {
    if (!colourOf.has(p.label)) {
      colourOf.set(p.label, phaseBandPalette[colourOf.size % phaseBandPalette.length])
    }
    const prev = segments[segments.length - 1]
    if (prev && prev.label === p.label && prev.end != null && prev.end >= p.entered_on) {
      prev.handoffs.push(p.entered_on)
      prev.end = p.closed_on ?? null
    } else {
      segments.push({
        label: p.label,
        color: colourOf.get(p.label),
        start: p.entered_on,
        end: p.closed_on ?? null,
        handoffs: [],
      })
    }
  }
  return segments
}

// One fetch per page. Returns the segments ([] until resolved / on error — the bands are an
// overlay, never the reason a chart fails to draw).
export function usePhaseMarkers() {
  const [markers, setMarkers] = useState([])
  useEffect(() => {
    let alive = true
    api.get('/engine/phase/history')
      .then((res) => { if (alive) setMarkers(phaseSegments(res.data?.history || [])) })
      .catch(() => { if (alive) setMarkers([]) })
    return () => { alive = false }
  }, [])
  return markers
}

// Where each segment lands on ONE chart, given that chart's own rows. `axis` is the x-axis kind:
//   'time'     — x values are epoch days; a band edge is a slot boundary (d ± 0.5).
//   'category' — x values are the rows' own categories; a band runs from the first data day in
//                its span to the last (the band scale gives each category a full slot).
// A segment is clipped to the data's first and last day. One wholly after the last data day has
// no band and is flagged noDataYet; one wholly before the first day is outside the window and
// appears nowhere. `legend` lists each visible name once, in ledger order.
export function bandLayout(segments, data, xKey, axis = 'category') {
  const empty = { bands: [], handoffs: [], legend: [] }
  if (!segments?.length || !data?.length) return empty

  const rawOf = new Map()
  for (const row of data) rawOf.set(epochDayOf(row[xKey]), row[xKey])
  const days = [...rawOf.keys()].sort((a, b) => a - b)
  const first = days[0]
  const last = days[days.length - 1]

  const bands = []
  const handoffs = []
  const seen = new Map()   // label → { color, shown, noData }
  segments.forEach((seg, i) => {
    const s = epochDayOf(seg.start)
    const e = seg.end == null ? Infinity : epochDayOf(seg.end)
    const entry = seen.get(seg.label) || { color: seg.color, shown: false, noData: false }
    seen.set(seg.label, entry)
    if (s > last) { entry.noData = true; return }
    if (e <= first) return
    entry.shown = true

    let x1
    let x2
    if (axis === 'time') {
      x1 = Math.max(s, first) - 0.5
      x2 = Math.min(e, last + 1) - 0.5
    } else {
      const a = days.find((d) => d >= s)
      const b = [...days].reverse().find((d) => d < e)
      x1 = a == null ? null : rawOf.get(a)
      x2 = b == null || a == null || b < a ? null : rawOf.get(b)
    }
    if (x1 != null && x2 != null && (axis !== 'time' || x2 > x1)) {
      bands.push({ key: `band-${i}`, color: seg.color, x1, x2 })
    }

    for (const h of seg.handoffs) {
      const hd = epochDayOf(h)
      if (hd <= first || hd > last) continue
      const at = axis === 'time' ? hd : rawOf.get(days.find((d) => d >= hd))
      handoffs.push({ key: `handoff-${i}-${h}`, color: seg.color, x: at })
    }
  })

  const legend = [...seen.entries()]
    .filter(([, v]) => v.shown || v.noData)
    .map(([label, v]) => ({ label, color: v.color, noDataYet: !v.shown }))
  return { bands, handoffs, legend }
}

// Recharts only registers a ReferenceArea / ReferenceLine it finds as a DIRECT child of the chart,
// so these return plain arrays for TimeSeriesChart to spread rather than a wrapper component.
export function bandAreasFor(layout) {
  return layout.bands.map((b) => (
    <ReferenceArea
      key={b.key}
      x1={b.x1}
      x2={b.x2}
      className="phase-band"
      fill={b.color}
      fillOpacity={phaseBandOpacity}
      stroke="none"
      ifOverflow="hidden"
    />
  ))
}

export function handoffLinesFor(layout) {
  return layout.handoffs.map((h) => (
    <ReferenceLine
      key={h.key}
      x={h.x}
      className="phase-handoff"
      stroke={h.color}
      strokeOpacity={0.7}
      strokeDasharray="3 3"
      ifOverflow="hidden"
    />
  ))
}
