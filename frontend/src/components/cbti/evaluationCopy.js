// Copy for the CBT-I evaluation offer, as pure functions.
//
// Extracted rather than inlined for the same reason the interpretation tile's copy was:
// there is no frontend test runner in this repo, so the only way this wording is
// reviewable in one place — and assertable the moment a runner exists — is to keep it
// out of JSX. The OWED test is recorded in the close-out.
//
// These describe a titration decision the ENGINE made and the operator is about to
// witness. They state what the engine computed and what it rests on; they do not tell
// the reader what to do beyond the accept they explicitly invoked (#118).

export function formatMinutes(m) {
  if (m == null) return '—'
  const h = Math.floor(m / 60)
  const min = m % 60
  return h > 0 ? `${h}h ${String(min).padStart(2, '0')}m` : `${min}m`
}

const VERBS = {
  extend: 'Extend the window',
  compress: 'Compress the window',
  hold: 'Hold the window',
  close: 'Close the block',
  adopt: 'Adopt the window',
}

// The delta phrase belongs ONLY to the two decisions that move the window. `close` and
// `hold` carry the current window unchanged, so appending a magnitude to them produces
// nonsense ("Close the block by +30 min") the moment a caller passes a basis whose
// proposed value differs for any other reason.
const MOVES = new Set(['extend', 'compress'])

export function decisionHeadline(decision, basis) {
  const verb = VERBS[decision] ?? `Decision: ${decision}`
  if (!basis || !MOVES.has(decision)) return verb
  const from = basis.window_minutes_current
  const to = basis.window_minutes_proposed
  if (from == null || to == null || from === to) return verb
  const delta = to - from
  return `${verb} by ${delta > 0 ? '+' : ''}${delta} min`
}

// "1 night dropped" reads as incidental; the operator needs to know the decision was
// computed WITHOUT those nights. Q45 is open, so some exclusions rest on an unverified
// nap attribution and must stay visible rather than being summarised away.
export function exclusionNote(nightsExcluded) {
  const n = Object.keys(nightsExcluded ?? {}).length
  if (n === 0) return null
  return `${n} night${n === 1 ? '' : 's'} excluded from the basis`
}

export function nextEvaluationNote(daysSince, cycleNights = 7) {
  if (daysSince == null) return null
  const left = cycleNights - daysSince
  if (left <= 0) return null
  return `Next evaluation in ${left} night${left === 1 ? '' : 's'}`
}
