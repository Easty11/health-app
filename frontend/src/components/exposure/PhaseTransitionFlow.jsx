// PhaseTransitionFlow — the structured phase-change form (#318, PR2). Eight steps behind the Phase
// card's single "Review / change phase" action; its ONE confirm performs the server's ONE atomic
// write (`POST /engine/phase/transition`, #317): close the outgoing phase, open the new one, write
// the schedule items, the phase_folders entry and any dated one-off items.
//
// Contract (operator rulings): phase change is a FORM the user completes, not a coach chat. The
// SERVER is the validator (#230) — this component enforces only what makes the form usable and
// shows the 422 `detail` VERBATIM, never re-validating shape client-side. The draft lives in
// component state ONLY: leaving the flow discards it, and the footer says so. Nothing is written
// before the final confirm; nothing here is written by the coach.
//
// "Extend" and "revise" are BOTH Continue (close-and-open of the same label) — the honest ledger
// representation (#317). Prefill comes from GET /engine/phase/transition/draft; every prefilled
// answer is editable and never silently applied.
//
// Same Tailwind vocabulary as PhaseForm — bg-white border rounded-2xl, gray headings, indigo
// accents. No new tokens.

import { useEffect, useMemo, useState } from 'react'
import api from '../../api'
import { formatApiError } from '../../lib/apiError'
import { todayLocal } from './phaseTime'

const CAPACITIES = ['mobility', 'stability', 'strength', 'power', 'endurance']
const SLOT_KINDS = ['capacity', 'load_window', 'activity']
const RECORDED_VIA = ['hevy', 'polar_h10', 'garmin', 'samsung_health', 'manual']
// A load_window/activity slot recorded on these has no load path today (HC stage 2, Q159) — WARN.
const NO_LOAD_PATH = new Set(['garmin', 'samsung_health'])

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

const fieldCls =
  'w-full text-xs border border-gray-300 rounded-lg px-2 py-1.5 text-gray-800 ' +
  'focus:outline-none focus:ring-1 focus:ring-indigo-400'
const labelCls = 'text-xs font-medium text-gray-700'

function _cap(s) {
  return typeof s === 'string' && s ? s[0].toUpperCase() + s.slice(1) : s
}

// Build the microcycle JSON from the quota slots the form captured (no JSON typing — S4). One
// sub-cycle "A"; the raw-JSON escape hatch (step 4) shows exactly this.
function buildMicrocycle(slots) {
  return {
    sub_cycle_days: 7,
    sub_cycles: [{
      label: 'A',
      slots: slots.map((s) => {
        const out = { sessions_per_cycle: Number(s.sessions) || 0, minutes: Number(s.minutes) || 0 }
        if (s.kind === 'capacity') out.capacity = s.key
        else if (s.kind === 'load_window') { out.load_window = s.key || 'metabolic'; out.device_sports = s.device_sports }
        else { out.activity = s.key; out.device_sports = s.device_sports }
        if (s.recorded_via) out.recorded_via = s.recorded_via
        return out
      }),
    }],
  }
}

export default function PhaseTransitionFlow({ onWritten, onCancel }) {
  const [step, setStep] = useState(1)
  const [draft, setDraft] = useState(null)         // prefill from the server
  const [status, setStatus] = useState('loading')  // loading | ready | error
  const [error, setError] = useState('')
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
  const [events, setEvents] = useState([])          // dated one-offs
  const [scheduleItems, setScheduleItems] = useState([])   // placement links {key, activity, days, satisfies}
  const [ackMismatch, setAckMismatch] = useState(false)
  const [folderChoice, setFolderChoice] = useState('none')  // 'none' | '<id>' | 'new'
  const [newFolderName, setNewFolderName] = useState('')

  useEffect(() => {
    let cancelled = false
    api.get('/engine/phase/transition/draft')
      .then((res) => {
        if (cancelled) return
        const d = res.data ?? {}
        setDraft(d)
        // Prefill (editable): Continue reuses the outgoing label + intent.
        const cur = d.current_phase
        if (cur) {
          setLabel(cur.label ?? '')
          setIntent(cur.intent ?? '')
          setPosture(cur.probe_posture ?? 'held')
        }
        setStatus('ready')
      })
      .catch(() => { if (!cancelled) setStatus('error') })
    return () => { cancelled = true }
  }, [])

  const sportOptions = useMemo(
    () => (draft?.sport_names_seen ?? []).map((s) => s.sport_name),
    [draft],
  )

  // scheduled-vs-quota per slot key, from the placement links (a live, in-form echo of #316).
  const scheduledByKey = useMemo(() => {
    const m = {}
    for (const it of scheduleItems) {
      const key = it.satisfies && Object.values(it.satisfies)[0]
      if (!key) continue
      m[key] = (m[key] || 0) + (Number(it.sessions_per_week) || (it.days?.length ?? 0))
    }
    return m
  }, [scheduleItems])

  const hasMismatch = useMemo(
    () => slots.some((s) => (scheduledByKey[s.key] || 0) !== (Number(s.sessions) || 0)),
    [slots, scheduledByKey],
  )

  function addSlot() {
    setSlots((p) => [...p, { kind: 'capacity', key: 'stability', sessions: 2, minutes: 30,
                             device_sports: [], recorded_via: '' }])
  }
  function updateSlot(i, patch) {
    setSlots((p) => p.map((s, j) => (j === i ? { ...s, ...patch } : s)))
  }
  function addEvent() {
    setEvents((p) => [...p, { activity: '', event_date: '', event_end: '', expected_load: 'heavy' }])
  }
  function addScheduleItem() {
    setScheduleItems((p) => [...p, { key: '', activity: '', days: [], satisfies: null,
                                     expected_load: 'moderate' }])
  }

  function buildPayload() {
    const microcycle = buildMicrocycle(slots)
    const phase = {
      label: label.trim(),
      probe_posture: posture,
      entered_on: todayLocal(),
      asserted_by: 'user',
      asserted_on: todayLocal(),
      source: 'api',
      microcycle,
    }
    if (intent.trim()) phase.intent = intent.trim()
    if (reviewOn) phase.review_on = reviewOn
    if (allCapacities) phase.capacities = null
    else if (capacities.length) phase.capacities = capacities
    const reasonBits = [verdict && `block did its job: ${verdict}`, closeReason.trim()].filter(Boolean)
    if (reasonBits.length) phase.close_prior_reason = reasonBits.join(' — ')

    const schedule_items = []
    for (const it of scheduleItems) {
      if (!it.key.trim()) continue
      const value = {
        activity: it.activity || it.key, days: it.days, hard: false,
        expected_load: it.expected_load, time_of_day: 'unknown', same_day_training: false,
        duration_weeks: null, season_end: null,
      }
      if (it.satisfies) value.satisfies = it.satisfies
      schedule_items.push({ action: 'upsert', key: it.key.trim(), value })
    }
    for (const ev of events) {
      if (!ev.activity.trim() || !ev.event_date) continue
      const value = {
        activity: ev.activity.trim(), hard: true, expected_load: ev.expected_load,
        time_of_day: 'unknown', same_day_training: false, duration_weeks: null, season_end: null,
        event_date: ev.event_date,
      }
      if (ev.event_end) value.event_end = ev.event_end
      const key = `event_${ev.event_date}_${ev.activity.trim().toLowerCase().replace(/\s+/g, '_')}`
      schedule_items.push({ action: 'upsert', key, value })
    }

    const body = { phase, schedule_items }
    if (folderChoice === 'new' && newFolderName.trim()) body.new_folder_name = newFolderName.trim()
    else if (folderChoice !== 'none' && folderChoice !== 'new') body.folder_id = folderChoice
    return body
  }

  async function confirm() {
    setError('')
    setSubmitting(true)
    try {
      await api.post('/engine/phase/transition', buildPayload())
      onWritten?.()
    } catch (err) {
      setError(formatApiError(err, 'Could not save the phase change.'))
    } finally {
      setSubmitting(false)
    }
  }

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
            <textarea value={closeReason} onChange={(e) => setCloseReason(e.target.value)} rows={2}
              placeholder="Notes (becomes the close reason)" className={fieldCls} />
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
            <input type="text" value={label} disabled={mode === 'continue'}
              onChange={(e) => setLabel(e.target.value)} className={fieldCls} />
          </label>
          {mode === 'move' && draft.current_phase && (
            <p className="text-[11px] text-gray-400">The plan of record is shown on the card for reference; type the new label yourself — the form does not read the plan prose.</p>
          )}
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Intent</span>
            <textarea value={intent} onChange={(e) => setIntent(e.target.value)} rows={2} className={fieldCls} />
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
            <input type="date" value={reviewOn} min={todayLocal()} onChange={(e) => setReviewOn(e.target.value)} className={fieldCls} />
          </label>
        </div>
      )}

      {/* Step 3 — hard commitments first + dated one-offs */}
      {step === 3 && (
        <div className="flex flex-col gap-2">
          <p className="text-[11px] text-gray-500">Dated one-off events in this block (a carnival, travel). Recurring hard commitments are managed as schedule items.</p>
          {events.map((ev, i) => (
            <div key={i} className="flex flex-col gap-1 border border-gray-200 rounded-lg p-2">
              <input type="text" value={ev.activity} placeholder="event, e.g. athletics carnival"
                onChange={(e) => setEvents((p) => p.map((x, j) => j === i ? { ...x, activity: e.target.value } : x))} className={fieldCls} />
              <div className="flex gap-2">
                <input type="date" value={ev.event_date} aria-label="event date"
                  onChange={(e) => setEvents((p) => p.map((x, j) => j === i ? { ...x, event_date: e.target.value } : x))} className={fieldCls} />
                <input type="date" value={ev.event_end} aria-label="event end"
                  onChange={(e) => setEvents((p) => p.map((x, j) => j === i ? { ...x, event_end: e.target.value } : x))} className={fieldCls} />
              </div>
            </div>
          ))}
          <button type="button" onClick={addEvent} className="self-start text-xs text-indigo-600 border border-indigo-200 rounded-full px-3 py-1">+ dated event</button>
        </div>
      )}

      {/* Step 4 — quota (builds the microcycle; no JSON typing) */}
      {step === 4 && (
        <div className="flex flex-col gap-2">
          {slots.map((s, i) => (
            <div key={i} className="flex flex-col gap-1 border border-gray-200 rounded-lg p-2">
              <div className="flex gap-2">
                <select value={s.kind} aria-label="slot kind" onChange={(e) => updateSlot(i, { kind: e.target.value })} className={fieldCls}>
                  {SLOT_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
                </select>
                <input type="text" value={s.key} aria-label="slot key" placeholder={s.kind === 'capacity' ? 'stability' : s.kind === 'activity' ? 'pilates' : 'metabolic'}
                  onChange={(e) => updateSlot(i, { key: e.target.value })} className={fieldCls} />
              </div>
              <div className="flex gap-2">
                <input type="number" min={0} value={s.sessions} aria-label="sessions per leg"
                  onChange={(e) => updateSlot(i, { sessions: e.target.value })} className={fieldCls} />
                <input type="number" min={5} value={s.minutes} aria-label="minutes"
                  onChange={(e) => updateSlot(i, { minutes: e.target.value })} className={fieldCls} />
              </div>
              {(s.kind === 'load_window' || s.kind === 'activity') && (
                <div className="flex flex-wrap gap-1">
                  {sportOptions.map((sp) => (
                    <button key={sp} type="button" aria-pressed={s.device_sports.includes(sp)}
                      onClick={() => updateSlot(i, { device_sports: s.device_sports.includes(sp) ? s.device_sports.filter((x) => x !== sp) : [...s.device_sports, sp] })}
                      className={`text-xs px-2 py-0.5 rounded-full border ${s.device_sports.includes(sp) ? 'bg-indigo-100 text-indigo-700 border-indigo-300' : 'bg-white text-gray-600 border-gray-300'}`}>{sp}</button>
                  ))}
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

      {/* Step 5 — placement (link quota sessions to days) */}
      {step === 5 && (
        <div className="flex flex-col gap-2">
          {scheduleItems.map((it, i) => (
            <div key={i} className="flex flex-col gap-1 border border-gray-200 rounded-lg p-2">
              <input type="text" value={it.key} aria-label="schedule key" placeholder="key, e.g. gym"
                onChange={(e) => setScheduleItems((p) => p.map((x, j) => j === i ? { ...x, key: e.target.value } : x))} className={fieldCls} />
              <input type="text" value={it.activity} aria-label="schedule activity" placeholder="activity"
                onChange={(e) => setScheduleItems((p) => p.map((x, j) => j === i ? { ...x, activity: e.target.value } : x))} className={fieldCls} />
              <select aria-label="satisfies slot" value={it.satisfies ? Object.values(it.satisfies)[0] : ''}
                onChange={(e) => {
                  const key = e.target.value
                  const slot = slots.find((s) => s.key === key)
                  setScheduleItems((p) => p.map((x, j) => j === i ? { ...x, satisfies: slot ? { [slot.kind]: key } : null } : x))
                }} className={fieldCls}>
                <option value="">— fills no quota slot —</option>
                {slots.map((s) => <option key={s.key} value={s.key}>{s.kind}: {s.key}</option>)}
              </select>
              <div className="flex flex-wrap gap-1">
                {['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].map((d) => (
                  <button key={d} type="button" aria-pressed={it.days.includes(d)}
                    onClick={() => setScheduleItems((p) => p.map((x, j) => j === i ? { ...x, days: x.days.includes(d) ? x.days.filter((y) => y !== d) : [...x.days, d] } : x))}
                    className={`text-xs px-2 py-0.5 rounded-full border ${it.days.includes(d) ? 'bg-indigo-100 text-indigo-700 border-indigo-300' : 'bg-white text-gray-600 border-gray-300'}`}>{d.slice(0, 3)}</button>
                ))}
              </div>
            </div>
          ))}
          <button type="button" onClick={addScheduleItem} className="self-start text-xs text-indigo-600 border border-indigo-200 rounded-full px-3 py-1">+ placement</button>
          <div className="border-t border-gray-100 pt-2 flex flex-col gap-1">
            {slots.map((s) => {
              const sched = scheduledByKey[s.key] || 0
              const q = Number(s.sessions) || 0
              const flag = sched > q ? ` — EXCESS +${sched - q}` : sched < q ? ` — UNPLACED ${q - sched}` : ''
              return <p key={s.key} className="text-xs text-gray-600">{_cap(s.key)} — scheduled {sched} · quota {q}{flag}</p>
            })}
            {hasMismatch && (
              <label className="flex items-center gap-2 text-xs text-amber-700 mt-1">
                <input type="checkbox" checked={ackMismatch} onChange={(e) => setAckMismatch(e.target.checked)} />
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
              <select aria-label={`recorded via ${s.key}`} value={s.recorded_via} onChange={(e) => updateSlot(i, { recorded_via: e.target.value })} className={fieldCls}>
                <option value="">— how is it recorded? —</option>
                {RECORDED_VIA.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
              {(s.kind === 'load_window' || s.kind === 'activity') && NO_LOAD_PATH.has(s.recorded_via) && (
                <p className="text-xs text-amber-700 leading-snug">⚠ counts for the plan but deposits no load until Health Connect stage 2 (Q159).</p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Step 7 — Hevy routine folder */}
      {step === 7 && (
        <div className="flex flex-col gap-2">
          <p className="text-[11px] text-gray-500">A folder per block; routines are created into it. Routines cannot be MOVED between folders through the API.</p>
          <select aria-label="folder choice" value={folderChoice} onChange={(e) => setFolderChoice(e.target.value)} className={fieldCls}>
            <option value="none">— no folder —</option>
            {(draft.routine_folders ?? []).map((f) => <option key={f.id} value={f.id}>{f.title}</option>)}
            <option value="new">+ new folder…</option>
          </select>
          {folderChoice === 'new' && (
            <input type="text" value={newFolderName} aria-label="new folder name" placeholder="folder name"
              onChange={(e) => setNewFolderName(e.target.value)} className={fieldCls} />
          )}
          {draft.routine_folders == null && <p className="text-[11px] text-amber-700">Hevy folders unavailable right now — you can still name a new folder.</p>}
        </div>
      )}

      {/* Step 8 — confirm */}
      {step === 8 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-gray-600">This will, in one write:</p>
          <ul className="text-xs text-gray-600 list-disc list-inside flex flex-col gap-0.5">
            <li>{mode === 'continue' ? 'Continue' : 'Move to'} phase <span className="font-medium">{label || '—'}</span> (close the current phase, open the new one)</li>
            <li>Set {slots.length} quota slot{slots.length === 1 ? '' : 's'}: {slots.map((s) => `${s.key} ×${s.sessions}`).join(', ') || '—'}</li>
            <li>Write {scheduleItems.filter((i) => i.key.trim()).length} schedule link{scheduleItems.filter((i) => i.key.trim()).length === 1 ? '' : 's'} and {events.filter((e) => e.activity.trim() && e.event_date).length} dated event{events.filter((e) => e.activity.trim() && e.event_date).length === 1 ? '' : 's'}</li>
            <li>{folderChoice === 'new' ? `Create Hevy folder "${newFolderName}"` : folderChoice === 'none' ? 'No folder change' : 'Use the selected Hevy folder'}</li>
          </ul>
          {error && <p className="text-xs text-red-600 whitespace-pre-wrap">{error}</p>}
        </div>
      )}

      {/* Footer — nav + the single confirm; draft-discard notice */}
      <div className="flex items-center justify-between border-t border-gray-100 pt-2">
        <button type="button" disabled={step === 1 || submitting} onClick={() => setStep((s) => s - 1)}
          className="text-xs text-gray-600 border border-gray-300 rounded-full px-3 py-1 disabled:opacity-40">Back</button>
        <span className="text-[10px] text-gray-400">Leaving discards this draft — nothing is saved until you confirm.</span>
        {step < 8 ? (
          <button type="button" disabled={step === 5 && hasMismatch && !ackMismatch}
            onClick={() => setStep((s) => s + 1)}
            className="text-xs text-white bg-indigo-600 rounded-full px-4 py-1 disabled:opacity-40">Next</button>
        ) : (
          <button type="button" disabled={submitting || !label.trim()} onClick={confirm}
            className="text-xs text-white bg-indigo-600 rounded-full px-4 py-1 font-medium disabled:opacity-40">
            {submitting ? 'Saving…' : 'Confirm — save phase change'}</button>
        )}
      </div>
    </div>
  )
}
