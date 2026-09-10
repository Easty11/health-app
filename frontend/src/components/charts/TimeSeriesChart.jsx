import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'

// The ONE jsdom-safe mounting pattern every chart in the app shares.
//
// Recharts' `ResponsiveContainer` measures its parent through a ResizeObserver, which reports
// 0×0 in jsdom — so a test-mounted responsive chart renders an empty 0×0 SVG with no series,
// and a test can only ever assert "it didn't throw". This wrapper makes a chart FIXED-size by
// default: given explicit width/height it renders real geometry the instant it mounts, in the
// browser and in jsdom alike, so tests assert on actual rendered SVG. `ResponsiveContainer` is
// opt-in (`responsive`) for callers that genuinely want fluid width and are not under test.
//
// `isAnimationActive={false}` is not cosmetic here: Recharts animates dots/paths in from a
// zero state over timers, so an animated chart has no final-position dots at first paint —
// exactly what a synchronous jsdom assertion would read. Disabling it draws the final state
// immediately.
// `yDomain`, `lineType` and `strokeWidth` are additive, defaulting to increment-1's behaviour
// (Recharts' own auto y-domain, monotone interpolation, 2px stroke) so LoadChart is unchanged.
// They exist for series that need an HONEST rendering the default would misstate:
//   * `yDomain={['auto','auto']}` lets a series that goes NEGATIVE (Banister `form`) show its
//     sub-zero range instead of being clamped at 0.
//   * `lineType="linear"` refuses smoothing for an ORDINAL daily observation (1–5 readiness),
//     where a monotone spline would invent between-day values the reading never claimed.
//   * a fixed `yDomain={[1,5]}` pins an ordinal scale so its axis reads the same every window.
// `Tooltip`'s optional `formatter` lets a chart show a derived value on hover (unused by default).
export default function TimeSeriesChart({
  data,
  lines,
  xKey = 'day',
  width = 640,
  height = 280,
  responsive = false,
  margin = { top: 8, right: 16, bottom: 8, left: 0 },
  yDomain,
  yAllowDataOverflow = false,
  lineType = 'monotone',
  strokeWidth = 2,
  tooltipFormatter,
}) {
  const chart = (
    <LineChart
      data={data}
      width={responsive ? undefined : width}
      height={responsive ? undefined : height}
      margin={margin}
    >
      <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
      <XAxis dataKey={xKey} tick={{ fontSize: 11 }} minTickGap={24} />
      <YAxis tick={{ fontSize: 11 }} width={44} domain={yDomain} allowDataOverflow={yAllowDataOverflow} />
      <Tooltip formatter={tooltipFormatter} />
      <Legend />
      {lines.map((l) => (
        <Line
          key={l.dataKey}
          type={lineType}
          dataKey={l.dataKey}
          name={l.name}
          stroke={l.color}
          strokeWidth={strokeWidth}
          dot={l.dot ?? false}
          activeDot={{ r: 4 }}
          connectNulls={false}
          isAnimationActive={false}
        />
      ))}
    </LineChart>
  )
  if (responsive) {
    return <ResponsiveContainer width="100%" height={height}>{chart}</ResponsiveContainer>
  }
  return chart
}
