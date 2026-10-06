// LegWrap — the leg history on /metrics (Know (d), PR 2; where Visuals increment 4 planned the weekly
// wrap). One row per completed leg from GET /engine/legs: the dates, a phase caption, done/quota per
// slot key, the leg-over-leg delta, a partial marker, and an empty state.
//
//   • QUOTA vs DONE only (R2) — no "scheduled" column; placement of a past leg is not reconstructible.
//   • Each leg was counted server-side against the quota ITS OWN phase declared (R3).
//   • A leg cut short by a phase change shows a "partial" marker and its actual dates (R4).
//   • R8: NO delta ("—") when the leg OR its predecessor is partial — a 4-day leg set against a full
//     one reads as a drop that is only a shorter leg. Presentation only: the server's `delta_done` is
//     the raw difference, and `previous_partial` carries the predecessor's flag (the oldest returned
//     row's predecessor is not itself in the list).
//   • Derived and stateless (R5): a read, nothing stored here. The quota label for the load_window kind
//     is "Conditioning" (R7, via legLabels).

import { useEffect, useState } from 'react'
import api from '../../api'
import { keyLabel, shortDate } from './legLabels'

// The delta cell. Shown only against a full predecessor, for a full leg, on a key present in both.
function deltaText(leg, k) {
  if (leg.partial || leg.previous_partial !== false) return '—'
  if (k.delta_done === null || k.delta_done === undefined) return '—'
  if (k.delta_done > 0) return `+${k.delta_done}`
  if (k.delta_done < 0) return `−${Math.abs(k.delta_done)}`
  return '±0'
}

function Row({ leg }) {
  return (
    <li data-testid="leg-row" className="py-2 border-t border-gray-100 first:border-t-0 flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
        <span className="text-xs font-medium text-gray-900 tabular-nums">
          {shortDate(leg.start_date)} – {shortDate(leg.end_date)}
        </span>
        {leg.partial && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700">partial</span>
        )}
        <span className="text-[11px] text-gray-500">{leg.phase?.label} · leg {leg.label}</span>
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-0.5">
        {(leg.keys ?? []).map((k) => (
          <li key={`${k.kind}:${k.key}`} className="text-xs text-gray-700 flex items-baseline gap-1">
            <span className="font-medium">{keyLabel(k.kind, k.key)}</span>
            <span className="tabular-nums">{k.done}/{k.quota}</span>
            <span data-testid="leg-delta" className="text-[11px] text-gray-400 tabular-nums">
              {deltaText(leg, k)}
            </span>
          </li>
        ))}
      </ul>
    </li>
  )
}

export default function LegWrap({ n = 8 }) {
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('loading')     // loading | ready | error

  useEffect(() => {
    let cancelled = false
    api.get(`/engine/legs?n=${n}`)
      .then((res) => { if (!cancelled) { setData(res.data ?? null); setStatus('ready') } })
      .catch(() => { if (!cancelled) setStatus('error') })
    return () => { cancelled = true }
  }, [n])

  if (status === 'loading') return null
  if (status === 'error') {
    return <p className="text-xs text-red-600 px-1">Could not load the leg wrap.</p>
  }

  const legs = Array.isArray(data?.legs) ? data.legs : []
  const excluded = typeof data?.excluded === 'string' ? data.excluded : null

  return (
    <section aria-label="Leg wrap" className="bg-white border border-gray-200 rounded-2xl p-4 flex flex-col gap-2">
      <h3 className="text-sm font-semibold text-gray-900">Done vs quota, by leg</h3>
      {legs.length === 0
        ? <p className="text-xs text-gray-500">No completed legs yet.</p>
        : <ul className="flex flex-col">{legs.map((leg) => <Row key={leg.start_date} leg={leg} />)}</ul>}
      {excluded && (
        <p className="text-[11px] text-gray-400 leading-snug">
          {excluded[0].toUpperCase() + excluded.slice(1)}. Newest first.
        </p>
      )}
    </section>
  )
}
