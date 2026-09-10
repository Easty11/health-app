import { useEffect, useMemo, useState } from 'react'
import api from '../../api'
import TimeSeriesChart from './TimeSeriesChart'

// Visuals increment 2 (1b): the Banister curves — FITNESS, FATIGUE, FORM — for one load
// window at a time, from the SAME `GET /series/load` the LoadChart reads (no new endpoint;
// `/series/load` already carries fitness/fatigue/form per point per #277). Read-only.
//
// One window at a time, not all overlaid: fitness/fatigue/form share a unit WITHIN a window
// but NOT across windows (mechanical is kg·reps, neuromuscular is nm·au), so three curves ×
// several windows on one axis would be the cross-unit overlay this project already rejects.
// The window selector defaults to the first populated window; the RANGE selector is the
// LoadChart's (lifted to the page), so this chart takes `days` as a prop and shows no range
// control of its own.
//
// FORM GOES NEGATIVE (form = fitness − fatigue), so the y-domain must admit sub-zero: passing
// `yDomain={['auto','auto']}` fits the axis to the data extent instead of clamping the floor
// at 0 and hiding every negative-form day.

const COLORS = { fitness: '#4f46e5', fatigue: '#d97706', form: '#0d9488' }
const LINES = [
  { key: 'fitness', name: 'Fitness' },
  { key: 'fatigue', name: 'Fatigue' },
  { key: 'form', name: 'Form' },
]

// A muted, hollow, dashed dot marks a MODEL-flagged cold-start day (`maturity === 'low'`) —
// the same annotate-never-suppress boundary the LoadChart draws. Here one maturity value per
// day governs all three curves, so every line's dot reads the merged row's `maturity`.
function MaturityDot(props) {
  const { cx, cy, payload, color } = props
  if (cx == null || cy == null) return null
  // A gap day (this line null on this row) draws no dot — Recharts still clones the element,
  // so guard on the datum being present for THIS line.
  const cold = payload?.maturity === 'low'
  return (
    <circle
      cx={cx}
      cy={cy}
      r={cold ? 2.5 : 3}
      className={cold ? 'form-dot form-dot--cold' : 'form-dot form-dot--mature'}
      data-maturity={cold ? 'low' : 'ok'}
      fill={cold ? 'var(--chart-cold-fill, #ffffff)' : color}
      stroke={color}
      strokeWidth={1}
      strokeDasharray={cold ? '2 1' : undefined}
      opacity={cold ? 0.55 : 1}
    />
  )
}

// One row per day for the selected window: fitness/fatigue/form plus the day's maturity the
// dots read. Ascending by day (the endpoint already sorts, but a client-side sort keeps the
// merge independent of that guarantee).
function windowRows(win) {
  if (!win) return []
  return [...win.points]
    .sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : 0))
    .map((p) => ({
      day: p.day,
      fitness: p.fitness,
      fatigue: p.fatigue,
      form: p.form,
      maturity: p.maturity,
    }))
}

export default function FormChart({ width, height, days = 90 }) {
  const [windows, setWindows] = useState(null) // null = loading, [] = loaded-empty
  const [error, setError] = useState('')
  const [chosen, setChosen] = useState(null) // the user's EXPLICIT window pick, or null

  // The effect body calls no setState synchronously — only its async then/catch callbacks do
  // (the LoadChart discipline that keeps `react-hooks/set-state-in-effect` clean). A range
  // change re-runs it; the previous window stays on screen until the new data resolves, so
  // there is no loading flash on a range change (only on first mount, where `windows` is null).
  useEffect(() => {
    let alive = true
    api.get('/series/load', { params: { days } })
      .then((res) => { if (alive) { setWindows(res.data?.windows || []); setError('') } })
      .catch(() => { if (alive) { setWindows([]); setError('Could not load Banister curves.') } })
    return () => { alive = false }
  }, [days])

  // Effective window is DERIVED, not stored in an effect: the user's explicit pick when it is
  // still populated, else the first populated window. `chosen` holds only an explicit choice,
  // so a range change that drops the picked window silently falls back without a stale-state
  // effect.
  const names = useMemo(() => (windows || []).map((w) => w.load_window), [windows])
  const selected = chosen && names.includes(chosen) ? chosen : (names[0] ?? null)

  const activeWindow = useMemo(
    () => (windows || []).find((w) => w.load_window === selected) || null,
    [windows, selected],
  )
  const data = useMemo(() => windowRows(activeWindow), [activeWindow])
  const lines = useMemo(
    () => LINES.map((l) => ({
      dataKey: l.key,
      name: l.name,
      color: COLORS[l.key],
      dot: <MaturityDot color={COLORS[l.key]} />,
    })),
    [],
  )

  const hasData = !!windows && windows.length > 0 && data.length > 0

  return (
    <section aria-label="Fitness, fatigue and form" className="bg-white border border-gray-200 rounded-2xl p-4 space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">Fitness · Fatigue · Form</h2>
          <p className="text-[11px] text-gray-400">Banister curves for one window · form goes negative · dashed points are cold-start.</p>
        </div>
        {windows && windows.length > 0 && (
          <div role="group" aria-label="Window" className="flex flex-wrap gap-1 justify-end">
            {windows.map((w) => (
              <button
                key={w.load_window}
                type="button"
                onClick={() => setChosen(w.load_window)}
                aria-pressed={w.load_window === selected}
                className={`rounded-lg px-2 py-1 text-xs font-medium capitalize transition-colors ${
                  w.load_window === selected
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {w.load_window}
              </button>
            ))}
          </div>
        )}
      </div>

      {windows === null && (
        <p className="text-xs text-gray-400 py-8 text-center">Loading Banister curves…</p>
      )}

      {windows !== null && !hasData && (
        <p className="text-xs text-gray-400 py-8 text-center">
          {error || 'No Banister curves yet — log some sessions and they will appear here.'}
        </p>
      )}

      {hasData && (
        <div className="overflow-x-auto">
          <TimeSeriesChart
            data={data}
            lines={lines}
            xKey="day"
            width={width}
            height={height}
            yDomain={['auto', 'auto']}
          />
        </div>
      )}
    </section>
  )
}
