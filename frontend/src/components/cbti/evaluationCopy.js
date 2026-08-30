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

// The engine reached no decision at all (server `sufficient: false`, #218). The headline
// must not borrow a decision verb: "Hold the window" reads as a titration outcome the
// operator could reasonably accept, and that misreading is what #214 turned into a real
// ledger write. This states the finding instead, and the card carrying it offers no
// accept control — the server refuses such a cycle with a 409 regardless.
export function insufficiencyHeadline() {
  return 'Not enough logged nights to evaluate'
}

// The #214 confirmation restates THE ACTUAL WRITE, not the decision the operator has
// already read above it. Returned as lines rather than a sentence so each consequence is
// separately visible — the buried one in the block-2 harm event was the clock reset, which
// no summary of "accept the decision" ever mentions.
//
// `cycleNights` mirrors `nextEvaluationNote`'s default for the same reason: there is no
// shared JS constant module, and the engine's CYCLE_NIGHTS is 4.
export function confirmationLines(basis, cycleNights = 4) {
  const b = basis ?? {}
  const lines = []
  if (b.window_minutes_current != null || b.window_minutes_proposed != null) {
    lines.push(`Window ${formatMinutes(b.window_minutes_current)} → ${formatMinutes(b.window_minutes_proposed)}`)
  }
  if (b.lights_out_current != null || b.lights_out_proposed != null) {
    lines.push(`Lights out ${b.lights_out_current ?? '—'} → ${b.lights_out_proposed ?? '—'}`)
  }
  // Always present: this is the consequence the operator is least likely to have in mind,
  // and it is the one that cannot be undone by prescribing again tomorrow.
  lines.push(`Closes the current cycle and resets the evaluation clock (~${cycleNights} days)`)
  return lines
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

// ── per-night ledger (Brief B) ───────────────────────────────────────────────
// The headline over the ledger rows: N valid of M nights, where a FLAGGED night counts
// as valid (it stays in the basis, #253) but is still marked in its own row. `nightsLogged`
// is the cycle-clipped count the server sends, never nights-since-effective-from.
export function basisLine(nightsCounted, nightsLogged) {
  const n = nightsCounted ?? 0
  const m = nightsLogged ?? n
  return `${n} valid of ${m} night${m === 1 ? '' : 's'}`
}

// The three-state status is a CLOSED set (server enum). An unrecognised value renders as
// itself rather than being coerced, so a future status can never silently read as one of
// these three.
const STATUS_LABEL = { included: 'Included', flagged: 'Flagged', excluded: 'Excluded' }
export function statusLabel(status) {
  return STATUS_LABEL[status] ?? status ?? '—'
}

// Reason codes are a CLOSED enum (server). The label humanises each; an unknown code
// falls through to the code itself, never to a fabricated phrase.
const REASON_LABEL = {
  ok: 'Clean night',
  alcohol: 'Alcohol',
  incomplete: 'Incomplete data',
  nap: 'Nap over threshold',
  travel_or_match: 'Travel or match',
  training_constrained: 'Late training',
  unknown: 'Unclassified',
}
export function reasonLabel(reason) {
  return REASON_LABEL[reason] ?? reason ?? '—'
}

// Tailwind classes per status — kept here so the chip's look is unit-checkable alongside
// its wording rather than buried in JSX. Flagged is amber (in the basis, but marked);
// included green; excluded a muted rose so a dropped night reads as dropped, not neutral.
const STATUS_CLASS = {
  included: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  flagged: 'bg-amber-50 text-amber-800 border-amber-200',
  excluded: 'bg-rose-50 text-rose-700 border-rose-200',
}
export function statusChipClass(status) {
  return STATUS_CLASS[status] ?? 'bg-gray-50 text-gray-600 border-gray-200'
}
