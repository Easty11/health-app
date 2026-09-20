// QuotaWindow — the due-slot resolver read surface (resolver brief STEP 7; consumes #276/#307).
//
// Reads GET /engine/resolver and renders the current quota window's per-slot position
// ({label} · {done}/{quota}), marking the due slot (Rule 4). A slot is one of three KINDS
// (#307/#315): a movement-quality `capacity` slot; a sport-scoped `load_window` conditioning
// slot (metabolic) shown as "Conditioning"; or an `activity` slot (#315 — a device-evidenced
// session of a declared sport, zero-load) shown as its title-cased activity name. The due marker
// reads the top-level `due_slot {kind, key}`, so it lands on any kind (never the old
// `due_capacity`, which is capacity-only and would mis-mark a non-capacity slot when both are
// null). The `uncounted` line names the miss reasons: `untagged` (zero primary tags) and
// `off_plan` (dominant capacity not in the window) for Hevy workouts; `concurrent_strength` (an
// aerobic session overlapping the gym), `untimed` (NULL start/stop), and `unclaimed_session` (a
// recorded session matching no slot's sport, e.g. a walk — "other activity"; detail `no_sport`
// when no sport was recorded) for canonical aerobic sessions. POSITION ONLY — dose (`minutes`) is
// not read here; Q106 stays open.
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

// A slot's display label: a load_window slot is a conditioning slot ("Conditioning" for the
// metabolic window); an activity slot is its title-cased activity name (#315); a capacity slot is
// its title-cased capacity token.
function slotLabel(s) {
  if (s.kind === 'load_window') {
    return s.load_window === 'metabolic' ? 'Conditioning' : titleCase(s.load_window)
  }
  if (s.kind === 'activity') return titleCase(s.activity)
  return titleCase(s.capacity)
}

// The token `due_slot` names this slot, matched on (kind, key) — capacity slots key on `capacity`,
// load_window slots on `load_window`, activity slots on `activity` (#315). Both/all-null can never
// spuriously match (unlike due_capacity).
function slotKey(s) {
  if (s.kind === 'load_window') return s.load_window
  if (s.kind === 'activity') return s.activity
  return s.capacity
}
function isDue(s, dueSlot) {
  if (!dueSlot) return false
  return dueSlot.kind === s.kind && dueSlot.key === slotKey(s)
}

// One "not counted" line per surfaced item. Hevy workouts carry `workout`; aerobic sessions
// carry `session`. Each reason renders its own phrasing; an unknown reason falls back to itself.
function uncountedLabel(u) {
  switch (u.reason) {
    case 'off_plan':
      return <>off-plan · {titleCase(u.capacity)}</>
    case 'untagged':
      return <>untagged · {u.untagged_exercises} exercise{u.untagged_exercises === 1 ? '' : 's'}</>
    case 'concurrent_strength':
      return <>concurrent strength · {u.sport_name}</>
    case 'untimed':
      return <>untimed · {u.sport_name}</>
    case 'unclaimed_session':
      return u.detail === 'no_sport'
        ? <>other activity · no recorded sport</>
        : <>other activity · {u.sport_name}</>
    default:
      return <>{u.reason}</>
  }
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
  const dueSlot = data.due_slot

  return (
    <section className="bg-white border border-gray-200 rounded-2xl p-4 flex flex-col gap-2">
      <h3 className="text-sm font-semibold text-gray-900">Quota · {window.label}</h3>

      <ul className="flex flex-col gap-1">
        {slots.map((s, i) => (
          <li key={`${s.kind}:${s.capacity ?? s.load_window ?? s.activity ?? i}`}
              className="flex items-center gap-2 text-xs text-gray-700">
            <span className="font-medium">{slotLabel(s)}</span>
            <span className="text-gray-400">·</span>
            <span className="tabular-nums">{s.done}/{s.quota}</span>
            {isDue(s, dueSlot) && (
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
              <li key={u.workout ?? u.session ?? i} className="text-[11px] text-gray-500 leading-snug">
                {uncountedLabel(u)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
