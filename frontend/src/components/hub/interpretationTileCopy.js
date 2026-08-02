// The interpretation tile's one line of copy (Q63 candidate (a), under #150 Constraint A).
//
// Extracted as a pure function so the #47 boundary has a SINGLE reviewable site rather than a
// template literal buried in JSX. What it may carry: counts, section structure, recency — the
// user's own data. What it may not: any phrasing that orders this user's problems for them
// ("needs attention", "your top three", "N need action"). #150's test — shows them their data =
// in; tells them what to do or ranks their issues = out.
//
// Counts come from `splitSections`, the same placement function the view uses, which CONSUMES
// `should_surface` rather than recomputing it. Recomputing moved-ness here would be a second
// source of truth that drifts silently — the exact defect sections.js was written to close.
//
// NOT `meta.generated_at`. That field exists, but `GET /interpretation` builds the payload on
// every request (`producer.py:560` stamps `datetime.now`), so it is always "now" — a tile reading
// "generated 2 Aug" every day of the year states nothing about the user's data and implies a
// stored artefact with an age. `trigger_panel.collected` is the real recency: the date of the draw
// being interpreted. Q63's own example ("last generated 30 May") is that collection date in the
// committed fixture, not a generation date.

import { splitSections } from '../interpretation/sections'

// Noon, not midnight — a date-only string parsed as UTC midnight renders as the previous day
// in local time. Same convention as HealthPanel's fmtDate.
export function formatCollected(dateStr) {
  if (!dateStr) return 'unknown date'
  const d = new Date(dateStr.slice(0, 10) + 'T12:00:00')
  if (Number.isNaN(d.getTime())) return 'unknown date'
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
}

export function interpretationTileCopy(interpretation) {
  const { moved, stable } = splitSections({ groups: interpretation?.groups ?? [] })
  const collected = formatCollected(interpretation?.meta?.trigger_panel?.collected)
  return `What Moved: ${moved.length} · Stable: ${stable.length} · collected ${collected}`
}
