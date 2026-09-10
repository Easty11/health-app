import { useEffect, useMemo, useState } from 'react'
import { ReferenceArea, ReferenceDot } from 'recharts'
import api from '../../api'
import TimeSeriesChart from './TimeSeriesChart'

// One canonical marker's value over collection dates (Lab visuals). The first consumer of
// `GET /series/lab/{canonical}`; the endpoint is the reusable piece (the appointment brief
// reads it too). Read-only — it draws what the platform already recorded and re-derives nothing.
//
// What the chart says that a bare line would not:
//   * The reference band is PER-DRAW and STEPPED (D1). Each segment spans two consecutive draws
//     and takes the EARLIER draw's range — the lab's range can change between draws, and a single
//     flat band would silently assert one range held throughout. N draws ⇒ N−1 segments.
//   * Point colour is the platform's `computed_flag` (H/L), never re-derived here. The tooltip
//     shows `lab_flag` alongside when the two DISAGREE (D1) — an edge value or an OCR slip, a real
//     signal, not noise.
//   * A CENSORED result ('<0.3') is a hollow marker AT the bound and a GAP in the line (D2) — the
//     assay reported "below 0.3", not a measurement of 0.3; plotting 0.3 as a vertex fabricates one.
//   * DERIVED points take a diamond; LOW-CONFIDENCE points are muted, same treatment as a
//     cold-start bar (D5).
// Qualitative / unmapped / unit-mismatched results never reach the plot — the endpoint returns
// them in `excluded[]` and they are summarised beneath (D3), unmapped ones pointing at the bind
// control on the ingestion surface below.

const BASE_COLOR = '#4f46e5'
const FLAG_COLOR = { H: '#dc2626', L: '#d97706' }
const LOW_CONFIDENCE = 0.85 // matches the extraction suspect threshold (labs.py field_confidence)

const EXCLUDED_LABEL = {
  qualitative: 'non-numeric (text result)',
  unit_mismatch: 'unit mismatch (not converted)',
  unmapped: 'not yet mapped to this marker',
}

// Integer days since the epoch — the numeric x for the time axis (TimeSeriesChart xType="time").
// A plain ISO date parses as UTC midnight, so this is exact and locale-independent.
function epochDay(dateStr) {
  return Math.round(Date.parse(dateStr) / 86400000)
}

function pointColor(p) {
  return FLAG_COLOR[p.computed_flag] || BASE_COLOR
}

// The measured-value dot. A censored point is null in the line data, so Recharts passes no
// coordinates and this draws nothing there — the gap stays a gap (D2). Derived → a diamond;
// low-confidence → muted (opacity + dashed stroke), the cold-start treatment (D5).
function LabDot(props) {
  const { cx, cy, payload } = props
  if (cx == null || cy == null || payload?.value == null) return null
  const color = pointColor(payload)
  const muted = payload.confidence < LOW_CONFIDENCE
  const common = {
    fill: muted ? '#fff' : color,
    stroke: color,
    strokeWidth: muted ? 1 : 1.5,
    strokeDasharray: muted ? '2 2' : undefined,
    fillOpacity: muted ? 0.4 : 1,
  }
  if (payload.is_derived) {
    // a diamond (rotated square) marks a derived value — a distinct SHAPE, legible without colour
    const r = 4
    return (
      <rect
        x={cx - r} y={cy - r} width={r * 2} height={r * 2}
        transform={`rotate(45 ${cx} ${cy})`}
        className="lab-dot lab-dot--derived" {...common}
      />
    )
  }
  return <circle cx={cx} cy={cy} r={3} className={`lab-dot${muted ? ' lab-dot--muted' : ''}`} {...common} />
}

function LabTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const p = payload[0]?.payload
  if (!p) return null
  const disagrees = p.lab_flag && p.lab_flag !== p.computed_flag
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs shadow-sm">
      <p className="font-medium text-gray-900">{p.date}</p>
      <p className="tabular-nums text-gray-700">
        {p.operator || ''}{p.raw_value}{p.unit ? ` ${p.unit}` : ''}
        {p.operator && <span className="text-gray-400"> (censored — below the reported limit)</span>}
      </p>
      {(p.ref_low != null || p.ref_high != null) && (
        <p className="text-gray-500">
          Reference range: {p.ref_low != null ? `${p.ref_low_exclusive ? '>' : '≥'}${p.ref_low}` : ''}
          {p.ref_low != null && p.ref_high != null ? '–' : ''}
          {p.ref_high != null ? `${p.ref_high_exclusive ? '<' : '≤'}${p.ref_high}` : ''}
        </p>
      )}
      {p.computed_flag && <p className="font-medium" style={{ color: pointColor(p) }}>Flag: {p.computed_flag}</p>}
      {disagrees && <p className="text-amber-700">Lab flagged {p.lab_flag} — disagrees with the computed {p.computed_flag || 'none'}</p>}
      {p.is_derived && <p className="text-gray-500">Derived (calculated, not directly measured)</p>}
      {p.confidence < LOW_CONFIDENCE && <p className="text-gray-400">Low extraction confidence</p>}
    </div>
  )
}

export default function LabChart({ canonical, width, height }) {
  // `series` carries the canonical it was fetched for, so a switch shows loading until the NEW
  // series arrives rather than briefly drawing the old marker's data. No synchronous setState in
  // the effect body — only its async callbacks set state (the LoadChart/ExerciseChart discipline
  // that keeps `react-hooks/set-state-in-effect` clean).
  const [series, setSeries] = useState(null)

  useEffect(() => {
    if (!canonical) return undefined
    let alive = true
    api.get(`/series/lab/${canonical}`)
      .then((res) => { if (alive) setSeries(res.data) })
      .catch(() => { if (alive) setSeries({ canonical, unit: null, points: [], excluded: [], error: true }) })
    return () => { alive = false }
  }, [canonical])

  // Only trust the series if it is the one for the current marker (a mid-switch stale series is
  // ignored, so the chart never draws another marker's points under this heading).
  const current = series && series.canonical === canonical ? series : null
  const points = current?.points || []
  const excluded = current?.excluded || []
  const unit = current?.unit || null

  // One row per point, keyed on epoch-day x. A censored point's `value` is null so the line
  // breaks there and no measured dot draws; its bound is carried as `raw_value` for the hollow
  // marker and the tooltip.
  const data = useMemo(() => (current?.points || []).map((p) => ({
    x: epochDay(p.date),
    value: p.operator ? null : p.value,
    raw_value: p.value,
    date: p.date,
    operator: p.operator,
    ref_low: p.ref_low,
    ref_high: p.ref_high,
    ref_low_exclusive: p.ref_low_exclusive,
    ref_high_exclusive: p.ref_high_exclusive,
    computed_flag: p.computed_flag,
    lab_flag: p.lab_flag,
    is_derived: p.is_derived,
    confidence: p.confidence,
    unit: current?.unit || null,
  })), [current])

  // Stepped reference band: one segment per gap between consecutive draws, taking the EARLIER
  // draw's range (D1). A draw with an incomplete range contributes no segment rather than a
  // half-open rectangle. So segments ≤ draws − 1, and = draws − 1 when every draw carries both bounds.
  const bandSegments = useMemo(() => {
    const pts = current?.points || []
    const segs = []
    for (let i = 0; i < pts.length - 1; i += 1) {
      const a = pts[i]
      if (a.ref_low == null || a.ref_high == null) continue
      segs.push({ x1: epochDay(a.date), x2: epochDay(pts[i + 1].date), y1: a.ref_low, y2: a.ref_high })
    }
    return segs
  }, [current])

  // Censored points: hollow markers AT the bound (never line vertices). Coloured by flag.
  const censored = useMemo(() => (current?.points || []).filter((p) => p.operator), [current])

  // Explicit y-domain so the band and the censored markers (which can sit far outside the
  // measured range, e.g. a '<0.3' below an 8–28 band) are always in view. Recharts' auto
  // domain considers the line only, not reference shapes.
  const yDomain = useMemo(() => {
    const vals = []
    for (const p of (current?.points || [])) {
      if (p.value != null) vals.push(p.value)
      if (p.ref_low != null) vals.push(p.ref_low)
      if (p.ref_high != null) vals.push(p.ref_high)
    }
    if (vals.length === 0) return ['auto', 'auto']
    const lo = Math.min(...vals)
    const hi = Math.max(...vals)
    const pad = (hi - lo) * 0.08 || 1
    return [lo - pad, hi + pad]
  }, [current])

  const hasData = points.length > 0
  const excludedByReason = useMemo(() => {
    const m = {}
    for (const e of (current?.excluded || [])) m[e.reason] = (m[e.reason] || 0) + 1
    return m
  }, [current])

  return (
    <section aria-label="Marker trend" className="bg-white border border-gray-200 rounded-2xl p-4 space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-gray-900">{canonical || 'Marker'}</h2>
        <p className="text-[11px] text-gray-400">
          Value over collection dates · shaded band is the lab reference range for that draw
          {unit ? ` · ${unit}` : ''}.
        </p>
      </div>

      {current === null && (
        <p className="text-xs text-gray-400 py-8 text-center">Loading marker…</p>
      )}

      {current !== null && !hasData && (
        <p className="text-xs text-gray-400 py-8 text-center">
          {current.error ? 'Could not load this marker.' : 'No plottable results for this marker yet.'}
        </p>
      )}

      {hasData && (
        <div className="overflow-x-auto">
          <TimeSeriesChart
            data={data}
            series={[{ dataKey: 'value', name: canonical, color: BASE_COLOR, unit, dot: <LabDot /> }]}
            xKey="x"
            xType="time"
            mark="line"
            lineType="linear"
            strokeWidth={1.5}
            width={width}
            height={height}
            yDomain={yDomain}
            tooltipContent={<LabTooltip />}
          >
            {bandSegments.map((s, i) => (
              <ReferenceArea
                key={`band-${i}`}
                x1={s.x1}
                x2={s.x2}
                y1={s.y1}
                y2={s.y2}
                className="lab-ref-band"
                fill="#4f46e5"
                fillOpacity={0.08}
                stroke="none"
                ifOverflow="extendDomain"
              />
            ))}
            {censored.map((p) => (
              <ReferenceDot
                key={`cens-${p.date}`}
                x={epochDay(p.date)}
                y={p.value}
                r={5}
                className="lab-censored-dot"
                fill="#fff"
                stroke={pointColor(p)}
                strokeWidth={1.5}
                ifOverflow="extendDomain"
              />
            ))}
          </TimeSeriesChart>
        </div>
      )}

      {excluded.length > 0 && (
        <div className="border-t border-gray-100 pt-2 space-y-1">
          <p className="text-[11px] font-medium text-gray-400 uppercase tracking-wide">
            {excluded.length} result{excluded.length === 1 ? '' : 's'} not plotted
          </p>
          {Object.entries(excludedByReason).map(([reason, n]) => (
            <p key={reason} className="text-xs text-gray-500">
              {n} {EXCLUDED_LABEL[reason] || reason}
              {reason === 'unmapped' && (
                <span className="text-amber-700"> — bind them on the results below to add them to this trend</span>
              )}
            </p>
          ))}
        </div>
      )}
    </section>
  )
}
