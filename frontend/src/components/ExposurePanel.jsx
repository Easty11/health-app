// Exposure panel — the full read surface for the exposure engine, hosted on /training above the
// workout record (recommendation above record). READ-ONLY this increment: no POST, the review badge
// is a prompt not a button (#228), and the Discuss button is a USER-INITIATED push through the
// existing chat channel (#59) — nothing here seeds the standing prompt, nothing fires on mount.
//
// It owns its own fetch of /engine/next, independent of ExposureTile (no shared cache this
// increment). Same four states as the tile — loading | ready | empty | error — but rendered as a
// panel. Absence is not emptiness: the error state is red and says fault; empty says no profile.
//
// The no-profile response (GATE 2, determined in-tree): /engine/next never 404s; with no profile it
// returns 200 with fortify.target = null. So `empty` = 404 (defensive) OR a 200 with no
// fortify.target; anything else non-2xx = error.
//
// A move, not a rewrite (#150 rule 4): the Tailwind vocabulary is the existing one from
// Tile / InterpretationTile / WorkoutPanel — bg-white border border-gray-200 rounded-2xl p-4,
// gray-900 headings, gray-500 detail, indigo accents. No new design tokens.

import { useEffect, useState } from 'react'
import api from '../api'
import { formatReviewDate } from './hub/exposureTileCopy'
import PhaseForm from './exposure/PhaseForm'
import ClosePhaseDialog from './exposure/ClosePhaseDialog'
import PhaseHistory from './exposure/PhaseHistory'

function Chip({ children, tone = 'gray' }) {
  const tones = {
    gray: 'bg-gray-100 text-gray-600',
    indigo: 'bg-indigo-100 text-indigo-700',
    amber: 'bg-amber-100 text-amber-700',
  }
  return (
    <span className={`inline-block text-xs px-2 py-0.5 rounded-full ${tones[tone]}`}>
      {children}
    </span>
  )
}

function Card({ title, children }) {
  return (
    <section className="bg-white border border-gray-200 rounded-2xl p-4 flex flex-col gap-2">
      {title && <h3 className="text-sm font-semibold text-gray-900">{title}</h3>}
      {children}
    </section>
  )
}

function Field({ label, children }) {
  return (
    <p className="text-xs text-gray-500 leading-snug">
      <span className="font-medium text-gray-700">{label}:</span> {children}
    </p>
  )
}

// The Discuss payload — a short plain-text block, mirroring WorkoutPanel's formatted feedback: an
// opening line, then mode / target / phase / vehicles. User-initiated (#59); never auto-sent.
function formatForChat(d) {
  const isProbe = d?.mode_recommended === 'probe'
  const mode = isProbe ? 'Probe' : 'Fortify'
  const target = d?.fortify?.target_label ?? '—'
  const vehicles = (d?.fortify?.vehicles ?? []).slice(0, 2).map((v) => v.label)

  const lines = ["Let's discuss my current exposure recommendation.", '']
  lines.push(`Mode: ${mode}`)
  lines.push(`Target: ${target}`)
  const phase = d?.training_phase
  if (phase) {
    const review = phase.review_due ? 'review due' : formatReviewDate(phase.review_on)
    lines.push(`Phase: ${phase.label} (${review})`)
  }
  if (vehicles.length) lines.push(`Vehicles: ${vehicles.join(', ')}`)
  return lines.join('\n')
}

export default function ExposurePanel({ onDiscuss }) {
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('loading') // loading | ready | empty | error
  // Write-surface UI state (increment 2). `refetchKey` re-runs the read effect after a write — the
  // single loop this increment closes: write → engine → panel refetch → the recommendation changes.
  const [formOpen, setFormOpen] = useState(false)
  const [closing, setClosing] = useState(false)
  const [refetchKey, setRefetchKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    api.get('/engine/next')
      .then((res) => {
        if (cancelled) return
        if (!res.data?.fortify?.target) {
          setStatus('empty')
          return
        }
        setData(res.data)
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setStatus(err.response?.status === 404 ? 'empty' : 'error')
      })
    return () => { cancelled = true }
  }, [refetchKey])

  // A successful open or close refetches /engine/next and collapses the form/dialog. NO chat push on
  // write (#59) — Discuss remains the only chat path, below, user-initiated.
  function onWritten() {
    setFormOpen(false)
    setClosing(false)
    setRefetchKey((k) => k + 1)
  }

  function openForm() {
    setClosing(false)
    setFormOpen(true)
  }

  if (status === 'loading') {
    return <p className="text-sm text-gray-500 p-4">Reading the engine…</p>
  }
  if (status === 'empty') {
    return <p className="text-sm text-gray-500 p-4">No exposure profile yet</p>
  }
  if (status === 'error') {
    return (
      <p className="text-sm text-red-600 p-4">
        Could not load — this is a fault, not an empty result
      </p>
    )
  }

  const isProbe = data.mode_recommended === 'probe'
  const phase = data.training_phase
  const probe = data.probe
  const fortify = data.fortify
  const dosing = fortify?.dosing ?? {}

  return (
    <div className="flex flex-col gap-3">
      {/* 1. Header — mode chip + effective budget */}
      <div className="flex items-center justify-between gap-2">
        <Chip tone="indigo">{isProbe ? 'Probe' : 'Fortify'}</Chip>
        <span className="text-xs text-gray-500">
          probe {data.budget?.probe} / fortify {data.budget?.fortify}
        </span>
      </div>

      {/* 2. Phase card — only when a phase is open */}
      {phase && (
        <Card title={`Phase · ${phase.label}`}>
          <Field label="Probe posture">{phase.probe_posture}</Field>
          <div className="flex flex-wrap gap-1 items-center">
            <span className="text-xs font-medium text-gray-700">Capacities:</span>
            {phase.capacities === null
              ? <Chip>all capacities</Chip>
              : phase.capacities.map((c) => <Chip key={c}>{c}</Chip>)}
          </div>
          <Field label="Entered">{phase.entered_on}</Field>
          <div className="flex flex-wrap gap-2 items-center">
            <Field label="Review on">{phase.review_on}</Field>
            {/* The review-due badge is a PROMPT that opens a form, never a transition (#228). Its
                text is unchanged; nothing submits without the operator. */}
            {phase.review_due && (
              <button
                type="button"
                onClick={openForm}
                className="inline-block text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700
                  hover:bg-amber-200 transition-colors"
              >
                Review due — open the next phase
              </button>
            )}
          </div>
          {phase.fortify_target_within_phase === false && (
            <p className="text-xs text-amber-700 leading-snug">
              This phase excludes the standing Fortify target's capacity — the engine is serving a
              declared target the phase does not permit.
            </p>
          )}
        </Card>
      )}

      {/* 2b. Phase controls (increment 2, write). Open next phase is always available — and is the
          only control at baseline (no phase). Close to baseline shows only when a phase is open. */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={openForm}
          className="text-xs font-medium text-indigo-600 hover:text-indigo-800 border
            border-indigo-200 rounded-full px-3 py-1 transition-colors"
        >
          Open next phase
        </button>
        {phase && (
          <button
            type="button"
            onClick={() => { setFormOpen(false); setClosing(true) }}
            className="text-xs font-medium text-gray-600 hover:text-gray-800 border
              border-gray-300 rounded-full px-3 py-1 transition-colors"
          >
            Close to baseline
          </button>
        )}
      </div>

      {formOpen && (
        <PhaseForm
          hasOpenPhase={!!phase}
          onWritten={onWritten}
          onCancel={() => setFormOpen(false)}
        />
      )}
      {closing && (
        <ClosePhaseDialog onWritten={onWritten} onCancel={() => setClosing(false)} />
      )}

      {/* 3. Fortify card */}
      <Card title={fortify.target_label}>
        {fortify.target_note && (
          <p className="text-xs text-gray-500 leading-snug">{fortify.target_note}</p>
        )}
        <div>
          <p className="text-xs font-medium text-gray-700 mb-1">Vehicles</p>
          <ol className="list-decimal list-inside flex flex-col gap-0.5">
            {(fortify.vehicles ?? []).map((v) => (
              <li key={v.key} className="text-xs text-gray-500 leading-snug">{v.label}</li>
            ))}
          </ol>
        </div>
        <div className="flex flex-wrap gap-1 items-center">
          <span className="text-xs font-medium text-gray-700">Windows:</span>
          {(dosing.windows ?? []).map((w) => <Chip key={w}>{w}</Chip>)}
        </div>
        {dosing.entry && <Field label="Entry">{dosing.entry}</Field>}
        {dosing.note && <p className="text-xs text-gray-500 leading-snug">{dosing.note}</p>}
      </Card>

      {/* 4. Probe card — only when a probe is suggested */}
      {probe ? (
        <Card title={`Probe · ${probe.label}`}>
          <Field label="Side">{probe.side}</Field>
          <Field label="Plane">{probe.plane}</Field>
          <Field label="Capacity">{probe.capacity}</Field>
          <Field label="Probing test">{probe.probing_test}</Field>
          <Field label="Expectation">{probe.expectation}</Field>
          <Field label="Idiom">{probe.idiom}</Field>
          <div className="flex flex-wrap gap-2 items-center">
            <Field label="Confidence">{probe.confidence}</Field>
            {probe.probe_priority && <Chip tone="indigo">priority</Chip>}
          </div>
        </Card>
      ) : (
        phase?.probe_posture === 'suppressed' && (
          <p className="text-xs text-gray-500 leading-snug px-1">
            Probe suppressed by training phase '{phase.label}'.
          </p>
        )
      )}

      {/* 5. Notes — verbatim, one line each */}
      {(data.notes ?? []).length > 0 && (
        <Card title="Notes">
          {data.notes.map((n, i) => (
            <p key={i} className="text-xs text-gray-500 leading-snug">{n}</p>
          ))}
        </Card>
      )}

      {/* 6. Phase history — the read-only ledger, collapsed by default (increment 2). */}
      <PhaseHistory />

      {/* 7. Discuss — user-initiated push into chat (#59), never automatic */}
      <button
        type="button"
        onClick={() => onDiscuss?.(formatForChat(data))}
        className="self-start text-xs font-medium text-indigo-600 hover:text-indigo-800
          border border-indigo-200 rounded-full px-3 py-1 transition-colors"
      >
        💬 Discuss in chat
      </button>
    </div>
  )
}
