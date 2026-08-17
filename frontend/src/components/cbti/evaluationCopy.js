// Copy for the CBT-I evaluation offer, as pure functions.
//
// Extracted rather than inlined for the same reason the interpretation tile's copy was:
// keeping the wording out of JSX makes it reviewable in one place and unit-testable. The
// repo runs vitest, so this copy is pinned in `evaluationCopy.test.js` — not left OWED.
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

// The hunting engine emits `adopt`/`extend`/`compress`/`hold` and no block-ending
// decision (a plateau is a converged HOLD that leaves the block open, #107), so no
// block-ending verb is carried.
const VERBS = {
  extend: 'Extend the window',
  compress: 'Compress the window',
  hold: 'Hold the window',
  adopt: 'Adopt the window',
}

// The delta phrase belongs ONLY to the two decisions that move the window. `hold` (and
// `adopt`) carry the current window unchanged, so appending a magnitude to them produces
// nonsense ("Hold the window by +30 min") the moment a caller passes a basis whose
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
// computed WITHOUT those nights, so the exclusions stay visible rather than being
// summarised away.
export function exclusionNote(nightsExcluded) {
  const n = Object.keys(nightsExcluded ?? {}).length
  if (n === 0) return null
  return `${n} night${n === 1 ? '' : 's'} excluded from the basis`
}

// The default matches the engine's CYCLE_NIGHTS (4-night hunting cadence). There is no
// shared JS constant module, so the literal is the existing pattern; if the cadence ever
// moves, the server can pass the length instead of relying on this default.
export function nextEvaluationNote(daysSince, cycleNights = 4) {
  if (daysSince == null) return null
  const left = cycleNights - daysSince
  if (left <= 0) return null
  return `Next evaluation in ${left} night${left === 1 ? '' : 's'}`
}
