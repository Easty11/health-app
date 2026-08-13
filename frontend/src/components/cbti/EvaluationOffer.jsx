// The PM evaluation offer — #118's witnessed trigger, surfaced at nightly close-out.
//
// Renders the engine's cycle decision AND ITS BASIS before anything is minted. That
// ordering is the decision, not a layout choice: #118 makes titration manual precisely
// so a prescription cannot change what the operator does without them having seen the
// decision and what it rested on.
//
// Accept is an explicit control and the ONLY write path. It posts an empty body — the
// server re-evaluates and mints from its own result, so nothing the client sends can
// produce a prescription the engine did not compute. Every eligible decision under the
// hunting engine is a prescription (extend / compress / hold, including a converged
// HOLD), so the offer always has an accept control — the engine emits no block-ending
// decision, and there is no dead-control arm.

import { useEffect, useState } from 'react'
import api from '../../api'
import {
  decisionHeadline, exclusionNote, formatMinutes, nextEvaluationNote,
} from './evaluationCopy'

function Row({ label, value }) {
  return (
    <>
      <span className="text-gray-500">{label}</span>
      <span className="text-gray-800 font-medium text-right tabular-nums">{value}</span>
    </>
  )
}

export default function EvaluationOffer({ onAccepted }) {
  const [ev, setEv] = useState(null)
  const [status, setStatus] = useState('loading') // loading | ready | error
  const [accepting, setAccepting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    api.get('/checkin-v2/cbti/evaluation')
      .then(({ data }) => {
        if (cancelled) return
        setEv(data)
        setStatus('ready')
      })
      .catch(() => { if (!cancelled) setStatus('error') })
    return () => { cancelled = true }
  }, [])

  async function accept() {
    setAccepting(true)
    setError('')
    try {
      const { data } = await api.post('/checkin-v2/cbti/evaluation/accept')
      setEv(data)
      onAccepted?.(data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not record the evaluation.')
    } finally {
      setAccepting(false)
    }
  }

  if (status !== 'ready' || !ev?.block_open) return null

  if (ev.reason === 'accepted') {
    return (
      <div className="bg-green-50 border border-green-200 rounded-2xl p-4 mb-4 text-left">
        <p className="text-sm font-semibold text-green-800">Evaluation recorded</p>
        <p className="text-xs text-green-700 mt-1">
          New window {formatMinutes(ev.basis?.window_minutes_proposed)} · lights out{' '}
          {ev.basis?.lights_out_proposed} → {ev.basis?.wake_anchor}. A new cycle starts tonight.
        </p>
      </div>
    )
  }

  // Not yet a full cycle — a quiet line, not a card.
  if (!ev.eligible) {
    const note = nextEvaluationNote(ev.days_since_effective_from)
    if (!note) return null
    return <p className="text-xs text-gray-400 mb-4 text-center">{note}</p>
  }

  const b = ev.basis
  const excluded = exclusionNote(b?.nights_excluded)

  return (
    <div className="bg-white border-2 border-indigo-200 rounded-2xl p-4 mb-4 text-left space-y-3">
      <div>
        <p className="text-[10px] font-medium text-indigo-400 uppercase tracking-wide">
          Cycle complete · evaluation ready
        </p>
        <p className="text-sm font-semibold text-gray-900 mt-1">
          {decisionHeadline(ev.decision, b)}
        </p>
        <p className="text-xs text-gray-500 mt-0.5">
          {formatMinutes(b?.window_minutes_current)} → {formatMinutes(b?.window_minutes_proposed)}
          {b?.lights_out_proposed && (
            <> · lights out {b.lights_out_proposed} → {b.wake_anchor}</>
          )}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-y-1.5 text-xs border-t border-gray-100 pt-2">
        <Row label="Nights counted" value={b?.nights_counted ?? '—'} />
        <Row label="Mean TST" value={formatMinutes(b?.tst_min)} />
        <Row label="Mean SE" value={b?.se_pct != null ? `${b.se_pct}%` : '—'} />
        <Row label="Cycle" value={`${b?.cycle_from ?? '—'} → ${b?.cycle_to ?? '—'}`} />
      </div>

      {/* The engine's own sentence, not a paraphrase — a HOLD names the first gate that
          failed, and that is the whole content of the decision. */}
      {ev.decision_reason && (
        <p className="text-[11px] text-gray-500 leading-snug border-t border-gray-100 pt-2">
          {ev.decision_reason}
        </p>
      )}

      {/* Q45 is open: some exclusions rest on the unverified date-1 nap attribution, so
          which nights were dropped is part of the basis, not a footnote. */}
      {excluded && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
          <p className="text-[11px] font-medium text-amber-800">{excluded}</p>
          <ul className="mt-1 space-y-0.5">
            {Object.entries(b.nights_excluded).map(([d, reason]) => (
              <li key={d} className="text-[11px] text-amber-700">{d} — {reason}</li>
            ))}
          </ul>
        </div>
      )}

      {error && <p className="text-xs text-red-600">{error}</p>}

      <button
        type="button"
        onClick={accept}
        disabled={accepting}
        className="w-full bg-indigo-600 text-white rounded-xl py-2.5 text-sm font-medium
          hover:bg-indigo-700 transition-colors disabled:opacity-50"
      >
        {accepting ? 'Recording…' : 'Accept and prescribe'}
      </button>
    </div>
  )
}
