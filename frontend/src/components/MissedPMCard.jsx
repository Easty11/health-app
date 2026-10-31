import { useState } from 'react'
import api from '../api'
import { EarlierSessions, SessionRatingList } from './srpe/SessionRatings'
import { useSessionRatings } from './srpe/useSessionRatings'

// Missed-PM catch-up card for the AM check-in. Offered when /checkin-v2/prefill carries
// `missed_pm` (yesterday's close-out was never submitted): the operator completes it
// here and it lands on YESTERDAY's daily_record via `for_date`, so it never touches
// today's row or blocks tonight's real close-out.
//
// Its own card, not NightlyCloseOut's: the two share only the per-session rating list (components/srpe), which is
// how effort is asked on both - one CR-10 for each of the missed day's sessions, a device-rated one shown read-only
// with an override, and a collapsed backfill of earlier unrated sessions. The whole-day RPE question is gone. The
// payload mirrors NightlyCloseOut's contract, minus that field, including
// the load-bearing nap rule: while a block is open a blank field submits 0 ("asked, no
// nap"), NEVER null; with no block the field is not shown and null is sent. The block
// flag is `missed_pm.cbti_block_open`, i.e. the state on the day being closed out.
//
// Not rendered here: the #118 evaluation offer - it is a live-cycle action and has no
// place in a retrospective entry.
//
// Skip is client state only: no write, the row stays null (null = "not asked").
//
// WHERE THE RESOLUTION LIVES. Whether the card is saved / already-closed / skipped is NOT this
// component's state: it is `outcome`, held by CheckInAM and reported through `onOutcome`. CheckInAM
// has two return trees (the form view and the "Morning check-in saved" view) and this card sits at
// a different child position in each, so submitting the AM unmounts one instance and mounts a fresh
// one. State local to the instance was lost at that switch and the card re-offered a day that had
// already been closed out (seen live, 11 Oct). Only the entry-in-progress (the fields, the saving
// flag, a save error) stays local.

const DAY_LABELS = ['Terrible', 'Poor', 'Okay', 'Good', 'Great']
const SESSION_LABELS = ['Very poor', 'Below plan', 'As planned', 'Above plan', 'Exceptional']

function TapSelect({ value, onChange, count = 5, labels }) {
  return (
    <div className="flex gap-2">
      {Array.from({ length: count }, (_, i) => i + 1).map(n => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          title={labels?.[n - 1]}
          className={`flex-1 py-2 rounded-lg text-sm font-medium border transition-colors ${
            value === n
              ? 'bg-indigo-600 text-white border-indigo-600'
              : 'bg-white text-gray-500 border-gray-200 hover:border-indigo-300'
          }`}
        >
          {n}
        </button>
      ))}
    </div>
  )
}

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })
}

export default function MissedPMCard({ missedPm, outcome = null, onOutcome = () => {} }) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const [todayRating, setTodayRating] = useState(3)
  const [trained, setTrained] = useState(false)
  const [sessionQuality, setSessionQuality] = useState(3)
  // The missed day's sessions: loaded only while the card is showing (a hook cannot be skipped, so it is told).
  const sr = useSessionRatings(missedPm?.date, { enabled: Boolean(missedPm) && outcome === null })
  const [napsMin, setNapsMin] = useState('')   // '' = blank; blank + open block submits 0, never null
  const [pmNotes, setPmNotes] = useState('')

  if (!missedPm) return null
  if (outcome === 'skipped') return null
  if (outcome === 'saved') {
    return <p className="text-xs text-gray-400 mb-5">Yesterday's close-out saved.</p>
  }
  if (outcome === 'already') {
    return <p className="text-xs text-gray-400 mb-5">Yesterday was already closed out.</p>
  }

  const blockOpen = Boolean(missedPm.cbti_block_open)
  // `missed_pm.srpe_needed` only words the empty state; the asks come from the sessions themselves.
  const srpeNeeded = missedPm.srpe_needed !== false

  async function save() {
    setSaving(true)
    setError('')
    try {
      // Ratings first, on their own route; a failure keeps the card open with the picks intact.
      if (!(await sr.saveToday())) return
      await api.post('/checkin-v2/pm', {
        for_date: missedPm.date,
        today_rating: todayRating,
        trained_today: trained,
        session_quality: trained ? sessionQuality : null,
        pm_notes: pmNotes.trim() || null,
        naps_min: blockOpen ? (napsMin === '' ? 0 : Number(napsMin)) : null,
      })
      onOutcome('saved')
    } catch (err) {
      if (err.response?.status === 409) {
        onOutcome('already')
      } else {
        setError(err.response?.data?.detail || 'Failed to save close-out')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="bg-white border border-indigo-100 rounded-2xl p-4 mb-6 space-y-5">
      <div>
        <h2 className="text-sm font-semibold text-gray-800">
          Close out yesterday ({fmtDate(missedPm.date)})
        </h2>
        <p className="text-[11px] text-gray-400 mt-0.5">
          The evening close-out was missed. This saves to yesterday, separately from this morning's check-in.
        </p>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium text-gray-700">How did yesterday land?</label>
        <TapSelect value={todayRating} onChange={setTodayRating} labels={DAY_LABELS} />
        <p className="text-xs text-gray-400 text-center">{DAY_LABELS[todayRating - 1]}</p>
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-gray-700">Trained yesterday?</label>
          <button
            type="button"
            role="switch"
            aria-checked={trained}
            aria-label="Trained yesterday"
            onClick={() => setTrained(v => !v)}
            className={`w-11 h-6 rounded-full transition-colors relative ${trained ? 'bg-indigo-600' : 'bg-gray-200'}`}
          >
            <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${trained ? 'translate-x-5' : ''}`} />
          </button>
        </div>
        {trained && (
          <div className="space-y-4 pl-1">
            <div className="space-y-2">
              <label className="text-sm font-medium text-gray-700">Session quality (planned vs actual)</label>
              <TapSelect value={sessionQuality} onChange={setSessionQuality} labels={SESSION_LABELS} />
            </div>
          </div>
        )}
      </div>

      <SessionRatingList sr={sr} dayWord="yesterday" srpeNeeded={srpeNeeded} />
      <EarlierSessions sr={sr} />

      {blockOpen && (
        <div className="space-y-1 border-t border-gray-100 pt-4">
          <label className="text-sm font-medium text-gray-700" htmlFor="missed-pm-naps">Naps yesterday (minutes)</label>
          <input
            id="missed-pm-naps"
            type="number"
            inputMode="numeric"
            min={0}
            placeholder="0"
            value={napsMin}
            onChange={e => setNapsMin(e.target.value)}
            className="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
          <p className="text-[10px] text-gray-400">Leave blank for no nap. Naps over 30 min exclude last night from the titration window.</p>
        </div>
      )}

      <div className="space-y-1">
        <label className="text-sm font-medium text-gray-700" htmlFor="missed-pm-notes">Notes (optional)</label>
        <textarea
          id="missed-pm-notes"
          value={pmNotes}
          onChange={e => setPmNotes(e.target.value)}
          rows={2}
          className="block w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
      </div>

      {error && <div className="bg-red-50 text-red-600 text-sm rounded-lg px-3 py-2">{error}</div>}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="flex-1 bg-indigo-600 text-white rounded-xl py-2.5 text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {saving ? 'Saving…' : 'Save yesterday'}
        </button>
        <button
          type="button"
          onClick={() => onOutcome('skipped')}
          disabled={saving}
          className="px-4 bg-white border border-gray-200 text-gray-600 rounded-xl py-2.5 text-sm font-medium hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          Skip
        </button>
      </div>
    </div>
  )
}
