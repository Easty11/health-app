// The PM evaluation offer — #118's witnessed trigger, surfaced at nightly close-out.
//
// Renders the engine's cycle decision AND ITS BASIS before anything is minted. That
// ordering is the decision, not a layout choice: #118 makes titration manual precisely
// so a prescription cannot change what the operator does without them having seen the
// decision and what it rested on.
//
// Accept is an explicit control and the ONLY write path. It posts an empty body — the
// server re-evaluates and mints from its own result, so nothing the client sends can
// produce a prescription the engine did not compute.
//
// ACCEPT IS TWO ACTS, NOT ONE (#214, resolving Q101). The offer card's own control fires
// no request: it expands a confirmation that restates the ACTUAL WRITE — the decision, the
// window and lights-out moves, and that accepting closes the current cycle and resets the
// ~4-day evaluation clock. Only the second, explicit control posts. The clock reset is the
// consequence the harm event turned on: block 2's operator tapped a live single-tap accept
// on an insufficiency HOLD and lost a buried fully-logged compress plus ~4 days.
//
// AND NOT EVERY OFFER IS ACCEPTABLE. A cycle the engine could not adjudicate (server
// `sufficient: false`) renders information-only — the engine's reason and the nights tally,
// with no accept control in either step. That is a presentation of the server's rule, not
// the rule itself: `POST .../accept` refuses such a cycle with a 409 whatever the client
// renders. Every decision-on-merits — extend, compress, adherence HOLD, converged HOLD —
// keeps the full two-step accept; there is no other dead-control arm.

import { useEffect, useState } from 'react'
import api from '../../api'
import {
  confirmationLines, decisionHeadline, exclusionNote, formatMinutes,
  insufficiencyHeadline, nextEvaluationNote,
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
  // The #214 gate. False = the offer is being read; true = the confirmation restating the
  // write is open. Nothing about entering or leaving this state touches the network.
  const [confirming, setConfirming] = useState(false)
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
  // The server's decision-class flag, never a parse of `decision_reason` (#218). Read
  // strictly: only an explicit `false` suppresses the accept control, so an older server
  // that omits the field keeps the two-step accept rather than silently going read-only.
  const acceptable = ev.sufficient !== false

  if (!acceptable) {
    return (
      <div className="bg-white border-2 border-gray-200 rounded-2xl p-4 mb-4 text-left space-y-3">
        <div>
          <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wide">
            Cycle complete · no decision
          </p>
          <p className="text-sm font-semibold text-gray-900 mt-1">{insufficiencyHeadline()}</p>
        </div>

        <div className="grid grid-cols-2 gap-y-1.5 text-xs border-t border-gray-100 pt-2">
          <Row label="Nights counted" value={b?.nights_counted ?? '—'} />
          <Row label="Nights logged this cycle" value={ev.nights_since_effective_from ?? '—'} />
          <Row label="Cycle" value={`${b?.cycle_from ?? '—'} → ${b?.cycle_to ?? '—'}`} />
        </div>

        {/* The engine's own sentence — it names the shortfall AND the exclusions that
            caused it, which is the whole content of a stall. */}
        {ev.decision_reason && (
          <p className="text-[11px] text-gray-500 leading-snug border-t border-gray-100 pt-2">
            {ev.decision_reason}
          </p>
        )}

        {/* Q45 stays visible here for the same reason it does on an acceptable offer, and
            more so: nap exclusions on the unverified date-1 attribution are the likeliest
            cause of the shortfall being read. */}
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

        {/* No accept control in any state — deliberately not a disabled button, which
            still reads as "an action that could be taken". Nothing is minted, nothing is
            reset, and the next cycle continues from the prescription already in force. */}
        <p className="text-[11px] text-gray-400 leading-snug border-t border-gray-100 pt-2">
          Nothing to record. The current prescription stands and the cycle continues.
        </p>
      </div>
    )
  }

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

      {/* STEP 1 — no network. The label says what the control does (opens a review), not
          what the flow eventually does, so a tap made without reading cannot write. */}
      {!confirming && (
        <button
          type="button"
          onClick={() => { setError(''); setConfirming(true) }}
          className="w-full bg-indigo-600 text-white rounded-xl py-2.5 text-sm font-medium
            hover:bg-indigo-700 transition-colors"
        >
          Review and accept…
        </button>
      )}

      {/* STEP 2 — the write, restated. This repeats the decision deliberately: the
          operator is confirming a LEDGER WRITE, and the write is not only the numbers
          above but the cycle close and clock reset that come with them. */}
      {confirming && (
        <div className="border-t border-gray-100 pt-3 space-y-2">
          <p className="text-[11px] font-semibold text-gray-800">
            Record this prescription? {decisionHeadline(ev.decision, b)}.
          </p>
          <ul className="space-y-0.5">
            {confirmationLines(b).map((line) => (
              <li key={line} className="text-[11px] text-gray-600 leading-snug">· {line}</li>
            ))}
          </ul>
          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={accept}
              disabled={accepting}
              className="flex-1 bg-indigo-600 text-white rounded-xl py-2.5 text-sm font-medium
                hover:bg-indigo-700 transition-colors disabled:opacity-50"
            >
              {accepting ? 'Recording…' : 'Confirm — record prescription'}
            </button>
            <button
              type="button"
              onClick={() => { setError(''); setConfirming(false) }}
              disabled={accepting}
              className="px-4 bg-white text-gray-600 border border-gray-300 rounded-xl py-2.5
                text-sm font-medium hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
