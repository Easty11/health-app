import {
  LineChart, Line, BarChart, Bar, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { referenceLinesFor } from './PhaseMarkers'

// The ONE jsdom-safe mounting pattern every chart in the app shares, and the home of the
// one invariant that a chart cannot break silently.
//
// SHARED AXIS ⇒ SHARED UNIT. Every series drawn here shares a single y-axis, so every series
// MUST carry the same `unit`. Overlaying incommensurable units on one axis (kg_reps and nm_au
// on the same scale) is meaningless and was the increment-1 defect this component now forbids:
// the fix is small multiples — one TimeSeriesChart per unit — and this guard is the wall that
// makes "just add another line" fail loudly instead of drawing a lie. It throws in dev and in
// test (where a violation is a bug to catch); in a production build it degrades to a console
// error rather than white-screening a viewer, because LoadChart never violates it.
//
// FIXED SIZE BY DEFAULT. Recharts' ResponsiveContainer measures its parent via ResizeObserver,
// which reports 0×0 in jsdom — a responsive chart renders an empty 0×0 SVG with no marks, so a
// test can only assert "it mounted". Given explicit width/height the chart draws real geometry
// the instant it mounts, in the browser and in jsdom alike. `ResponsiveContainer` is opt-in.
//
// `isAnimationActive={false}` draws the final state immediately — an animated chart has no
// final-position marks at first paint, exactly what a synchronous jsdom assertion would read.
//
// `yDomain`, `lineType`, `strokeWidth` and `legend` are additive (Visuals increment 2),
// defaulting to increment-1's behaviour (Recharts' own auto y-domain, monotone interpolation,
// 2px stroke, no legend) so `LoadChart` is unchanged. They exist for series that need an HONEST
// rendering the default would misstate:
//   * `yDomain={['auto','auto']}` lets a series that goes NEGATIVE (Banister `form`) show its
//     sub-zero range instead of a floor clamped at 0; a fixed `yDomain={[1,5]}` pins an ordinal
//     scale so its axis reads the same every window.
//   * `lineType="linear"` refuses smoothing for an ORDINAL daily observation (1–5 readiness),
//     where a monotone spline would invent between-day values the reading never claimed.
//   * `legend` labels a multi-series line overlay (FormChart's fitness/fatigue/form, all one
//     unit); a small multiple with one series names it in its own caption and needs none.
export default function TimeSeriesChart({
  data,
  series,
  xKey = 'day',
  mark = 'line',            // 'line' | 'bar' — bars for discrete per-day quantities (daily_load)
  width = 640,
  height = 200,
  responsive = false,
  hideXLabels = false,
  margin = { top: 8, right: 16, bottom: 8, left: 8 },
  yDomain,
  lineType = 'monotone',
  strokeWidth = 2,
  legend = false,
  markers = [],            // [{date, label}] training-phase boundaries (Visuals increment 3, D4)
}) {
  const units = [...new Set(series.map((s) => s.unit).filter((u) => u != null))]
  if (units.length > 1) {
    const msg = `TimeSeriesChart: all series on one y-axis must share a unit — got [${units.join(', ')}]. Use small multiples, one chart per unit.`
    if (import.meta.env?.DEV || import.meta.env?.MODE === 'test') throw new Error(msg)
    console.error(msg)
  }
  const unit = units[0]
  // Phase-boundary reference lines, snapped to this chart's categories. Built here (not nested
  // in a child component) so they spread as DIRECT children of the Recharts chart — the only
  // place Recharts registers them.
  const refLines = referenceLinesFor(markers, data, xKey)
  const yLabel = unit
    ? { value: unit, angle: -90, position: 'insideLeft', style: { fontSize: 11, fill: '#6b7280' } }
    : undefined

  const axes = (
    <>
      <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
      <XAxis dataKey={xKey} tick={hideXLabels ? false : { fontSize: 11 }} minTickGap={24} />
      <YAxis tick={{ fontSize: 11 }} width={56} label={yLabel} domain={yDomain} />
      <Tooltip />
      {legend && <Legend />}
    </>
  )

  let chart
  if (mark === 'bar') {
    chart = (
      <BarChart data={data} width={responsive ? undefined : width} height={responsive ? undefined : height} margin={margin}>
        {axes}
        {series.map((s) => (
          <Bar key={s.dataKey} dataKey={s.dataKey} name={s.name} fill={s.color} isAnimationActive={false}>
            {/* One Cell per row so a bar can be styled by that day's maturity. A day with a
                null value (a rest/zero day, mapped to null upstream) renders no bar at all. */}
            {data.map((row, idx) => {
              const cold = s.matKey ? row[s.matKey] === 'low' : false
              return (
                <Cell
                  key={idx}
                  className={`load-bar ${cold ? 'load-bar--cold' : 'load-bar--mature'}`}
                  data-maturity={cold ? 'low' : 'ok'}
                  fill={s.color}
                  fillOpacity={cold ? 0.4 : 1}
                  stroke={cold ? s.color : undefined}
                  strokeDasharray={cold ? '2 2' : undefined}
                />
              )
            })}
          </Bar>
        ))}
        {refLines}
      </BarChart>
    )
  } else {
    chart = (
      <LineChart data={data} width={responsive ? undefined : width} height={responsive ? undefined : height} margin={margin}>
        {axes}
        {series.map((s) => (
          <Line
            key={s.dataKey}
            type={lineType}
            dataKey={s.dataKey}
            name={s.name}
            stroke={s.color}
            strokeWidth={strokeWidth}
            dot={s.dot ?? false}
            activeDot={{ r: 4 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        ))}
        {refLines}
      </LineChart>
    )
  }

  if (responsive) {
    return <ResponsiveContainer width="100%" height={height}>{chart}</ResponsiveContainer>
  }
  return chart
}
