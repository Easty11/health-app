// PhaseMarkers — the pure logic behind the training-phase bands and legend (R11). No DOM:
// phaseSegments and bandLayout are pure functions of the ledger and a chart's rows.
//
// R11 REPLACED the D4 line-and-label design. The tests that pinned its drop and snap rules
// ("snaps a boundary to the first category on or after it", "drops a boundary before the window
// or after the last category", the one-reference-line-per-boundary tests and the
// "collapse to one line" test) are gone with it; the cases they covered now read the opposite
// way or not at all — see "a phase after the last data day is never dropped" below.

import { readFileSync } from 'node:fs'
import { expect, test } from 'vitest'
import {
  bandLayout, epochDayOf, phaseBandPalette, phaseSegments,
} from './PhaseMarkers'
import phaseHistory from '../../fixtures/phaseHistory.json'

const row = (id, label, entered_on, closed_on = null) => ({ id, label, entered_on, closed_on })

// ---------- phaseSegments ----------

test('the ledger (newest first) becomes ascending spans, each carrying its name and span', () => {
  const segs = phaseSegments(phaseHistory)
  expect(segs.map((s) => [s.label, s.start, s.end])).toEqual([
    ['base build', '2026-08-01', '2026-09-07'],
    ['decompression', '2026-09-07', null],
  ])
})

test('baseline (a null phase or a label-less row) contributes nothing', () => {
  expect(phaseSegments([null, { entered_on: '2026-01-01' }])).toEqual([])
  expect(phaseSegments([])).toEqual([])
  expect(phaseSegments(undefined)).toEqual([])
})

test('colour is per phase NAME: a name re-entered after another phase keeps its colour', () => {
  const segs = phaseSegments([
    row(1, 'A', '2026-01-01', '2026-01-10'),
    row(2, 'B', '2026-01-10', '2026-01-20'),
    row(3, 'A', '2026-01-20'),
  ])
  expect(segs).toHaveLength(3)                       // A, B, A: a second band, not a merge
  expect(segs[0].color).toBe(segs[2].color)          // same name, same colour
  expect(segs[0].color).not.toBe(segs[1].color)      // different name, different colour
  expect(segs.map((s) => s.color)).toEqual([phaseBandPalette[0], phaseBandPalette[1], phaseBandPalette[0]])
})

test('colour follows the name, not the ledger row: two rows under one name share it', () => {
  const segs = phaseSegments([
    row(1, 'A', '2026-01-01', '2026-01-05'),
    row(2, 'B', '2026-01-05', '2026-01-09'),   // a different name between, so no merge
    row(3, 'A', '2026-01-09', '2026-01-12'),
    row(4, 'A', '2026-01-12'),                 // straight after row 3: merges into it
  ])
  expect(new Set(segs.filter((s) => s.label === 'A').map((s) => s.color)).size).toBe(1)
})

test('back-to-back rows with one name are one band, with a handoff at the join', () => {
  const segs = phaseSegments([
    row(1, 'aerobic base', '2026-10-04', '2026-10-09'),
    row(2, 'aerobic base', '2026-10-09'),
  ])
  expect(segs).toHaveLength(1)
  expect(segs[0]).toMatchObject({ start: '2026-10-04', end: null, handoffs: ['2026-10-09'] })
})

test('the same name after a gap is a second band, not a merge', () => {
  const segs = phaseSegments([
    row(1, 'A', '2026-01-01', '2026-01-05'),   // ended, baseline in between
    row(2, 'A', '2026-01-09'),
  ])
  expect(segs).toHaveLength(2)
  expect(segs[0].color).toBe(segs[1].color)
})

test('a zero-length row (#379) draws no band and adds no handoff', () => {
  const segs = phaseSegments([
    row(1, 'aerobic base', '2026-10-04', '2026-10-04'),   // same-day correction: zero-length
    row(2, 'aerobic base', '2026-10-04'),
  ])
  expect(segs).toHaveLength(1)
  expect(segs[0].handoffs).toEqual([])                    // the dropped row is no handoff
})

test('a zero-length row between two same-name rows leaves them one band', () => {
  const segs = phaseSegments([
    row(1, 'A', '2026-01-01', '2026-01-05'),
    row(2, 'B', '2026-01-05', '2026-01-05'),               // never spanned a day
    row(3, 'A', '2026-01-05'),
  ])
  expect(segs.map((s) => s.label)).toEqual(['A'])
  expect(segs[0].handoffs).toEqual(['2026-01-05'])
})

// ---------- bandLayout ----------

// Six data days, 1 to 6 Aug 2026.
const DAYS = ['2026-08-01', '2026-08-02', '2026-08-03', '2026-08-04', '2026-08-05', '2026-08-06']
const CAT = DAYS.map((d) => ({ date: d, v: 1 }))
const TIME = DAYS.map((d) => ({ x: epochDayOf(d), v: 1 }))
const D1 = epochDayOf('2026-08-01')

test('time axis: a band edge is a slot boundary, so adjacent bands abut', () => {
  const segs = phaseSegments([row(1, 'A', '2026-08-01', '2026-08-04'), row(2, 'B', '2026-08-04')])
  const { bands } = bandLayout(segs, TIME, 'x', 'time')
  expect(bands.map((b) => [b.x1, b.x2])).toEqual([
    [D1 - 0.5, D1 + 2.5],        // days 1-3
    [D1 + 2.5, D1 + 5.5],        // days 4-6, ends at the series end
  ])
})

test('category axis: a band runs from its first data day to its last', () => {
  const segs = phaseSegments([row(1, 'A', '2026-08-01', '2026-08-04'), row(2, 'B', '2026-08-04')])
  const { bands } = bandLayout(segs, CAT, 'date', 'category')
  expect(bands.map((b) => [b.x1, b.x2])).toEqual([
    ['2026-08-01', '2026-08-03'],
    ['2026-08-04', '2026-08-06'],
  ])
})

test('an open phase ends at the series end, not at today', () => {
  const { bands } = bandLayout(phaseSegments([row(1, 'A', '2026-08-02')]), TIME, 'x', 'time')
  expect(bands).toHaveLength(1)
  expect(bands[0].x2).toBe(D1 + 5.5)
})

test('a phase that began before the window is clipped to the first data day', () => {
  const segs = phaseSegments([row(1, 'old', '2026-06-01', '2026-08-03'), row(2, 'new', '2026-08-03')])
  const { bands, legend } = bandLayout(segs, TIME, 'x', 'time')
  expect(bands[0].x1).toBe(D1 - 0.5)
  expect(legend.map((l) => l.label)).toEqual(['old', 'new'])
})

test('a phase wholly before the window is outside it: no band, no legend entry', () => {
  const segs = phaseSegments([row(1, 'gone', '2026-06-01', '2026-07-20'), row(2, 'A', '2026-07-20')])
  const { bands, legend } = bandLayout(segs, TIME, 'x', 'time')
  expect(bands).toHaveLength(1)
  expect(legend.map((l) => l.label)).toEqual(['A'])
})

test('a phase after the last data day is never dropped: legend only, marked no data yet', () => {
  // Replaces the pinned drop-after-the-last-category rule.
  const segs = phaseSegments([row(1, 'A', '2026-07-01', '2026-08-07'), row(2, 'next', '2026-08-07')])
  for (const [data, key, axis] of [[TIME, 'x', 'time'], [CAT, 'date', 'category']]) {
    const { bands, legend } = bandLayout(segs, data, key, axis)
    expect(bands).toHaveLength(1)                                  // A only
    expect(legend).toEqual([
      expect.objectContaining({ label: 'A', noDataYet: false }),
      expect.objectContaining({ label: 'next', noDataYet: true }),
    ])
  }
})

test('a name seen both in the window and after it is not marked no data yet', () => {
  const segs = phaseSegments([
    row(1, 'A', '2026-08-01', '2026-08-03'),
    row(2, 'B', '2026-08-03', '2026-08-07'),
    row(3, 'A', '2026-08-07'),
  ])
  const { legend } = bandLayout(segs, TIME, 'x', 'time')
  expect(legend.find((l) => l.label === 'A').noDataYet).toBe(false)
})

test('a boundary between data days is placed by its date, not snapped to the next data day', () => {
  // Replaces the pinned snap-to-next-day rule. Data on 1 and 10 Aug; the phase starts on the 5th.
  const rows = [{ x: epochDayOf('2026-08-01'), v: 1 }, { x: epochDayOf('2026-08-10'), v: 1 }]
  const { bands } = bandLayout(phaseSegments([row(1, 'A', '2026-08-05')]), rows, 'x', 'time')
  expect(bands[0].x1).toBe(epochDayOf('2026-08-05') - 0.5)
})

test('handoffs draw only inside the window', () => {
  const segs = phaseSegments([
    row(1, 'A', '2026-07-01', '2026-07-10'),
    row(2, 'A', '2026-07-10', '2026-08-03'),    // handoff before the window: no line
    row(3, 'A', '2026-08-03'),                  // handoff inside it
  ])
  const { handoffs } = bandLayout(segs, TIME, 'x', 'time')
  expect(handoffs.map((h) => h.x)).toEqual([epochDayOf('2026-08-03')])
})

test('a zero-length row draws nothing and is not in the legend', () => {
  const segs = phaseSegments([row(1, 'typo', '2026-08-03', '2026-08-03'), row(2, 'A', '2026-08-03')])
  const { bands, handoffs, legend } = bandLayout(segs, TIME, 'x', 'time')
  expect(bands).toHaveLength(1)
  expect(handoffs).toEqual([])
  expect(legend.map((l) => l.label)).toEqual(['A'])
})

test('no rows or no segments lays out nothing', () => {
  expect(bandLayout([], TIME, 'x', 'time')).toEqual({ bands: [], handoffs: [], legend: [] })
  expect(bandLayout(phaseSegments([row(1, 'A', '2026-08-01')]), [], 'x', 'time').bands).toEqual([])
})

// ---------- one palette ----------

test('band colours are written in one place: phaseBandPalette', () => {
  const dir = new URL('.', import.meta.url)
  const hex = /#[0-9a-fA-F]{6}\b/g
  const legend = readFileSync(new URL('PhaseLegend.jsx', dir), 'utf8')
  expect(legend.match(hex)).toBeNull()
  const markers = readFileSync(new URL('PhaseMarkers.jsx', dir), 'utf8')
  const found = markers.match(hex) || []
  expect(found.sort()).toEqual([...phaseBandPalette].sort())
})
