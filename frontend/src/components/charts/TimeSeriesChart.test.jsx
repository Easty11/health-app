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
