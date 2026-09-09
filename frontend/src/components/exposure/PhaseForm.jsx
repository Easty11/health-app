// PhaseForm — the open-a-phase write surface (Exposure UI increment 2, W1). Composed beside the
// read path in ExposurePanel; the read path is unedited (#272 additive).
//
// The React app is an API CLIENT (#230): every phase it opens carries source "api", asserted_by
// "user", asserted_on today-local — fixed, not operator-editable; no new `source` value is minted.
//
// The server is the validator. This form enforces only what makes it usable — a label and a posture
// must be chosen before submit, and the advanced microcycle must be parseable JSON-object before it
// is sent. Everything else (taxonomy tokens, entered_on ≤ today + monotonic, review_on ≥ entered_on,
// microcycle shape) is the server's rule; on 422 we show its `detail` verbatim, never re-validate it
// client-side.

import { useState } from 'react'
import api from '../../api'
import { formatApiError } from '../../lib/apiError'
import { todayLocal } from './phaseTime'

const CAPACITIES = ['mobility', 'stability', 'strength', 'power', 'endurance']

export default function PhaseForm({ hasOpenPhase = false, onWritten, onCancel }) {
  const [label, setLabel] = useState('')
  const [posture, setPosture] = useState('') // '' | 'held' | 'suppressed' — no default; operator chooses
  const [capacities, setCapacities] = useState([]) // selected tokens
  const [allCapacities, setAllCapacities] = useState(false) // mutually exclusive with `capacities`
  const [intent, setIntent] = useState('')
  const [enteredOn, setEnteredOn] = useState(todayLocal())
  const [reviewOn, setReviewOn] = useState('')
  const [closePriorReason, setClosePriorReason] = useState('')
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [microcycle, setMicrocycle] = useState('')
  const [microError, setMicroError] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  function toggleCapacity(token) {
    setAllCapacities(false)
    setCapacities((prev) =>
      prev.includes(token) ? prev.filter((c) => c !== token) : [...prev, token],
    )
  }

  function toggleAll() {
    setAllCapacities((prev) => {
      const next = !prev
      if (next) setCapacities([]) // mutually exclusive
      return next
    })
  }

  // The one sanctioned client check on microcycle: parses, and the result is a plain object. Shape
  // is the server's to validate. Returns { ok, value, message }.
  function parseMicrocycle() {
    const raw = microcycle.trim()
    if (!raw) return { ok: true, value: undefined } // empty → key omitted → lands null → weekly_template
    let parsed
    try {
      parsed = JSON.parse(raw)
    } catch {
      return { ok: false, message: 'Microcycle must be valid JSON.' }
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { ok: false, message: 'Microcycle must be a JSON object.' }
    }
    return { ok: true, value: parsed }
  }

  const canSubmit = label.trim() !== '' && posture !== '' && !submitting

  async function submit(e) {
    e?.preventDefault?.()
    setError('')
    setMicroError('')

    const micro = parseMicrocycle()
    if (!micro.ok) {
      setMicroError(micro.message)
      setAdvancedOpen(true)
      return
    }

    const body = {
      label: label.trim(),
      probe_posture: posture,
      entered_on: enteredOn,
      asserted_by: 'user',
      asserted_on: todayLocal(),
      source: 'api',
    }
    if (intent.trim()) body.intent = intent.trim()
    if (reviewOn) body.review_on = reviewOn
    if (hasOpenPhase && closePriorReason.trim()) body.close_prior_reason = closePriorReason.trim()
    if (allCapacities) body.capacities = null
    else if (capacities.length) body.capacities = capacities
    if (micro.value !== undefined) body.microcycle = micro.value

    setSubmitting(true)
    try {
      await api.post('/engine/phase', body)
      onWritten?.()
    } catch (err) {
      setError(formatApiError(err, 'Could not open the phase.'))
    } finally {
      setSubmitting(false)
    }
  }

  const fieldCls =
    'w-full text-xs border border-gray-300 rounded-lg px-2 py-1.5 text-gray-800 ' +
    'focus:outline-none focus:ring-1 focus:ring-indigo-400'
  const labelCls = 'text-xs font-medium text-gray-700'

  return (
    <form
      onSubmit={submit}
      className="bg-white border border-indigo-200 rounded-2xl p-4 flex flex-col gap-3"
    >
      <p className="text-sm font-semibold text-gray-900">New phase</p>

      {/* label */}
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Label</span>
        <input
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g. Aerobic Base"
          className={fieldCls}
        />
      </label>

      {/* probe_posture — two-way toggle, no default */}
      <div className="flex flex-col gap-1">
        <span className={labelCls}>Probe posture</span>
        <div className="flex gap-2">
          {['held', 'suppressed'].map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPosture(p)}
              aria-pressed={posture === p}
              className={`text-xs px-3 py-1 rounded-full border capitalize transition-colors ${
                posture === p
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* capacities — chip multi-select + mutually-exclusive All toggle */}
      <div className="flex flex-col gap-1">
        <span className={labelCls}>Capacities</span>
        <div className="flex flex-wrap gap-1.5">
          {CAPACITIES.map((token) => (
            <button
              key={token}
              type="button"
              onClick={() => toggleCapacity(token)}
              aria-pressed={!allCapacities && capacities.includes(token)}
              className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
                !allCapacities && capacities.includes(token)
                  ? 'bg-indigo-100 text-indigo-700 border-indigo-300'
                  : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
              }`}
            >
              {token}
            </button>
          ))}
          <button
            type="button"
            onClick={toggleAll}
            aria-pressed={allCapacities}
            className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
              allCapacities
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
            }`}
          >
            All capacities
          </button>
        </div>
      </div>

      {/* intent */}
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Intent <span className="text-gray-400">(optional)</span></span>
        <textarea
          value={intent}
          onChange={(e) => setIntent(e.target.value)}
          rows={2}
          className={fieldCls}
        />
      </label>

      {/* entered_on / review_on */}
      <div className="flex gap-3">
        <label className="flex flex-col gap-1 flex-1">
          <span className={labelCls}>Entered on</span>
          <input
            type="date"
            value={enteredOn}
            max={todayLocal()}
            onChange={(e) => setEnteredOn(e.target.value)}
            className={fieldCls}
          />
        </label>
        <label className="flex flex-col gap-1 flex-1">
          <span className={labelCls}>Review on <span className="text-gray-400">(optional)</span></span>
          <input
            type="date"
            value={reviewOn}
            min={enteredOn}
            onChange={(e) => setReviewOn(e.target.value)}
            className={fieldCls}
          />
        </label>
      </div>

      {/* close_prior_reason — only when a phase is currently open */}
      {hasOpenPhase && (
        <label className="flex flex-col gap-1">
          <span className={labelCls}>
            Close prior reason <span className="text-gray-400">(optional)</span>
          </span>
          <input
            type="text"
            value={closePriorReason}
            onChange={(e) => setClosePriorReason(e.target.value)}
            className={fieldCls}
          />
          <span className="text-[11px] text-gray-400 leading-snug">
            The server defaults this to "opened {label.trim() || '<label>'}".
          </span>
        </label>
      )}

      {/* Advanced ▸ microcycle JSON — the A/B authoring escape hatch, not an editor (ROADMAP) */}
      <div className="border-t border-gray-100 pt-2">
        <button
          type="button"
          onClick={() => setAdvancedOpen((o) => !o)}
          aria-expanded={advancedOpen}
          className="text-xs font-medium text-gray-600"
        >
          {advancedOpen ? '▾' : '▸'} Advanced · microcycle
        </button>
        {advancedOpen && (
          <div className="flex flex-col gap-1 mt-2">
            <textarea
              value={microcycle}
              onChange={(e) => setMicrocycle(e.target.value)}
              rows={4}
              placeholder='{ "weekly": [ … ] }'
              className={`${fieldCls} font-mono`}
            />
            <span className="text-[11px] text-gray-400 leading-snug">
              Leave empty to fall back to your weekly template. A new phase does not inherit the
              previous phase's microcycle.
            </span>
            {microError && <p className="text-xs text-red-600">{microError}</p>}
          </div>
        )}
      </div>

      {error && <p className="text-xs text-red-600">{error}</p>}

      <div className="flex gap-2 pt-1">
        <button
          type="submit"
          disabled={!canSubmit}
          className="flex-1 bg-indigo-600 text-white rounded-xl py-2 text-sm font-medium
            hover:bg-indigo-700 transition-colors disabled:opacity-50"
        >
          {submitting ? 'Opening…' : 'Open phase'}
        </button>
        <button
          type="button"
          onClick={() => onCancel?.()}
          disabled={submitting}
          className="px-4 bg-white text-gray-600 border border-gray-300 rounded-xl py-2
            text-sm font-medium hover:bg-gray-50 transition-colors disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}
