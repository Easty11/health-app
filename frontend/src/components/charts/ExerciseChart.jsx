import { useEffect, useMemo, useState } from 'react'
import api from '../../api'
import TimeSeriesChart from './TimeSeriesChart'

// Per-exercise strength progression (Visuals increment 3) — the first chart Hevy can't draw,
// because the training-phase markers overlaid on it (via `markers`) are ours, not theirs.
//
// TWO SMALL MULTIPLES, never one overlay: e1RM is kg and volume is kg·reps — different units,
// so they cannot share a y-axis (TimeSeriesChart's shared-axis⇒shared-unit guard would throw).
//   * e1RM — a LINE with dots, gaps where the session has no Epley-eligible set (the endpoint
//     sends null; connectNulls=false in the wrapper breaks the line rather than inventing a
//     value). This is the STRENGTH signal (brief D1).
//   * Volume — BARS (a discrete per-session quantity, the same encoding LoadChart uses); a
//     zero-volume day draws no bar. This is the WORK signal (D2).
//
// The exercise SELECTOR lists templates with ≥3 sessions in range, most-frequent first, and
// defaults to the most frequent (D5) — `GET /series/exercises`. The chosen template's series
// comes from `GET /series/exercise/{id}`. The RANGE is the page's (shared with the other
// charts), taken as the `days` prop; this chart shows no range control of its own.

const E1RM_COLOR = '#4f46e5'
const VOLUME_COLOR = '#0d9488'

// Visible dot per e1RM observation; a gap (null e1RM) gives Recharts null coords, so this
// returns nothing and no dot is drawn there — the gap stays a gap.
function E1rmDot(props) {
  const { cx, cy } = props
  if (cx == null || cy == null) return null
  return <circle cx={cx} cy={cy} r={2.5} className="e1rm-dot" fill={E1RM_COLOR} stroke={E1RM_COLOR} strokeWidth={1} />
}

// One row per session date: e1RM (null → gap) and volume (0 → null so no bar is drawn).
function seriesRows(points) {
  return [...(points || [])]
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
    .map((p) => ({
      date: p.date,
      e1rm_kg: p.e1rm_kg,
      volume_kg_reps: p.volume_kg_reps === 0 ? null : p.volume_kg_reps,
    }))
}

export default function ExerciseChart({ width, height, days = 90, markers = [] }) {
  const [list, setList] = useState(null)      // null = loading, [] = loaded-empty (selector source)
  const [chosen, setChosen] = useState(null)  // the user's EXPLICIT pick, or null
  const [series, setSeries] = useState(null)  // the chosen template's {template_id,title,points}
  const [error, setError] = useState('')

  // Selector source. No synchronous setState in the effect body — only its async callbacks set
  // state (the LoadChart discipline that keeps `react-hooks/set-state-in-effect` clean).
  useEffect(() => {
    let alive = true
    api.get('/series/exercises', { params: { days } })
      .then((res) => { if (alive) { setList(res.data || []); setError('') } })
      .catch(() => { if (alive) { setList([]); setError('Could not load exercises.') } })
    return () => { alive = false }
  }, [days])

  // Effective template is DERIVED: the explicit pick while it is still in the list, else the
  // most frequent (list[0], the endpoint's default). `chosen` holds only an explicit choice, so
  // a range change that drops the picked template silently falls back.
  const ids = useMemo(() => (list || []).map((e) => e.template_id), [list])
  const selected = chosen && ids.includes(chosen) ? chosen : (ids[0] ?? null)

  // The chosen template's series. Re-fetches on a range change or a new pick. No synchronous
  // setState in the effect body (the LoadChart discipline that keeps `react-hooks/set-state-in-
  // effect` clean) — when there is no selection there are no exercises to show, so the stale
  // series is simply never rendered (hasExercises is false); only the async callbacks set state.
  useEffect(() => {
    if (!selected) return undefined
    let alive = true
    api.get(`/series/exercise/${selected}`, { params: { days } })
      .then((res) => { if (alive) setSeries(res.data) })
      .catch(() => { if (alive) setSeries(null) })
    return () => { alive = false }
  }, [selected, days])

  const data = useMemo(() => seriesRows(series?.points), [series])
  const listed = list !== null
  const hasExercises = listed && list.length > 0
  const hasData = hasExercises && !!series && data.length > 0
  const panelHeight = height ?? 180

  return (
    <section aria-label="Exercise progression" className="bg-white border border-gray-200 rounded-2xl p-4 space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-900">Exercise progression</h2>
          <p className="text-[11px] text-gray-400">Estimated 1RM and volume per session · phase boundaries marked.</p>
        </div>
        {hasExercises && (
          <div role="group" aria-label="Exercise" className="flex flex-wrap gap-1 justify-end">
            {list.map((e) => (
              <button
                key={e.template_id}
                type="button"
                onClick={() => setChosen(e.template_id)}
                aria-pressed={e.template_id === selected}
                className={`rounded-lg px-2 py-1 text-xs font-medium transition-colors ${
                  e.template_id === selected
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {e.title}
              </button>
            ))}
          </div>
        )}
      </div>

      {list === null && (
        <p className="text-xs text-gray-400 py-8 text-center">Loading exercises…</p>
      )}

      {listed && !hasExercises && (
        <p className="text-xs text-gray-400 py-8 text-center">
          {error || 'No exercise yet has three logged sessions in range — keep training and it will appear here.'}
        </p>
      )}

      {hasExercises && !hasData && (
        <p className="text-xs text-gray-400 py-8 text-center">Loading {series?.title || 'exercise'}…</p>
      )}

      {hasData && (
        <div className="space-y-4">
          <figure className="m-0" aria-label="Estimated 1RM">
            <figcaption className="text-xs font-medium text-gray-600">
              {series.title} · estimated 1RM <span className="text-gray-400 font-normal">(kg)</span>
            </figcaption>
            <div className="overflow-x-auto">
              <TimeSeriesChart
                data={data}
                series={[{ dataKey: 'e1rm_kg', name: 'e1RM', color: E1RM_COLOR, unit: 'kg', dot: <E1rmDot /> }]}
                xKey="date"
                mark="line"
                lineType="linear"
                strokeWidth={1.5}
                width={width}
                height={panelHeight}
                yDomain={['auto', 'auto']}
                markers={markers}
                hideXLabels
              />
            </div>
          </figure>
          <figure className="m-0" aria-label="Volume">
            <figcaption className="text-xs font-medium text-gray-600">
              Volume <span className="text-gray-400 font-normal">(kg·reps)</span>
            </figcaption>
            <div className="overflow-x-auto">
              <TimeSeriesChart
                data={data}
                series={[{ dataKey: 'volume_kg_reps', name: 'Volume', color: VOLUME_COLOR, unit: 'kg·reps' }]}
                xKey="date"
                mark="bar"
                width={width}
                height={panelHeight}
                markers={markers}
              />
            </div>
          </figure>
        </div>
      )}
    </section>
  )
}
