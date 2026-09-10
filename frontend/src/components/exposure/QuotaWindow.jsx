// QuotaWindow — the due-slot resolver read surface (resolver brief STEP 7; consumes #276).
//
// Reads GET /engine/resolver and renders the current quota window's per-slot position
// ({label} · {done}/{quota}), marking the due slot (Rule 4), plus an `uncounted` line that
// distinguishes an `untagged` workout (zero primary tags) from an `off_plan` one (dominant
// capacity not in the window). POSITION ONLY — dose (`minutes`) is not read here; Q106 stays open.
//
// Baseline (no phase microcycle, no weekly template) → `window` is null, 200 — the #272 no-profile
// contract; the surface renders nothing rather than a fault. It owns its own fetch, re-run on
// `refetchKey` so a phase open/close (which changes the window) refreshes it alongside /engine/next.
//
// Same Tailwind vocabulary as the rest of the panel — bg-white border border-gray-200 rounded-2xl,
// gray-900 heading, gray-500 detail, indigo accent. No new design tokens.

import { useEffect, useState } from 'react'
import api from '../../api'

function titleCase(s) {
  return typeof s === 'string' && s ? s[0].toUpperCase() + s.slice(1) : s
}

export default function QuotaWindow({ refetchKey = 0 }) {
  const [data, setData] = useState(null)
  const [status, setStatus] = useState('loading') // loading | ready | error

  useEffect(() => {
    let cancelled = false
    api.get('/engine/resolver')
      .then((res) => {
        if (cancelled) return
        setData(res.data ?? null)
        setStatus('ready')
      })
      .catch(() => { if (!cancelled) setStatus('error') })
    return () => { cancelled = true }
  }, [refetchKey])

  // Loading is silent — the panel already showed its own loader; this is a secondary read.
  if (status === 'loading') return null
  if (status === 'error') {
    return <p className="text-xs text-red-600 px-1">Could not load the quota window.</p>
  }

  const window = data?.window
  if (!window) return null // baseline / no plan → nothing (the #272 no-profile contract)

  const slots = data.slots ?? []
  const uncounted = data.uncounted ?? []
  const due = data.due_capacity

  return (
    <section className="bg-white border border-gray-200 rounded-2xl p-4 flex flex-col gap-2">
      <h3 className="text-sm font-semibold text-gray-900">Quota · {window.label}</h3>

      <ul className="flex flex-col gap-1">
        {slots.map((s) => (
          <li key={s.capacity} className="flex items-center gap-2 text-xs text-gray-700">
            <span className="font-medium">{titleCase(s.capacity)}</span>
            <span className="text-gray-400">·</span>
            <span className="tabular-nums">{s.done}/{s.quota}</span>
            {due === s.capacity && (
              <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700">
                due
              </span>
            )}
          </li>
        ))}
      </ul>

      {uncounted.length > 0 && (
        <div className="border-t border-gray-100 pt-2">
          <p className="text-[11px] font-medium text-gray-600 mb-0.5">Not counted</p>
          <ul className="flex flex-col gap-0.5">
            {uncounted.map((u, i) => (
              <li key={u.workout ?? i} className="text-[11px] text-gray-500 leading-snug">
                {u.reason === 'off_plan'
                  ? <>off-plan · {titleCase(u.capacity)}</>
                  : <>untagged · {u.untagged_exercises} exercise{u.untagged_exercises === 1 ? '' : 's'}</>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
