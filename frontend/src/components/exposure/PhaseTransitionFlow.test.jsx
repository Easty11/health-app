// @vitest-environment jsdom
//
// PhaseTransitionFlow — the 8-step phase-change form + the 2026-09-21 real-run fixes. Gates:
//   G1  a prefilled quota slot changed → the replace-or-add prompt; "add" yields two slots (F6).
//   G2  the confirm shows a DIFF (removals first); removing all capacity demands an extra tick (B2/F16).
//   G4  the step-5 counter is the server's `consistency_rows` — the form renders the preview rows,
//       never a client re-derivation (F9, B3).
//   G5  the review note becomes `close_prior_reason` (F1).
//   G6  every input across the steps carries an accessible name (F3/labelling).
//   F17 a structured overlap 422 is translated and a "separate sessions" resubmit adds `distinct_from`.
// Plus the standing contract: prefill, the draft-discard notice, the single confirm → onWritten, a
// string 422 shown verbatim, a new placement shipping a resolved time (never 'unknown', B1).

/* global process -- the near-midnight test sets TZ so todayLocal() is exercised in the operator's zone */
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { act } from 'react'

vi.mock('../../api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '../../api'
import PhaseTransitionFlow from './PhaseTransitionFlow'
import { todayLocal } from './phaseTime'

const DRAFT = {
  current_phase: {
    label: 'decompression', intent: 'deload', probe_posture: 'held', entered_on: '2026-09-07',
    microcycle: { sub_cycle_days: 7, sub_cycles: [{ label: 'A', slots: [
      { capacity: 'stability', sessions_per_cycle: 2, minutes: 30 }] }] },
  },
  outgoing_review: [
    { window: { label: 'A', start_date: '2026-09-07', end_date: '2026-09-13' },
      slots: [{ kind: 'capacity', key: 'stability', quota: 2, done: 2 }], uncounted: [] },
  ],
  schedule_items: [
    { id: 5, key: 'gym', value: {
      activity: 'gym', days: ['monday', 'wednesday', 'friday'], hard: false, expected_load: 'moderate',
      time_of_day: 'evening', same_day_training: false, satisfies: { capacity: 'stability' } } },
  ],
  sport_names_seen: [{ sport_name: 'Pilates', source: 'health_connect' }],
  routine_folders: [{ id: '11', title: 'Decompression' }],
  freshness: { hc_synced_at: null, hc_stale: true, polar_stale: true, polar_pull_ts_exists: false },
  week_plan: { window: {}, days: [
    { date: '2026-09-21', weekday: 'monday', available: true, caution: null },
    { date: '2026-09-22', weekday: 'tuesday', available: false, caution: null },
  ] },
}

let previewRows = []
let transitionResult = { data: { training_phase: {}, no_op: false } }
let transitionReject = null

beforeEach(() => {
  api.get.mockReset(); api.post.mockReset()
  previewRows = []; transitionResult = { data: { training_phase: {}, no_op: false } }; transitionReject = null
  api.get.mockResolvedValue({ data: DRAFT })
  api.post.mockImplementation((url) => {
    if (url.includes('preview')) return Promise.resolve({ data: { consistency_rows: previewRows } })
    if (transitionReject) return Promise.reject(transitionReject)
    return Promise.resolve(transitionResult)
  })
})
afterEach(cleanup)

async function renderFlow(onWritten = vi.fn()) {
  await act(async () => { render(<PhaseTransitionFlow onWritten={onWritten} onCancel={vi.fn()} />) })
  await waitFor(() => expect(screen.getByText(/step 1 of 8/i)).toBeTruthy())
  return onWritten
}
const next = async () => { await act(async () => { fireEvent.click(screen.getByRole('button', { name: /^next$/i })) }) }
const transitionCalls = () => api.post.mock.calls.filter(([u]) => u === '/engine/phase/transition')

let labelledSeen = 0
function assertAllLabelled() {
  // A step may legitimately hold no form controls (only buttons + text) — the gate is that every
  // control that DOES exist carries an accessible name, so no minimum is asserted per step.
  const controls = document.querySelectorAll('input, select, textarea')
  for (const c of controls) {
    labelledSeen += 1
    const aria = c.getAttribute('aria-label')
    const wrap = c.closest('label')
    const name = aria || (wrap ? wrap.textContent.trim() : '')
    expect(name, `unlabelled control: ${c.outerHTML.slice(0, 90)}`).toBeTruthy()
  }
}

test('prefills from the draft, advances, and always shows the draft-discard notice', async () => {
  await renderFlow()
  expect(screen.getByText(/Review the outgoing phase/i)).toBeTruthy()
  expect(screen.getByText(/Leaving discards this draft/i)).toBeTruthy()
  expect(screen.getByText(/Stability 2\/2/)).toBeTruthy()
  await next()
  expect(screen.getByText(/step 2 of 8/i)).toBeTruthy()
  expect(screen.getByDisplayValue('decompression')).toBeTruthy()   // continued, locked label
})

test('G1: changing a prefilled quota slot asks replace-or-add; add yields two slots (F6)', async () => {
  await renderFlow()
  await next(); await next(); await next()   // → step 4 (quota)
  expect(screen.getByText(/step 4 of 8/i)).toBeTruthy()
  expect(screen.getByText('Slot 1 of 1')).toBeTruthy()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /change kind \/ target/i })) })
  expect(screen.getByText(/Replace it, or add a new one/i)).toBeTruthy()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /add a new slot/i })) })
  expect(screen.getByText('Slot 1 of 2')).toBeTruthy()
  expect(screen.getByText('Slot 2 of 2')).toBeTruthy()   // the prefilled stability survives
})

test('G2: confirm shows a removal and removing all capacity demands an extra tick (B2/F16)', async () => {
  await renderFlow()
  await next(); await next(); await next()   // → step 4
  // Swap the only (capacity) slot for an activity slot: no capacity quota remains, but the phase still
  // has a slot (R3 forbids zero slots, so "drop stability" alone no longer reaches step 8).
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /\+ quota slot/i })) })
  await act(async () => { fireEvent.change(screen.getByLabelText('slot 2 kind'), { target: { value: 'activity' } }) })
  await act(async () => { fireEvent.change(screen.getByLabelText('slot 2 key'), { target: { value: 'pilates' } }) })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Pilates' })) })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /remove slot 1/i })) })  // drop stability
  for (let i = 0; i < 4; i++) await next()   // 5,6,7,8
  expect(screen.getByText(/step 8 of 8/i)).toBeTruthy()
  expect(screen.getByText(/REMOVES stability/)).toBeTruthy()
  const confirmBtn = screen.getByRole('button', { name: /confirm — save phase change/i })
  expect(confirmBtn.disabled).toBe(true)
  await act(async () => { fireEvent.click(screen.getByRole('checkbox', { name: /acknowledge removing all capacity/i })) })
  expect(confirmBtn.disabled).toBe(false)
})

test('G4: the step-5 counter renders the server preview rows, no client re-derivation (F9)', async () => {
  previewRows = [{ kind: 'capacity', key: 'stability', quota: 3, done: 0, scheduled: 3, excess: 0, unplaced: 0 }]
  await renderFlow()
  await next(); await next(); await next(); await next()   // → step 5
  expect(screen.getByText(/step 5 of 8/i)).toBeTruthy()
  await waitFor(() => expect(screen.getByText(/Stability — scheduled 3 · quota 3/)).toBeTruthy())
  expect(screen.queryByText(/UNPLACED/)).toBeNull()
  expect(screen.getByRole('button', { name: /^next$/i }).disabled).toBe(false)
})

test('G4b: a preview mismatch gates Next until acknowledged (F14)', async () => {
  previewRows = [{ kind: 'capacity', key: 'stability', quota: 3, done: 0, scheduled: 1, excess: 0, unplaced: 2 }]
  await renderFlow()
  await next(); await next(); await next(); await next()   // → step 5
  await waitFor(() => expect(screen.getByText(/UNPLACED 2/)).toBeTruthy())
  expect(screen.getByRole('button', { name: /^next$/i }).disabled).toBe(true)
  expect(screen.getByText(/Acknowledge the schedule ≠ quota mismatch/i)).toBeTruthy()
  await act(async () => { fireEvent.click(screen.getByRole('checkbox', { name: /acknowledge schedule does not match quota/i })) })
  expect(screen.getByRole('button', { name: /^next$/i }).disabled).toBe(false)
})

test('G5: the review note becomes close_prior_reason (F1)', async () => {
  const onWritten = await renderFlow()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /^yes$/i })) })
  await act(async () => { fireEvent.change(screen.getByLabelText(/close reason notes/i), { target: { value: 'great block, felt strong' } }) })
  for (let i = 0; i < 7; i++) await next()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /confirm — save phase change/i })) })
  await waitFor(() => expect(onWritten).toHaveBeenCalled())
  expect(transitionCalls()[0][1].phase.close_prior_reason).toBe('block did its job: yes — great block, felt strong')
})

test('G6: every input across the steps carries an accessible name', async () => {
  await renderFlow()
  assertAllLabelled()                       // step 1
  await next(); assertAllLabelled()         // step 2
  await next(); assertAllLabelled()         // step 3
  await next(); assertAllLabelled()         // step 4
  await next()                              // step 5
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /\+ placement/i })) })
  assertAllLabelled()                       // step 5 with a new placement's inputs
  await next(); assertAllLabelled()         // step 6
  await next(); assertAllLabelled()         // step 7
  expect(labelledSeen).toBeGreaterThan(8)   // the walk actually inspected controls, not a no-op
})

test('the single confirm POSTs the transition; a new placement ships a resolved time (B1)', async () => {
  api.get.mockResolvedValue({ data: { ...DRAFT, schedule_items: [] } })  // a clean first placement
  const onWritten = await renderFlow()
  await next(); await next(); await next(); await next()   // → step 5
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /\+ placement/i })) })
  await act(async () => { fireEvent.change(screen.getByLabelText(/placement 1 key/i), { target: { value: 'gym' } }) })
  await act(async () => { fireEvent.change(screen.getByLabelText(/placement 1 time range/i), { target: { value: '17:30-18:30' } }) })
  for (let i = 0; i < 3; i++) await next()   // 6,7,8
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /confirm — save phase change/i })) })
  await waitFor(() => expect(onWritten).toHaveBeenCalled())
  const op = transitionCalls()[0][1].schedule_items.find((o) => o.key === 'gym')
  expect(op.value.time_of_day).toBe('evening')        // derived from 17:30 — never 'unknown'
  expect(op.value.time_range).toBe('17:30-18:30')
})

test('F17: a structured overlap 422 is translated and "separate sessions" resubmits with distinct_from', async () => {
  transitionReject = { response: { status: 422, data: { detail: {
    code: 'day_time_clash', error: 'schedule_item overlaps an active row on days; retry with distinct_from',
    key: 'gym_tue',
    overlapping: [{ id: 9, activity: 'swim', days: ['tuesday'], time_of_day: 'evening' }],
    resolve_with: ['distinct_from'] } } } }
  api.get.mockResolvedValue({ data: { ...DRAFT, schedule_items: [] } })  // a clean first placement
  const onWritten = await renderFlow()
  await next(); await next(); await next(); await next()   // → step 5
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /\+ placement/i })) })
  await act(async () => { fireEvent.change(screen.getByLabelText(/placement 1 key/i), { target: { value: 'gym_tue' } }) })
  for (let i = 0; i < 3; i++) await next()   // → step 8
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /confirm — save phase change/i })) })
  await waitFor(() => expect(screen.getByText(/Schedule clash/i)).toBeTruthy())
  expect(screen.getByText(/clashes with/i)).toBeTruthy()
  expect(screen.getByText(/swim/)).toBeTruthy()
  expect(onWritten).not.toHaveBeenCalled()
  // "separate sessions" → clears the clash and, on resubmit, the op carries distinct_from.
  transitionReject = null
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /separate sessions — resubmit/i })) })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /confirm — save phase change/i })) })
  await waitFor(() => expect(onWritten).toHaveBeenCalled())
  const calls = transitionCalls()
  const lastBody = calls[calls.length - 1][1]
  expect(lastBody.schedule_items.find((o) => o.key === 'gym_tue').value.distinct_from).toEqual([9])
})

test('a string 422 detail is shown verbatim (server is the validator)', async () => {
  const detail = 'microcycle.sub_cycles[0].slots[0].device_sports must be a non-empty list of sport names'
  transitionReject = { response: { status: 422, data: { detail } } }
  const onWritten = await renderFlow()
  for (let i = 0; i < 7; i++) await next()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /confirm — save phase change/i })) })
  await waitFor(() => expect(screen.getByText(detail)).toBeTruthy())
  expect(onWritten).not.toHaveBeenCalled()
})


// ---- step 4 slot keys: pickers from the backend's vocabularies, and the checks that used to wait for step 8 ----

const SLOT_OPTIONS = { capacity: ['stability', 'mobility', 'strength'], load_window: ['metabolic'] }

async function toStep4(options = SLOT_OPTIONS) {
  api.get.mockResolvedValue({ data: { ...DRAFT, ...(options ? { slot_options: options } : {}) } })
  await renderFlow()
  await next(); await next(); await next()
  expect(screen.getByText(/step 4 of 8/i)).toBeTruthy()
}
const addSlotBtn = () => screen.getByRole('button', { name: /\+ quota slot/i })
const nextBtn = () => screen.getByRole('button', { name: /^next$/i })
const optionValues = (sel) => within(sel).getAllByRole('option').map((o) => o.value)

test('slots: a new capacity slot is a picker of the backend capacities, defaulting to one not yet used', async () => {
  await toStep4()
  await act(async () => { fireEvent.click(addSlotBtn()) })
  const key = screen.getByLabelText('slot 2 key')
  expect(key.tagName).toBe('SELECT')                                  // not a free-text box
  expect(optionValues(key)).toEqual(SLOT_OPTIONS.capacity)            // exactly the offered vocabulary; 'gym' is not in it
  expect(key.value).toBe('mobility')                                  // stability is already slot 1
  expect(nextBtn().disabled).toBe(false)
})

test('slots: changing a slot kind resets its key to one valid for the new kind', async () => {
  await toStep4()
  await act(async () => { fireEvent.click(addSlotBtn()) })
  await act(async () => { fireEvent.change(screen.getByLabelText('slot 2 kind'), { target: { value: 'load_window' } }) })
  const key = screen.getByLabelText('slot 2 key')
  expect(key.tagName).toBe('SELECT')
  expect(optionValues(key)).toEqual(['metabolic'])
  expect(key.value).toBe('metabolic')                                 // not the stale 'mobility'
  await act(async () => { fireEvent.change(screen.getByLabelText('slot 2 kind'), { target: { value: 'activity' } }) })
  const act2 = screen.getByLabelText('slot 2 key')
  expect(act2.tagName).toBe('INPUT')                                   // the open kind stays free text
  expect(act2.value).toBe('')
})

test('slots: a duplicate capacity names the clash and blocks Next until fixed', async () => {
  await toStep4()
  await act(async () => { fireEvent.click(addSlotBtn()) })
  await act(async () => { fireEvent.change(screen.getByLabelText('slot 2 key'), { target: { value: 'stability' } }) })
  expect(screen.getByRole('alert').textContent).toMatch(/Already a capacity slot for "stability" \(slot 1\)/)
  expect(nextBtn().disabled).toBe(true)
  expect(screen.getByText(/Fix the quota slot\(s\) marked above/i)).toBeTruthy()
  await act(async () => { fireEvent.change(screen.getByLabelText('slot 2 key'), { target: { value: 'strength' } }) })
  expect(screen.queryByRole('alert')).toBeNull()
  expect(nextBtn().disabled).toBe(false)
})

test('slots: a second metabolic slot is refused at step 4 with the activity-slot hint (the 4 Oct retry)', async () => {
  await toStep4()
  for (let i = 0; i < 2; i += 1) {
    await act(async () => { fireEvent.click(addSlotBtn()) })
    const slotNo = i + 2
    await act(async () => { fireEvent.change(screen.getByLabelText(`slot ${slotNo} kind`), { target: { value: 'load_window' } }) })
    await act(async () => { fireEvent.click(screen.getAllByRole('button', { name: 'Pilates' })[i]) })   // a device sport, so only the duplicate remains
  }
  const alert = screen.getByRole('alert')
  expect(alert.textContent).toMatch(/Already a load_window slot for "metabolic" \(slot 2\)/)
  expect(alert.textContent).toMatch(/activity slot/)
  expect(nextBtn().disabled).toBe(true)
})

test('slots: a load_window or activity slot with no device sport blocks Next until one is picked', async () => {
  await toStep4()
  await act(async () => { fireEvent.click(addSlotBtn()) })
  await act(async () => { fireEvent.change(screen.getByLabelText('slot 2 kind'), { target: { value: 'load_window' } }) })
  expect(screen.getByRole('alert').textContent).toMatch(/at least one device sport/)
  expect(nextBtn().disabled).toBe(true)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Pilates' })) })
  expect(screen.queryByRole('alert')).toBeNull()
  expect(nextBtn().disabled).toBe(false)
})

test('slots: a draft without slot_options (an older backend) keeps the text box and does not block', async () => {
  await toStep4(null)
  await act(async () => { fireEvent.click(addSlotBtn()) })
  const key = screen.getByLabelText('slot 2 key')
  expect(key.tagName).toBe('INPUT')                                   // fallback: the save stays the validator
  // The default 'stability' still duplicates slot 1, and a duplicate is knowable without the options.
  expect(screen.getByRole('alert').textContent).toMatch(/Already a capacity slot for "stability"/)
  await act(async () => { fireEvent.change(key, { target: { value: 'Gym' } }) })
  expect(screen.queryByRole('alert')).toBeNull()                      // not knowable here: the save decides
  expect(nextBtn().disabled).toBe(false)
})


// ---- step 5: a slot picked on an existing item left on "Keep" must reach the counter and the save ----
// 4 Oct 2026: Keep retains the stored link and ignores the dropdown, and the dropdown was editable anyway,
// so a choice looked applied and was dropped (the counter read UNPLACED, and the save sent nothing).

async function toStep5WithSecondSlot() {
  api.get.mockResolvedValue({ data: { ...DRAFT, slot_options: SLOT_OPTIONS } })
  await renderFlow()
  await next(); await next(); await next()                                   // -> step 4
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /\+ quota slot/i })) })   // adds mobility
  await next()                                                               // -> step 5
  expect(screen.getByText(/step 5 of 8/i)).toBeTruthy()
}
const pressed = (name) => screen.getByRole('button', { name }).getAttribute('aria-pressed')
const lastPreviewValues = () => {
  const calls = api.post.mock.calls.filter(([u]) => u.includes('preview'))
  return calls[calls.length - 1][1].schedule_item_values
}
async function saveFromStep5() {
  for (let i = 0; i < 3; i++) await next()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /confirm — save phase change/i })) })
  await waitFor(() => expect(transitionCalls().length).toBe(1))
  return transitionCalls()[0][1].schedule_items
}

test('placement: a different slot on a Keep item switches it to Relink, and the counter and save carry the choice', async () => {
  await toStep5WithSecondSlot()
  expect(pressed('Keep')).toBe('true')
  expect(screen.getByText(/Picking a different slot switches this to Relink/i)).toBeTruthy()
  await act(async () => { fireEvent.change(screen.getByLabelText('placement 1 satisfies slot'), { target: { value: 'mobility' } }) })
  expect(pressed('Relink')).toBe('true')
  expect(pressed('Keep')).toBe('false')
  expect(screen.queryByText(/Picking a different slot switches this to Relink/i)).toBeNull()
  await waitFor(() => expect(lastPreviewValues().map((v) => v.satisfies)).toEqual([{ capacity: 'mobility' }]))
  const ops = await saveFromStep5()
  expect(ops).toHaveLength(1)
  expect(ops[0]).toMatchObject({ action: 'upsert', key: 'gym', value: { satisfies: { capacity: 'mobility' } } })
})

test('placement: picking the stored slot again leaves the item on Keep and sends no schedule op', async () => {
  await toStep5WithSecondSlot()
  await act(async () => { fireEvent.change(screen.getByLabelText('placement 1 satisfies slot'), { target: { value: 'mobility' } }) })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Keep' })) })        // back to Keep: stored link restored
  expect(pressed('Keep')).toBe('true')
  await waitFor(() => expect(lastPreviewValues().map((v) => v.satisfies)).toEqual([{ capacity: 'stability' }]))
  expect(await saveFromStep5()).toEqual([])
})

test('placement: clearing the slot on a Keep item is a change (Relink to no slot), not a silent no-op', async () => {
  await toStep5WithSecondSlot()
  await act(async () => { fireEvent.change(screen.getByLabelText('placement 1 satisfies slot'), { target: { value: '' } }) })
  expect(pressed('Relink')).toBe('true')
  const ops = await saveFromStep5()
  expect(ops[0]).toMatchObject({ action: 'upsert', key: 'gym', value: { satisfies: null } })
})


// ---- the kind hints: a slot claims sessions to COUNT them; load accrues from the device data regardless ----
// Q210 ruled (a): activity slots claim first for per-category counts, one metabolic load_window takes the
// remainder, and load deposits for every device session whichever slot counted it. The activity hint used to
// say "never deposits load", which read as the session carrying no load.

test('hints: the activity kind says the slot counts sessions and load still accrues (not "never deposits load")', async () => {
  await toStep4()
  await act(async () => { fireEvent.click(addSlotBtn()) })
  await act(async () => { fireEvent.change(screen.getByLabelText('slot 2 kind'), { target: { value: 'activity' } }) })
  const hint = screen.getByText(/^activity — a recorded session/)
  expect(hint.textContent).toMatch(/claims sessions for counting only/)
  expect(hint.textContent).toMatch(/their load still accrues/)
  expect(screen.queryByText(/never deposits load/i)).toBeNull()
})

test('hints: the load_window kind says it takes the remainder after activity slots, and load accrues either way', async () => {
  await toStep4()
  await act(async () => { fireEvent.click(addSlotBtn()) })
  await act(async () => { fireEvent.change(screen.getByLabelText('slot 2 kind'), { target: { value: 'load_window' } }) })
  const hint = screen.getByText(/^load_window — H10/)
  expect(hint.textContent).toMatch(/no activity slot claims first/)
  expect(hint.textContent).toMatch(/load accrues from every session either way/)
})


// ---- #378 / #379: the build's settlement (R3, R5, R6) ----

const sameDayDraft = (extra = {}) => ({
  ...DRAFT,
  current_phase: { ...DRAFT.current_phase, entered_on: todayLocal() },
  ...extra,
})
const stepTo = async (n) => { for (let i = 1; i < n; i++) await next() }
const confirmBtn = () => screen.getByRole('button', { name: /confirm — save phase change/i })
const saveFromStep1 = async () => {
  await stepTo(8)
  await act(async () => { fireEvent.click(confirmBtn()) })
  await waitFor(() => expect(transitionCalls().length).toBe(1))
  return transitionCalls()[0][1]
}

test('R3: step 4 blocks Next with no quota slot and says why; one slot unblocks it', async () => {
  await toStep4()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /remove slot 1/i })) })
  expect(screen.queryByText('Slot 1 of 1')).toBeNull()
  expect(nextBtn().disabled).toBe(true)
  expect(screen.getByText('A phase needs at least one quota slot.')).toBeTruthy()
  await act(async () => { fireEvent.click(addSlotBtn()) })
  expect(nextBtn().disabled).toBe(false)
  expect(screen.queryByText('A phase needs at least one quota slot.')).toBeNull()
})

test('R3: a baseline start (no open phase, so no prefilled slot) cannot pass step 4 without adding one', async () => {
  api.get.mockResolvedValue({ data: { ...DRAFT, current_phase: null, outgoing_review: [], schedule_items: [] } })
  await renderFlow()
  expect(screen.getByText(/No open phase to review/i)).toBeTruthy()
  await stepTo(4)
  expect(screen.getByText(/step 4 of 8/i)).toBeTruthy()
  expect(nextBtn().disabled).toBe(true)
  expect(screen.getByText('A phase needs at least one quota slot.')).toBeTruthy()
})

test('R5: a same-day correction hides the block verdict and relabels the note box; "Then" stays', async () => {
  api.get.mockResolvedValue({ data: sameDayDraft() })
  await renderFlow()
  expect(screen.queryByText(/Did the block do its job/i)).toBeNull()
  expect(screen.queryByRole('button', { name: /^(yes|partly|no)$/i })).toBeNull()
  expect(screen.getByText('What are you correcting? (optional)')).toBeTruthy()
  expect(screen.getByRole('button', { name: /continue this phase/i })).toBeTruthy()
  expect(screen.getByRole('button', { name: /move to a new phase/i })).toBeTruthy()
})

test('R5: a block opened on an earlier day still gets the verdict and the original note label', async () => {
  await renderFlow()
  expect(screen.getByText('Did the block do its job?')).toBeTruthy()
  expect(screen.queryByText('What are you correcting? (optional)')).toBeNull()
  expect(screen.getByText(/Notes — this becomes the phase’s close reason/)).toBeTruthy()
})

test('R5: an empty correction note omits close_prior_reason, so the server default applies', async () => {
  api.get.mockResolvedValue({ data: sameDayDraft() })
  await renderFlow()
  const body = await saveFromStep1()
  expect('close_prior_reason' in body.phase).toBe(false)
})

test('R5: a correction note is the whole close reason, with no verdict prefix', async () => {
  api.get.mockResolvedValue({ data: sameDayDraft() })
  await renderFlow()
  await act(async () => { fireEvent.change(screen.getByLabelText(/close reason notes/i), { target: { value: 'wrong quota on the first save' } }) })
  const body = await saveFromStep1()
  expect(body.phase.close_prior_reason).toBe('wrong quota on the first save')
})

test('R6: step 1 and the step-8 confirm name the row the save closes (label, entered date)', async () => {
  await renderFlow()
  expect(screen.getByTestId('closing-row').textContent).toBe('This save closes “decompression” · entered 2026-09-07')
  await stepTo(8)
  expect(screen.getByTestId('closing-row').textContent).toBe('Closes “decompression” · entered 2026-09-07')
  expect(screen.queryByText(/opened today/)).toBeNull()
})

test('R6: a same-day correction adds "opened today" on step 1 and on the confirm', async () => {
  api.get.mockResolvedValue({ data: sameDayDraft() })
  await renderFlow()
  expect(screen.getByTestId('closing-row').textContent).toBe(`This save closes “decompression” · entered ${todayLocal()} · opened today`)
  await stepTo(8)
  expect(screen.getByTestId('closing-row').textContent).toBe(`Closes “decompression” · entered ${todayLocal()} · opened today`)
})

test('R6: with no open phase the confirm says it closes nothing', async () => {
  api.get.mockResolvedValue({ data: { ...DRAFT, current_phase: null, outgoing_review: [], schedule_items: [] } })
  await renderFlow()
  expect(screen.queryByTestId('closing-row')).toBeNull()
  await next()                                                              // step 2: name the first phase
  await act(async () => { fireEvent.change(screen.getByLabelText('phase label'), { target: { value: 'first' } }) })
  await next(); await next()                                                // step 4: R3 needs a slot
  await act(async () => { fireEvent.click(addSlotBtn()) })
  for (let i = 0; i < 4; i++) await next()                                  // 5,6,7,8
  expect(screen.getByText(/step 8 of 8/i)).toBeTruthy()
  expect(screen.getByTestId('closing-row').textContent).toBe('Opens a first phase — no row is closed.')
})

// The same-day test compares the open row's entered_on with todayLocal(), the value this form sends as the
// new row's entered_on. Near midnight UTC the operator's day (AEST, UTC+10) is already the next date: a
// row the server stamped "today" in AEST must count as same-day, and the UTC date must not.
test('same-day near midnight UTC: 14:30Z on 5 Oct is 00:30 AEST on 6 Oct, and that is "today"', async () => {
  const prevTz = process.env.TZ
  process.env.TZ = 'Australia/Brisbane'
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-10-05T14:30:00Z'))
  try {
    expect(todayLocal()).toBe('2026-10-06')                          // the AEST day, not the UTC date
    api.get.mockResolvedValue({ data: { ...DRAFT, current_phase: { ...DRAFT.current_phase, entered_on: '2026-10-06' } } })
    await renderFlow()
    expect(screen.getByTestId('closing-row').textContent).toMatch(/opened today$/)
    expect(screen.queryByText(/Did the block do its job/i)).toBeNull()
    cleanup()
    // A row entered on the UTC date (5 Oct) is yesterday in AEST: the verdict is asked.
    api.get.mockResolvedValue({ data: { ...DRAFT, current_phase: { ...DRAFT.current_phase, entered_on: '2026-10-05' } } })
    await renderFlow()
    expect(screen.getByTestId('closing-row').textContent).not.toMatch(/opened today/)
    expect(screen.getByText('Did the block do its job?')).toBeTruthy()
  } finally {
    vi.useRealTimers()
    if (prevTz === undefined) delete process.env.TZ; else process.env.TZ = prevTz
  }
})
