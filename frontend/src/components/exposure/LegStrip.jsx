// LegStrip — the current leg as a strip of days (Know (d), PR 2; replaces the "Schedule vs quota" lines
// on the Phase card). Reads the GET /engine/week-plan payload the card already holds.
//
// One column per day of the leg's window, in window order — derived from `week.days`, never from a
// hardcoded Mon–Sun (the block-2 leg runs Sun–Sat because the phase was entered on a Sunday).
//   • HARD items are solid blocks with their time.
//   • ACTUAL sessions are filled marks on the day they happened (R6: a done session is never matched
//     to a planned item — that is Q197 — and nothing is ever "missed" for moving day).
//   • SOFT pools (flexible items) appear ONLY in the tray below, once per quota key, never repeated per
//     day: "Gym · 1/2 · Mon Wed Fri", with "to place N" when the quota exceeds what is scheduled.
//   • A day with `available: false` is greyed; `caution` is a small note.
// R9 (amends R6): a soft item whose candidate-day count EQUALS its pool (`schedule_sessions_per_week`
// == the number of days it lists) has no choice left to make, so it ALSO renders on its days, as an
// OUTLINED block (not solid: it is not a fixed commitment). A pool with more days than sessions stays
// tray-only. Done still renders only where it happened; nothing is matched to a planned item (Q197).
//
// Layout: at 640px and above the strip is one column per day; below it, one ROW per day (the day label,
// then its blocks), because seven columns at phone width leave a block a few characters wide. A block's
// text is truncated with the full text in its `title`, never wrapped character by character.
//
// The tray counts per key (done/quota from the resolver, scheduled from the #316 derivation). Its
// candidate days are de-duplicated and listed Mon -> Sun. The quota label for the load_window kind is
// "Conditioning" (R7, via legLabels).

import { WEEKDAY_ORDER, dayAbbrev, keyLabel, shortDate } from './legLabels'

// A hard item's displayed time: an explicit range, else its band; "unknown" is no time at all.
function timeLabel(h) {
  if (h.time_range) return h.time_range
  if (h.time_of_day && h.time_of_day !== 'unknown') return h.time_of_day
  return null
}

// `satisfies` is `{capacity|activity|load_window: <key>}`; the kind is its one key.
function satisfiesId(sat) {
  if (!sat || typeof sat !== 'object') return null
  const kind = Object.keys(sat)[0]
  return kind ? { kind, key: sat[kind], id: `${kind}:${sat[kind]}` } : null
}

// A flexible item's identity across the window's days (the same item is listed on every candidate day).
function itemId(f) {
  const sat = satisfiesId(f.satisfies)
  return `${f.activity ?? ''}|${sat ? sat.id : ''}`
}

// R9: the ids of flexible items whose pool equals the number of distinct weekdays they appear on in the
// window. A missing or non-numeric `pool` (an older server) never equals a count, so it stays tray-only.
function fixedItemIds(days) {
  const seen = new Map()            // id -> { pool, weekdays: Set }
  for (const d of days) {
    for (const f of d.flexible ?? []) {
      const id = itemId(f)
      const e = seen.get(id) ?? { pool: f.pool, weekdays: new Set() }
      e.weekdays.add(d.weekday)
      seen.set(id, e)
    }
  }
  return new Set([...seen].filter(([, e]) => e.pool === e.weekdays.size).map(([id]) => id))
}

// Candidate weekdays as a de-duplicated, Monday-first list of abbreviations.
function orderedDays(weekdays) {
  return WEEKDAY_ORDER.filter((w) => weekdays.has(w)).map(dayAbbrev)
}

// Tray rows: one per quota key (from `week.keys`), then one per unlinked soft item. The linked
// activities name the row; the candidate days are the days a FLEXIBLE item could fall on, minus the
// items R9 already draws on their days.
function trayRows(week, fixed) {
  const linked = new Map()          // id -> { names: Set, weekdays: Set }
  const unlinked = new Map()        // activity -> Set of weekdays
  for (const d of week.days ?? []) {
    for (const f of d.flexible ?? []) {
      const sat = satisfiesId(f.satisfies)
      const isFixed = fixed.has(itemId(f))
      if (sat) {
        const row = linked.get(sat.id) ?? { names: new Set(), weekdays: new Set() }
        if (f.activity) row.names.add(f.activity)
        if (!isFixed) row.weekdays.add(d.weekday)
        linked.set(sat.id, row)
      } else if (f.activity) {
        const set = unlinked.get(f.activity) ?? new Set()
        if (!isFixed) set.add(d.weekday)
        unlinked.set(f.activity, set)
      }
    }
    for (const h of d.hard ?? []) {
      const sat = satisfiesId(h.satisfies)
      if (sat && h.activity) {
        const row = linked.get(sat.id) ?? { names: new Set(), weekdays: new Set() }
        row.names.add(h.activity)
        linked.set(sat.id, row)
      }
    }
  }
  const rows = (week.keys ?? []).map((k) => {
    const id = `${k.kind}:${k.key}`
    const l = linked.get(id)
    const kl = keyLabel(k.kind, k.key)
    const names = l ? [...l.names] : []
    return {
      id, keyLabel: kl, label: names.length ? names.join(' / ') : kl,
      done: k.done, quota: k.quota, days: l ? orderedDays(l.weekdays) : [],
      toPlace: k.unplaced > 0 ? k.unplaced : 0, over: k.excess > 0 ? k.excess : 0,
    }
  })
  for (const [activity, weekdays] of unlinked) {
    rows.push({ id: `unlinked:${activity}`, label: activity, keyLabel: null, days: orderedDays(weekdays), unlinked: true })
  }
  return rows
}

function DayColumn({ d, fixed }) {
  const available = d.available !== false
  const blockCls = 'rounded px-1.5 py-0.5 text-[11px] leading-tight min-w-0 max-w-full'
  return (
    <div data-testid="leg-day" data-date={d.date} data-available={String(available)}
      className={`min-w-0 rounded-lg border p-1.5 flex flex-row items-start gap-2 sm:flex-col sm:gap-1 sm:p-1 ${
        available ? 'bg-white border-gray-200' : 'bg-gray-100 border-gray-200 opacity-70'}`}>
      <p className="w-14 shrink-0 text-[11px] font-medium text-gray-600 leading-tight sm:w-full sm:text-center">
        {dayAbbrev(d.weekday)}
        <span className="ml-1 text-gray-400 tabular-nums sm:ml-0 sm:block">
          {String(d.date ?? '').slice(8).replace(/^0/, '')}
        </span>
      </p>
      <div className="flex flex-wrap gap-1 min-w-0 flex-1 sm:w-full sm:flex-none sm:flex-col sm:flex-nowrap">
        {(d.hard ?? []).map((h, i) => {
          const time = timeLabel(h)
          return (
            <div key={`h${i}`} data-testid="leg-hard" title={[h.activity, time].filter(Boolean).join(' · ')}
              className={`${blockCls} bg-gray-800 text-white`}>
              <span className="block truncate">{h.activity}</span>
              {time && <span className="block truncate text-gray-300">{time}</span>}
            </div>
          )
        })}
        {(d.flexible ?? []).filter((f) => fixed.has(itemId(f))).map((f, i) => {
          const time = timeLabel(f)
          return (
            <div key={`f${i}`} data-testid="leg-soft-fixed"
              title={`${[f.activity, time].filter(Boolean).join(' · ')} · every listed day`}
              className={`${blockCls} border border-gray-700 bg-white text-gray-800`}>
              <span className="block truncate">{f.activity}</span>
              {time && <span className="block truncate text-gray-500">{time}</span>}
            </div>
          )
        })}
        {(d.actual ?? []).map((a, i) => {
          const label = a.title || a.sport_name || keyLabel(a.kind, a.key)
          return (
            <div key={`a${i}`} data-testid="leg-actual" title={label}
              className={`${blockCls} bg-indigo-600 text-white`}>
              <span className="block truncate">● {label}</span>
            </div>
          )
        })}
        {d.caution && <p className="w-full text-[10px] text-amber-700 leading-tight sm:text-center">{d.caution}</p>}
      </div>
    </div>
  )
}

export default function LegStrip({ week }) {
  const days = week?.days ?? []
  const win = week?.window
  const fixed = fixedItemIds(days)
  const rows = trayRows(week ?? {}, fixed)
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[11px] font-medium text-gray-600">
        This leg{win?.label ? ` · ${win.label}` : ''}
        {win?.start_date && win?.end_date ? ` · ${shortDate(win.start_date)} – ${shortDate(win.end_date)}` : ''}
      </p>
      {days.length > 0 && (
        <div role="group" aria-label="Leg days"
          className="grid grid-cols-1 gap-1 sm:[grid-template-columns:repeat(var(--leg-cols),minmax(0,1fr))]"
          style={{ '--leg-cols': days.length }}>
          {days.map((d) => <DayColumn key={d.date} d={d} fixed={fixed} />)}
        </div>
      )}
      {rows.length > 0 && (
        <ul className="flex flex-col gap-0.5" aria-label="Quota tray">
          {rows.map((r) => (
            <li key={r.id} className="text-xs text-gray-600 flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
              <span title={r.days.length > 0 ? `candidate days: ${r.days.join(' ')}` : undefined}>
                {r.unlinked
                  ? `${r.label} · no quota`
                  : `${r.label} · ${r.done}/${r.quota}`}
                {r.days.length > 0 ? ` · ${r.days.join(' ')}` : ''}
              </span>
              {r.keyLabel && r.keyLabel !== r.label && (
                <span className="text-[10px] text-gray-400">({r.keyLabel})</span>
              )}
              {r.toPlace > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700">
                  to place {r.toPlace}
                </span>
              )}
              {r.over > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700">
                  {r.over} over quota
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
