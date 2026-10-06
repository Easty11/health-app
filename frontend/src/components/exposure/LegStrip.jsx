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
// The tray counts per key (done/quota from the resolver, scheduled from the #316 derivation). The quota
// label for the load_window kind is "Conditioning" (R7, via legLabels).

import { dayAbbrev, keyLabel, shortDate } from './legLabels'

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

// Tray rows: one per quota key (from `week.keys`), then one per unlinked soft item. The linked
// activities name the row; the candidate days are the days a FLEXIBLE item could fall on.
function trayRows(week) {
  const linked = new Map()          // id -> { names: Set, days: string[] }
  const unlinked = new Map()        // activity -> days[]
  for (const d of week.days ?? []) {
    for (const f of d.flexible ?? []) {
      const sat = satisfiesId(f.satisfies)
      if (sat) {
        const row = linked.get(sat.id) ?? { names: new Set(), days: [] }
        if (f.activity) row.names.add(f.activity)
        row.days.push(dayAbbrev(d.weekday))
        linked.set(sat.id, row)
      } else if (f.activity) {
        unlinked.set(f.activity, [...(unlinked.get(f.activity) ?? []), dayAbbrev(d.weekday)])
      }
    }
    for (const h of d.hard ?? []) {
      const sat = satisfiesId(h.satisfies)
      if (sat && h.activity) {
        const row = linked.get(sat.id) ?? { names: new Set(), days: [] }
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
      done: k.done, quota: k.quota, days: l ? l.days : [],
      toPlace: k.unplaced > 0 ? k.unplaced : 0, over: k.excess > 0 ? k.excess : 0,
    }
  })
  for (const [activity, days] of unlinked) {
    rows.push({ id: `unlinked:${activity}`, label: activity, keyLabel: null, days, unlinked: true })
  }
  return rows
}

function DayColumn({ d }) {
  const available = d.available !== false
  return (
    <div data-testid="leg-day" data-date={d.date} data-available={String(available)}
      className={`min-w-0 rounded-lg border p-1 flex flex-col gap-1 ${
        available ? 'bg-white border-gray-200' : 'bg-gray-100 border-gray-200 opacity-70'}`}>
      <p className="text-[10px] font-medium text-gray-600 text-center leading-tight">
        {dayAbbrev(d.weekday)}
        <span className="block text-gray-400 tabular-nums">{String(d.date ?? '').slice(8).replace(/^0/, '')}</span>
      </p>
      {(d.hard ?? []).map((h, i) => (
        <div key={`h${i}`} data-testid="leg-hard"
          className="rounded bg-gray-800 text-white px-1 py-0.5 text-[10px] leading-tight break-words">
          {h.activity}
          {timeLabel(h) && <span className="block text-gray-300">{timeLabel(h)}</span>}
        </div>
      ))}
      {(d.actual ?? []).map((a, i) => (
        <div key={`a${i}`} data-testid="leg-actual"
          className="rounded bg-indigo-600 text-white px-1 py-0.5 text-[10px] leading-tight break-words">
          ● {a.title || a.sport_name || keyLabel(a.kind, a.key)}
        </div>
      ))}
      {d.caution && <p className="text-[9px] text-amber-700 leading-tight text-center">{d.caution}</p>}
    </div>
  )
}

export default function LegStrip({ week }) {
  const days = week?.days ?? []
  const win = week?.window
  const rows = trayRows(week ?? {})
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[11px] font-medium text-gray-600">
        This leg{win?.label ? ` · ${win.label}` : ''}
        {win?.start_date && win?.end_date ? ` · ${shortDate(win.start_date)} – ${shortDate(win.end_date)}` : ''}
      </p>
      {days.length > 0 && (
        <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}>
          {days.map((d) => <DayColumn key={d.date} d={d} />)}
        </div>
      )}
      {rows.length > 0 && (
        <ul className="flex flex-col gap-0.5" aria-label="Quota tray">
          {rows.map((r) => (
            <li key={r.id} className="text-xs text-gray-600 flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
              <span>
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
