// PhaseCard — the phase surface (#318, PR2 S5; extended #319). Composes the current phase, week N of
// the block, the review badge, the plan-of-record headline + STALE flag (#319), the quota position
// (QuotaWindow), the #312/#316 week line (scheduled · quota · done + freshness, from GET
// /engine/week-plan), phase history, and ONE action: Review / change phase — which opens the
// structured 8-step flow (PhaseTransitionFlow). It replaces the phase portion of ExposurePanel's
// read surface: the two ad-hoc controls (Open next phase / Close to baseline) and the inline
// PhaseForm/ClosePhaseDialog are gone from the primary surface — a phase change is the form's single
// confirmed atomic write now (#317), never two loose buttons.
//
// PLAN OF RECORD (#319, closing the #318 §44 divergence): the macro plan headline + a STALE badge
// come from GET /engine/plan-of-record, which returns the SAME stale flag the chat section computes
// (context_builder.plan_of_record_stale — one definition, never re-derived here). Full macro on
// expand.
//
// ADVANCED (#319, item 4): PhaseForm/ClosePhaseDialog are not deleted yet. Until the 8-step flow has
// completed one real transition in prod, a small "advanced: open / close phase directly" link mounts
// them, so the direct write paths remain reachable. Removed in a later PR once the flow is confirmed.
//
// Same Tailwind vocabulary as the rest of the panel.

import { useEffect, useState } from 'react'
import api from '../../api'
import QuotaWindow from './QuotaWindow'
import PhaseHistory from './PhaseHistory'
import PhaseForm from './PhaseForm'
import ClosePhaseDialog from './ClosePhaseDialog'

function Chip({ children, tone = 'gray' }) {
  const tones = {
    gray: 'bg-gray-100 text-gray-600',
    indigo: 'bg-indigo-100 text-indigo-700',
    amber: 'bg-amber-100 text-amber-700',
  }
  return <span className={`inline-block text-xs px-2 py-0.5 rounded-full ${tones[tone]}`}>{children}</span>
}

function _cap(s) {
  return typeof s === 'string' && s ? s[0].toUpperCase() + s.slice(1) : s
}

// Week N of the block: whole weeks since entered_on, 1-based. Null if entered_on is unparseable.
function weekOfBlock(enteredOn) {
  if (!enteredOn) return null
  const entered = new Date(enteredOn + 'T00:00:00')
  if (Number.isNaN(entered.getTime())) return null
  const days = Math.floor((Date.now() - entered.getTime()) / 86400000)
  return days < 0 ? 1 : Math.floor(days / 7) + 1
}

// The macro's headline: its first non-empty line, stripped of leading markdown heading marks. Null
// when there is no usable text (the block is then omitted).
function planHeadline(macro) {
  if (typeof macro !== 'string') return null
  for (const raw of macro.split('\n')) {
    const line = raw.replace(/^#+\s*/, '').trim()
    if (line) return line
  }
  return null
}

// The advanced (direct) open/close controls — the retained PhaseForm/ClosePhaseDialog behind a
// disclosure. A successful write bubbles onWritten (ExposurePanel refetches) and collapses the panel.
function AdvancedPhaseControls({ hasOpenPhase, onWritten }) {
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState(null) // null | 'open' | 'close'

  function written() {
    setMode(null)
    setOpen(false)
    onWritten?.()
  }

  return (
    <div className="border-t border-gray-100 pt-2">
      <button
        type="button"
        onClick={() => { setOpen((o) => !o); setMode(null) }}
        aria-expanded={open}
        className="text-[11px] font-medium text-gray-500 hover:text-gray-700"
      >
        {open ? '▾' : '▸'} Advanced · open / close phase directly
      </button>
      {open && (
        <div className="flex flex-col gap-2 mt-2">
          {mode === null && (
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setMode('open')}
                className="text-xs font-medium text-indigo-600 border border-indigo-200 rounded-full px-3 py-1 hover:bg-indigo-50"
              >
                {hasOpenPhase ? 'Open a new phase' : 'Open a phase'}
              </button>
              {hasOpenPhase && (
                <button
                  type="button"
                  onClick={() => setMode('close')}
                  className="text-xs font-medium text-gray-600 border border-gray-300 rounded-full px-3 py-1 hover:bg-gray-50"
                >
                  Close to baseline
                </button>
              )}
            </div>
          )}
          {mode === 'open' && (
            <PhaseForm hasOpenPhase={hasOpenPhase} onWritten={written} onCancel={() => setMode(null)} />
          )}
          {mode === 'close' && (
            <ClosePhaseDialog onWritten={written} onCancel={() => setMode(null)} />
          )}
        </div>
      )}
    </div>
  )
}

// The plan-of-record headline + STALE badge, full macro on expand. Renders nothing when no plan is
// set (macro null) — matching the chat section's omit-when-absent contract.
function PlanOfRecord({ plan }) {
  const [expanded, setExpanded] = useState(false)
  const headline = planHeadline(plan?.macro)
  if (!headline) return null
  return (
    <div className="border-t border-gray-100 pt-2 flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] font-medium text-gray-600">Plan of record</p>
        {plan.stale && <Chip tone="amber">plan may be stale</Chip>}
      </div>
      <p className="text-xs text-gray-700 leading-snug">{headline}</p>
      {plan.revised_on && (
        <p className="text-[11px] text-gray-400">
          revised {plan.revised_on}{plan.revised_by ? ` by ${plan.revised_by}` : ''}
        </p>
      )}
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        aria-expanded={expanded}
        className="self-start text-[11px] font-medium text-gray-500 hover:text-gray-700"
      >
        {expanded ? '▾ Hide full plan' : '▸ Show full plan'}
      </button>
      {expanded && (
        <pre className="text-[11px] text-gray-600 leading-snug whitespace-pre-wrap font-sans bg-gray-50 rounded-lg p-2">
          {plan.macro}
        </pre>
      )}
    </div>
  )
}

export default function PhaseCard({ phase, refetchKey = 0, onReviewChange, onWritten }) {
  const [week, setWeek] = useState(null)      // /engine/week-plan | null
  const [wkStatus, setWkStatus] = useState('loading')
  const [plan, setPlan] = useState(null)      // /engine/plan-of-record | null

  useEffect(() => {
    let cancelled = false
    api.get('/engine/week-plan')
      .then((res) => { if (!cancelled) { setWeek(res.data ?? null); setWkStatus('ready') } })
      .catch(() => { if (!cancelled) setWkStatus('error') })
    return () => { cancelled = true }
  }, [refetchKey])

  useEffect(() => {
    let cancelled = false
    api.get('/engine/plan-of-record')
      .then((res) => { if (!cancelled) setPlan(res.data ?? null) })
      .catch(() => { if (!cancelled) setPlan(null) })
    return () => { cancelled = true }
  }, [refetchKey])

  if (!phase) {
    // Baseline: no open phase. The primary action opens a first one via the flow; the advanced
    // disclosure keeps the direct PhaseForm reachable (#319, item 4).
    return (
      <section className="bg-white border border-gray-200 rounded-2xl p-4 flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-gray-900">Training phase</h3>
        <p className="text-xs text-gray-500">No phase open — you are on the standing weekly template.</p>
        <PlanOfRecord plan={plan} />
        <button type="button" onClick={onReviewChange}
          className="self-start text-xs font-medium text-indigo-600 border border-indigo-200 rounded-full px-3 py-1 hover:bg-indigo-50">
          Open a phase
        </button>
        <AdvancedPhaseControls hasOpenPhase={false} onWritten={onWritten} />
      </section>
    )
  }

  const n = weekOfBlock(phase.entered_on)

  return (
    <section className="bg-white border border-gray-200 rounded-2xl p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-900">
          Phase · {phase.label}{n ? ` · week ${n}` : ''}
        </h3>
        {phase.review_due
          ? <Chip tone="amber">review due</Chip>
          : phase.review_on && <Chip>review {phase.review_on}</Chip>}
      </div>

      <p className="text-xs text-gray-500 leading-snug">
        <span className="font-medium text-gray-700">Posture:</span> {phase.probe_posture} ·{' '}
        <span className="font-medium text-gray-700">entered</span> {phase.entered_on}
      </p>
      <div className="flex flex-wrap gap-1 items-center">
        <span className="text-xs font-medium text-gray-700">Capacities:</span>
        {phase.capacities === null
          ? <Chip>all</Chip>
          : (phase.capacities ?? []).map((c) => <Chip key={c}>{c}</Chip>)}
      </div>

      {/* Plan of record (#319) — headline + STALE badge, full macro on expand */}
      <PlanOfRecord plan={plan} />

      {/* Quota position (the #276/#307 resolver read) */}
      <QuotaWindow refetchKey={refetchKey} />

      {/* The #312/#316 week line: scheduled · quota · done + freshness */}
      {wkStatus === 'ready' && week && (
        <div className="border-t border-gray-100 pt-2 flex flex-col gap-0.5">
          <p className="text-[11px] font-medium text-gray-600">Schedule vs quota</p>
          {(week.keys ?? []).map((k) => {
            const flag = k.excess > 0 ? ` — MISMATCH +${k.excess}`
              : k.unplaced > 0 ? ` — UNPLACED ${k.unplaced}` : ''
            return (
              <p key={`${k.kind}:${k.key}`} className="text-xs text-gray-600">
                {_cap(k.key)} — scheduled {k.scheduled} · quota {k.quota} · done {k.done}{flag}
              </p>
            )
          })}
          {week.needs_planning && (
            <p className="text-xs text-amber-700">Planning needed — no schedule item is placed against the quota.</p>
          )}
          {week.freshness && (week.freshness.hc_stale || week.freshness.polar_stale) && (
            <p className="text-[11px] text-amber-700 leading-snug">
              Device-evidenced counts may be incomplete — the platform hasn't heard from the device this window.
            </p>
          )}
        </div>
      )}

      {/* ONE action */}
      <button type="button" onClick={onReviewChange}
        className="self-start text-xs font-medium text-indigo-600 border border-indigo-200 rounded-full px-3 py-1 hover:bg-indigo-50 transition-colors">
        Review / change phase
      </button>

      <PhaseHistory />

      <AdvancedPhaseControls hasOpenPhase onWritten={onWritten} />
    </section>
  )
}
