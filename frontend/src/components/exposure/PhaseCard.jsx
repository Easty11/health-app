// PhaseCard — the phase surface (#318, PR2 S5). Composes the current phase, week N of the block,
// the review badge, the quota position (QuotaWindow), the #312/#316 week line (scheduled · quota ·
// done + freshness, from GET /engine/week-plan), phase history, and ONE action: Review / change
// phase — which opens the structured 8-step flow (PhaseTransitionFlow). It replaces the phase
// portion of ExposurePanel's read surface: the two ad-hoc controls (Open next phase / Close to
// baseline) and the inline PhaseForm/ClosePhaseDialog are gone — a phase change is the form's single
// confirmed atomic write now (#317), never two loose buttons.
//
// DIVERGENCE (reported at the gate, §44): the brief lists a plan-of-record headline + STALE flag on
// the card. Omitted in PR2 — the plan of record is already surfaced in the chat context (#312/#313),
// and putting it on the card would need either a new read endpoint or a client-side duplicate of the
// backend STALE derivation (`_section_training_plan`). Neither is warranted for a headline; the
// review-due badge already prompts the operator to reconsider the block.
//
// Same Tailwind vocabulary as the rest of the panel.

import { useEffect, useState } from 'react'
import api from '../../api'
import QuotaWindow from './QuotaWindow'
import PhaseHistory from './PhaseHistory'

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

export default function PhaseCard({ phase, refetchKey = 0, onReviewChange }) {
  const [week, setWeek] = useState(null)      // /engine/week-plan | null
  const [wkStatus, setWkStatus] = useState('loading')

  useEffect(() => {
    let cancelled = false
    api.get('/engine/week-plan')
      .then((res) => { if (!cancelled) { setWeek(res.data ?? null); setWkStatus('ready') } })
      .catch(() => { if (!cancelled) setWkStatus('error') })
    return () => { cancelled = true }
  }, [refetchKey])

  if (!phase) {
    // Baseline: no open phase. The only action is to open a first one.
    return (
      <section className="bg-white border border-gray-200 rounded-2xl p-4 flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-gray-900">Training phase</h3>
        <p className="text-xs text-gray-500">No phase open — you are on the standing weekly template.</p>
        <button type="button" onClick={onReviewChange}
          className="self-start text-xs font-medium text-indigo-600 border border-indigo-200 rounded-full px-3 py-1 hover:bg-indigo-50">
          Open a phase
        </button>
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
    </section>
  )
}
