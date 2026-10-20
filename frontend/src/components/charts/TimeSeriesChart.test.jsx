// @vitest-environment jsdom
//
// TimeSeriesChart — the shared-axis ⇒ shared-unit invariant. This is the check that would have
// caught the increment-1 defect (kg_reps and nm_au overlaid on one y-axis). Series on one axis
// MUST share a unit; a violation throws in dev/test rather than drawing an incommensurable
// overlay. These mount at a fixed size so any rendered assertion is on real SVG.

import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render } from '@testing-library/react'

import TimeSeriesChart from './TimeSeriesChart'
import { phaseSegments } from './PhaseMarkers'

const DATA = [
  { day: '2026-07-01', a: 10, b: 3 },
  { day: '2026-07-02', a: 12, b: 4 },
]

afterEach(cleanup)

test('throws when two series on one axis carry different units', () => {
  // Silence React's error-boundary console noise for the expected throw.
  const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
  expect(() => render(
    <TimeSeriesChart
      data={DATA}
      mark="bar"
      width={400}
      height={200}
      series={[
        { dataKey: 'a', name: 'mechanical', color: '#4f46e5', unit: 'kg_reps' },
        { dataKey: 'b', name: 'neuromuscular', color: '#0d9488', unit: 'nm_au' },
      ]}
    />,
  )).toThrow(/unit/i)
  spy.mockRestore()
})

test('does not throw when series share a unit', () => {
  const { container } = render(
    <TimeSeriesChart
      data={DATA}
      mark="bar"
      width={400}
      height={200}
      series={[
        { dataKey: 'a', name: 'set A', color: '#4f46e5', unit: 'kg_reps' },
        { dataKey: 'b', name: 'set B', color: '#0d9488', unit: 'kg_reps' },
      ]}
    />,
  )
  expect(container.querySelector('.recharts-wrapper')).toBeTruthy()
})

const SEGS = phaseSegments([
  { id: 0, label: 'decompression', entered_on: '2026-06-01', closed_on: '2026-07-02' },
  { id: 1, label: 'base build', entered_on: '2026-07-02', closed_on: null },
])
const ONE_SERIES = [{ dataKey: 'a', name: 'a', color: '#4f46e5', unit: 'kg' }]
const bandRects = (c) => [...c.querySelectorAll('.phase-band path')]
  .map((p) => ({ x: parseFloat(p.getAttribute('x')), w: parseFloat(p.getAttribute('width')), fill: p.getAttribute('fill') }))

test('draws a shaded band per phase, with no text label in the chart (R11)', () => {
  const { container } = render(
    <TimeSeriesChart data={DATA} width={400} height={200} series={ONE_SERIES} markers={SEGS} />,
  )
  expect(container.querySelectorAll('.recharts-reference-area')).toHaveLength(2)
  expect(container.querySelector('.recharts-reference-line')).toBeNull()   // no boundary lines
  expect(container.textContent).not.toContain('decompression')             // the name is the legend's
  expect(container.textContent).not.toContain('base build')
})

test('a band is drawn for the phase and none for one that starts after the last data day', () => {
  const after = phaseSegments([{ id: 0, label: 'later', entered_on: '2026-09-01', closed_on: null }])
  const { container } = render(
    <TimeSeriesChart data={DATA} width={400} height={200} series={ONE_SERIES} markers={after} />,
  )
  expect(container.querySelector('.recharts-reference-area')).toBeNull()   // legend-only (PhaseLegend)
})

test('bands sit behind the series: the reference area precedes the bars in the SVG', () => {
  const { container } = render(
    <TimeSeriesChart data={DATA} mark="bar" width={400} height={200} series={ONE_SERIES} markers={SEGS} />,
  )
  const area = container.querySelector('.recharts-reference-area')
  const bar = container.querySelector('.load-bar, .recharts-bar-rectangle')
  expect(area.compareDocumentPosition(bar) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

test.each(['bar', 'line'])('on a %s chart the day slots are whole, so adjacent bands abut', (mark) => {
  const six = ['01', '02', '03', '04', '05', '06'].map((d, i) => ({ day: `2026-08-${d}`, a: i + 1 }))
  const segs = phaseSegments([
    { id: 0, label: 'A', entered_on: '2026-08-01', closed_on: '2026-08-04' },
    { id: 1, label: 'B', entered_on: '2026-08-04', closed_on: null },
  ])
  const { container } = render(
    <TimeSeriesChart data={six} mark={mark} width={600} height={200} series={ONE_SERIES} markers={segs} />,
  )
  const [a, b] = bandRects(container)
  expect(a.x + a.w).toBeCloseTo(b.x, 3)          // no gap, no overlap
  expect(a.w).toBeCloseTo(b.w, 3)                // three slots each
  expect(a.fill).not.toBe(b.fill)                // two names, two colours
})

test('xType="time" places points at their true temporal distance (90d vs 365d, D4)', () => {
  // Three points 0 / 90 / 365 days apart. On a NUMBER (time) x-axis the middle point must sit
  // at 90/365 of the way from the first to the last — a categorical axis would space them evenly
  // (0.5) and flatten the irregular gaps that matter for lab draws.
  const { container } = render(
    <TimeSeriesChart
      data={[{ x: 0, v: 1 }, { x: 90, v: 2 }, { x: 365, v: 3 }]}
      xKey="x"
      xType="time"
      width={600}
      height={200}
      series={[{ dataKey: 'v', name: 'v', color: '#4f46e5', unit: 'x', dot: true }]}
    />,
  )
  const dots = [...container.querySelectorAll('.recharts-line-dot')]
  expect(dots).toHaveLength(3)
  const cx = dots.map((d) => parseFloat(d.getAttribute('cx')))
  const fraction = (cx[1] - cx[0]) / (cx[2] - cx[0])
  expect(fraction).toBeCloseTo(90 / 365, 2)  // proportional, not the 0.5 a category axis would give
})
