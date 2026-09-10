// @vitest-environment jsdom
//
// TimeSeriesChart — the shared-axis ⇒ shared-unit invariant. This is the check that would have
// caught the increment-1 defect (kg_reps and nm_au overlaid on one y-axis). Series on one axis
// MUST share a unit; a violation throws in dev/test rather than drawing an incommensurable
// overlay. These mount at a fixed size so any rendered assertion is on real SVG.

import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render } from '@testing-library/react'

import TimeSeriesChart from './TimeSeriesChart'

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

test('draws a phase-marker reference line at an in-range boundary date', () => {
  const { container } = render(
    <TimeSeriesChart
      data={DATA}
      width={400}
      height={200}
      series={[{ dataKey: 'a', name: 'a', color: '#4f46e5', unit: 'kg' }]}
      markers={[{ date: '2026-07-02', label: 'decompression' }]}
    />,
  )
  expect(container.querySelector('.recharts-reference-line')).toBeTruthy()
  expect(container.textContent).toContain('decompression')  // the phase name is the label
})

test('an out-of-range boundary draws no reference line', () => {
  const { container } = render(
    <TimeSeriesChart
      data={DATA}
      width={400}
      height={200}
      series={[{ dataKey: 'a', name: 'a', color: '#4f46e5', unit: 'kg' }]}
      markers={[{ date: '2020-01-01', label: 'ancient' }]}
    />,
  )
  expect(container.querySelector('.recharts-reference-line')).toBeNull()
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
