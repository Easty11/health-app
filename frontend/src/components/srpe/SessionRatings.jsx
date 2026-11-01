import { useState } from 'react'
import { keyOf } from './useSessionRatings'

// The per-session rating UI for the close-out and the AM catch-up (state and I/O live in `useSessionRatings`).
// One CR-10 per counted session; a session a device already rated shows that rating read-only with an Override;
// the earlier-sessions backfill is collapsed and saves on its own button. There is no default value: a rating exists
// only because it was tapped.

const SCALE = Array.from({ length: 11 }, (_, i) => i)
const ANCHORS = { 0: 'Rest', 1: 'Very easy', 2: 'Easy', 3: 'Moderate', 4: 'Somewhat hard', 5: 'Hard', 7: 'Very hard', 9: 'Almost maximal', 10: 'Maximal' }

function ScaleInput({ name, value, onPick }) {
  return (
    <div>
      <div role="group" aria-label={`Rate ${name}`} className="grid grid-cols-11 gap-1">
        {SCALE.map((n) => (
          <button
            key={n}
            type="button"
            title={ANCHORS[n]}
            aria-pressed={value === n}
            onClick={() => onPick(n)}
            className={`py-2 rounded-md text-xs font-medium border transition-colors ${
              value === n
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white text-gray-500 border-gray-200 hover:border-indigo-300'
            }`}
          >
            {n}
          </button>
        ))}
      </div>
      <p className="text-[10px] text-gray-400 mt-1 flex justify-between"><span>0 rest</span><span>10 maximal</span></p>
    </div>
  )
}

function fmtDay(iso) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
}

const meta = (s) => [s.minutes != null ? `${s.minutes} min` : null, s.start_local].filter(Boolean).join(' · ')

function SessionRow({ s, sr, withDay = false }) {
  const key = keyOf(s)
  // Override is remembered against the rating it was opened on: once a new rating has been saved and re-read, the
  // identity differs and the row is a read-only rating again.
  const identity = `${s.rpe}|${s.source}`
  const [overridingOn, setOverridingOn] = useState(null)
  const overriding = overridingOn === identity
  const picked = sr.pending[key]
  const rated = s.rpe != null
  const asking = picked != null || !rated || overriding
  return (
    <li className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium text-gray-700">
          {withDay && <span className="text-gray-400 font-normal">{fmtDay(s.day)} · </span>}
          {s.label}
        </span>
        <span className="text-[11px] text-gray-400 shrink-0">{meta(s)}</span>
      </div>
      {asking ? (
        <div className="space-y-1">
          <ScaleInput name={withDay ? `${s.label} ${s.day}` : s.label} value={picked} onPick={(n) => sr.pick(key, n)} />
          {rated && (
            <button
              type="button"
              onClick={() => { sr.unpick(key); setOverridingOn(null) }}
              className="text-[11px] text-gray-400 hover:text-gray-600"
            >
              Keep {s.rpe} ({s.source})
            </button>
          )}
        </div>
      ) : (
        <div className="flex items-center justify-between text-xs">
          <span className="text-gray-600">
            RPE <span className="font-semibold tabular-nums text-gray-800">{s.rpe}</span>
            <span className="text-gray-400"> · {s.source}</span>
          </span>
          {s.rateable !== false && (
            <button type="button" onClick={() => setOverridingOn(identity)} className="text-indigo-600 hover:text-indigo-800">
              Override
            </button>
          )}
        </div>
      )}
      {!rated && s.rateable === false && (
        <p className="text-[11px] text-gray-400">No recorded start or duration, so this cannot be rated here.</p>
      )}
    </li>
  )
}

/** The day's sessions, each with its CR-10 ask (or its rating, read-only, with an Override). */
export function SessionRatingList({ sr, dayWord = 'today', srpeNeeded = true }) {
  if (sr.sessions === null) return null
  return (
    <div className="space-y-3">
      <label className="text-sm font-medium text-gray-700">Rate {dayWord}'s sessions</label>
      {sr.loadFailed && (
        <p className="text-xs text-gray-400">Couldn't load your sessions. You can still save; rate them later from the next close-out.</p>
      )}
      {!sr.loadFailed && sr.sessions.length === 0 && (
        <p className="text-xs text-gray-400">
          {srpeNeeded ? `No session recorded ${dayWord} yet, so there is nothing to rate.` : `No sessions ${dayWord}.`}
        </p>
      )}
      {sr.sessions.length > 0 && (
        <ul className="space-y-4">
          {sr.sessions.map((s) => <SessionRow key={keyOf(s)} s={s} sr={sr} />)}
        </ul>
      )}
      {sr.error && <div className="bg-red-50 text-red-600 text-sm rounded-lg px-3 py-2">{sr.error}</div>}
    </div>
  )
}

/** Collapsed catch-up for earlier sessions nobody rated, saved on its own button. Hidden when there are none. */
export function EarlierSessions({ sr }) {
  const [open, setOpen] = useState(false)
  if (sr.earlier.length === 0) return null
  return (
    <div className="border border-gray-200 rounded-xl">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 text-sm text-gray-600"
      >
        <span>Earlier sessions unrated ({sr.earlier.length})</span>
        <span className="text-gray-400" aria-hidden="true">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-4">
          <p className="text-[11px] text-gray-400">
            Sessions from the last two weeks that no app rated. Give each a real number, or leave it.
          </p>
          <ul className="space-y-4">
            {sr.earlier.map((s) => <SessionRow key={keyOf(s)} s={s} sr={sr} withDay />)}
          </ul>
          <button
            type="button"
            disabled={sr.saving || sr.pendingEarlier === 0}
            onClick={() => sr.saveEarlier()}
            className="w-full bg-white border border-indigo-200 text-indigo-700 rounded-xl py-2 text-sm font-medium hover:bg-indigo-50 disabled:opacity-50 transition-colors"
          >
            {sr.saving ? 'Saving…' : `Save earlier ratings (${sr.pendingEarlier})`}
          </button>
        </div>
      )}
    </div>
  )
}
