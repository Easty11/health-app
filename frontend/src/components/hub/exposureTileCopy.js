// The exposure tile's one line of copy — the same #150 Constraint A boundary the interpretation
// tile holds: it shows the user their engine state (mode, the named object, the open phase), it
// does NOT reproduce the recommendation or tell them what to do. The panel on /training is the one
// home for the full surface; the tile is a doorway that names what waits behind it.
//
// Extracted as a pure function so the copy has a single reviewable site rather than a template
// literal buried in JSX (mirrors interpretationTileCopy).
//
// Composition (F1): `<Mode> · <object> [· <Phase>, review …]`, joined with ` · `, ≤ ~60 chars.
//   - mode word: Fortify | Probe
//   - object: fortify.target_label when fortify, probe.label when probe
//   - phase, only when training_phase present: capitalised label + `review due` (review_due) or
//     `review <d Mon>` from review_on.

// Noon, not midnight — a date-only string parsed as UTC midnight renders as the previous day in
// local time. Same convention as interpretationTileCopy.formatCollected / HealthPanel.fmtDate.
export function formatReviewDate(dateStr) {
  if (!dateStr) return 'review date unknown'
  const d = new Date(dateStr.slice(0, 10) + 'T12:00:00')
  if (Number.isNaN(d.getTime())) return 'review date unknown'
  return `review ${d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}`
}

function capitalise(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s
}

export function exposureTileCopy(payload) {
  const isProbe = payload?.mode_recommended === 'probe'
  const mode = isProbe ? 'Probe' : 'Fortify'
  const object = isProbe
    ? (payload?.probe?.label ?? '—')
    : (payload?.fortify?.target_label ?? '—')

  const parts = [mode, object]

  const phase = payload?.training_phase
  if (phase) {
    const review = phase.review_due ? 'review due' : formatReviewDate(phase.review_on)
    parts.push(`${capitalise(phase.label)}, ${review}`)
  }

  return parts.join(' · ')
}
