// The home load card (top of the Dashboard, full width). Headline form, the fitness-vs-fatigue
// sparkline, the 7-day-vs-28-day means, and the age of the data under all of it.
//
// A load number never shows without its age. The freshness line is the point of this card: it
// names how old the data is and which pipe is late, and the whole card dims and the line turns
// amber when a pipe feeding load is stale (Health Connect delivery older than ~13 h, decided
// server-side in `GET /freshness`). If freshness itself cannot be read, the card says so in amber
// and dims; it does not show a load number with no age.
//
// Deliberately NOT here (rulings F1, #18/#255): no band label for form (cut-points are a separate
// decision), no acute:chronic ratio, no sweet-spot verdict. Form is shown as a number with the
// direction fatigue is moving, nothing more. The Metrics page keeps the full detail.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../api'
import { formatAge, formatPipeAge } from '../../lib/formatAge'
import { fatigueDirection, round1 } from '../../lib/fatigueDirection'

const LANE = 'metabolic'          // the lane this card reads (load_metrics 'metabolic' window)
const SPARK_DAYS = 42

function Sparkline({ points }) {
  const W = 300
  const H = 56
  const pad = 3
  const values = points.flatMap((p) => [p.fitness, p.fatigue])
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const span = hi - lo || 1
  const x = (i) => pad + (i * (W - 2 * pad)) / Math.max(points.length - 1, 1)
  const y = (v) => H - pad - ((v - lo) / span) * (H - 2 * pad)
  const line = (key) => points.map((p, i) => `${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join(' ')
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="w-full h-14"
      role="img"
      aria-label={`Fitness and fatigue over the last ${SPARK_DAYS} days`}
      preserveAspectRatio="none"
    >
      <polyline data-series="fitness" points={line('fitness')} fill="none" stroke="#4f46e5" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      <polyline data-series="fatigue" points={line('fatigue')} fill="none" stroke="#d97706" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

function MeanBar({ label, value, max, color, unit }) {
  const pct = max > 0 ? Math.max((value / max) * 100, 0) : 0
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-20 text-gray-500 shrink-0">{label}</span>
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} data-bar={label} />
      </div>
      <span className="w-24 text-right text-gray-700 tabular-nums">{round1(value)} {unit}</span>
    </div>
  )
}

export default function LoadCard() {
  const [series, setSeries] = useState(undefined)     // undefined = loading, null = failed
  const [fresh, setFresh] = useState(undefined)

  useEffect(() => {
    let live = true
    api.get('/series/load', { params: { days: SPARK_DAYS, windows: LANE } })
      .then(({ data }) => live && setSeries(data))
      .catch(() => live && setSeries(null))
    api.get('/freshness')
      .then(({ data }) => live && setFresh(data))
      .catch(() => live && setFresh(null))
    return () => { live = false }
  }, [])

  if (series === undefined || fresh === undefined) return null

  const win = series?.windows?.find((w) => w.load_window === LANE)
  const points = win ? [...win.points].sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : 0)) : []
  const latest = points[points.length - 1]
  const dir = fatigueDirection(points)

  // Amber when a pipe feeding load is stale, or when the age cannot be read at all.
  const ageUnknown = fresh === null || !fresh?.pipes
  const amber = ageUnknown || fresh.load_inputs_stale === true
  const asOf = fresh?.data_as_of ? formatAge(fresh.data_as_of.age_hours) : (ageUnknown ? 'unknown' : 'never')

  return (
    <section
      aria-label="Load summary"
      data-stale={amber ? 'true' : 'false'}
      className="bg-white border border-gray-200 rounded-2xl p-4"
    >
      {/* Dimmed when stale; the freshness line below is NOT inside this wrapper, so the amber
          warning stays at full contrast while the numbers recede. */}
      <div data-testid="load-content" className={amber ? 'opacity-50' : ''}>
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <p className="text-xs text-gray-500">Form</p>
            {latest ? (
              <p className="text-3xl font-bold text-gray-900 tabular-nums" data-testid="form-value">
                {round1(latest.form)}
              </p>
            ) : (
              <p className="text-sm text-gray-500 mt-1">No training load computed yet.</p>
            )}
          </div>
          {dir && (
            <p className="text-sm text-gray-600" data-testid="fatigue-direction" data-direction={dir.key}>
              <span aria-hidden="true">{dir.arrow}</span> {dir.text}
            </p>
          )}
          <Link to="/metrics" className="text-xs font-medium text-indigo-600 hover:text-indigo-800 shrink-0">
            Metrics →
          </Link>
        </div>

        {latest && latest.maturity === 'low' && (
          <p className="text-[11px] text-gray-400 mt-1">Early estimate: less than 42 days of history.</p>
        )}

        {points.length >= 2 && (
          <div className="mt-3">
            <Sparkline points={points} />
            <div className="flex gap-4 text-[11px] text-gray-500 mt-1">
              <span><span className="inline-block w-2 h-2 rounded-full bg-indigo-600 mr-1" />Fitness</span>
              <span><span className="inline-block w-2 h-2 rounded-full bg-amber-600 mr-1" />Fatigue</span>
              <span className="ml-auto">last {SPARK_DAYS} days</span>
            </div>
          </div>
        )}

        {latest && (
          <div className="mt-3 space-y-1.5">
            {(() => {
              const max = Math.max(latest.acute_load, latest.chronic_load)
              return (
                <>
                  <MeanBar label="7-day mean" value={latest.acute_load} max={max} color="bg-amber-500" unit={win.unit} />
                  <MeanBar label="28-day mean" value={latest.chronic_load} max={max} color="bg-indigo-500" unit={win.unit} />
                </>
              )
            })()}
          </div>
        )}
      </div>

      <p
        data-testid="freshness-line"
        className={`text-[11px] mt-3 ${amber ? 'text-amber-600 font-medium' : 'text-gray-400'}`}
      >
        {ageUnknown
          ? 'Data age unavailable: freshness could not be read.'
          : `Data as of ${asOf} · Health Connect ${formatPipeAge(fresh.pipes.health_connect)} · Polar ${formatPipeAge(fresh.pipes.polar)}`}
      </p>
    </section>
  )
}
