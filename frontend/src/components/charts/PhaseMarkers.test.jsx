// PhaseMarkers — the pure logic behind the training-phase overlay (Visuals increment 3, D4).
// No DOM: phaseBoundaries/snapToCategory are pure, and referenceLinesFor returns React elements
// whose props are inspected directly (they render as direct children inside TimeSeriesChart,
// exercised by the chart tests).

import { expect, test } from 'vitest'
import { phaseBoundaries, referenceLinesFor, snapToCategory } from './PhaseMarkers'
import phaseHistory from '../../fixtures/phaseHistory.json'

// ---------- phaseBoundaries ----------

test('each phase contributes its entered_on, and its closed_on when closed', () => {
  const b = phaseBoundaries(phaseHistory)
  // decompression (open): entered_on only. base build (closed): entered_on + closed_on.
  expect(b).toEqual([
    { date: '2026-09-07', label: 'decompression' },
    { date: '2026-08-01', label: 'base build' },
    { date: '2026-09-07', label: 'base build' },
  ])
})

test('baseline (a null phase or a label-less row) contributes nothing', () => {
  expect(phaseBoundaries([null, { entered_on: '2026-01-01' }])).toEqual([])
  expect(phaseBoundaries([])).toEqual([])
  expect(phaseBoundaries(undefined)).toEqual([])
})

// ---------- snapToCategory ----------

const CATS = ['2026-08-01', '2026-08-05', '2026-08-10', '2026-08-20']

test('snaps a boundary to the first category on or after it', () => {
  expect(snapToCategory(CATS, '2026-08-05')).toBe('2026-08-05')  // exact
  expect(snapToCategory(CATS, '2026-08-07')).toBe('2026-08-10')  // between → next
})

test('drops a boundary before the window or after the last category', () => {
  expect(snapToCategory(CATS, '2026-07-01')).toBeNull()  // before the window (off-screen)
  expect(snapToCategory(CATS, '2026-09-01')).toBeNull()  // after the last category
  expect(snapToCategory([], '2026-08-01')).toBeNull()
})

// ---------- referenceLinesFor ----------

const DATA = CATS.map((d) => ({ date: d, v: 1 }))

test('builds one reference line per in-range boundary, labelled with the phase name', () => {
  const lines = referenceLinesFor([{ date: '2026-08-07', label: 'decompression' }], DATA, 'date')
  expect(lines).toHaveLength(1)
  expect(lines[0].props.x).toBe('2026-08-10')            // snapped
  expect(lines[0].props.label.value).toBe('decompression')
})

test('boundaries that snap to the same category collapse to one line', () => {
  // A close/open handoff shares a day — here both snap to 2026-08-10.
  const lines = referenceLinesFor(
    [{ date: '2026-08-07', label: 'base build' }, { date: '2026-08-10', label: 'decompression' }],
    DATA, 'date',
  )
  expect(lines).toHaveLength(1)
})

test('an out-of-range boundary produces no line', () => {
  expect(referenceLinesFor([{ date: '2026-07-01', label: 'old' }], DATA, 'date')).toHaveLength(0)
  expect(referenceLinesFor([{ date: '2026-08-05', label: 'x' }], [], 'date')).toHaveLength(0)
})
