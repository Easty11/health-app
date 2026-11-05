// @vitest-environment jsdom
//
// Settings -> Heart rate zones (design 0010 §6). The card renders the server's config as sent: both classes with
// bpm bands, the anchors with provenance / date / retest, the HRmax prompts, the Garmin mirror. The append form
// forces the dated-vs-restatement choice, previews the bpm bands before Save, and after Save forces the load
// chain. HRmax is read-only here and names the operator script.

import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { act } from 'react'

vi.mock('../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../api'
import HRZonesCard from './HRZonesCard'

const cls = (key, label, basis_label, sports, band_pct, edges_bpm, anchors, missing = []) =>
  ({ key, label, basis: key, basis_label, sports, band_pct, edges_bpm, anchors, missing })
const entry = (id, bpm, provenance, effective_from, extra = {}) =>
  ({ id, bpm, provenance, effective_from, note: 'n', restates_id: null, rationale: null, created_at: null, superseded: false, ...extra })

const CFG = {
  as_of: '2026-11-05',
  classes: [
    cls('lthr', 'cycling', '% of LTHR (Friel)', ['Biking', 'Indoor cycling'], [0, 81, 90, 94, 100], [0, 128, 143, 149, 158], { lthr: 158 }),
    cls('hrr', 'other sports', '% of heart-rate reserve (Karvonen)', [], [50, 60, 70, 80, 90], [115, 128, 141, 154, 167], { hrmax: 179, rhr: 51 }),
  ],
  anchors: {
    hrmax: { kind: 'hrmax', label: 'HRmax', in_force: entry(1, 179, 'observed', '2026-03-01'), retest: false, entries: [entry(1, 179, 'observed', '2026-03-01')], writable: false, writer: 'scripts/set_hrmax.py' },
    lthr: { kind: 'lthr', label: 'LTHR', in_force: entry(2, 158, 'device_estimated', '2026-03-01'), retest: true, entries: [entry(2, 158, 'device_estimated', '2026-03-01')], writable: true, writer: null },
    rhr: { kind: 'rhr', label: 'Resting HR', in_force: entry(3, 51, 'stated', '2026-03-01'), retest: false, entries: [entry(3, 51, 'stated', '2026-03-01')], writable: true, writer: null },
  },
  default_effective_from: '2026-03-01',
  r8_pending: true,
  hrmax_prompts: [{ id: 9, date: '2026-11-05', sport: 'Biking', hr_max: 181, hrmax_in_force: 179 }],
  garmin: {
    profile: { cycling: { basis: '%LTHR', bands: ['<81', '81-89', '90-93', '94-99', '100+'] }, default: { basis: '%HRR', bands: ['50-59', '60-69', '70-79', '80-89', '90-100'] } },
    snapshot: { captured_at: '2026-11-04T00:00:00+00:00', max_hr_bpm: 181, lthr_bpm: 158, rhr_7d_auto_bpm: 49, method: 'HR_RESERVE' },
  },
}

const EMPTY = {
  ...CFG,
  classes: [
    cls('lthr', 'cycling', '% of LTHR (Friel)', ['Biking'], [0, 81, 90, 94, 100], null, {}, ['lthr']),
    cls('hrr', 'other sports', '% of heart-rate reserve (Karvonen)', [], [50, 60, 70, 80, 90], null, {}, ['rhr']),
  ],
  anchors: {
    ...CFG.anchors,
    lthr: { ...CFG.anchors.lthr, in_force: null, retest: false, entries: [] },
    rhr: { ...CFG.anchors.rhr, in_force: null, entries: [] },
  },
  hrmax_prompts: [],
}

const PREVIEW = {
  kind: 'rhr', bpm: 48, effective_from: '2026-10-01', change: 'dated', rows_changed: 3, rows: [], restates: null,
  classes_before: CFG.classes,
  classes_after: [CFG.classes[0], { ...CFG.classes[1], edges_bpm: [114, 127, 140, 153, 166], anchors: { hrmax: 179, rhr: 48 } }],
}

const renderIt = async () => { await act(async () => { render(<HRZonesCard showToast={() => {}} />) }) }
const type = (testId, value) => fireEvent.change(screen.getByTestId(testId), { target: { value } })

beforeEach(() => { vi.clearAllMocks(); api.get.mockResolvedValue({ data: CFG }) })
afterEach(cleanup)

test('both classes render their bands in bpm, with the basis and the members', async () => {
  await renderIt()
  const lthr = await screen.findByTestId('zone-class-lthr')
  expect(lthr.textContent).toContain('% of LTHR (Friel)')
  expect(lthr.textContent).toContain('Biking · Indoor cycling')
  expect(lthr.textContent).toContain('128–142')          // z2 in bpm
  expect(lthr.textContent).toContain('<81')              // z1 has no floor
  const hrr = screen.getByTestId('zone-class-hrr')
  expect(hrr.textContent).toContain('Karvonen')
  expect(hrr.textContent).toContain('128–140')
  expect(hrr.textContent).toContain('167+')
})

test('anchors show value, provenance, date, the retest flag, and HRmax is read-only naming the script', async () => {
  await renderIt()
  const lthr = await screen.findByTestId('anchor-lthr')
  expect(lthr.dataset.retest).toBe('true')
  expect(lthr.textContent).toContain('158 bpm · device_estimated · from 2026-03-01')
  expect(lthr.textContent).toContain('retest')
  const hrmax = screen.getByTestId('anchor-hrmax')
  expect(hrmax.dataset.retest).toBe('false')
  expect(hrmax.textContent).toContain('179 bpm')
  expect(hrmax.textContent).toContain('scripts/set_hrmax.py')
  expect(screen.getByTestId('hrmax-prompt').textContent).toContain('181 bpm against 179')
  const mirror = screen.getByTestId('garmin-mirror')
  expect(mirror.textContent).toContain('%LTHR')
  expect(screen.getByTestId('garmin-snapshot').textContent).toContain('LTHR 158 · 7-day auto RHR 49')
})

test('a missing anchor leaves the class without bpm bands and names it', async () => {
  api.get.mockResolvedValue({ data: EMPTY })
  await renderIt()
  expect((await screen.findByTestId('zone-class-lthr-missing')).textContent).toContain('missing anchor lthr')
  expect(screen.getByTestId('zone-class-hrr-missing').textContent).toContain('missing anchor rhr')
  expect(screen.getByTestId('anchor-rhr').textContent).toContain('none in force')
  // R8: the first entry defaults to the earliest session date, editable
  expect(screen.getByTestId('anchor-date').value).toBe('2026-03-01')
  expect(screen.getByTestId('r8-note').textContent).toContain('R8')
})

test('the form forces the change choice and previews before Save', async () => {
  api.post.mockImplementation((url) => Promise.resolve({ data: url.endsWith('/preview') ? PREVIEW : { written: true } }))
  await renderIt()
  await screen.findByTestId('anchor-form')
  type('anchor-kind', 'rhr')
  type('anchor-bpm', '48')
  type('anchor-date', '2026-10-01')
  type('anchor-note', 'supine, 7 mornings')
  // nothing chosen yet: neither button is live
  expect(screen.getByTestId('anchor-preview-btn').disabled).toBe(true)
  expect(screen.getByTestId('anchor-save-btn').disabled).toBe(true)
  fireEvent.click(within(screen.getByTestId('anchor-change')).getByDisplayValue('dated'))
  expect(screen.getByTestId('anchor-preview-btn').disabled).toBe(false)
  expect(screen.getByTestId('anchor-save-btn').disabled).toBe(true)      // Save waits for the preview
  await act(async () => { fireEvent.click(screen.getByTestId('anchor-preview-btn')) })
  expect(api.post).toHaveBeenCalledWith('/hr-zones/anchors/preview', expect.objectContaining({ kind: 'rhr', bpm: 48, change: 'dated', effective_from: '2026-10-01' }))
  const preview = await screen.findByTestId('anchor-preview')
  expect(preview.textContent).toContain('3 sessions re-zone')
  expect(preview.textContent).toContain('128–140')         // before
  expect(preview.textContent).toContain('127–139')         // after
  expect(screen.getByTestId('anchor-save-btn').disabled).toBe(false)
  await act(async () => { fireEvent.click(screen.getByTestId('anchor-save-btn')) })
  const calls = api.post.mock.calls.map((c) => c[0])
  expect(calls).toEqual(['/hr-zones/anchors/preview', '/hr-zones/anchors', '/load/refresh?force=true'])
  expect(api.post.mock.calls[1][1]).toEqual(expect.objectContaining({ kind: 'rhr', bpm: 48, change: 'dated', note: 'supine, 7 mornings', rationale: null }))
  expect(api.get).toHaveBeenCalledTimes(2)                 // reloaded after the write
})

test('a restatement needs its rationale, and a refusal shows the way out', async () => {
  api.post.mockRejectedValue({ response: { data: { detail: 'nothing to restate: no RHR dated 2026-10-01' } } })
  await renderIt()
  await screen.findByTestId('anchor-form')
  type('anchor-kind', 'rhr'); type('anchor-bpm', '48'); type('anchor-date', '2026-10-01'); type('anchor-note', 'n')
  fireEvent.click(within(screen.getByTestId('anchor-change')).getByDisplayValue('restate'))
  expect(screen.getByTestId('anchor-preview-btn').disabled).toBe(true)   // rationale missing
  type('anchor-rationale', 'the earlier read was taken standing')
  expect(screen.getByTestId('anchor-preview-btn').disabled).toBe(false)
  await act(async () => { fireEvent.click(screen.getByTestId('anchor-preview-btn')) })
  expect((await screen.findByTestId('anchor-error')).textContent).toContain('nothing to restate')
  expect(api.post.mock.calls[0][1].rationale).toBe('the earlier read was taken standing')
})

test('an unreadable config says so instead of rendering nothing', async () => {
  api.get.mockRejectedValue(new Error('500'))
  await renderIt()
  expect((await screen.findByTestId('hr-zones-unavailable')).textContent).toContain('could not be read')
})
