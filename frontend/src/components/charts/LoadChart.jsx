import { useEffect, useMemo, useState } from 'react'
import api from '../../api'
import TimeSeriesChart from './TimeSeriesChart'

// Daily training load per window, from `GET /series/load` — SMALL MULTIPLES, not an overlay.
// One chart per populated window, stacked, each with its own y-axis labelled in that window's
// unit and a shared x-axis domain (so the days line up across the stack). Load is a discrete
// per-day quantity, so it is drawn as BARS; a zero/rest day renders as no bar; pre-maturity
// (cold-start) days keep the muted treatment. Read-only — draws what the Banister rollup wrote.
//
// Why not one chart with many lines: the windows carry incommensurable units (kg_reps vs nm_au
// vs trimp_edw_au). Sharing one y-axis across them is meaningless — TimeSeriesChart now forbids
// it (shared axis ⇒ shared unit). Small multiples is the fix.

const RANGES = [30, 90, 180]

// One colour per window in series order; wraps if more windows light up than colours listed.
const COLORS = ['#4f46e5', '#0d9488', '#d97706', '#db2777', '#2563eb', '#65a30d']

// Fold every window's series onto one shared day domain: one row per day, each window's
// `daily_load` under its own key (0 → null so a rest day draws no bar) plus its maturity under
// `<window>__mat`. Passing this same array to every small multiple is what aligns their x-axes.
function mergeDomain(windows) {
  const byDay = new Map()
  for (const w of windows) {
    for (const p of w.points) {
      let row = byDay.get(p.day)
      if (!row) {
        row = { day: p.day }
        byDay.set(p.day, row)
      }
      row[w.load_window] = p.daily_load === 0 ? null : p.daily_load
      row[`${w.load_window}__mat`] = p.maturity
    }
  }
  return [...byDay.values()].sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : 0))
}

// Range state is optionally LIFTED (Visuals increment 2): when the parent passes `days` +
// `onSelectRange`, LoadChart becomes the controlled lead for a range shared with FormChart and
// ReadinessChart on the same page — its selector drives the parent, which feeds all three the
// same window. Passed neither (its standalone/increment-1 use, and its own test), it owns its
// range internally exactly as before. The selector renders and behaves identically in both
// modes; only WHERE the chosen `days` lives differs.
export default function LoadChart({ width, height, initialDays = 90, days: daysProp, onSelectRange }) {
  const controlled = daysProp != null && typeof onSelectRange === 'function'
  const [internalDays, setInternalDays] = useState(initialDays)
  const days = controlled ? daysProp : internalDays
  const [windows, setWindows] = useState(null) // null = loading, [] = loaded-empty
  const [error, setError] = useState('')

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
    if (controlled) onSelectRange(r)
    else setInternalDays(r)
  }

  const data = useMemo(() => (windows ? mergeDomain(windows) : []), [windows])
  const hasData = !!windows && windows.length > 0 && data.length > 0

  return (
    <section aria-label="Training load" className="bg-white border border-gray-200 rounded-2xl p-4 space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">Training load</h2>
          <p className="text-[11px] text-gray-400">Daily load per window · faded bars are pre-maturity (cold-start).</p>
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
        <div className="space-y-4">
          {windows.map((w, i) => (
            <figure key={w.load_window} className="m-0" aria-label={`${w.load_window} load`}>
              <figcaption className="text-xs font-medium text-gray-600">
                {w.load_window} <span className="text-gray-400 font-normal">({w.unit})</span>
              </figcaption>
              <div className="overflow-x-auto">
                <TimeSeriesChart
                  data={data}
                  series={[{ dataKey: w.load_window, name: w.load_window, color: COLORS[i % COLORS.length], unit: w.unit, matKey: `${w.load_window}__mat` }]}
                  xKey="day"
                  mark="bar"
                  width={width}
                  height={height}
                  hideXLabels={i < windows.length - 1}
                />
              </div>
            </figure>
          ))}
        </div>
      )}
    </section>
  )
}
