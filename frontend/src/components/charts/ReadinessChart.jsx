import { useEffect, useMemo, useState } from 'react'
import api from '../../api'
import TimeSeriesChart from './TimeSeriesChart'

// Visuals increment 2: the OBSERVED readiness trend, from `GET /series/readiness`. Read-only.
//
// SMALL MULTIPLES, not one overlaid chart, and deliberately so: the two series live on
// different scales that must not share a y-axis — morning readiness is a 1–5 ORDINAL
// self-report, resting HRV is a continuous quantity in milliseconds. Overlaying them would be
// the cross-unit axis this project rejects (the same trap the load windows avoid). So each gets
// its own panel and its own axis.
//
// This is NOT an actual-vs-forecast surface. `model_forecast` is written nowhere today and, on
// a 0–10 scale, is not a residual against a 1–5 self-report anyway (OPEN_QUESTIONS Q141). Until
// that resolves, this shows only what was observed — honestly, each series on its own scale.
//
// Two rules the panels share:
//   * NULLS ARE GAPS. A day with no AM check-in is `morning_readiness === null` and breaks the
//     line (connectNulls=false in the wrapper) rather than dropping to zero — a missing report
//     is not a readiness of zero.
//   * NO SMOOTHING. `lineType="linear"` for the ordinal self-report: a monotone spline would
//     invent between-day values the 1–5 reading never asserted.

const READINESS_COLOR = '#4f46e5'
const HRV_COLOR = '#0d9488'

// Visible dot per observed day. A gap day (null value for this series) gives Recharts null
// coordinates, so this returns nothing and no dot is drawn there — the gap stays a gap.
function ObservationDot(color, cls) {
  function Dot(props) {
    const { cx, cy } = props
    if (cx == null || cy == null) return null
    return (
      <circle cx={cx} cy={cy} r={2.5} className={cls} fill={color} stroke={color} strokeWidth={1} />
    )
  }
  return <Dot />
}

function Panel({ label, hint, data, dataKey, name, color, dotClass, yDomain, width, height }) {
  return (
    <div aria-label={label} className="space-y-1">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-xs font-semibold text-gray-700">{label}</h3>
        <p className="text-[11px] text-gray-400">{hint}</p>
      </div>
      <div className="overflow-x-auto">
        <TimeSeriesChart
          data={data}
          lines={[{ dataKey, name, color, dot: ObservationDot(color, dotClass) }]}
          xKey="date"
          width={width}
          height={height}
          yDomain={yDomain}
          lineType="linear"
          strokeWidth={1.5}
        />
      </div>
    </div>
  )
}

export default function ReadinessChart({ width, height, days = 90 }) {
  const [points, setPoints] = useState(null) // null = loading, [] = loaded-empty
  const [error, setError] = useState('')

  // No synchronous setState in the effect body — only its async then/catch callbacks set state
  // (the LoadChart discipline that keeps `react-hooks/set-state-in-effect` clean). A range
  // change re-runs it and the previous points stay until the new data resolves; only first
  // mount shows the loading state (`points` starts null).
  useEffect(() => {
    let alive = true
    api.get('/series/readiness', { params: { days } })
      .then((res) => { if (alive) { setPoints(res.data?.points || []); setError('') } })
      .catch(() => { if (alive) { setPoints([]); setError('Could not load readiness.') } })
    return () => { alive = false }
  }, [days])

  const data = useMemo(() => points || [], [points])
  const hasData = !!points && points.length > 0

  // A panel's height defaults to a compact small-multiple; fall to that when no explicit height
  // is given so the two panels stack without either dominating.
  const panelHeight = height ?? 180

  return (
    <section aria-label="Readiness" className="bg-white border border-gray-200 rounded-2xl p-4 space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-gray-900">Readiness</h2>
        <p className="text-[11px] text-gray-400">Observed trend · missing days are gaps, not zeros.</p>
      </div>

      {points === null && (
        <p className="text-xs text-gray-400 py-8 text-center">Loading readiness…</p>
      )}

      {points !== null && !hasData && (
        <p className="text-xs text-gray-400 py-8 text-center">
          {error || 'No readiness yet — submit a morning check-in and it will appear here.'}
        </p>
      )}

      {hasData && (
        <div className="space-y-4">
          <Panel
            label="Morning self-report"
            hint="1–5 ordinal"
            data={data}
            dataKey="morning_readiness"
            name="Morning readiness"
            color={READINESS_COLOR}
            dotClass="readiness-dot"
            yDomain={[1, 5]}
            width={width}
            height={panelHeight}
          />
          <Panel
            label="Resting HRV"
            hint="ms"
            data={data}
            dataKey="passive_hrv_ms"
            name="Resting HRV"
            color={HRV_COLOR}
            dotClass="hrv-dot"
            yDomain={['auto', 'auto']}
            width={width}
            height={panelHeight}
          />
        </div>
      )}
    </section>
  )
}
