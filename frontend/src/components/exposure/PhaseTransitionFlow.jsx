// PhaseTransitionFlow — the structured phase-change form (#318, PR2; 2026-09-21 real-run fixes).
// Eight steps behind the Phase card's single "Review / change phase" action; its ONE confirm
// performs the server's ONE atomic write (`POST /engine/phase/transition`, #317): close the
// outgoing phase, open the new one, write the schedule items, the phase_folders entry and any
// dated one-off items.
//
// Contract (operator rulings): phase change is a FORM the user completes, not a coach chat. The
// SERVER is the validator (#230) — this component enforces only what makes the form usable and
// shows the server's refusal (translated for overlaps, verbatim under a disclosure). The draft
// lives in component state ONLY: leaving the flow discards it, and the footer says so.
//
// This revision fixes the first real run (21 Sep 2026): every placement ships a resolvable time,
// never 'unknown' (B1); the confirm shows a DIFF with removals first (B2); step 5 loads the
// existing schedule and the counter is the backend's own `consistency_rows` (B3). See DECISIONS
// #320.
//
// Same Tailwind vocabulary as PhaseForm — bg-white border rounded-2xl, gray headings, indigo
// accents. Mobile-first: single column, verified at 380 px (F19).

import { useEffect, useMemo, useRef, useState } from 'react'
import api from '../../api'
import { todayLocal } from './phaseTime'
import {
  TIME_BUCKETS, buildMicrocycle, deriveTimeOfDay, diffSlots, microcycleSlots,
  normaliseActivityName, normaliseTimeRange, removesAllCapacity, slotIdentity,
} from './phaseTransitionLib'

const CAPACITIES = ['mobility', 'stability', 'strength', 'power', 'endurance']
const SLOT_KINDS = ['capacity', 'load_window', 'activity']
const RECORDED_VIA = ['hevy', 'polar_h10', 'garmin', 'samsung_health', 'manual']
// A slot recorded on these has no load path today (HC stage 2, Q159) — WARN (F15, load_window only).
const NO_LOAD_PATH = new Set(['garmin', 'samsung_health'])
const WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

// What each quota KIND records — one-line evidence hint (F4).
const KIND_EVIDENCE = {
  capacity: 'capacity — Hevy workouts',
  load_window: 'load_window — H10 / Garmin sessions of the sports you pick',
  activity: 'activity — a recorded session of the sports you pick; never deposits load',
}

const STEP_TITLES = [
  'Review the outgoing phase',
  'The new phase',
  'Hard commitments first',
  'Quota',
  'Placement',
  'How each session is recorded',
  'Hevy routine folder',
  'Confirm',
]
// What each step is FOR (F18) — one sentence under the header.
const STEP_BLURBS = [
  'Judge whether the block you are closing did its job; your note becomes its close reason.',
  'Name and shape the phase you are opening.',
  'Confirm the fixed commitments and any dated one-off events in this block.',
  'Set how many sessions per week each capacity, load window or activity wants.',
  'Place each quota session on the week and link it to the slot it fills.',
  'Say how each quota session will be recorded, so the plan knows what counts.',
  'Pick or name the Hevy folder this block’s routines go into.',
  'Review exactly what will change, then write it in one go.',
]

const fieldCls =
  'w-full text-xs border border-gray-300 rounded-lg px-2 py-1.5 text-gray-800 ' +
  'focus:outline-none focus:ring-1 focus:ring-indigo-400'
const labelCls = 'text-xs font-medium text-gray-700'
const blurbCls = 'text-[11px] text-gray-500 leading-snug'

function _cap(s) {
  return typeof s === 'string' && s ? s[0].toUpperCase() + s.slice(1) : s
}

export default function PhaseTransitionFlow({ onWritten, onCancel }) {
  const [step, setStep] = useState(1)
  const [draft, setDraft] = useState(null)         // prefill from the server
  const [status, setStatus] = useState('loading')  // loading | ready | error
  const [error, setError] = useState('')            // verbatim server text (kept under a disclosure)
  const [overlap, setOverlap] = useState(null)      // structured 422 overlap (F17)
  const [submitting, setSubmitting] = useState(false)

  // Answers (the draft the confirm assembles) — component state only.
  const [mode, setMode] = useState('continue')     // 'continue' | 'move'
  const [verdict, setVerdict] = useState('')        // yes | partly | no
  const [closeReason, setCloseReason] = useState('')
  const [label, setLabel] = useState('')
  const [intent, setIntent] = useState('')
  const [posture, setPosture] = useState('held')
  const [capacities, setCapacities] = useState([])
  const [allCapacities, setAllCapacities] = useState(false)
  const [reviewOn, setReviewOn] = useState('')
  const [slots, setSlots] = useState([])            // quota slots → microcycle
  const [slotPrompt, setSlotPrompt] = useState(null)  // {index} — the F6 replace-or-add ask
  const [events, setEvents] = useState([])          // NEW dated one-offs
  const [hardItems, setHardItems] = useState([])    // existing hard items (F2/F3): keep/change/remove
  const [placements, setPlacements] = useState([])  // existing soft items + new rows (F8)
  const [previewRows, setPreviewRows] = useState([])  // the counter — backend consistency_rows (F9)
  const [previewStale, setPreviewStale] = useState(false)
  const [ackMismatch, setAckMismatch] = useState(false)
  const [ackRemoveCapacity, setAckRemoveCapacity] = useState(false)  // F16 extra tick (B2)
  const [folderChoice, setFolderChoice] = useState('none')  // 'none' | '<id>' | 'new'
  const [newFolderName, setNewFolderName] = useState('')

  const outgoingSlots = useMemo(
    () => microcycleSlots(draft?.current_phase?.microcycle),
    [draft],
  )

  useEffect(() => {
    let cancelled = false
    api.get('/engine/phase/transition/draft')
      .then((res) => {
        if (cancelled) return
        const d = res.data ?? {}
        setDraft(d)
        const cur = d.current_phase
        if (cur) {
          setLabel(cur.label ?? '')
          setIntent(cur.intent ?? '')
          setPosture(cur.probe_posture ?? 'held')
        }
        // Prefill quota slots from the outgoing microcycle (F6); each editable, none silently applied.
        setSlots(microcycleSlots(cur?.microcycle).map((s) => ({ ...s, origin: 'prefill' })))
        // Split the active schedule items: hard recurring → step 3; soft → step 5 placement (F8).
        const items = d.schedule_items ?? []
        setHardItems(items
          .filter((it) => it.value?.hard === true && !it.value?.event_date)
          .map((it) => ({
            id: it.id, key: it.key, disposition: 'keep',
            activity: it.value?.activity ?? it.key,
            days: it.value?.days ?? [],
            expected_load: it.value?.expected_load ?? 'moderate',
            value: it.value,
          })))
        setPlacements(items
          .filter((it) => it.value?.hard === false)
          .map((it) => ({
            id: it.id, key: it.key, isExisting: true, disposition: 'keep',
            activity: it.value?.activity ?? it.key,
            days: it.value?.days ?? [],
            satisfies: it.value?.satisfies ?? null,
            timeBucket: TIME_BUCKETS.includes(it.value?.time_of_day) ? it.value.time_of_day : 'evening',
            timeRange: it.value?.time_range ?? '',
            sameDayTraining: !!it.value?.same_day_training,
            value: it.value,
          })))
        setStatus('ready')
      })
      .catch(() => { if (!cancelled) setStatus('error') })
    return () => { cancelled = true }
  }, [])

  const sportOptions = useMemo(
    () => (draft?.sport_names_seen ?? []).map((s) => s.sport_name),
    [draft],
  )

  // The schedule-item VALUES that would be active after this transition — kept-and-linked existing
  // items (relinked as chosen) + new rows — fed to the preview so the counter is the backend's own
  // `consistency_rows`, never a client re-derivation (F9, B3).
  const effectiveValues = useMemo(() => {
    const out = []
    for (const p of placements) {
      if (p.isExisting && p.disposition === 'retire') continue
      if (p.isExisting && p.disposition === 'keep') { out.push(p.value); continue }
      if (p.isExisting) { out.push({ ...p.value, satisfies: p.satisfies }); continue }  // relink
      // a new row
      if (!p.key?.trim()) continue
      out.push(newRowValue(p))
    }
    return out
  }, [placements])

  const previewSlots = useMemo(
    () => slots.map((s) => ({ kind: s.kind, key: s.key, quota: Number(s.sessions) || 0 })),
    [slots],
  )

  // Live counter (F9): POST the proposed slots + effective values to the preview and render its
  // rows. Debounced; a failed call keeps the last good rows and flags them stale (never blocks).
  const previewTimer = useRef(null)
  useEffect(() => {
    // Only while the counter is on screen (step 5). This keeps opening-and-leaving the flow a pure
    // read of the draft — no POST until the operator reaches placement (preserves the #59 gate).
    if (status !== 'ready' || step !== 5) return undefined
    clearTimeout(previewTimer.current)
    previewTimer.current = setTimeout(() => {
      api.post('/engine/phase/transition/preview',
        { slots: previewSlots, schedule_item_values: effectiveValues })
        .then((res) => { setPreviewRows(res.data?.consistency_rows ?? []); setPreviewStale(false) })
        .catch(() => setPreviewStale(true))
    }, 250)
    return () => clearTimeout(previewTimer.current)
  }, [status, step, previewSlots, effectiveValues])

  const mismatchRows = useMemo(
    () => previewRows.filter((r) => (r.excess || 0) > 0 || (r.unplaced || 0) > 0),
    [previewRows],
  )
  const hasMismatch = mismatchRows.length > 0

  // ---- quota slots (step 4) ---------------------------------------------- //
  function addSlot() {
    setSlots((p) => [...p, { kind: 'capacity', key: 'stability', sessions: 2, minutes: 30,
                             device_sports: [], recorded_via: '', origin: 'new' }])
  }
  function updateSlot(i, patch) {
    setSlots((p) => p.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  }
  function removeSlot(i) {
    setSlots((p) => p.filter((_, j) => j !== i))
  }
  // Replace this prefilled slot in place (F6) — its kind/key become editable.
  function resolvePromptReplace() {
    setSlots((p) => p.map((s, j) => (j === slotPrompt.index ? { ...s, origin: 'new' } : s)))
    setSlotPrompt(null)
  }
  // Add a new slot, leaving the prefilled one intact (F6).
  function resolvePromptAdd() {
    setSlots((p) => [...p, { kind: 'activity', key: '', sessions: 1, minutes: 30,
                             device_sports: [], recorded_via: '', origin: 'new' }])
    setSlotPrompt(null)
  }

  // ---- events + hard items (step 3) -------------------------------------- //
  function addEvent() {
    setEvents((p) => [...p, { activity: '', event_date: '', event_end: '', expected_load: 'heavy' }])
  }

  // ---- placements (step 5) ----------------------------------------------- //
  function addPlacement() {
    setPlacements((p) => [...p, {
      isExisting: false, disposition: 'keep', key: '', activity: '', days: [], satisfies: null,
      timeBucket: 'evening', timeRange: '', sameDayTraining: false, expected_load: 'moderate',
    }])
  }
  function updatePlacement(i, patch) {
    setPlacements((p) => p.map((x, j) => (j === i ? { ...x, ...patch } : x)))
  }
  function removePlacement(i) {
    setPlacements((p) => p.filter((_, j) => j !== i))
  }

  function newRowValue(p) {
    const activity = normaliseActivityName(p.activity || p.key)
    const value = {
      activity, days: p.days, hard: false, expected_load: p.expected_load,
      time_of_day: deriveTimeOfDay(p.timeBucket, p.timeRange),
      same_day_training: !!p.sameDayTraining, duration_weeks: null, season_end: null,
    }
    const range = normaliseTimeRange(p.timeRange)
    if (range) value.time_range = range
    if (p.satisfies) value.satisfies = p.satisfies
    if (p.distinctFrom?.length) value.distinct_from = p.distinctFrom
    return value
  }

  const diff = useMemo(() => diffSlots(outgoingSlots, slots), [outgoingSlots, slots])
  const mustAckCapacity = useMemo(
    () => removesAllCapacity(outgoingSlots, slots), [outgoingSlots, slots],
  )

  function buildPayload() {
    const microcycle = buildMicrocycle(slots)
    const phase = {
      label: label.trim(), probe_posture: posture, entered_on: todayLocal(),
      asserted_by: 'user', asserted_on: todayLocal(), source: 'api', microcycle,
    }
    if (intent.trim()) phase.intent = intent.trim()
    if (reviewOn) phase.review_on = reviewOn
    if (allCapacities) phase.capacities = null
    else if (capacities.length) phase.capacities = capacities
    // The review answer IS the close reason (F1/G5): verdict + the operator's note.
    const reasonBits = [verdict && `block did its job: ${verdict}`, closeReason.trim()].filter(Boolean)
    if (reasonBits.length) phase.close_prior_reason = reasonBits.join(' — ')

    const schedule_items = []
    // Hard items (step 3): unchanged → no op (F11); changed → upsert preserving unshown fields;
    // removed → retire.
    for (const h of hardItems) {
      if (h.disposition === 'remove') { schedule_items.push({ action: 'retire', key: h.key }); continue }
      if (h.disposition === 'change') {
        schedule_items.push({ action: 'upsert', key: h.key,
          value: { ...h.value, days: h.days, expected_load: h.expected_load } })
      }
    }
    // Placements (step 5): existing kept → no op (F11); relinked → upsert preserving fields with the
    // new satisfies; retired → retire; new → upsert with a resolved time (never 'unknown', B1).
    for (const p of placements) {
      if (p.isExisting) {
        if (p.disposition === 'retire') { schedule_items.push({ action: 'retire', key: p.key }); continue }
        if (p.disposition === 'relink') {
          schedule_items.push({ action: 'upsert', key: p.key, value: { ...p.value, satisfies: p.satisfies } })
        }
        continue
      }
      if (!p.key?.trim()) continue
      schedule_items.push({ action: 'upsert', key: p.key.trim(), value: newRowValue(p) })
    }
    // Dated one-offs (step 3): event_date, no days → the day-overlap check does not apply, so
    // 'unknown' time is correct here (a dated event is not a weekly placement).
    for (const ev of events) {
      if (!ev.activity.trim() || !ev.event_date) continue
      const value = {
        activity: ev.activity.trim(), hard: true, expected_load: ev.expected_load,
        time_of_day: 'unknown', same_day_training: false, duration_weeks: null, season_end: null,
        event_date: ev.event_date,
      }
      if (ev.event_end) value.event_end = ev.event_end
      const key = `event_${ev.event_date}_${normaliseActivityName(ev.activity)}`
      schedule_items.push({ action: 'upsert', key, value })
    }

    const body = { phase, schedule_items }
    if (folderChoice === 'new' && newFolderName.trim()) body.new_folder_name = newFolderName.trim()
    else if (folderChoice !== 'none' && folderChoice !== 'new') body.folder_id = folderChoice
    return body
  }

  // Acknowledge the clashing row(s) on the offending placement, then resubmit (F17).
  function acknowledgeOverlap() {
    if (!overlap) return
    const ids = (overlap.overlapping ?? []).map((o) => o.id).filter((x) => x != null)
    setPlacements((p) => p.map((x) => (
      !x.isExisting && x.key?.trim() === overlap.key
        ? { ...x, distinctFrom: Array.from(new Set([...(x.distinctFrom ?? []), ...ids])) }
        : x
    )))
    setOverlap(null)
    setError('')
  }

  async function confirm() {
    setError('')
    setOverlap(null)
    setSubmitting(true)
    try {
      await api.post('/engine/phase/transition', buildPayload())
      onWritten?.()
    } catch (err) {
      const detail = err?.response?.data?.detail
      if (detail && typeof detail === 'object' && detail.code === 'day_time_clash') {
        setOverlap(detail)                       // structured — translated by the render (F17)
        setError(detail.error || 'schedule overlap')
      } else if (typeof detail === 'string') {
        setError(detail)                         // handler string, shown verbatim
      } else {
        setError('Could not save the phase change.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  // Why Next is disabled (F14/F16) — a named reason beats a dead button.
  let nextBlockedReason = ''
  if (step === 5 && hasMismatch && !ackMismatch) {
    nextBlockedReason = 'Acknowledge the schedule ≠ quota mismatch below to continue.'
  }
  const nextDisabled = !!nextBlockedReason
  const confirmDisabled = submitting || !label.trim() || (mustAckCapacity && !ackRemoveCapacity)

  if (status === 'loading') return <p className="text-sm text-gray-500 p-4">Reading the current phase…</p>
  if (status === 'error') {
    return (
      <div className="bg-white border border-gray-200 rounded-2xl p-4 flex flex-col gap-2">
        <p className="text-sm text-red-600">Could not load the phase-change draft.</p>
        <button type="button" onClick={onCancel} className="self-start text-xs text-gray-600 underline">Close</button>
      </div>
    )
  }

  return (
    <div className="bg-white border border-indigo-200 rounded-2xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-gray-900">
          Change phase · step {step} of 8 — {STEP_TITLES[step - 1]}
        </p>
        <button type="button" onClick={onCancel} className="text-xs text-gray-500 hover:text-gray-700">✕</button>
      </div>
      <p className={blurbCls}>{STEP_BLURBS[step - 1]}</p>

      {/* Step 1 — review the outgoing phase */}
      {step === 1 && (
        <div className="flex flex-col gap-2">
          {(draft.outgoing_review ?? []).length === 0
            ? <p className="text-xs text-gray-500">No open phase to review — this opens a first phase.</p>
            : (draft.outgoing_review ?? []).map((w, i) => (
              <div key={i} className="text-xs text-gray-600 border-b border-gray-100 pb-1">
                <span className="font-medium">{w.window?.label}</span>{' '}
                ({w.window?.start_date} → {w.window?.end_date}):{' '}
                {(w.slots ?? []).map((s) => `${_cap(s.key)} ${s.done}/${s.quota}`).join(' · ')}
              </div>
            ))}
          <div className="flex flex-col gap-1">
            <span className={labelCls}>Did the block do its job?</span>
            <div className="flex gap-2">
              {['yes', 'partly', 'no'].map((v) => (
                <button key={v} type="button" onClick={() => setVerdict(v)} aria-pressed={verdict === v}
                  className={`text-xs px-3 py-1 rounded-full border capitalize ${
                    verdict === v ? 'bg-indigo-600 text-white border-indigo-600'
                      : 'bg-white text-gray-600 border-gray-300'}`}>{v}</button>
              ))}
            </div>
            <label className="flex flex-col gap-1">
              <span className={labelCls}>Notes — this becomes the phase’s close reason</span>
              <textarea value={closeReason} onChange={(e) => setCloseReason(e.target.value)} rows={2}
                aria-label="close reason notes" placeholder="What happened this block?" className={fieldCls} />
            </label>
          </div>
          <div className="flex flex-col gap-1">
            <span className={labelCls}>Then</span>
            <div className="flex gap-2">
              {[['continue', 'Continue this phase (revise)'], ['move', 'Move to a new phase']].map(([v, t]) => (
                <button key={v} type="button" onClick={() => setMode(v)} aria-pressed={mode === v}
                  className={`text-xs px-3 py-1 rounded-full border ${
                    mode === v ? 'bg-indigo-600 text-white border-indigo-600'
                      : 'bg-white text-gray-600 border-gray-300'}`}>{t}</button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Step 2 — the new phase */}
      {step === 2 && (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Label {mode === 'continue' && <span className="text-gray-400">(locked — continuing)</span>}</span>
            <input type="text" value={label} disabled={mode === 'continue'} aria-label="phase label"
              onChange={(e) => setLabel(e.target.value)} className={fieldCls} />
          </label>
          {mode === 'move' && draft.current_phase && (
            <p className="text-[11px] text-gray-400">The plan of record is shown on the card for reference; type the new label yourself — the form does not read the plan prose.</p>
          )}
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Intent</span>
            <textarea value={intent} onChange={(e) => setIntent(e.target.value)} rows={2} aria-label="phase intent" className={fieldCls} />
          </label>
          <div className="flex flex-col gap-1">
            <span className={labelCls}>Probe posture</span>
            <div className="flex gap-2">
              {['held', 'suppressed'].map((p) => (
                <button key={p} type="button" onClick={() => setPosture(p)} aria-pressed={posture === p}
                  className={`text-xs px-3 py-1 rounded-full border capitalize ${
                    posture === p ? 'bg-indigo-600 text-white border-indigo-600'
                      : 'bg-white text-gray-600 border-gray-300'}`}>{p}</button>
              ))}
            </div>
          </div>
          <div className="flex flex-col gap-1">
            <span className={labelCls}>Capacities</span>
            <div className="flex flex-wrap gap-1.5">
              {CAPACITIES.map((t) => (
                <button key={t} type="button" aria-pressed={!allCapacities && capacities.includes(t)}
                  onClick={() => { setAllCapacities(false); setCapacities((p) => p.includes(t) ? p.filter((c) => c !== t) : [...p, t]) }}
                  className={`text-xs px-2 py-0.5 rounded-full border ${
                    !allCapacities && capacities.includes(t) ? 'bg-indigo-100 text-indigo-700 border-indigo-300'
                      : 'bg-white text-gray-600 border-gray-300'}`}>{t}</button>
              ))}
              <button type="button" aria-pressed={allCapacities}
                onClick={() => { setAllCapacities((v) => { if (!v) setCapacities([]); return !v }) }}
                className={`text-xs px-2 py-0.5 rounded-full border ${
                  allCapacities ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-gray-600 border-gray-300'}`}>All</button>
            </div>
          </div>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Review on <span className="text-gray-400">(optional)</span></span>
            <input type="date" value={reviewOn} min={todayLocal()} onChange={(e) => setReviewOn(e.target.value)} aria-label="review on" className={fieldCls} />
          </label>
        </div>
      )}

      {/* Step 3 — hard commitments (existing hard items + dated one-offs) */}
      {step === 3 && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-2">
            <span className={labelCls}>Fixed commitments</span>
            {hardItems.length === 0 && <p className="text-[11px] text-gray-500">No fixed hard commitments on file.</p>}
            {hardItems.map((h, i) => (
              <div key={h.key} className="flex flex-col gap-1 border border-gray-200 rounded-lg p-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-gray-700">{h.activity} <span className="text-gray-400">({h.key})</span></span>
                  <div className="flex gap-1">
                    {[['keep', 'Keep'], ['change', 'Change'], ['remove', 'Remove']].map(([d, t]) => (
                      <button key={d} type="button" aria-pressed={h.disposition === d}
                        onClick={() => setHardItems((p) => p.map((x, j) => j === i ? { ...x, disposition: d } : x))}
                        className={`text-[11px] px-2 py-0.5 rounded-full border ${
                          h.disposition === d ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-gray-600 border-gray-300'}`}>{t}</button>
                    ))}
                  </div>
                </div>
                {h.disposition === 'change' && (
                  <div className="flex flex-col gap-1">
                    <label className="flex flex-col gap-0.5">
                      <span className="text-[11px] text-gray-500">Expected load</span>
                      <select aria-label={`expected load ${h.key}`} value={h.expected_load}
                        onChange={(e) => setHardItems((p) => p.map((x, j) => j === i ? { ...x, expected_load: e.target.value } : x))} className={fieldCls}>
                        {['light', 'moderate', 'heavy', 'none'].map((l) => <option key={l} value={l}>{l}</option>)}
                      </select>
                    </label>
                    <span className="text-[11px] text-gray-500">Days</span>
                    <div className="flex flex-wrap gap-1">
                      {WEEKDAYS.map((d) => (
                        <button key={d} type="button" aria-pressed={h.days.includes(d)}
                          onClick={() => setHardItems((p) => p.map((x, j) => j === i ? { ...x, days: x.days.includes(d) ? x.days.filter((y) => y !== d) : [...x.days, d] } : x))}
                          className={`text-[11px] px-2 py-0.5 rounded-full border ${h.days.includes(d) ? 'bg-indigo-100 text-indigo-700 border-indigo-300' : 'bg-white text-gray-600 border-gray-300'}`}>{d.slice(0, 3)}</button>
                      ))}
                    </div>
                  </div>
                )}
                {h.disposition === 'remove' && <p className="text-[11px] text-amber-700">Will be retired.</p>}
              </div>
            ))}
          </div>
          <div className="flex flex-col gap-2">
            <span className={labelCls}>Dated one-off events</span>
            <p className={blurbCls}>A carnival, travel — a single dated commitment (not a weekly item).</p>
            {events.map((ev, i) => (
              <div key={i} className="flex flex-col gap-1 border border-gray-200 rounded-lg p-2">
                <label className="flex flex-col gap-0.5">
                  <span className="text-[11px] text-gray-500">Event</span>
                  <input type="text" value={ev.activity} placeholder="e.g. athletics carnival" aria-label={`event ${i + 1} name`}
                    onChange={(e) => setEvents((p) => p.map((x, j) => j === i ? { ...x, activity: e.target.value } : x))} className={fieldCls} />
                </label>
                <div className="flex gap-2">
                  <label className="flex flex-col gap-0.5 flex-1">
                    <span className="text-[11px] text-gray-500">Start</span>
                    <input type="date" value={ev.event_date} aria-label={`event ${i + 1} date`}
                      onChange={(e) => setEvents((p) => p.map((x, j) => j === i ? { ...x, event_date: e.target.value } : x))} className={fieldCls} />
                  </label>
                  <label className="flex flex-col gap-0.5 flex-1">
                    <span className="text-[11px] text-gray-500">End <span className="text-gray-400">(optional)</span></span>
                    <input type="date" value={ev.event_end} aria-label={`event ${i + 1} end`}
                      onChange={(e) => setEvents((p) => p.map((x, j) => j === i ? { ...x, event_end: e.target.value } : x))} className={fieldCls} />
                  </label>
                </div>
              </div>
            ))}
            <button type="button" onClick={addEvent} className="self-start text-xs text-indigo-600 border border-indigo-200 rounded-full px-3 py-1">+ dated event</button>
          </div>
        </div>
      )}

      {/* Step 4 — quota (builds the microcycle; no JSON typing) */}
      {step === 4 && (
        <div className="flex flex-col gap-2">
          {slots.map((s, i) => (
            <div key={i} className="flex flex-col gap-1 border border-gray-200 rounded-lg p-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-700">Slot {i + 1} of {slots.length}</span>
                <button type="button" onClick={() => removeSlot(i)} aria-label={`remove slot ${i + 1}`}
                  className="text-[11px] text-gray-400 hover:text-red-600 border border-gray-200 rounded-full px-2">Remove</button>
              </div>
              <div className="flex gap-2">
                <div className="flex flex-col gap-0.5 flex-1">
                  <span className="text-[11px] text-gray-500">Kind</span>
                  {s.origin === 'prefill' ? (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-700">{s.kind}</span>
                      <button type="button" onClick={() => setSlotPrompt({ index: i })}
                        className="text-[11px] text-indigo-600 underline">change kind / target</button>
                    </div>
                  ) : (
                    <select value={s.kind} aria-label={`slot ${i + 1} kind`} onChange={(e) => updateSlot(i, { kind: e.target.value })} className={fieldCls}>
                      {SLOT_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
                    </select>
                  )}
                </div>
                <div className="flex flex-col gap-0.5 flex-1">
                  <span className="text-[11px] text-gray-500">Capacity / name</span>
                  {s.origin === 'prefill' ? (
                    <span className="text-xs text-gray-700 py-1.5">{s.key}</span>
                  ) : (
                    <input type="text" value={s.key} aria-label={`slot ${i + 1} key`}
                      placeholder={s.kind === 'capacity' ? 'stability' : s.kind === 'activity' ? 'pilates' : 'metabolic'}
                      onChange={(e) => updateSlot(i, { key: e.target.value })} className={fieldCls} />
                  )}
                </div>
              </div>
              {slotPrompt && slotPrompt.index === i && (
                <div className="flex flex-col gap-1 bg-amber-50 border border-amber-200 rounded-lg p-2">
                  <span className="text-[11px] text-amber-800">This slot came from the outgoing phase. Replace it, or add a new one?</span>
                  <div className="flex gap-2">
                    <button type="button" onClick={resolvePromptReplace} className="text-[11px] text-white bg-indigo-600 rounded-full px-3 py-1">Replace this slot</button>
                    <button type="button" onClick={resolvePromptAdd} className="text-[11px] text-indigo-600 border border-indigo-300 rounded-full px-3 py-1">Add a new slot</button>
                  </div>
                </div>
              )}
              <div className="flex gap-2">
                <label className="flex flex-col gap-0.5 flex-1">
                  <span className="text-[11px] text-gray-500">Sessions per week</span>
                  <input type="number" min={0} value={s.sessions} aria-label={`slot ${i + 1} sessions per week`}
                    onChange={(e) => updateSlot(i, { sessions: e.target.value })} className={fieldCls} />
                </label>
                <label className="flex flex-col gap-0.5 flex-1">
                  <span className="text-[11px] text-gray-500">Minutes per session <span className="text-gray-400">— advisory, not counted</span></span>
                  <input type="number" min={5} value={s.minutes} aria-label={`slot ${i + 1} minutes`}
                    onChange={(e) => updateSlot(i, { minutes: e.target.value })} className={fieldCls} />
                </label>
              </div>
              <p className="text-[11px] text-gray-400">{KIND_EVIDENCE[s.kind]}</p>
              {(s.kind === 'load_window' || s.kind === 'activity') && (
                <div className="flex flex-col gap-0.5">
                  <span className="text-[11px] text-gray-500">Device sports that count</span>
                  <div className="flex flex-wrap gap-1">
                    {sportOptions.map((sp) => (
                      <button key={sp} type="button" aria-pressed={s.device_sports.includes(sp)}
                        onClick={() => updateSlot(i, { device_sports: s.device_sports.includes(sp) ? s.device_sports.filter((x) => x !== sp) : [...s.device_sports, sp] })}
                        className={`text-xs px-2 py-0.5 rounded-full border ${s.device_sports.includes(sp) ? 'bg-indigo-100 text-indigo-700 border-indigo-300' : 'bg-white text-gray-600 border-gray-300'}`}>{sp}</button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
          <button type="button" onClick={addSlot} className="self-start text-xs text-indigo-600 border border-indigo-200 rounded-full px-3 py-1">+ quota slot</button>
          <details className="mt-1">
            <summary className="text-[11px] text-gray-500 cursor-pointer">Advanced · the microcycle JSON this builds</summary>
            <pre className="text-[10px] text-gray-500 bg-gray-50 rounded p-2 overflow-auto">{JSON.stringify(buildMicrocycle(slots), null, 2)}</pre>
          </details>
        </div>
      )}

      {/* Step 5 — placement */}
      {step === 5 && (
        <div className="flex flex-col gap-2">
          {(draft.week_plan?.days ?? []).some((d) => !d.available || d.caution) && (
            <div className="text-[11px] text-gray-500 border border-gray-100 rounded-lg p-2 flex flex-col gap-0.5">
              <span className="font-medium text-gray-600">This week</span>
              {(draft.week_plan?.days ?? []).map((d) => (
                <span key={d.date}>
                  {_cap(d.weekday)} — {d.available ? 'available' : 'blocked'}{d.caution ? ` · ${d.caution}` : ''}
                </span>
              ))}
            </div>
          )}
          {placements.map((p, i) => (
            <div key={i} className="flex flex-col gap-1 border border-gray-200 rounded-lg p-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-700">
                  {p.isExisting ? <>{p.activity} <span className="text-gray-400">({p.key}, on file)</span></> : `New session ${i + 1}`}
                </span>
                {!p.isExisting && (
                  <button type="button" onClick={() => removePlacement(i)} aria-label={`remove placement ${i + 1}`}
                    className="text-[11px] text-gray-400 hover:text-red-600 border border-gray-200 rounded-full px-2">Remove</button>
                )}
              </div>
              {p.isExisting ? (
                <div className="flex gap-1">
                  {[['keep', 'Keep'], ['relink', 'Relink'], ['retire', 'Retire']].map(([d, t]) => (
                    <button key={d} type="button" aria-pressed={p.disposition === d}
                      onClick={() => updatePlacement(i, { disposition: d })}
                      className={`text-[11px] px-2 py-0.5 rounded-full border ${
                        p.disposition === d ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-gray-600 border-gray-300'}`}>{t}</button>
                  ))}
                </div>
              ) : (
                <div className="flex gap-2">
                  <label className="flex flex-col gap-0.5 flex-1">
                    <span className="text-[11px] text-gray-500">Key</span>
                    <input type="text" value={p.key} aria-label={`placement ${i + 1} key`} placeholder="e.g. gym"
                      onChange={(e) => updatePlacement(i, { key: e.target.value })} className={fieldCls} />
                  </label>
                  <label className="flex flex-col gap-0.5 flex-1">
                    <span className="text-[11px] text-gray-500">Activity</span>
                    <input type="text" value={p.activity} aria-label={`placement ${i + 1} activity`} placeholder="e.g. pilates"
                      onChange={(e) => updatePlacement(i, { activity: e.target.value })} className={fieldCls} />
                  </label>
                </div>
              )}
              {(p.disposition !== 'retire') && (
                <>
                  <label className="flex flex-col gap-0.5">
                    <span className="text-[11px] text-gray-500">Fills quota slot</span>
                    <select aria-label={`placement ${i + 1} satisfies slot`} value={p.satisfies ? Object.values(p.satisfies)[0] : ''}
                      onChange={(e) => {
                        const key = e.target.value
                        const slot = slots.find((s) => s.key === key)
                        updatePlacement(i, { satisfies: slot ? { [slot.kind]: key } : null })
                      }} className={fieldCls}>
                      <option value="">— fills no quota slot —</option>
                      {slots.map((s) => <option key={s.key} value={s.key}>{s.kind}: {s.key}</option>)}
                    </select>
                  </label>
                  {!p.isExisting && (
                    <>
                      <span className="text-[11px] text-gray-500">Days</span>
                      <div className="flex flex-wrap gap-1">
                        {WEEKDAYS.map((d) => (
                          <button key={d} type="button" aria-pressed={p.days.includes(d)}
                            onClick={() => updatePlacement(i, { days: p.days.includes(d) ? p.days.filter((y) => y !== d) : [...p.days, d] })}
                            className={`text-xs px-2 py-0.5 rounded-full border ${p.days.includes(d) ? 'bg-indigo-100 text-indigo-700 border-indigo-300' : 'bg-white text-gray-600 border-gray-300'}`}>{d.slice(0, 3)}</button>
                        ))}
                      </div>
                      <div className="flex gap-2">
                        <label className="flex flex-col gap-0.5 flex-1">
                          <span className="text-[11px] text-gray-500">Time of day</span>
                          <select aria-label={`placement ${i + 1} time of day`} value={p.timeBucket}
                            onChange={(e) => updatePlacement(i, { timeBucket: e.target.value })} className={fieldCls}>
                            {TIME_BUCKETS.map((b) => <option key={b} value={b}>{b}</option>)}
                          </select>
                        </label>
                        <label className="flex flex-col gap-0.5 flex-1">
                          <span className="text-[11px] text-gray-500">Exact time <span className="text-gray-400">(optional, e.g. 17:30-18:30)</span></span>
                          <input type="text" value={p.timeRange} aria-label={`placement ${i + 1} time range`} placeholder="HH:MM-HH:MM"
                            onChange={(e) => updatePlacement(i, { timeRange: e.target.value })} className={fieldCls} />
                        </label>
                      </div>
                      <label className="flex items-center gap-2 text-[11px] text-gray-600">
                        <input type="checkbox" checked={p.sameDayTraining} aria-label={`placement ${i + 1} same-day training ok`}
                          onChange={(e) => updatePlacement(i, { sameDayTraining: e.target.checked })} />
                        Same-day training is fine (does not block the day)
                      </label>
                    </>
                  )}
                </>
              )}
            </div>
          ))}
          <button type="button" onClick={addPlacement} className="self-start text-xs text-indigo-600 border border-indigo-200 rounded-full px-3 py-1">+ placement</button>
          <div className="border-t border-gray-100 pt-2 flex flex-col gap-1">
            <span className={labelCls}>Scheduled vs quota {previewStale && <span className="text-amber-600">(counter may be stale)</span>}</span>
            {previewRows.length === 0 && <p className="text-xs text-gray-500">No quota slots yet.</p>}
            {previewRows.map((r) => {
              const flag = r.excess > 0 ? ` — EXCESS +${r.excess}` : r.unplaced > 0 ? ` — UNPLACED ${r.unplaced}` : ''
              return <p key={`${r.kind}:${r.key}`} className={`text-xs ${flag ? 'text-amber-700' : 'text-gray-600'}`}>{_cap(r.key)} — scheduled {r.scheduled} · quota {r.quota}{flag}</p>
            })}
            {hasMismatch && (
              <label className="flex items-center gap-2 text-xs text-amber-700 mt-1">
                <input type="checkbox" checked={ackMismatch} aria-label="acknowledge schedule does not match quota"
                  onChange={(e) => setAckMismatch(e.target.checked)} />
                I acknowledge the schedule does not match the quota and want to continue.
              </label>
            )}
          </div>
        </div>
      )}

      {/* Step 6 — how each session is recorded */}
      {step === 6 && (
        <div className="flex flex-col gap-2">
          {slots.length === 0 && <p className="text-xs text-gray-500">No quota slots to record.</p>}
          {slots.map((s, i) => (
            <div key={i} className="flex flex-col gap-1 border border-gray-200 rounded-lg p-2">
              <span className="text-xs font-medium text-gray-700">{s.kind}: {s.key}</span>
              <label className="flex flex-col gap-0.5">
                <span className="text-[11px] text-gray-500">Recorded via</span>
                <select aria-label={`recorded via ${s.key || i + 1}`} value={s.recorded_via} onChange={(e) => updateSlot(i, { recorded_via: e.target.value })} className={fieldCls}>
                  <option value="">— how is it recorded? —</option>
                  {RECORDED_VIA.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </label>
              {/* F15: the no-load warning is for load_window slots only; an activity slot is zero-load
                  by design, so warn only when its device has no evidence path at all. */}
              {s.kind === 'load_window' && NO_LOAD_PATH.has(s.recorded_via) && (
                <p className="text-xs text-amber-700 leading-snug">⚠ counts for the plan but deposits no load until Health Connect stage 2 (Q159).</p>
              )}
              {s.kind === 'activity' && (s.device_sports?.length ?? 0) === 0 && s.recorded_via === '' && (
                <p className="text-xs text-amber-700 leading-snug">⚠ no evidence path — pick how a session is recorded, or it can never count.</p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Step 7 — Hevy routine folder */}
      {step === 7 && (
        <div className="flex flex-col gap-2">
          <p className="text-[11px] text-gray-500">A folder per block; routines are created into it. Routines cannot be MOVED between folders through the API.</p>
          <label className="flex flex-col gap-0.5">
            <span className="text-[11px] text-gray-500">Folder</span>
            <select aria-label="folder choice" value={folderChoice} onChange={(e) => setFolderChoice(e.target.value)} className={fieldCls}>
              <option value="none">— no folder —</option>
              {(draft.routine_folders ?? []).map((f) => <option key={f.id} value={f.id}>{f.title}</option>)}
              <option value="new">+ new folder…</option>
            </select>
          </label>
          {folderChoice === 'new' && (
            <label className="flex flex-col gap-0.5">
              <span className="text-[11px] text-gray-500">New folder name</span>
              <input type="text" value={newFolderName} aria-label="new folder name" placeholder="folder name"
                onChange={(e) => setNewFolderName(e.target.value)} className={fieldCls} />
            </label>
          )}
          {draft.routine_folders == null && <p className="text-[11px] text-amber-700">Hevy folders unavailable right now — you can still name a new folder.</p>}
        </div>
      )}

      {/* Step 8 — confirm (a DIFF against the outgoing phase; removals first) */}
      {step === 8 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-gray-600">This will change, in one write:</p>
          <ul className="text-xs list-disc list-inside flex flex-col gap-0.5">
            {diff.removes.map((s) => (
              <li key={`r-${slotIdentity(s)}`} className="text-red-700">REMOVES {s.key} ×{s.sessions}</li>
            ))}
            {diff.changes.map((s) => (
              <li key={`c-${slotIdentity(s)}`} className="text-amber-700">CHANGES {s.key} {s.from} → {s.to}</li>
            ))}
            {diff.adds.map((s) => (
              <li key={`a-${slotIdentity(s)}`} className="text-gray-700">ADDS {s.key} ×{s.sessions}</li>
            ))}
            {diff.removes.length + diff.changes.length + diff.adds.length === 0 && (
              <li className="text-gray-500">No quota-slot changes</li>
            )}
          </ul>
          <p className="text-xs text-gray-600 mt-1">Schedule:</p>
          <ul className="text-xs text-gray-600 list-disc list-inside flex flex-col gap-0.5">
            <li>{placements.filter((p) => p.isExisting && p.disposition === 'keep').length} kept · {placements.filter((p) => p.disposition === 'relink').length} relinked · {[...placements, ...hardItems].filter((p) => p.disposition === 'retire' || p.disposition === 'remove').length} retired · {placements.filter((p) => !p.isExisting && p.key?.trim()).length} added</li>
            <li>{events.filter((e) => e.activity.trim() && e.event_date).length} dated event{events.filter((e) => e.activity.trim() && e.event_date).length === 1 ? '' : 's'}</li>
            <li>{mode === 'continue' ? 'Continue' : 'Move to'} phase <span className="font-medium">{label || '—'}</span></li>
            <li>{folderChoice === 'new' ? `Create Hevy folder "${newFolderName}"` : folderChoice === 'none' ? 'No folder change' : 'Use the selected Hevy folder'}</li>
          </ul>
          {mustAckCapacity && (
            <label className="flex items-center gap-2 text-xs text-red-700 mt-1 border border-red-200 rounded-lg p-2">
              <input type="checkbox" checked={ackRemoveCapacity} aria-label="acknowledge removing all capacity slots"
                onChange={(e) => setAckRemoveCapacity(e.target.checked)} />
              This phase has NO capacity (gym) quota. I understand and want to continue.
            </label>
          )}
          {overlap && (
            <div className="text-xs text-amber-800 border border-amber-200 bg-amber-50 rounded-lg p-2 flex flex-col gap-1">
              <span className="font-medium">Schedule clash</span>
              {(overlap.overlapping ?? []).map((o) => (
                <span key={o.id}>“{overlap.key}” clashes with <span className="font-medium">{o.activity}</span> on {(o.days ?? []).join(', ')} ({o.time_of_day}).</span>
              ))}
              <span>Go back to step 5 to change the day or time — or, if these really are separate sessions:</span>
              <button type="button" onClick={acknowledgeOverlap} className="self-start text-[11px] text-white bg-indigo-600 rounded-full px-3 py-1">These are separate sessions — resubmit</button>
              <details><summary className="text-[11px] text-gray-500 cursor-pointer">Server message</summary>
                <pre className="text-[10px] text-gray-500 whitespace-pre-wrap">{error}</pre></details>
            </div>
          )}
          {error && !overlap && <p className="text-xs text-red-600 whitespace-pre-wrap">{error}</p>}
        </div>
      )}

      {/* Footer — nav + the single confirm; draft-discard notice */}
      <div className="flex flex-col gap-1 border-t border-gray-100 pt-2">
        {step === 8 && nextBlockedReason === '' && confirmDisabled && !submitting && label.trim() && (
          <span className="text-[11px] text-red-600">Tick the acknowledgement above to continue.</span>
        )}
        {nextBlockedReason && <span className="text-[11px] text-amber-700">{nextBlockedReason}</span>}
        <div className="flex items-center justify-between">
          <button type="button" disabled={step === 1 || submitting} onClick={() => setStep((s) => s - 1)}
            className="text-xs text-gray-600 border border-gray-300 rounded-full px-3 py-1 disabled:opacity-40">Back</button>
          <span className="text-[10px] text-gray-400">Leaving discards this draft — nothing is saved until you confirm.</span>
          {step < 8 ? (
            <button type="button" disabled={nextDisabled} onClick={() => setStep((s) => s + 1)}
              className="text-xs text-white bg-indigo-600 rounded-full px-4 py-1 disabled:opacity-40">Next</button>
          ) : (
            <button type="button" disabled={confirmDisabled} onClick={confirm}
              className="text-xs text-white bg-indigo-600 rounded-full px-4 py-1 font-medium disabled:opacity-40">
              {submitting ? 'Saving…' : 'Confirm — save phase change'}</button>
          )}
        </div>
      </div>
    </div>
  )
}
