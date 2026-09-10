import { useEffect, useMemo, useState } from 'react'
import api from '../../api'
import TimeSeriesChart from './TimeSeriesChart'

// First chart in the app (Visuals increment 1): daily training load per window, from
// `GET /series/load`. One LINE per load_window over `daily_load`; the range selector reloads
// the series at 30/90/180 days. Read-only — it draws what the Banister rollup already wrote,
// shaping nothing.

const RANGES = [30, 90, 180]

// Window palette — brand-neutral, distinguishable in both themes. One colour per window in
// series order; wraps if more windows ever light up than colours listed.
const COLORS = ['#4f46e5', '#0d9488', '#d97706', '#db2777', '#2563eb', '#65a30d']

// A muted, hollow, dashed dot marks a point the MODEL ITSELF flags as cold-start
// (`maturity === 'low'`): before a window has ≥42d continuous history its EWMA stocks are not
// yet trustworthy. Annotate-never-suppress (#10/#28) — the point is drawn, just visibly
// provisional, never dropped. `matKey` is the merged-row field holding this window's maturity
// for the day; Recharts clones this element per point, adding cx/cy/payload/index.
function MaturityDot(props) {
  const { cx, cy, payload, matKey, color } = props
  if (cx == null || cy == null) return null
  const cold = payload?.[matKey] === 'low'
  return (
    <circle
      cx={cx}
      cy={cy}
      r={cold ? 2.5 : 3}
      className={cold ? 'load-dot load-dot--cold' : 'load-dot load-dot--mature'}
      data-maturity={cold ? 'low' : 'ok'}
      fill={cold ? 'var(--chart-cold-fill, #ffffff)' : color}
      stroke={color}
      strokeWidth={1}
      strokeDasharray={cold ? '2 1' : undefined}
      opacity={cold ? 0.55 : 1}
    />
  )
}

// Fold the per-window series into one row per day keyed by window (`daily_load`) plus the
// per-window maturity (`<window>__mat`) the dot reads. Days present in only some windows leave
// the others null on that row, so a window's line breaks over days it has no data for
// (connectNulls={false}) rather than drawing a false straight segment across the gap.
function mergeSeries(windows) {
  const byDay = new Map()
  for (const w of windows) {
    for (const p of w.points) {
      let row = byDay.get(p.day)
      if (!row) {
        row = { day: p.day }
        byDay.set(p.day, row)
      }
      row[w.load_window] = p.daily_load
      row[`${w.load_window}__mat`] = p.maturity
    }
  }
  return [...byDay.values()].sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : 0))
}

export default function LoadChart({ width, height, initialDays = 90 }) {
  const [days, setDays] = useState(initialDays)
  const [windows, setWindows] = useState(null) // null = loading, [] = loaded-empty
  const [error, setError] = useState('')

  // Fetch on mount and whenever the range changes. The loading reset (windows → null) lives in
  // `selectRange`, not here, so the effect body calls no setState synchronously — only its
  // async then/catch callbacks do, which is the intended place. On mount `windows` is already
  // null (its initial value), so the loading state shows without an in-effect reset.
  useEffect(() => {
    let alive = true
    api.get('/series/load', { params: { days } })
      .then((res) => { if (alive) setWindows(res.data?.windows || []) })
      .catch(() => { if (alive) { setWindows([]); setError('Could not load training load.') } })
    return () => { alive = false }
  }, [days])

  function selectRange(r) {
    if (r === days) return
    setWindows(null)   // back to loading until the new range resolves
    setError('')
    setDays(r)
  }

  const data = useMemo(() => (windows ? mergeSeries(windows) : []), [windows])
  const lines = useMemo(
    () => (windows || []).map((w, i) => {
      const color = COLORS[i % COLORS.length]
      return {
        dataKey: w.load_window,
        name: w.unit ? `${w.load_window} (${w.unit})` : w.load_window,
        color,
        dot: <MaturityDot matKey={`${w.load_window}__mat`} color={color} />,
      }
    }),
    [windows],
  )

  const hasData = !!windows && windows.length > 0 && data.length > 0

  return (
    <section aria-label="Training load" className="bg-white border border-gray-200 rounded-2xl p-4 space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">Training load</h2>
          <p className="text-[11px] text-gray-400">Daily load per window · dashed points are pre-maturity (cold-start).</p>
        </div>
        <div role="group" aria-label="Range" className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => selectRange(r)}
              aria-pressed={r === days}
              className={`rounded-lg px-2 py-1 text-xs font-medium transition-colors ${
                r === days
                  ? 'bg-indigo-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {r}d
            </button>
          ))}
        </div>
      </div>

      {windows === null && (
        <p className="text-xs text-gray-400 py-8 text-center">Loading training load…</p>
      )}

      {windows !== null && !hasData && (
        <p className="text-xs text-gray-400 py-8 text-center">
          {error || 'No training load yet — log some sessions and it will appear here.'}
        </p>
      )}

      {hasData && (
        <div className="overflow-x-auto">
          <TimeSeriesChart data={data} lines={lines} xKey="day" width={width} height={height} />
        </div>
      )}
    </section>
  )
}
